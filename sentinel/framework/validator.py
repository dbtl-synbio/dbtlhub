"""The validator: does a package satisfy its contract?

Deterministic, no LLM, no network. It is the only authority on validity - an
agent never declares its own output valid.

Contracts are ordinary JSON Schema (the subset below), plus an "x-dbtl-checks"
section for the rules a schema cannot express: uniqueness across a list, and
cross-references between parts of the package. Those two turned out to be where
the real handover bugs live, which is itself worth reporting from the week.

Each contract is written twice: contracts/<name>.yaml, which is what a person
edits because it can carry the reason for a check beside the check, and
contracts/<name>.schema.json, the same contract with the comments stripped.
PyYAML is the only dependency this module has and it is optional: without it
the JSON is read and nothing else changes.

Supported JSON Schema keywords:
    type, required, properties, items, minItems, enum, const, pattern,
    minimum, maximum

    from framework.validator import load_contract, validate
    report = validate(package, load_contract("build_to_test"))
    if not report.ok: print(report.text())
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent / "contracts"

TYPES = {"object": dict, "array": list, "string": str, "number": (int, float),
         "integer": int, "boolean": bool, "null": type(None)}


@dataclass
class Error:
    path: str
    code: str
    message: str
    fix_hint: str = ""
    # "error" stops the handover. "flag" does not: it is something the crate
    # states honestly and the receiving phase has to be told about, like a
    # coding sequence recorded as a right partial. Refusing it would call an
    # accurate crate invalid; dropping it would send Build a truncated gene
    # without saying so. Neither is acceptable, so there are two severities.
    severity: str = "error"

    def __str__(self) -> str:
        mark = "" if self.severity == "error" else "[flag] "
        return f"{self.path:<42} {self.code:<20} {mark}{self.message}"


@dataclass
class Report:
    errors: list[Error] = field(default_factory=list)

    @property
    def blocking(self) -> list[Error]:
        return [e for e in self.errors if e.severity == "error"]

    @property
    def flags(self) -> list[Error]:
        return [e for e in self.errors if e.severity != "error"]

    @property
    def ok(self) -> bool:
        """A flag does not make a package invalid. It makes it conditional."""
        return not self.blocking

    def codes(self) -> list[str]:
        return [e.code for e in self.errors]

    def text(self, indent: str = "  ") -> str:
        return "\n".join(indent + str(e) for e in self.errors)


def load_profile(name: str) -> dict:
    """Load a use-case profile, e.g. 'bioprospecting'."""
    path = CONTRACT_DIR / "profiles" / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"no profile {name} in {CONTRACT_DIR / 'profiles'}")
    return json.loads(path.read_text())


def _bind(node, patterns: dict):
    """Replace every x-pattern placeholder with the profile's regex, in place.

    The generic contract says "this field is an identifier"; the profile says
    what an identifier looks like in this use case. Without a profile the
    structure is still checked, the formats simply are not.
    """
    if isinstance(node, dict):
        key = node.pop("x-pattern", None)
        if key:
            regex = patterns.get(key)
            if regex:
                node["pattern"] = regex
        for value in node.values():
            _bind(value, patterns)
    elif isinstance(node, list):
        for item in node:
            _bind(item, patterns)


def _read_contract(name: str) -> dict:
    """Read one contract file: the YAML if it is readable, else the JSON.

    The YAML is the form a person edits, because it can carry the reason a
    check exists beside the check, and a JSON Schema cannot. The JSON is the
    same contract with the comments stripped, kept so that this framework
    still runs on the standard library alone: if PyYAML is not installed the
    JSON is read and nothing else changes.

    The order is deliberate. A YAML file that exists and cannot be parsed is
    an error rather than a reason to quietly fall back, because falling back
    would validate against a contract the author did not just edit.
    """
    yaml_path = CONTRACT_DIR / f"{name}.yaml"
    json_path = CONTRACT_DIR / f"{name}.schema.json"

    if yaml_path.exists():
        try:
            import yaml                                  # optional dependency
        except ImportError:
            if not json_path.exists():
                raise FileNotFoundError(
                    f"contract {name} is only available as YAML "
                    f"({yaml_path}) and PyYAML is not installed")
        else:
            return yaml.safe_load(yaml_path.read_text())

    if not json_path.exists():
        raise FileNotFoundError(f"no contract {name} in {CONTRACT_DIR}")
    return json.loads(json_path.read_text())


def load_contract(name: str, profile: str | dict | None = None) -> dict:
    """Load a contract, bound to a use-case profile.

    The contract is the common ground between bioprospecting and
    biomanufacturing; the profile supplies the identifier formats and the
    mandatory measurements. Both cases therefore validate against the same
    structure, which is what makes a handover comparable across teams.
    """
    contract = _read_contract(name)

    if profile is not None:
        prof = load_profile(profile) if isinstance(profile, str) else profile
        _bind(contract, prof.get("patterns", {}))
        contract["x-dbtl-profile"] = prof
    return contract


# --------------------------------------------------------------------------- #
# JSON Schema subset
# --------------------------------------------------------------------------- #

def _check_node(value, schema: dict, path: str, errors: list[Error]) -> None:
    if "const" in schema and value != schema["const"]:
        errors.append(Error(path, "wrong_const",
                            f"expected {schema['const']!r}, got {value!r}"))
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(Error(path, "not_in_enum",
                            f"expected one of {schema['enum']}, got {value!r}"))
        return

    expected = schema.get("type")
    if expected:
        # "type" may be a single name or a list of alternatives
        names = [expected] if isinstance(expected, str) else list(expected)
        matched = False
        for name in names:
            py = TYPES.get(name)
            if py is None:
                matched = True          # unknown type name: do not block
                break
            # bool is a subclass of int in Python; a flag is not a number unless
            # the schema actually allows booleans
            if isinstance(value, bool) and name in ("number", "integer"):
                continue
            if isinstance(value, py):
                matched = True
                break
        if not matched:
            errors.append(Error(path, "wrong_type",
                                f"expected {' or '.join(names)}, "
                                f"got {type(value).__name__}"))
            return

    if isinstance(value, str) and "pattern" in schema:
        if not re.search(schema["pattern"], value):
            errors.append(Error(path, "bad_format",
                                f"{value!r} does not match {schema['pattern']}"))

    for key, op in (("minimum", lambda v, b: v < b), ("maximum", lambda v, b: v > b)):
        if key in schema and isinstance(value, (int, float)) and op(value, schema[key]):
            errors.append(Error(path, f"out_of_range", f"{value} violates {key} {schema[key]}"))

    if isinstance(value, dict):
        for name in schema.get("required", []):
            # An empty string is an absent value. This contract's premise is
            # that a number on its own is not a measurement; accepting
            # unit: "" would let a required field be present and say nothing,
            # which is the same failure wearing a different shape.
            if name not in value or value[name] in (None, ""):
                sub = schema.get("properties", {}).get(name, {})
                errors.append(Error(f"{path}.{name}" if path else name, "missing_field",
                                    sub.get("description", "required field is absent")))
        for name, sub in schema.get("properties", {}).items():
            if name in value and value[name] is not None:
                _check_node(value[name], sub, f"{path}.{name}" if path else name, errors)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(Error(path, "too_few_items",
                                f"expected at least {schema['minItems']}, got {len(value)}"))
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                _check_node(item, item_schema, f"{path}[{i}]", errors)


# --------------------------------------------------------------------------- #
# contract-level checks (what a schema cannot say)
# --------------------------------------------------------------------------- #

def _dig(obj, dotted: str):
    """Follow a dotted path. 'a.b' walks into dicts; 'a[].b' collects over a list."""
    if dotted in ("", None):
        return obj
    cur = obj
    for part in dotted.split("."):
        collect = part.endswith("[]")
        key = part[:-2] if collect else part
        if isinstance(cur, list):
            cur = [c.get(key) if isinstance(c, dict) else None for c in cur]
        elif isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
        if collect and isinstance(cur, list):
            flat = []
            for c in cur:
                flat.extend(c) if isinstance(c, list) else flat.append(c)
            cur = flat
    return cur


def _check_unique(package, check, errors, profile=None):
    rows = _dig(package, check["of"]) or []
    seen: dict[tuple, int] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        key = tuple(_dig(row, f) for f in check["fields"])
        if any(k is None for k in key):
            continue                      # a missing field is the schema's business
        if key in seen:
            shown = "/".join(str(k) for k in key)
            errors.append(Error(
                f"{check['of']}[{seen[key]}],[{i}].{'+'.join(check['fields'])}",
                check.get("code", "not_unique"),
                f"{shown}: {check.get('message', 'duplicate')}",
                check.get("fix_hint", "")))
        else:
            seen[key] = i


def _check_cross_ref(package, check, errors, profile=None):
    allowed = _dig(package, check["against"])
    allowed = {a for a in (allowed or []) if a is not None}
    field = check["field"]
    # 'design_item_id'              a key on the row
    # 'proposes.derived_from_item'  a key further in
    # 'evidence[]'                  every member of a list on the row
    many = field.endswith("[]")
    path = field[:-2] if many else field

    for i, row in enumerate(_dig(package, check["of"]) or []):
        if not isinstance(row, dict):
            continue
        found = _dig(row, path)
        if found is None:
            continue
        pairs = (list(enumerate(found)) if many and isinstance(found, list)
                 else [(None, found)])
        for j, value in pairs:
            if value is None or value in allowed:
                continue
            where = (f"{check['of']}[{i}].{path}"
                     + (f"[{j}]" if j is not None else ""))
            errors.append(Error(
                where, check.get("code", "unknown_ref"),
                f"{value!r}: {check.get('message', 'not found in ' + check['against'])}",
                check.get("fix_hint", "")))


def _check_required_quantities(package, check, errors, profile=None):
    """Every sample must carry the measurements its profile declares mandatory.

    This is the check that makes the two use cases comparable: the contract says
    "measurements carry units", the profile says *which* measurements a handover
    is incomplete without.
    """
    wanted = _dig(profile or {}, check.get("from_profile", "")) or []
    if not wanted:
        return
    for i, row in enumerate(_dig(package, check["of"]) or []):
        if not isinstance(row, dict):
            continue
        present = {}
        for m in _dig(row, check["at"]) or []:
            if isinstance(m, dict) and m.get("quantity"):
                present[m["quantity"]] = m
        for req in wanted:
            quantity, unit = req["quantity"], req.get("unit")
            got = present.get(quantity)
            if got is None:
                errors.append(Error(
                    f"{check['of']}[{i}].{check['at']}", check.get("code", "missing_quantity"),
                    f"{quantity!r}: {check.get('message', 'required by profile')}",
                    f"expected unit {unit!r}" + (f", e.g. from {req['method_hint']}"
                                                 if req.get("method_hint") else "")))
            elif unit and not got.get("unit"):
                errors.append(Error(
                    f"{check['of']}[{i}].{check['at']}.{quantity}", "wrong_unit",
                    f"expected {unit!r}, and the unit is empty",
                    "a measurement with a blank unit is a number, and the "
                    "contract exists to refuse a bare number"))
            elif unit and got["unit"] != unit:
                errors.append(Error(
                    f"{check['of']}[{i}].{check['at']}.{quantity}", "wrong_unit",
                    f"expected {unit!r}, got {got['unit']!r}",
                    "convert, or state the basis the value is normalised to"))


# --------------------------------------------------------------------------- #
# graph-level checks: what a document-shaped validator cannot see
# --------------------------------------------------------------------------- #
# These three exist because the Design -> Build handover is not a document, it is
# a graph. A JSON Schema can confirm that a crate has entities; only a traversal
# can confirm that a sequence is connected to the thing it came from. In a stack
# with rdflib + pyshacl these are SHACL shapes - the logic is identical, and
# framework/contracts/shapes/ carries the SHACL version of the same rules.

def _types(node) -> set:
    t = node.get("@type")
    if isinstance(t, str):
        return {t}
    return set(t or [])


def _ids(value) -> list[str]:
    """Collect @id references out of a JSON-LD value, however it was written."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [value["@id"]] if "@id" in value else []
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_ids(v))
        return out
    return []


