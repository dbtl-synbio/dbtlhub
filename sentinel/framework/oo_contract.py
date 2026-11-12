#!/usr/bin/env python3
"""Running a `sentinel-oo` contract, unchanged, inside this sentinel.

    python3 framework/oo_contract.py

WHY THIS EXISTS
Two sentinels now guard the same handover. Anil Wipat's `sentinel-oo` and this
framework were written independently, and a comparison of their Design -> Build
contracts found thirteen checks on one side, twenty on the other, and exactly
two in common. That is not a disagreement: they are looking at different
objects. His requirements apply to ENTITIES IN A CRATE, by type; ours apply to
PATHS IN A PACKAGE - `order.items`, `bindings`, `crate.@graph`.

The wrong response is to reimplement his twenty as ours, which would create a
second copy that drifts. The right one is to run his file as it is. So this
module reads a `sentinel-oo` contract and executes it against the crate a
package carries, reporting through our own `Error` so one sentinel can hold a
handover to both agreements at once and record both in the crate.

HIS LANGUAGE, NOT A TRANSLATION OF IT
A requirement says where it applies, what it reads, and one of five demands:

    be recorded                        with an optional `one_of`
    be unique
    point at something in the crate    with an optional `of_type`
    be a number between                with `between: [low, high]`
    hold data                          the file exists and is not empty

`applies_to` is `root`, `descriptor`, or a type: `type:Protein` means every
entity of that type. What it reads is either a `property` written on the
entity, or a `named_value` hanging off it - which is how a Process Run Crate
records most numbers: the value is a separate PropertyValue the entity points
at, and a reader that knew only the first shape would see half the crate.

`expects` lists the types the contract is written for. A crate holding none of
them is refused outright, because every requirement about an absent type
matches nothing and passes: his own note records twelve of eighteen passing
that way on a crate from an unrelated domain, accepted with no findings.

WHAT THIS MODULE WILL NOT DO
It does not repair, and it does not change his file. If the two sentinels
disagree about a crate, that disagreement is the finding, and it belongs in
front of both authors rather than smoothed over here.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from framework.validator import Error                              # noqa: E402

# His vocabulary, copied deliberately rather than imported: this framework must
# not depend on his package being installed, and a divergence should show up as
# a refusal here rather than as a silent change in behaviour.
MUSTS = {"be recorded", "be unique", "point at something in the crate",
         "be a number between", "hold data"}
NEEDS = {"be a number between": "between"}
REQUIREMENT_KEYS = {"name", "applies_to", "property", "named_value", "must",
                    "one_of", "of_type", "between", "severity", "message",
                    "repairable"}
CONTRACT_KEYS = {"contract", "version", "description", "expects", "requires"}
SEVERITIES = {"refuse", "flag"}

# His severities, in our words. `refuse` blocks a handover, `flag` does not.
AS_OURS = {"refuse": "error", "flag": "flag"}


class ForeignContractError(Exception):
    """The file does not make sense as a sentinel-oo contract."""


@dataclass(frozen=True)
class Requirement:
    name: str
    applies_to: str
    must: str
    severity: str
    message: str
    property: str | None = None
    named_value: str | None = None
    one_of: tuple[str, ...] | None = None
    of_type: str | None = None
    between: tuple[float, float] | None = None
    repairable: bool = False


@dataclass(frozen=True)
class ForeignContract:
    name: str
    version: str
    description: str
    expects: tuple[str, ...]
    requirements: tuple[Requirement, ...]
    source: str = ""

    @property
    def id(self) -> str:
        return f"sentinel-oo:{self.name}/{self.version}"


# --------------------------------------------------------------------------- #
#  Reading one
# --------------------------------------------------------------------------- #
def load(path: Path | str) -> ForeignContract:
    """Read a contract file. Unknown keys are refused, never ignored.

    Refusing is his rule and it is the right one: a misspelled key that is
    quietly dropped sits in a file looking effective for years.
    """
    path = Path(path)
    try:
        import yaml                                        # noqa: PLC0415
    except ImportError as exc:                             # pragma: no cover
        raise ForeignContractError(
            "a sentinel-oo contract is YAML and PyYAML is not installed"
        ) from exc
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ForeignContractError(f"{path.name} is not a mapping")

    unknown = set(raw) - CONTRACT_KEYS
    if unknown:
        raise ForeignContractError(
            f"{path.name} has keys this reader does not know: "
            f"{sorted(unknown)}. Known: {sorted(CONTRACT_KEYS)}")
    for needed in ("contract", "version", "requires"):
        if needed not in raw:
            raise ForeignContractError(f"{path.name} has no {needed!r}")

    requirements = []
    for i, item in enumerate(raw["requires"] or [], start=1):
        if not isinstance(item, dict):
            raise ForeignContractError(f"requirement {i} is not a mapping")
        strange = set(item) - REQUIREMENT_KEYS
        if strange:
            raise ForeignContractError(
                f"requirement {item.get('name', i)!r} has unknown keys "
                f"{sorted(strange)}")
        must = item.get("must")
        if must not in MUSTS:
            raise ForeignContractError(
                f"requirement {item.get('name', i)!r} asks for {must!r}, "
                f"which is not one of {sorted(MUSTS)}")
        extra = NEEDS.get(must)
        if extra and item.get(extra) is None:
            raise ForeignContractError(
                f"requirement {item.get('name', i)!r} needs {extra!r}")
        severity = item.get("severity", "refuse")
        if severity not in SEVERITIES:
            raise ForeignContractError(
                f"requirement {item.get('name', i)!r} has severity "
                f"{severity!r}, not one of {sorted(SEVERITIES)}")
        if (item.get("property") is None and item.get("named_value") is None
                and must != "hold data"):
            # `hold data` is the exception, and his own file is why this
            # reader knows it: it applies to a File entity and reads that
            # entity's own identifier, which IS the path to the file. A
            # reader that demanded a property here refused his contract.
            raise ForeignContractError(
                f"requirement {item.get('name', i)!r} reads neither a "
                f"property nor a named value")
        between = item.get("between")
        requirements.append(Requirement(
            name=str(item.get("name", f"requirement-{i}")),
            applies_to=str(item.get("applies_to", "root")),
            must=must, severity=severity,
            message=str(item.get("message", "")),
            property=item.get("property"),
            named_value=item.get("named_value"),
            one_of=tuple(item["one_of"]) if item.get("one_of") else None,
            of_type=item.get("of_type"),
            between=(float(between[0]), float(between[1])) if between else None,
            repairable=bool(item.get("repairable", False)),
        ))

    return ForeignContract(
        name=str(raw["contract"]), version=str(raw["version"]),
        description=str(raw.get("description", "")),
        expects=tuple(raw.get("expects") or ()),
        requirements=tuple(requirements), source=str(path))


# --------------------------------------------------------------------------- #
#  Reading a crate his way
# --------------------------------------------------------------------------- #
def types_of(entity: dict) -> tuple[str, ...]:
    """Every kind this entity says it is, INCLUDING `additionalType`.

    Schema.org has no word for an expression construct or a gene-calling
    step, so a Process Run Crate says `@type: CreateAction` and hangs the
    domain kind off `additionalType`. A reader that knew only `@type` would
    see a crate full of CreateActions and CreativeWorks and no biology at
    all - which is exactly what happened: this function read `@type` alone,
    so every `expects` in his contract matched nothing, every one of his
    example crates was refused, and the refusal was reported as his contract
    having moved ahead of his own examples. It had not. The fault was here.
    """
    raw = entity.get("@type")
    if raw is None:
        raw = []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    return tuple(str(t) for t in raw) + values_of(entity, "additionalType")


def values_of(entity: dict | None, prop: str) -> tuple[str, ...]:
    """Everything an entity records under one property, as text.

    A property is written several ways in crates that exist: one reference, a
    list, a plain string, a number, or a mixed list. All mean the same, and a
    check that understood one shape would pass crates it should not.
    """
    if entity is None:
        return ()
    raw = entity.get(prop)
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    out = []
    for item in raw:
        if isinstance(item, dict):
            ref = item.get("@id")
            if ref:
                out.append(str(ref))
        elif item is not None and str(item).strip():
            out.append(str(item))
    return tuple(out)


def named_values_of(entity: dict, wanted: str, index: dict) -> tuple[str, ...]:
    """Every value hanging off an entity under a given name.

    Every reference the entity makes is followed, not one chosen property: a
    recipe hangs its values off `additionalProperty` and a step hangs its
    settings off `object`, and a reader that knew only one would see half the
    crate. A reference that does not resolve is skipped - that it is broken is
    a fault of its own, and some other requirement's business.
    """
    out = []
    for key in entity:
        if key.startswith("@"):
            continue
        for ref in values_of(entity, key):
            carrier = index.get(ref)
            if carrier is None or "PropertyValue" not in types_of(carrier):
                continue
            if str(carrier.get("name", "")) == wanted:
                out.extend(values_of(carrier, "value"))
    return tuple(out)


def _targets(applies_to: str, graph: list[dict], index: dict) -> list[dict]:
    if applies_to == "descriptor":
        return [index.get("ro-crate-metadata.json")] if \
            index.get("ro-crate-metadata.json") else []
    if applies_to == "root":
        descriptor = index.get("ro-crate-metadata.json", {})
        about = descriptor.get("about")
        ref = about.get("@id") if isinstance(about, dict) else "./"
        root = index.get(ref) or index.get("./")
        return [root] if root else []
    wanted = (applies_to.split(":", 1)[1] if applies_to.startswith("type:")
              else applies_to)
    return [e for e in graph if wanted in types_of(e)]


def _read(requirement: Requirement, entity: dict, index: dict) -> tuple[str, ...]:
    if requirement.property is not None:
        return values_of(entity, requirement.property)
    if requirement.named_value is not None:
        return named_values_of(entity, requirement.named_value, index)
    # Neither: the requirement is about the entity itself. Only `hold data`
    # reaches here, and what it reads is the identifier, which for a File is
    # the path to the file.
    ref = entity.get("@id")
    return (str(ref),) if ref else ()


# --------------------------------------------------------------------------- #
#  Checking
# --------------------------------------------------------------------------- #
def check(contract: ForeignContract, crate: dict,
          base: Path | None = None) -> list[Error]:
    """Run a sentinel-oo contract against a crate. Reports through our Error.

    `base` is the folder the crate sits in, needed only by `hold data`. Without
    it that demand reports that it could not be run, as a flag - never a silent
    pass, which is the failure mode this framework spends most of its effort
    making impossible.
    """
    graph = [e for e in crate.get("@graph") or [] if isinstance(e, dict)]
    index = {e.get("@id"): e for e in graph if e.get("@id")}
    errors: list[Error] = []

    # `expects` first: a crate holding none of what the contract is for would
    # pass nearly everything by matching nothing.
    present: set[str] = set()
    for entity in graph:
        present.update(types_of(entity))
    for wanted in contract.expects:
        if wanted not in present:
            errors.append(Error(
                "./", f"crate_contains_{wanted}",
                f"nothing of type {wanted} is in this crate, and the contract "
                f"{contract.name} is written for crates that contain it - "
                f"every requirement about that type would match nothing and "
                f"pass",
                "not auto-fixable: either this crate came from a different "
                "phase, or a type name in it has been changed.",
                "error"))

    for requirement in contract.requirements:
        severity = AS_OURS[requirement.severity]
        reads = (requirement.property
                 or (f"its named value {requirement.named_value!r}"
                     if requirement.named_value else "the file it names"))
        targets = _targets(requirement.applies_to, graph, index)

        if requirement.must == "hold data" and base is None:
            errors.append(Error(
                requirement.applies_to, f"{requirement.name}:not_checked",
                f"'hold data' needs the folder the crate sits in, and this "
                f"crate was checked in memory. {len(targets)} entit"
                f"{'y' if len(targets) == 1 else 'ies'} were not checked.",
                "hand the sentinel a crate on disk to run this requirement.",
                "flag"))
            continue

        for entity in targets:
            where = f"{requirement.applies_to}[{entity.get('@id', '?')}]"
            got = _read(requirement, entity, index)

            if requirement.must == "be recorded":
                if not got:
                    errors.append(_fault(requirement, where, severity, reads))
                elif requirement.one_of:
                    for value in got:
                        if value not in requirement.one_of:
                            errors.append(_fault(requirement, where, severity,
                                                 reads, value))
            elif requirement.must == "point at something in the crate":
                for value in got:
                    target = index.get(value)
                    if target is None or (
                            requirement.of_type
                            and requirement.of_type not in types_of(target)):
                        errors.append(_fault(requirement, where, severity,
                                             reads, value))
            elif requirement.must == "be a number between":
                low, high = requirement.between
                for value in got:
                    try:
                        number = float(value)
                    except (TypeError, ValueError):
                        errors.append(_fault(requirement, where, severity,
                                             reads, value))
                        continue
                    if not low <= number <= high:
                        errors.append(_fault(requirement, where, severity,
                                             reads, value))
            elif requirement.must == "hold data":
                for value in got:
                    # A file identified by a web address is not looked at.
                    # The crate does not carry it, fetching it is a different
                    # act with different consequences, and this says so
                    # rather than guessing. Without this skip, every crate
                    # here was refused once for each file that lives
                    # elsewhere and was never going to be carried - which is
                    # what made our reading of his contract disagree with
                    # his own engine on all six example crates.
                    if value.startswith(("http://", "https://")):
                        continue
                    spot = (base / value) if base else None
                    if spot is None:
                        errors.append(_fault(
                            requirement, where, severity, reads,
                            f"{value}: the data did not arrive with this "
                            f"crate, so whether it holds anything could not "
                            f"be checked"))
                    elif not spot.is_file():
                        errors.append(_fault(requirement, where, severity,
                                             reads, f"{value}: no such file"))
                    elif spot.stat().st_size == 0:
                        errors.append(_fault(requirement, where, severity,
                                             reads, f"{value}: the file is "
                                                    f"empty"))

        if requirement.must == "be unique":
            # Across all targets at once, and every holder of a shared value is
            # reported: a person fixing it needs to see both ends of the clash.
            holders: dict[str, list[str]] = {}
            for entity in targets:
                for value in _read(requirement, entity, index):
                    holders.setdefault(value, []).append(entity.get("@id", "?"))
            for value, sharing in holders.items():
                if len(sharing) > 1:
                    for who in sharing:
                        errors.append(_fault(
                            requirement, f"{requirement.applies_to}[{who}]",
                            severity, reads, value))
    return errors


def _fault(requirement: Requirement, where: str, severity: str,
           reads: str, value: str | None = None) -> Error:
    """One failure, with the contract author's own sentence.

    His message, not ours. The whole point of writing the sentence in the
    contract is that the person who wrote the rule explains it.
    """
    said = requirement.message or f"{reads} does not satisfy {requirement.must}"
    if value is not None:
        said = f"{said} (it records {value!r})"
    return Error(where, requirement.name, said,
                 "repairable, per the contract" if requirement.repairable
                 else "not auto-fixable: see the contract's own message.",
                 severity)


def available(folder: Path | str) -> dict[str, Path]:
    """Every sentinel-oo contract in a folder, by handover name.

    Keyed by the `contract` field rather than the filename, because the
    sentinel asks for a handover by name and a file may be called anything.
    """
    out: dict[str, Path] = {}
    folder = Path(folder)
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.yaml")):
        try:
            out[load(path).name] = path
        except Exception:                          # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- #
def main() -> None:
    his = (Path.home() / "Research" / "dbtlhub" / "sentinel-oo"
           / "examples" / "contracts")
    print(f"\n{'=' * 78}\nA SENTINEL-OO CONTRACT, READ AND RUN HERE\n{'=' * 78}\n")
    found = available(his)
    if not found:
        print(f"  no contracts under {his}\n")
        return
    for name, path in found.items():
        contract = load(path)
        print(f"  {name}/{contract.version}  {len(contract.requirements)} "
              f"requirements, expects {list(contract.expects)}")
        print(f"      {path}")

    name, path = next(iter(found.items()))
    contract = load(path)
    musts: dict[str, int] = {}
    for requirement in contract.requirements:
        musts[requirement.must] = musts.get(requirement.must, 0) + 1
    print(f"\n  what {name} asks for:")
    for must, count in sorted(musts.items(), key=lambda kv: -kv[1]):
        print(f"    {count:>3}  {must}")

    # Against one of his own example crates, and then one of ours.
    crates = (Path.home() / "Research" / "dbtlhub" / "bioprospecting"
              / "exampleROcrates" / "design-to-build")
    print(f"\n{'=' * 78}\nAGAINST CRATES ON THIS MACHINE\n{'=' * 78}\n")
    for folder in sorted(crates.glob("*/")) + sorted(crates.glob("invalid/*/")):
        metadata = folder / "ro-crate-metadata.json"
        if not metadata.is_file():
            continue
        crate = json.loads(metadata.read_text())
        found_errors = check(contract, crate, base=folder)
        blocking = [e for e in found_errors if e.severity == "error"]
        print(f"  {folder.name:<28}"
              f"{'REFUSED' if blocking else 'accepted':<10}"
              f"{len(blocking)} blocking, {len(found_errors) - len(blocking)} flag(s)")
        for error in blocking[:3]:
            print(f"      {error.code}: {error.message[:88]}")
    print()


if __name__ == "__main__":
    main()
