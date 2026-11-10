"""The validator: does a package satisfy its contract?

Deterministic, no LLM, no network, no dependencies. It is the only authority on
validity - an agent never declares its own output valid.

Contracts are ordinary JSON Schema (the subset below), plus an "x-dbtl-checks"
section for the rules a schema cannot express: uniqueness across a list, and
cross-references between parts of the package. Those two turned out to be where
the real handover bugs live, which is itself worth reporting from the week.

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

    def __str__(self) -> str:
        return f"{self.path:<42} {self.code:<20} {self.message}"


@dataclass
class Report:
    errors: list[Error] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

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


def load_contract(name: str, profile: str | dict | None = None) -> dict:
    """Load a contract, bound to a use-case profile.

    The contract is the common ground between bioprospecting and
    biomanufacturing; the profile supplies the identifier formats and the
    mandatory measurements. Both cases therefore validate against the same
    structure, which is what makes a handover comparable across teams.
    """
    path = CONTRACT_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"no contract {name} in {CONTRACT_DIR}")
    contract = json.loads(path.read_text())

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
            if name not in value or value[name] is None:
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
            elif unit and got.get("unit") and got["unit"] != unit:
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
          "empty": _check_empty}


def validate(package: dict, contract: dict) -> Report:
    """Check a package against a contract. Returns a Report; never raises."""
    errors: list[Error] = []
    _check_node(package, contract, "", errors)
    profile = contract.get("x-dbtl-profile", {})
    for check in contract.get("x-dbtl-checks", []):
        handler = CHECKS.get(check["kind"])
        if handler:
            handler(package, check, errors, profile)
    return Report(errors)