def _index(nodes) -> dict:
    return {n["@id"]: n for n in nodes or [] if isinstance(n, dict) and "@id" in n}


def _reverse_actions(index: dict, rules: dict) -> dict:
    """entity id -> the action(s) that produced it.

    RO-Crate has no property pointing from a thing to the action that made it,
    so a Process Run Crate is walked backwards by scanning for the action whose
    `result` contains the entity. Building the reverse index once turns that
    scan into a lookup. Crates written with PROV properties simply produce an
    empty index here and are walked by `follow` instead - which is why a
    contract can accept both without knowing which it is reading.
    """
    action_type = rules.get("action_type", "CreateAction")
    produces = rules.get("produces", "result")
    back: dict[str, list] = {}
    for node in index.values():
        if action_type not in _types(node):
            continue
        for made in _ids(node.get(produces)):
            back.setdefault(made, []).append(node["@id"])
    return back


def _check_provenance_chain(package, check, errors, profile=None):
    """Can this sequence be traced, link by link, back to where it came from?

    This is the check the whole Design -> Build contract exists for. A FASTA that
    reaches the synthesis provider while its chain of derivation stops in mid-air
    is a sequence with no origin: it can be synthesised, but no result obtained
    from it can ever be defended.
    """
    rules = _dig(profile or {}, check.get("from_profile", "")) or {}
    root_type = rules.get("root_type")
    follow = rules.get("follow") or ["prov:wasDerivedFrom"]
    if not root_type:
        return
    roots = [root_type] if isinstance(root_type, str) else list(root_type)
    within = rules.get("root_within") or {}
    index = _index(_dig(package, check["in"]))
    back = _reverse_actions(index, rules)

    def is_root(node) -> bool:
        if not any(r in _types(node) for r in roots):
            return False
        # Several entities can share a type - in a Process Run Crate the field
        # sample, the DNA extract and the library are all a Sample. The root is
        # the one that belongs to the study rather than to another sample.
        if not within or node.get(within.get("prop")) is None:
            return True            # nothing to disambiguate: the type is enough
        for ref in _ids(node.get(within.get("prop"))):
            target = index.get(ref)
            if target and within.get("type") in _types(target):
                return True
        return False

    def predecessors(node) -> list:
        """One step further back, whichever dialect the crate was written in."""
        out = []
        for prop in follow:                       # PROV, isBasedOn, isPartOf...
            out.extend(_ids(node.get(prop)))
        if rules.get("action_type", "CreateAction") in _types(node):
            out.extend(_ids(node.get(rules.get("consumes", "object"))))
        out.extend(back.get(node.get("@id"), ()))  # the action that made it
        return out

    for i, row in enumerate(_dig(package, check["of"]) or []):
        if not isinstance(row, dict):
            continue
        start = row.get(check["field"])
        if start is None or start not in index:
            continue                       # cross_ref already reported this
        seen, queue, path = {start}, [start], []
        reached = False
        while queue:
            node = index.get(queue.pop(0))
            if node is None:
                continue
            path.append(node["@id"])
            if is_root(node):
                reached = True
                break
            for ref in predecessors(node):
                if ref not in seen:
                    seen.add(ref)
                    queue.append(ref)
        if not reached:
            errors.append(Error(
                f"{check['of']}[{i}].{check['field']}",
                check.get("code", "broken_provenance_chain"),
                f"{start!r}: {check.get('message', 'no path to ' + '/'.join(roots))} "
                f"(walked {len(seen)} entit{'y' if len(seen) == 1 else 'ies'}, "
                f"deepest {path[-1] if path else '-'})",
                check.get("fix_hint", "")))


