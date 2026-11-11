"""Load the forms, check an instance against the template, hand the result on.

Three jobs, and nothing else:

    1. read `template.yaml` or `bioprospecting.yaml` into the `Form` / `Filled`
       dataclasses of `architect/forms.py`
    2. check an instance against its template using INSTANCE_MAY /
       INSTANCE_MAY_NOT from that same file, naming the rule that was broken
    3. turn a `Filled` into a `Specification` from
       `architect/specification.py` - agreed values, limits, reads

It also audits the forms themselves, which is the part that keeps them honest.
Every field carries a `feeds` list saying what it becomes, written in a small
grammar:

    agreed:<key>             -> Specification.agree(key, value)
    limit:<quantity>         -> Specification.state_limit(quantity, value, unit)
    reads:role=<role>        -> Specification.declare_read(crate, role=...)
    steps:Form.steps         -> the use case's own numbered workflow
    package:<handover>#<path>-> a real field of a real handover contract
    profile:<path>           -> a real key of the active profile
    gap:<handover>#<path>    -> a field the contract does NOT have yet

`audit()` resolves each of those against the files on disk: a `package:` or
`profile:` target that does not exist is reported, and so is a `gap:` target
that DOES exist - because the day a contract grows the field, the honest
comment in the form becomes a lie and somebody has to come back and delete it.
It also checks every name the forms quote in backticks against the names the
contracts and profiles really use, so `why_it_is_asked` cannot cite a check
code that was renamed.

PyYAML if it is there, a `<form>.json` sidecar beside the form if it is not -
the same fallback the contracts use. Neither available is said plainly rather
than guessed at. Standard library otherwise. No network, no LLM.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent              # architect/forms
REPO = HERE.parent.parent
CONTRACT_DIR = REPO / "framework" / "contracts"
PROFILE_DIR = CONTRACT_DIR / "profiles"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    import yaml
except ImportError:                                  # pragma: no cover
    yaml = None


# --------------------------------------------------------------------------- #
#  The seam
# --------------------------------------------------------------------------- #
# `architect/forms.py` and this package `architect/forms/` have the same dotted
# name, and a package shadows a module. So the seam is loaded from its path
# rather than imported, which is also a statement: this package implements that
# file and does not get to redefine it.
def _seam():
    path = REPO / "architect" / "forms.py"
    spec = importlib.util.spec_from_file_location("architect._forms_seam", path)
    if spec is None or spec.loader is None:          # pragma: no cover
        raise ImportError(f"cannot load the form seam from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_forms = _seam()
Field = _forms.Field
Filled = _forms.Filled
Form = _forms.Form
Kind = _forms.Kind
Section = _forms.Section
INSTANCE_MAY = _forms.INSTANCE_MAY
INSTANCE_MAY_NOT = _forms.INSTANCE_MAY_NOT

from architect.contract import HANDOVERS, PHASES          # noqa: E402
from architect.specification import Specification         # noqa: E402


# --------------------------------------------------------------------------- #
#  Refusals
# --------------------------------------------------------------------------- #
class FormError(ValueError):
    """The file itself is not a form: a missing key, a kind nobody renders."""


class InstanceDoesNotFit(ValueError):
    """An instance broke one of the INSTANCE_MAY_NOT rules.

    The message names the rule verbatim, the field it happened on, and what an
    instance is allowed to do instead - because "validation failed" sends
    somebody looking for a typo when the real answer is "that is not a change
    an instance may make".
    """

    def __init__(self, rule: str, field_key: str, detail: str) -> None:
        if rule not in INSTANCE_MAY_NOT:
            raise AssertionError(
                f"{rule!r} is not one of INSTANCE_MAY_NOT in architect/forms.py; "
                f"the rule text here must be the rule text there")
        super().__init__(
            f"this instance does something an instance may not do.\n"
            f"  rule broken: {rule}\n"
            f"  field:       {field_key}\n"
            f"  what it did: {detail}\n"
            f"  an instance may: " + "; ".join(INSTANCE_MAY) + "\n"
            f"  if the template is wrong, change the template - that makes the "
            f"change for every use case, which is the point.")
        self.rule = rule
        self.field_key = field_key
        self.detail = detail


# --------------------------------------------------------------------------- #
#  Reading a form file
# --------------------------------------------------------------------------- #
_FIELD_KEYS = {"key", "label", "kind", "phase", "required", "unit", "options",
               "default", "placeholder", "why_it_is_asked", "feeds", "answer"}
_SECTION_KEYS = {"key", "title", "intent", "fields"}
_FORM_KEYS = {"name", "title", "based_on", "description", "sections", "steps"}


def _read(path: Path) -> dict:
    """YAML if PyYAML is installed, the JSON sidecar if it is not."""
    if yaml is not None and path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(path.read_text())
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        raise FormError(
            f"cannot read {path.name}: PyYAML is not installed and there is no "
            f"{sidecar.name} beside it. Install PyYAML, or write the sidecar.")
    return json.loads(sidecar.read_text())


def _field(raw: dict, where: str) -> tuple[Field, Any, bool]:
    """One field, plus its `answer` if the file already settles it."""
    if not isinstance(raw, dict) or "key" not in raw:
        raise FormError(f"{where}: a field needs at least a 'key'; got {raw!r}")
    unknown = set(raw) - _FIELD_KEYS
    if unknown:
        raise FormError(f"{where}/{raw['key']}: unknown key(s) "
                        f"{sorted(unknown)}; a typo here would silently drop "
                        f"the thing it was meant to say")
    try:
        kind = Kind(raw.get("kind", "text"))
    except ValueError:
        raise FormError(f"{where}/{raw['key']}: kind {raw.get('kind')!r} is "
                        f"not one the interface can render; expected one of "
                        f"{[k.value for k in Kind]}") from None
    phase = raw.get("phase")
    if phase is not None and phase not in PHASES:
        raise FormError(f"{where}/{raw['key']}: phase {phase!r} is not one of "
                        f"{PHASES}")
    if kind is Kind.QUANTITY and "unit" not in raw:
        raise FormError(f"{where}/{raw['key']}: a QUANTITY must say which unit "
                        f"it is in, or say 'unit:' empty so an instance can fix "
                        f"it; a bare number is the fault the contracts refuse")
    field = Field(
        key=str(raw["key"]),
        label=str(raw.get("label", raw["key"])),
        kind=kind,
        phase=phase,
        required=bool(raw.get("required", False)),
        unit=raw.get("unit") or None,
        options=[str(o) for o in (raw.get("options") or [])],
        default=raw.get("default"),
        placeholder=str(raw.get("placeholder", "")),
        why_it_is_asked=" ".join(str(raw.get("why_it_is_asked", "")).split()),
        feeds=[str(f) for f in (raw.get("feeds") or [])],
    )
    return field, raw.get("answer"), "answer" in raw


def load_form(path: Path | str) -> tuple[Form, dict[str, Any]]:
    """Read a form file. Returns the form and the answers the file itself gives.

    An instance may answer a field in the file - the profile this use case is,
    the instruments it owns - because those do not change between rounds. What
    does change between rounds is left unanswered, which is how `missing()`
    stays meaningful.
    """
    path = Path(path)
    raw = _read(path)
    if not isinstance(raw, dict):
        raise FormError(f"{path.name}: expected a mapping at the top level")
    unknown = set(raw) - _FORM_KEYS
    if unknown:
        raise FormError(f"{path.name}: unknown top-level key(s) {sorted(unknown)}")
    for needed in ("name", "title", "sections"):
        if needed not in raw:
            raise FormError(f"{path.name}: missing top-level '{needed}'")

    sections: list[Section] = []
    answers: dict[str, Any] = {}
    seen: set[str] = set()
    for raw_section in raw["sections"]:
        unknown = set(raw_section) - _SECTION_KEYS
        if unknown:
            raise FormError(f"{path.name}/{raw_section.get('key')}: unknown "
                            f"key(s) {sorted(unknown)}")
        for needed in ("key", "title", "intent"):
            if needed not in raw_section:
                raise FormError(f"{path.name}: section "
                                f"{raw_section.get('key', '?')} needs '{needed}'")
        fields: list[Field] = []
        for raw_field in raw_section.get("fields") or []:
            field, answer, answered = _field(raw_field,
                                             f"{path.name}/{raw_section['key']}")
            if field.key in seen:
                raise FormError(f"{path.name}: field {field.key!r} appears "
                                f"twice; a value could not be attributed")
            seen.add(field.key)
            fields.append(field)
            if answered:
                answers[field.key] = answer
        sections.append(Section(key=str(raw_section["key"]),
                                title=str(raw_section["title"]),
                                intent=" ".join(str(raw_section["intent"]).split()),
                                fields=fields))

    steps = list(raw.get("steps") or [])
    _check_steps(steps, path.name)
    form = Form(name=str(raw["name"]), title=str(raw["title"]),
                based_on=raw.get("based_on"),
                description=" ".join(str(raw.get("description", "")).split()),
                sections=sections, steps=steps)
    return form, answers


def _check_steps(steps: list[dict], where: str) -> None:
    """The workflow has to be a workflow: numbered, in order, one handover each."""
    handovers_seen: dict[str, int] = {}
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise FormError(f"{where}: step {index} is not a mapping")
        for needed in ("number", "name", "phase"):
            if needed not in step:
                raise FormError(f"{where}: step {index} needs '{needed}'")
        if step["number"] != index:
            raise FormError(f"{where}: step numbered {step['number']} is in "
                            f"position {index}; the Architect reports progress "
                            f"by these numbers, so they must be the order")
        if step["phase"] not in PHASES:
            raise FormError(f"{where}: step {index} is in phase "
                            f"{step['phase']!r}, not one of {PHASES}")
        handover = step.get("handover_after")
        if handover is None:
            continue
        if handover not in HANDOVERS.values():
            raise FormError(f"{where}: step {index} says handover_after "
                            f"{handover!r}; the four are "
                            f"{sorted(HANDOVERS.values())}")
        if handover in handovers_seen:
            raise FormError(f"{where}: {handover} follows step "
                            f"{handovers_seen[handover]} and step {index}; a "
                            f"handover happens once per cycle")
        handovers_seen[handover] = index


def load_template() -> tuple[Form, dict[str, Any]]:
    return load_form(HERE / "template.yaml")


def load_instance(name: str) -> tuple[Form, dict[str, Any]]:
    return load_form(HERE / f"{name}.yaml")


# --------------------------------------------------------------------------- #
#  Checking an instance against its template
# --------------------------------------------------------------------------- #
def validate_instance(instance: Form, template: Form) -> list[str]:
    """Raise on anything INSTANCE_MAY_NOT; return what it legitimately did.

    The returned list is the record of the use case's own narrowing - it is
    what makes two instances of the same template comparable at a glance.
    """
    if instance.based_on not in (None, template.name):
        raise FormError(f"{instance.name} says based_on={instance.based_on!r} "
                        f"but was checked against {template.name!r}")
    changes: list[str] = []
    instance_fields = {f.key: f for f in instance.all_fields()}

    for field in template.all_fields():
        here = instance_fields.get(field.key)
        if here is None:
            if field.required:
                raise InstanceDoesNotFit(
                    "remove a field the template marks required", field.key,
                    f"the template marks {field.key!r} required and the "
                    f"instance has no such field, so two projects could no "
                    f"longer be compared on it")
            changes.append(f"dropped optional field {field.key}")
            continue
        if here.kind is not field.kind:
            raise InstanceDoesNotFit(
                "change a field's kind", field.key,
                f"the template renders it as {field.kind.value} and the "
                f"instance as {here.kind.value}; the interface and the loader "
                f"would accept two different things under one name")
        if field.required and not here.required:
            raise InstanceDoesNotFit(
                "remove a field the template marks required", field.key,
                "it is still listed but no longer marked required, which has "
                "exactly the effect of removing it: missing() stops reporting it")
        if set(here.feeds) != set(field.feeds):
            raise InstanceDoesNotFit(
                "change what a field feeds", field.key,
                f"the template feeds {sorted(field.feeds)} and the instance "
                f"feeds {sorted(here.feeds)}; whatever the answer becomes "
                f"downstream is the template's decision, not a use case's")
        if field.unit and here.unit != field.unit:
            raise InstanceDoesNotFit(
                "change what a field feeds", field.key,
                f"the template fixes the unit as {field.unit!r} and the "
                f"instance uses {here.unit!r}; the same number in another unit "
                f"is another number, and it lands in the same limits entry")
        if field.options:
            widened = [o for o in here.options if o not in field.options]
            if widened:
                raise InstanceDoesNotFit(
                    "widen a CHOICE beyond the template's options", field.key,
                    f"the instance offers {widened}, which the template does "
                    f"not; a downstream reader binds the template's options")
            if len(here.options) < len(field.options):
                changes.append(f"narrowed {field.key} to "
                               f"{', '.join(here.options) or '(none)'}")
        if not field.required and here.required:
            changes.append(f"made {field.key} required")
        if not field.unit and here.unit:
            changes.append(f"fixed {field.key} unit = {here.unit}")
        if here.label != field.label:
            changes.append(f"relabelled {field.key}")

    for key, field in instance_fields.items():
        if template.field(key) is None:
            changes.append(f"added field {key} ({field.kind.value})")
    if instance.steps and not template.steps:
        changes.append(f"supplied {len(instance.steps)} steps of its own")
    return changes


# --------------------------------------------------------------------------- #
#  Auditing the forms against the files they claim to feed
# --------------------------------------------------------------------------- #
_file_cache: dict[Path, dict] = {}


def _load_json_or_yaml(path: Path) -> dict:
    if path not in _file_cache:
        if yaml is not None and path.suffix in (".yaml", ".yml"):
            _file_cache[path] = yaml.safe_load(path.read_text())
        else:
            _file_cache[path] = json.loads(path.read_text())
    return _file_cache[path]


def _contract(handover: str) -> dict:
    candidate = CONTRACT_DIR / f"{handover}.yaml"
    if yaml is None or not candidate.exists():
        candidate = CONTRACT_DIR / f"{handover}.schema.json"
    return _load_json_or_yaml(candidate)


def _profile(name: str) -> dict:
    return _load_json_or_yaml(PROFILE_DIR / f"{name}.json")


def _descend_schema(node: Any, segment: str) -> Any:
    """One `a.b[].c` segment of a JSON Schema path, or None."""
    name, brackets = segment, 0
    while name.endswith("[]"):
        name, brackets = name[:-2], brackets + 1
    if not isinstance(node, dict):
        return None
    node = (node.get("properties") or {}).get(name)
    for _ in range(brackets):
        if not isinstance(node, dict):
            return None
        node = node.get("items")
    return node


def _resolve_package(target: str) -> str:
    """'build_to_test#not_delivered[].reason' -> '' if it exists, else why not."""
    if "#" not in target:
        return "no '#': expected <handover>#<path>"
    handover, path = target.split("#", 1)
    if handover not in HANDOVERS.values():
        return f"no such handover: {handover}"
    node: Any = _contract(handover)
    walked: list[str] = []
    for segment in path.split("."):
        node = _descend_schema(node, segment)
        walked.append(segment)
        if node is None:
            return (f"{handover} has no {'.'.join(walked)} "
                    f"(looked in {handover}.yaml)")
    return ""


def _resolve_profile(target: str, profiles: list[str]) -> str:
    """A dotted path into a profile JSON. Must resolve in at least one profile."""
    failures = []
    for name in profiles:
        node: Any = _profile(name)
        walked: list[str] = []
        for segment in target.split("."):
            key, brackets = segment, 0
            while key.endswith("[]"):
                key, brackets = key[:-2], brackets + 1
            walked.append(segment)
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
            for _ in range(brackets):
                if isinstance(node, list) and node:
                    node = node[0]
                elif isinstance(node, list):
                    node = None
                # a list of scalars is its own leaf; stop descending
            if node is None:
                failures.append(f"{name} has no {'.'.join(walked)}")
                break
        else:
            return ""
    return "; ".join(failures)


def _vocabulary() -> set[str]:
    """Every name the contracts and the profiles actually use.

    Used to check the names the forms quote in backticks. A form that cites
    `broken_provenance_chain` after somebody renames the check is a form that
    lies about why it asks a question, and nothing else would notice.
    """
    words: set[str] = set()

    def walk_schema(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    words.update(str(k) for k in value)
                elif key in ("required", "enum") and isinstance(value, list):
                    words.update(str(v) for v in value if isinstance(v, str))
                elif key in ("code", "kind", "quantity", "function") and isinstance(value, str):
                    words.add(value)
                walk_schema(value)
        elif isinstance(node, list):
            for item in node:
                walk_schema(item)

    def walk_profile(node: Any) -> None:
        if isinstance(node, dict):
            words.update(str(k) for k in node)
            for key, value in node.items():
                if key in ("requires", "accept", "follow", "root_type",
                           "one_of") and isinstance(value, list):
                    words.update(str(v) for v in value if isinstance(v, str))
                elif key in ("quantity", "unit", "property", "type", "at",
                             "properties_at", "action_type", "produces",
                             "consumes") and isinstance(value, str):
                    words.add(value)
                walk_profile(value)
        elif isinstance(node, list):
            for item in node:
                walk_profile(item)

    for handover in sorted(set(HANDOVERS.values())):
        walk_schema(_contract(handover))
        words.add(handover)
    for profile in sorted(p.stem for p in PROFILE_DIR.glob("*.json")):
        walk_profile(_profile(profile))
        words.add(profile)
    # The contracts' own structural keywords. They are keys in those files, so
    # citing one is citing something real - `required`, `fix_hint`, `x-pattern`.
    words.update({"required", "fix_hint", "message", "code", "of", "field",
                  "fields", "against", "from_profile", "in", "measure",
                  "function", "properties", "items", "enum", "pattern",
                  "const", "description", "severity", "note", "why"})
    # Names from architect/specification.py that a form may legitimately cite.
    words.update({"agree", "state_limit", "declare_read", "unresolved",
                  "missing", "to_seed", "requirements_for", "limits_for",
                  "NEEDED_AGREEMENTS", "Specification", "set_by", "x-pattern",
                  "x-dbtl-checks", "x-handover", "dimensionless"})
    return words


_CITATION = re.compile(r"`([^`]+)`")
_SPLIT = re.compile(r"[.#/\[\]()]+")


def audit(form: Form, *, profiles: list[str] | None = None) -> list[str]:
    """Every way a form could be lying, as a list of lines. Empty is the goal."""
    problems: list[str] = []
    if profiles is None:
        profiles = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    vocabulary = _vocabulary()

    for field in form.all_fields():
        if not field.why_it_is_asked:
            problems.append(f"{field.key}: no why_it_is_asked, so nobody can "
                            f"tell what breaks without it")
        if not field.feeds:
            problems.append(f"{field.key}: feeds nothing, so it will quietly "
                            f"stop being filled in")
        for entry in field.feeds:
            kind, _, target = entry.partition(":")
            if kind == "package":
                why = _resolve_package(target)
                if why:
                    problems.append(f"{field.key}: feeds 'package:{target}' "
                                    f"and {why}")
            elif kind == "profile":
                why = _resolve_profile(target, profiles)
                if why:
                    problems.append(f"{field.key}: feeds 'profile:{target}' "
                                    f"and {why}")
            elif kind == "gap":
                if not _resolve_package(target):
                    problems.append(
                        f"{field.key}: feeds 'gap:{target}', but that field "
                        f"now EXISTS in the contract. The honest note in the "
                        f"form has become false - change gap: to package: and "
                        f"rewrite why_it_is_asked")
            elif kind not in ("agreed", "limit", "reads", "steps"):
                problems.append(f"{field.key}: feeds {entry!r}, whose prefix "
                                f"is not one of agreed, limit, reads, steps, "
                                f"package, profile, gap")
        for citation in _CITATION.findall(field.why_it_is_asked):
            for part in (p for p in _SPLIT.split(citation) if p):
                if part not in vocabulary:
                    problems.append(
                        f"{field.key}: why_it_is_asked quotes `{citation}` and "
                        f"no contract or profile uses the name {part!r}")
    return problems


# --------------------------------------------------------------------------- #
#  Filling, and handing the result to specification.py
# --------------------------------------------------------------------------- #
def fill(form: Form, answers: dict[str, Any] | None = None, *,
         source: str = "form file") -> Filled:
    """A `Filled` with whatever answers are to hand.

    `workflow_steps` is answered by the form's own `steps` block if it has one:
    the steps are a top-level thing in `Form` because the Architect reads them
    directly, and asking for them twice would let the two disagree.
    """
    values = dict(answers or {})
    if form.steps and form.field("workflow_steps") is not None:
        values.setdefault("workflow_steps", form.steps)
    filled = Filled(form=form, values={}, provenance={})
    for key, value in values.items():
        if form.field(key) is None:
            raise FormError(f"answer given for {key!r}, which is not a field "
                            f"of {form.name}")
        filled.values[key] = value
        filled.provenance[key] = {"source": source}
    return filled


def answer(filled: Filled, key: str, value: Any, *,
           source: str = "researcher") -> Filled:
    if filled.form.field(key) is None:
        raise FormError(f"{key!r} is not a field of {filled.form.name}")
    filled.values[key] = value
    filled.provenance[key] = {"source": source}
    return filled


def to_specification(filled: Filled, *, run_id: str = "") -> Specification:
    """Turn a filled form into what `architect/specification.py` consumes.

    Driven by `feeds`, not by a second table in this file. A field that says it
    becomes an agreed value becomes one; a field that says it becomes a limit
    is passed to `state_limit` with its own unit. The order matters: reads are
    declared before limits, because `unresolved()` reports a limit whose
    'from' crate was never read.
    """
    form = filled.form
    profile_field = next((f for f in form.all_fields()
                          if "agreed:profile" in f.feeds), None)
    profile = filled.values.get(profile_field.key) if profile_field else None
    who = str(filled.values.get("recorded_by") or "unattributed")
    spec = Specification(profile=profile or None,
                         run_id=run_id or str(filled.values.get("run_id", "")),
                         set_by=who)

    from_crate = str(filled.values.get("limits_from_crate", ""))

    for field in form.all_fields():
        value = filled.values.get(field.key)
        if field.unanswered(value):
            continue
        for entry in field.feeds:
            kind, _, target = entry.partition(":")
            if kind == "reads":
                role = target.partition("=")[2] or "constraints"
                for crate in (value if isinstance(value, list) else [value]):
                    spec.declare_read(str(crate), role=role)

    for field in form.all_fields():
        value = filled.values.get(field.key)
        if field.unanswered(value):
            continue
        for entry in field.feeds:
            kind, _, target = entry.partition(":")
            if kind == "agreed" and target != "profile":
                spec.agree(target, value, set_by=who, note=field.label)
            elif kind == "limit":
                spec.state_limit(target, value, field.unit or "dimensionless",
                                 from_crate=from_crate, stated_by=who,
                                 applies_to=((field.phase,) if field.phase
                                             else ()))
    return spec


# --------------------------------------------------------------------------- #
#  What this looks like when it runs
# --------------------------------------------------------------------------- #
def _demo() -> None:
    rule = "-" * 78

    template, template_answers = load_template()
    instance, instance_answers = load_instance("bioprospecting")

    print(rule)
    print("THE TWO FORMS")
    print(rule)
    for form in (template, instance):
        print(f"\n  {form.name}  ({form.title})")
        print(f"    based_on: {form.based_on}")
        print(f"    {len(form.sections)} sections, {len(form.all_fields())} "
              f"fields, {len(form.required_keys())} required, "
              f"{len(form.steps)} steps")
        for section in form.sections:
            required = sum(1 for f in section.fields if f.required)
            print(f"      {section.key:<16} {len(section.fields):>2} fields "
                  f"({required} required)  {section.title}")

    print()
    print(rule)
    print("INSTANCE AGAINST TEMPLATE - the INSTANCE_MAY / INSTANCE_MAY_NOT rules")
    print(rule)
    changes = validate_instance(instance, template)
    print(f"  accepted. {len(changes)} legitimate changes:")
    for change in changes:
        print(f"    - {change}")

    print()
    print("  and three things it is not allowed to do, each refused by name:")
    import copy
    for mutate, what in (
        (lambda f: f.sections[0].fields.pop(0), "drop the required 'profile' field"),
        (lambda f: f.field("order_format").options.append("csv"),
         "offer an order format the template does not"),
        (lambda f: setattr(f.field("replicates"), "kind", Kind.TEXT),
         "render replicates as free text"),
    ):
        broken = copy.deepcopy(instance)
        mutate(broken)
        try:
            validate_instance(broken, template)
        except InstanceDoesNotFit as refused:
            print(f"\n    if the instance tried to {what}:")
            for line in str(refused).splitlines()[:4]:
                print(f"      {line}")
        else:
            raise AssertionError(f"{what} was accepted")

    print()
    print(rule)
    print("AUDIT - does every field feed something that exists?")
    print(rule)
    # The template is audited against every profile on disk - a generic field
    # has to feed something that exists in at least one. The instance is
    # audited against its own profile only, which is stricter.
    for form, profiles in ((template, None), (instance, ["bioprospecting"])):
        problems = audit(form, profiles=profiles)
        print(f"  {form.name}: {len(problems)} problems "
              f"(profiles checked: {profiles or 'all on disk'})")
        for problem in problems:
            print(f"    ! {problem}")
    feeds = [e for f in instance.all_fields() for e in f.feeds]
    counts: dict[str, int] = {}
    for entry in feeds:
        counts[entry.split(":", 1)[0]] = counts.get(entry.split(":", 1)[0], 0) + 1
    print(f"  {len(feeds)} feeds targets resolved, by kind: "
          + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("  (gap = the contract does not carry it yet; the audit fails the day "
          "it does)")

    print()
    print(rule)
    print("missing() ON AN EMPTY FILL")
    print(rule)
    empty = fill(instance, {})
    print(f"  ready: {empty.ready()}; {len(empty.missing())} of "
          f"{len(instance.required_keys())} required fields unanswered")
    print("  (workflow_steps is the one already answered: the instance's own "
          "`steps` block is its answer)")
    for field in empty.missing():
        print(f"    {field.key:<22} {field.label}")

    print()
    print(rule)
    print("missing() ON A PARTIAL FILL - the answers the instance file itself "
          "gives")
    print(rule)
    partial = fill(instance, instance_answers,
                   source="architect/forms/bioprospecting.yaml")
    print(f"  {len(partial.values)} answered by the use case, "
          f"{len(partial.missing())} still missing - these are the per-round "
          f"answers:")
    for field in partial.missing():
        print(f"    {field.key:<22} {field.kind.value:<9} {field.label}")
        print(f"      because: {field.why_it_is_asked[:96]}")

    print()
    print(rule)
    print("A COMPLETE FILL - one round, answered")
    print(rule)
    round_answers = {
        "run_id": "BP-round-1",
        "recorded_by": "Anil Wipat",
        "objective": "find a thermostable esterase in the hot-spring metagenome",
        "target": "esterase activity on p-nitrophenyl butyrate",
        "provenance_dialect": "process_run_crate",
        "access_permit": "permit_recorded",
        "identifier_style": "CAND",
        "gene_calling_mode": "closed_ends",
        "equipment": ["Opentrons OT-2", "Agilent TapeStation 4200",
                      "BMG CLARIOstar Plus"],
        "replicates": 3,
        "library_size": 96,
        "budget": 4000,
        "reads_crates": ["crate://bp/seed-round-1",
                         "crate://bp/field-collection-2026"],
        "limits_from_crate": "crate://bp/seed-round-1",
        "container_id": "PLATE-1",
        "synthesis_provider": "Twist Bioscience",
        "reader_upper_limit": 3.5,
        "hit_calling_rule": "activity above 3 standard deviations of the "
                            "no-enzyme control, on 3 of 3 replicates",
        "attrition_ledger": [
            "step 3 -> 96 candidates selected",
            "step 5 -> 86 synthesised; 10 lost: vendor declined, repeat "
            "sequence",
            "step 7 -> 75 passed PCR; 11 lost: no product at expected size",
        ],
    }
    complete = fill(instance, {**instance_answers, **round_answers},
                    source="round 1")
    print(f"  ready: {complete.ready()}; missing: "
          f"{[f.key for f in complete.missing()]}")

    spec = to_specification(complete)
    print(f"\n  to_specification() -> {spec!r}")
    print("\n  agreed:")
    for key, record in spec.attribution.items():
        shown = str(record["value"])
        print(f"    {key:<18} = {shown[:62]}")
        print(f"    {'':<18}   set by {record['set_by']}"
              + (f" ({record['note']})" if record["note"] else ""))
    print("\n  limits, in the contracts' own envelope shape:")
    for limit in spec.limits:
        print(f"    {limit}")
    print("\n  reads:")
    for read in spec.reads:
        print(f"    {read}")
    print("\n  to_seed() - handed straight to the Design phase agent:")
    print("   " + json.dumps(spec.to_seed(), indent=2).replace("\n", "\n   "))
    print("\n  unresolved() - what a complete form still cannot settle:")
    for gap in spec.unresolved():
        print(f"    - {gap[:112]}")
    if not spec.unresolved():
        print("    (nothing)")
    else:
        print("    both are the profile's own open questions. The form records "
              "an answer for this\n    round and does not close them, because "
              "neither is one person's to settle.")

    print()
    print(rule)
    print("THE STEPS, AND WHICH HANDOVER FOLLOWS WHICH")
    print(rule)
    for step in instance.steps:
        hand = step.get("handover_after")
        mark = "  manual: " + ", ".join(step["manual_parts"]) if step.get(
            "manual_parts") else ""
        count = f"  [{step['count_observed']} items]" if step.get(
            "count_observed") else ""
        print(f"  {step['number']:>2}. {step['name']:<46} {step['phase']:<7}"
              f"{count}")
        if step.get("routes"):
            print(f"      fork: " + " | ".join(step["routes"])
                  + "  (the route has to travel with the sample; no contract "
                    "field carries it)")
        if mark:
            print(f"    {mark}")
        if hand:
            print(f"      ==> handover {step['handover_number']}: {hand}")
    not_done = [s["number"] for s in instance.steps if s.get("carried_out") is False]
    print(f"\n  steps never carried out in the cycle this form was drawn from: "
          f"{not_done}")


if __name__ == "__main__":
    _demo()