def _check_required_provenance(package, check, errors, profile=None):
    """The metadata counterpart of required_quantities.

    required_quantities says which numbers a handover is incomplete without;
    this says which *context* it is incomplete without, per kind of entity. Same
    mechanism, same profile file, so the two use cases differ in a table rather
    than in code.
    """
    entries = _dig(profile or {}, check.get("from_profile", "")) or []
    if not entries:
        return
    nodes = _dig(package, check["of"]) or []
    index = _index(nodes)
    matched_any: list[str] = []
    alternatives = []

    for entry in entries:
        if entry.get("one_of"):
            alternatives.append(entry)      # evaluated once every type is known
            continue
        wanted_type = entry.get("type")
        matching = [n for n in nodes if isinstance(n, dict) and wanted_type in _types(n)]
        # A type can be worn by several entities that are not the same kind of
        # thing: in a Process Run Crate the field sample, the DNA extract and
        # the library are all a Sample, and only the first was collected from
        # the ground. `within` narrows the entry to the ones that belong to the
        # named kind of parent; an entity with no such property is unambiguous
        # and is kept.
        narrow = entry.get("within")
        if narrow and matching:
            matching = [n for n in matching
                        if n.get(narrow.get("prop")) is None
                        or any(narrow.get("type") in _types(index.get(r, {}))
                               for r in _ids(n.get(narrow.get("prop"))))]
        # `where` picks out one entity among many of a type - the gene-calling
        # action among eleven CreateActions, say. Matched on what the crate
        # already says, never on array position.
        pick = entry.get("where")
        if pick and matching:
            matching = [n for n in matching if _matches(n, pick)]
            if not matching and entry.get("if_present"):
                continue
        if not matching:
            # `if_present` marks an entry that belongs to one crate dialect.
            # A Process Run Crate has no dwc:Location and a Darwin Core crate
            # has no schema.org Sample; demanding both would fail every real
            # crate. One of them still has to match - see require_one_of below.
            if entry.get("if_present"):
                continue
            errors.append(Error(
                check["of"], check.get("code", "missing_provenance"),
                f"no entity of type {wanted_type!r} anywhere in the crate",
                entry.get("why", "")))
            continue
        matched_any.append(wanted_type)
        for node in matching:
            where = f"{check['of']}[{node['@id']}]"
            # Flat keys, or named PropertyValue entries hanging off a property
            # - the two ways a crate carries the same fact.
            named = _named_properties(node, entry.get("properties_at"), index)
            for prop in entry.get("requires", []):
                missing = (node.get(prop) in (None, "", [], {})
                           if entry.get("properties_at") is None
                           else named.get(prop) in (None, "", [], {}))
                if missing:
                    errors.append(Error(
                        f"{where}.{prop}", check.get("code", "missing_provenance"),
                        check.get("message", "required by profile"),
                        entry.get("why", "")))
            if entry.get("measurements"):
                present = {m.get("quantity"): m
                           for m in (node.get(entry.get("at", "")) or [])
                           if isinstance(m, dict)}
                for req in entry["measurements"]:
                    got = present.get(req["quantity"])
                    if got is None:
                        errors.append(Error(
                            f"{where}.{entry.get('at')}",
                            check.get("code", "missing_provenance"),
                            f"{req['quantity']!r}: required by profile",
                            f"expected unit {req.get('unit')!r}"
                            + (f", e.g. from {req['method_hint']}"
                               if req.get("method_hint") else "")))
                    elif req.get("unit") and got.get("unit") != req["unit"]:
                        errors.append(Error(
                            f"{where}.{entry.get('at')}.{req['quantity']}",
                            "wrong_unit",
                            f"expected {req['unit']!r}, got {got.get('unit')!r}",
                            "convert, or state the basis explicitly"))

    for entry in alternatives:
        if any(t in matched_any for t in entry["one_of"]):
            continue
        errors.append(Error(
            check["of"], check.get("code", "missing_provenance"),
            f"the crate holds none of {entry['one_of']} - there is nothing in "
            f"it that states where the material came from",
            entry.get("why", "")))


def _matches(node: dict, pick: dict) -> bool:
    value = node.get(pick.get("prop"))
    if "equals" in pick:
        return value == pick["equals"]
    ends = pick.get("id_ends_with")
    if ends:
        return any(str(ref).endswith(ends) for ref in _ids(value))
    return value is not None


def _named_properties(node: dict, at: str | None, index: dict) -> dict:
    """Resolve `additionalProperty` style metadata into {name: value}.

    A Process Run Crate does not put collection_date on the sample. It puts a
    reference to a PropertyValue entry that has a name and a value, which is
    how one crate can carry MIxS, Darwin Core and instrument settings without
    inventing a property for each. Flat keys and PropertyValue entries say the
    same thing, so the profile should be able to ask for either.
    """
    if not at:
        return {}
    out = {}
    for ref in _ids(node.get(at)):
        pv = index.get(ref)
        if isinstance(pv, dict) and pv.get("name") is not None:
            out[pv["name"]] = pv.get("value")
    for inline in (node.get(at) or []) if isinstance(node.get(at), list) else []:
        if isinstance(inline, dict) and inline.get("name") is not None:
            out[inline["name"]] = inline.get("value")
    return out


def _check_accounted_for(package, check, errors, profile=None):
    """Everything the previous phase committed to has to be answered for.

    `cross_ref` catches the easy direction: something arrived that was never
    asked for. This is the other one, and it is the one that goes unnoticed -
    a well that was asked for and simply is not in the record. Nothing is
    wrong with any row; a row is just absent, and absence has no field to
    check.

    Design states the intended layout, Build records what arrived, and the
    difference falls out of the two records instead of somebody noticing it.
    A failure is a legitimate outcome: it just has to be stated, not omitted.
    """
    seen: set = set()
    for path in (check.get("against") or []):
        for value in (_dig(package, path) or []):
            if value is not None:
                seen.add(value)

    for i, row in enumerate(_dig(package, check["of"]) or []):
        value = row.get(check["field"]) if isinstance(row, dict) else row
        if value is None or value in seen:
            continue
        errors.append(Error(
            f"{check['of']}[{i}].{check.get('field', '')}".rstrip("."),
            check.get("code", "unaccounted_item"),
            f"{value!r}: {check.get('message', 'committed to, and not answered for')}",
            check.get("fix_hint", ""),
            check.get("severity", "error")))


def _check_within_limits(package, check, errors, profile=None):
    """Does this package respect a limit the receiving phase stated?

    Every other check in this framework asks whether what arrived is complete.
    This one asks something different, and it only became necessary once the
    use cases started sharing crates: whether what arrived is *buildable* by
    the phase that has to build it.

    The limits are carried in the package, with `from` naming the crate they
    were read out of, so the claim is checkable and attributable. A limit is
    not a use-case constant and does not belong in the profile: it is this
    run's equipment, this round's budget, and it changes between rounds.
    """
    limits = {lim.get("quantity"): lim for lim in (package.get("limits") or [])
              if isinstance(lim, dict)}
    limit = limits.get(check.get("quantity"))
    if limit is None or limit.get("value") is None:
        # Nothing to respect. A contract may insist the limit be stated by
        # listing its quantity in required_limits; silence here is not a pass.
        return

    rows = _dig(package, check["of"]) or []
    measure = check.get("measure", "count")
    if measure == "count":
        actual, where = len(rows), check["of"]
    else:
        values = [_dig(r, check["field"]) for r in rows if isinstance(r, dict)]
        values = [v for v in values if isinstance(v, (int, float))]
        if not values:
            return
        actual = max(values)
        where = f"{check['of']}[].{check['field']}"

    if actual <= limit["value"]:
        return
    errors.append(Error(
        where, check.get("code", "exceeds_limit"),
        f"{actual} {limit.get('unit', '')}".strip()
        + f" against a stated limit of {limit['value']} "
        + f"{limit.get('unit', '')}".rstrip()
        + (f" (from {limit['from']})" if limit.get("from") else ""),
        check.get("fix_hint", ""), check.get("severity", "error")))


def _check_entity_value(package, check, errors, profile=None):
    """Does a referenced entity say something the receiving phase must act on?

    Anil Wipat's note on the use case's example crates asks for exactly this:
    "do the values mean what Build expects?" A gene called with open ends may
    be a truncated fragment, and the crate says so honestly, per protein. The
    crate is not wrong and must not be refused - but Build cannot be sent a
    right partial sequence without being told.
    """
    rules = _dig(profile or {}, check.get("from_profile", "")) or []
    if not rules:
        return
    index = _index(_dig(package, check["in"]))

    for i, row in enumerate(_dig(package, check["of"]) or []):
        if not isinstance(row, dict):
            continue
        node = index.get(row.get(check["field"]))
        if node is None:
            continue
        for rule in rules:
            named = _named_properties(node, rule.get("at"), index)
            value = named.get(rule["property"], node.get(rule["property"]))
            if value is None:
                if rule.get("required"):
                    errors.append(Error(
                        f"{check['of']}[{i}].{rule['property']}",
                        check.get("code", "flagged_entity"),
                        f"the profile requires {rule['property']!r} on an "
                        f"ordered entity, and it is not stated",
                        rule.get("why", ""), rule.get("severity", "error")))
                continue
            if rule.get("accept") and value not in rule["accept"]:
                errors.append(Error(
                    f"{check['of']}[{i}].{rule['property']}",
                    check.get("code", "flagged_entity"),
                    f"{node.get('identifier', node.get('@id'))}: "
                    f"{rule['property']} is {value!r}, "
                    f"not {' or '.join(map(repr, rule['accept']))}",
                    rule.get("why", ""), rule.get("severity", "flag")))


def _check_references_resolve(package, check, errors, profile=None):
    """Does every relative @id the crate mentions exist in the crate?

    An absolute URI may point anywhere and is nobody's business here. A
    RELATIVE one is a promise that the thing is in this crate, and a promise
    that resolves to nothing is silent: the entity that makes it validates,
    the graph simply has a hole where the other end should be.

    Found by running this against a crate written elsewhere, where a
    `hasPart` named a file that was never described and never shipped, and
    every check passed.
    """
    nodes = _dig(package, check["of"]) or []
    present = {n.get("@id") for n in nodes if isinstance(n, dict)}
    seen: set[tuple[str, str]] = set()

    def walk(node, owner):
        if isinstance(node, dict):
            ref = node.get("@id")
            if len(node) == 1 and isinstance(ref, str):
                if (not ref.startswith(("http://", "https://", "urn:"))
                        and ref not in present):
                    seen.add((owner, ref))
            for value in node.values():
                walk(value, owner)
        elif isinstance(node, list):
            for item in node:
                walk(item, owner)

    for entity in nodes:
        if isinstance(entity, dict):
            walk(entity, entity.get("@id", "?"))

    for owner, ref in sorted(seen):
        errors.append(Error(
            f"{check['of']}[{owner}]", check.get("code", "dangling_reference"),
            f"{ref!r}: {check.get('message', 'named here and nowhere in the crate')}",
            check.get("fix_hint", ""), check.get("severity", "error")))


def _check_root_declares(package, check, errors, profile=None):
    """Does the ROOT say which profile the content follows?

    The metadata descriptor says which version of RO-Crate the file follows.
    That is a different statement, and having it is not having the other. A
    crate whose root declares nothing can be parsed and cannot be interpreted,
    and merging the two claims - which this framework did - makes the second
    one look present when only the first is.
    """
    nodes = _dig(package, check["of"]) or []
    index = {n.get("@id"): n for n in nodes if isinstance(n, dict)}
    descriptor = index.get("ro-crate-metadata.json", {})
    about = descriptor.get("about")
    ref = about.get("@id") if isinstance(about, dict) else "./"
    root = index.get(ref) or index.get("./")
    if root is None:
        return                      # a missing root is another check's business

    claims = root.get(check.get("property", "conformsTo"))
    claims = [claims] if isinstance(claims, dict) else (claims or [])
    ids = [c.get("@id") if isinstance(c, dict) else c for c in claims]
    wanted = check.get("contains", "")
    if any(wanted in (i or "") for i in ids):
        return
    errors.append(Error(
        f"{check['of']}[{ref}].{check.get('property', 'conformsTo')}",
        check.get("code", "root_declares_no_profile"),
        f"{check.get('message', 'the root declares no profile')}"
        + (f" (it declares {ids})" if ids else " (it declares nothing)"),
        check.get("fix_hint", ""), check.get("severity", "error")))


def _check_empty(package, check, errors, profile=None):
    """A list that must be empty for the handover to be complete."""
    for item in _dig(package, check["of"]) or []:
        errors.append(Error(f"{check['of']}", check.get("code", "not_empty"),
                            f"{item!r}: {check.get('message', 'must be empty')}",
                            check.get("fix_hint", "")))


def _derive_crate_checksum(package):
    from framework.kg import crate_checksum
    crate = package.get("crate")
    return crate_checksum(crate) if crate else None


# A contract may only ask for a derivation this table names. It cannot name a
# function to import, because a contract is data and data must not choose code.
DERIVATIONS = {"crate_checksum": _derive_crate_checksum}


def _check_derived(package, check, errors, profile=None):
    """A field that must equal a value computable from the package itself.

    Requiring the field to be *present* is not enough. A missing checksum is a
    fixable error, so some engine will supply one - and an engine that is wrong,
    or hostile, can supply a plausible string that satisfies 'present' while
    the crate's integrity claim becomes a lie. The claim has to be checked, not
    the field.
    """
    claimed = _dig(package, check["of"])
    if claimed is None:
        return                       # absence is the schema's business, not ours
    derive = DERIVATIONS.get(check.get("function"))
    if derive is None:
        return
    actual = derive(package)
    if actual is None or claimed == actual:
        return
    errors.append(Error(
        check["of"], check.get("code", "derived_mismatch"),
        f"{check.get('message', 'does not match the value derived from the data')} "
        f"(claimed {str(claimed)[:24]}..., derived {str(actual)[:24]}...)",
        check.get("fix_hint", "")))


CHECKS = {"unique": _check_unique, "cross_ref": _check_cross_ref,
          "derived": _check_derived,
          "required_quantities": _check_required_quantities,
          "provenance_chain": _check_provenance_chain,
          "required_provenance": _check_required_provenance,
          "entity_value": _check_entity_value,
          "within_limits": _check_within_limits,
          "references_resolve": _check_references_resolve,
          "root_declares": _check_root_declares,
          "accounted_for": _check_accounted_for,
          "empty": _check_empty}


def validate(package: dict, contract: dict) -> Report:
    """Check a package against a contract. Returns a Report; never raises."""
    errors: list[Error] = []
    _check_node(package, contract, "", errors)
    profile = contract.get("x-dbtl-profile", {})
    for check in contract.get("x-dbtl-checks", []):
        handler = CHECKS.get(check["kind"])
        if handler is None:
            # A misspelt kind used to delete a check in silence. A contract
            # asking for something this validator cannot do is a contract
            # nobody is enforcing, so say so rather than pass.
            errors.append(Error(
                f"x-dbtl-checks.{check.get('code', check.get('kind', '?'))}",
                "unknown_check_kind",
                f"this contract asks for a check of kind "
                f"{check.get('kind')!r}, which this validator does not "
                f"implement, so nothing checked it",
                "either the kind is misspelt, or the validator is older than "
                "the contract. Do not assume the check passed."))
            continue
        try:
            handler(package, check, errors, profile)
        except (KeyError, TypeError, ValueError) as exc:
            # A check whose own settings are wrong - a missing `fields`, a
            # `between` that is not a pair - used to come back as a traceback
            # from inside this file. A contract is written by somebody who is
            # not holding this code open, so a malformed check has to read as
            # a sentence about their file, and it has to be a FINDING rather
            # than a crash: a run that stops here has checked nothing and
            # said nothing about the rest of the contract.
            errors.append(Error(
                f"x-dbtl-checks.{check.get('code', check.get('kind', '?'))}",
                "malformed_check",
                f"the {check.get('kind')!r} check named "
                f"{check.get('code', '?')!r} could not run: "
                f"{type(exc).__name__}: {exc}. Nothing checked it.",
                f"look at this check in the contract. A {check.get('kind')!r} "
                f"check needs the settings that kind reads - see the other "
                f"checks of the same kind for the shape."))
        else:
            _check_it_matched_something(package, check, errors)
    return Report(errors)


# Kinds whose whole point is an empty target, or whose target is a single
# field the schema already governs. Everything else is expected to find
# something to look at.
_MAY_MATCH_NOTHING = {"empty", "derived"}


def _check_it_matched_something(package, check, errors) -> None:
    """Did this check have anything to look at?

    A rule that matches no entity passes, and a package that matches no rule
    comes back clean. That is how a package from an entirely different process
    can be accepted with nothing found: not because it satisfied the contract,
    but because the contract never touched it.

    So a check that examined nothing says so. It is a flag by default rather
    than a refusal - an empty list is sometimes legitimate, and a run should
    not be stopped by it without a human agreeing - but it is never silent. A
    contract that wants it to stop the handover sets `expects: required`.
    """
    if check.get("kind") in _MAY_MATCH_NOTHING:
        return
    where = check.get("of")
    if not where:
        return
    found = _dig(package, where)
    if found not in (None, [], {}, ""):
        return
    severity = "error" if check.get("expects") == "required" else "flag"
    errors.append(Error(
        where, "matched_nothing",
        f"the {check.get('kind')} check {check.get('code', '')!r} had nothing "
        f"to examine: {where!r} is absent or empty, so it passed without "
        f"looking at anything".replace("'' ", ""),
        "an empty target is sometimes correct. If it is not, this package is "
        "being accepted by a contract that never touched it.",
        severity))
