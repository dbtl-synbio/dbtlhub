"""Contracts: one handover's requirements, written as a file.

This is the module that makes the whole design work or not. A handover must be
describable entirely by data, so that adding one means writing a file rather
than writing code inside this package and merging it. If anybody ever needs to
edit Python to add a handover, this module has failed.

Nothing here executes anything a contract says. A contract is read as data,
checked for sense, and handed to the rule engine. A contract file containing
text that looks like code is text.

A contract also contains no instruction to a model. There is no field for one,
and a file carrying an unknown field is rejected rather than ignored. The
reasons are in section 10 of the specification: a contract says what must be
true and stays true for years, a prompt says where to look and goes stale; rule
authors want their rules to pass and would write prompts that find a value
whether or not it is there; and this service accepts contracts from the sender,
so prompt text in a contract means the sender writes the model's instructions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


class ContractError(Exception):
    """A contract file does not make sense. Raised when it is read, so the
    author finds out on their own machine rather than six weeks later when
    somebody posts a crate."""


class ContractNotFound(Exception):
    """No contract of that name. The message names the ones there are, because
    the usual cause is a typo."""


# What a requirement may say. Anything else is an error rather than something
# quietly ignored, so a misspelled key cannot sit in a file looking effective.
REQUIREMENT_KEYS = {
    "name",
    "applies_to",
    "property",
    "named_value",
    "must",
    "one_of",
    "of_type",
    "between",
    "severity",
    "message",
    "repairable",
}

CONTRACT_KEYS = {"contract", "version", "description", "expects", "requires"}

SEVERITIES = {"refuse", "flag"}

# Everything a requirement can demand. The list is deliberately short and
# grows one entry at a time, on purpose: a language that can say anything can
# also say things nobody can check, and this list is what a contract author
# can be shown as the whole of their vocabulary.
#
# Only "be recorded" fires when a property is absent. The others have nothing
# to say about a property that is not there, because "it must be present" and
# "it must be sound" are two requirements, and a rule that did both would make
# one of them unsayable.
MUSTS = {
    "be recorded",
    "be unique",
    "point at something in the crate",
    "be a number between",
    "hold data",
}

# Which extra field each demand needs, if any.
NEEDS = {
    "be a number between": "between",
}

# Where a requirement applies. "root" and "descriptor" name the two entities
# every crate has; anything else is read as a type, so `type:CoatingRecipe`
# means every entity of that type. The contract files under examples/ use
# that type throughout.
#
# No contract is named here on purpose. A test greps this source for every
# handover name it knows and fails the day one appears, because a handover
# is data and naming one in code is the first step to special-casing it.
SPECIAL_TARGETS = {"root", "descriptor"}


@dataclass(frozen=True)
class Requirement:
    """One thing that must be true, and the sentence to say when it is not.

    A requirement reads either a property sitting directly on an entity, or a
    named value hanging off it. Crates following the Process Run Crate profile
    record most numbers and strings the second way: the film thickness is not
    written on a recipe, it is a separate entity carrying the name "film
    thickness" and the value 42 which the recipe points at.
    """

    name: str
    applies_to: str
    property: str | None
    named_value: str | None
    must: str
    severity: str
    message: str
    one_of: tuple[str, ...] | None = None
    of_type: str | None = None
    between: tuple[float, float] | None = None
    repairable: bool = False

    @property
    def reads(self) -> str:
        """What this requirement looks at, for a message a person reads."""
        return self.property or f"its named value {self.named_value!r}"

    def demand_in_words(self) -> str:
        """What this requirement asks for, as a person would say it."""
        if self.must == "be recorded":
            said = f"must record {self.reads}"
            if self.one_of:
                said += f", one of: {', '.join(self.one_of)}"
            return said
        if self.must == "be unique":
            return f"must not share {self.reads} with another"
        if self.must == "point at something in the crate":
            target = f" of type {self.of_type}" if self.of_type else ""
            return f"{self.reads} must point at something{target} in the crate"
        if self.must == "be a number between":
            low, high = self.between
            return f"{self.reads} must be between {low} and {high}"
        return f"{self.reads} {self.must}"


@dataclass(frozen=True)
class Contract:
    """One handover's requirements. There is no code for any handover."""

    name: str
    version: str
    requirements: tuple[Requirement, ...]
    checksum: str
    description: str = ""
    source_path: str | None = None

    # What kinds of thing this contract is for. Every type named here must be
    # present in the crate, or the handover is refused before any requirement
    # is applied.
    #
    # It exists because of a fault found on 11 November 2026 by deploying two
    # instances and sending a crate to the wrong one. A requirement whose
    # `applies_to` type is absent from the crate matches nothing and passes,
    # which is correct on its own and disastrous in aggregate: 12 of 18
    # requirements in one contract passed that way, and the verdict was
    # ACCEPTED with no findings on a crate from an unrelated domain.
    #
    # Blessing a crate nobody checked is worse than refusing a good one, so
    # a contract now says what it is for.
    #
    # It is the author's choice rather than something inferred from the
    # requirements, because a contract may legitimately carry requirements
    # about entity types that are optional, and only the author knows which
    # of them must be there.
    expects: tuple[str, ...] = ()

    def summary(self) -> str:
        """The contract in plain words.

        A producing team reads this to check themselves before they are
        checked, so every requirement appears and none is abbreviated away.
        """
        lines = [f"{self.name} version {self.version}"]
        if self.description:
            lines += ["", self.description.strip()]
        if self.expects:
            lines += [
                "",
                "It is for crates containing all of: "
                + ", ".join(self.expects),
                "A crate containing none of those is refused rather than "
                "accepted without being checked.",
            ]
        else:
            lines += [
                "",
                "⚠ This contract does not say what it is for, so it accepts "
                "any crate whose packaging is sound, including one from "
                "another phase. Every requirement about a type the crate "
                "does not contain matches nothing and passes. Add an "
                "`expects` block.",
            ]
        lines += ["", f"{len(self.requirements)} requirement(s):"]
        for requirement in self.requirements:
            verb = "refuses the handover" if requirement.severity == "refuse" else "raises a flag"
            lines.append("")
            lines.append(f"  {requirement.name}")
            lines.append(f"    {requirement.applies_to} {requirement.demand_in_words()}")
            lines.append(f"    failing it {verb}")
            lines.append(f"    {requirement.message}")
        return "\n".join(lines)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def parse(text: str, source_path: str | None = None) -> Contract:
    """Read one contract from the authored form.

    Everything that can be wrong with a contract is found here, with the file
    named, rather than at the moment somebody posts a crate.
    """
    try:
        body = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContractError(f"{source_path or 'contract'}: not readable: {exc}") from exc

    where = source_path or "contract"
    _require(isinstance(body, dict), f"{where}: a contract is a set of named values")

    unknown = set(body) - CONTRACT_KEYS
    _require(
        not unknown,
        f"{where}: does not understand {sorted(unknown)}. "
        f"A contract may say {sorted(CONTRACT_KEYS)} and nothing else.",
    )

    name = body.get("contract")
    version = body.get("version")
    _require(isinstance(name, str) and name, f"{where}: no contract name")
    _require(
        isinstance(version, str) and version,
        f"{where}: no version. A version is what somebody cites in an argument "
        "about why a batch was refused.",
    )

    raw_expects = body.get("expects") or []
    _require(
        isinstance(raw_expects, list),
        f"{where}: `expects` is a list of the entity types this contract is "
        "for, such as [PlateWell, Protein]",
    )
    for position, entry in enumerate(raw_expects, start=1):
        _require(
            isinstance(entry, str) and entry.strip(),
            f"{where}: `expects` entry {position} is not the name of a type",
        )
    expects = tuple(entry.strip().removeprefix("type:") for entry in raw_expects)

    raw_requirements = body.get("requires") or []
    _require(
        isinstance(raw_requirements, list),
        f"{where}: `requires` is a list of requirements",
    )

    requirements = []
    seen_names = set()
    for position, raw in enumerate(raw_requirements, start=1):
        requirements.append(_parse_requirement(raw, where, position, seen_names))

    return Contract(
        name=name,
        version=version,
        description=body.get("description") or "",
        expects=expects,
        requirements=tuple(requirements),
        checksum="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_path=source_path,
    )


def _parse_requirement(raw, where: str, position: int, seen: set) -> Requirement:
    at = f"{where}: requirement {position}"
    _require(isinstance(raw, dict), f"{at} is not a set of named values")

    unknown = set(raw) - REQUIREMENT_KEYS
    _require(
        not unknown,
        f"{at} does not understand {sorted(unknown)}. A requirement may say "
        f"{sorted(REQUIREMENT_KEYS)} and nothing else. In particular there is "
        "no field for instructing a model.",
    )

    name = raw.get("name")
    _require(isinstance(name, str) and name, f"{at} has no name")
    _require(name not in seen, f"{at}: two requirements are called {name!r}")
    seen.add(name)

    applies_to = raw.get("applies_to")
    _require(
        isinstance(applies_to, str) and applies_to,
        f"{at} ({name}) does not say what it applies to",
    )

    prop = raw.get("property")
    named = raw.get("named_value")

    # `hold data` is the only demand that reads no property and no named
    # value. It is about the file an entity stands for, not about anything
    # written on it, so insisting on one of the two would be asking for a
    # field with nothing to put in it.
    if raw.get("must") == "hold data":
        _require(
            not prop and not named,
            f"{at} ({name}) says 'hold data', which is about the file an "
            "entity stands for, so it takes neither `property` nor "
            "`named_value`.",
        )
    else:
        _require(
            bool(prop) != bool(named),
            f"{at} ({name}) must say either `property`, for something "
            "written on the entity itself, or `named_value`, for a value "
            "hanging off it. It says both or neither.",
        )
    if prop is not None:
        _require(isinstance(prop, str) and prop, f"{at} ({name}): property is a name")
    if named is not None:
        _require(
            isinstance(named, str) and named,
            f"{at} ({name}): named_value is the name of the value, as written "
            "in the crate",
        )

    must = raw.get("must", "be recorded")
    _require(
        must in MUSTS,
        f"{at} ({name}) says {must!r}, which is not something a requirement "
        f"can demand. It may say: {sorted(MUSTS)}. "
        "Adding a fifth is a change to the product rather than to this file: "
        "MUSTS in src/sentinel_oo/contract.py, a branch in _apply in "
        "src/sentinel_oo/rules.py, and tests for both. See "
        "docs/WRITING_A_CONTRACT.md.",
    )

    severity = raw.get("severity")
    _require(
        severity in SEVERITIES,
        f"{at} ({name}) has severity {severity!r}. It is {sorted(SEVERITIES)}: "
        "either the handover stops or it is mentioned, and there is nothing "
        "in between that anybody can act on.",
    )

    message = raw.get("message")
    _require(
        isinstance(message, str) and message.strip(),
        f"{at} ({name}) has no message. A violation nobody can read is not "
        "worth raising.",
    )

    one_of = raw.get("one_of")
    if one_of is not None:
        _require(
            isinstance(one_of, list) and one_of,
            f"{at} ({name}): one_of is a list of permitted values",
        )
        one_of = tuple(str(value) for value in one_of)

    needed = NEEDS.get(must)
    _require(
        needed is None or raw.get(needed) is not None,
        f"{at} ({name}) says {must!r} but does not say `{needed}`",
    )

    between = raw.get("between")
    if between is not None:
        _require(
            isinstance(between, list)
            and len(between) == 2
            and all(isinstance(v, (int, float)) for v in between),
            f"{at} ({name}): between is a lowest and a highest number",
        )
        _require(
            between[0] <= between[1],
            f"{at} ({name}): the lowest number is above the highest",
        )
        between = (float(between[0]), float(between[1]))

    of_type = raw.get("of_type")
    if of_type is not None:
        _require(
            isinstance(of_type, str) and of_type,
            f"{at} ({name}): of_type names a kind of entity",
        )

    return Requirement(
        name=name,
        applies_to=applies_to,
        property=prop,
        named_value=named,
        must=must,
        severity=severity,
        message=message.strip(),
        one_of=one_of,
        of_type=of_type,
        between=between,
        repairable=bool(raw.get("repairable", False)),
    )


class ContractRegistry:
    """Holds contracts. Executes nothing."""

    def __init__(self, contracts: dict[str, Contract]):
        self._contracts = dict(contracts)

    @classmethod
    def from_dir(cls, folder: str | Path) -> "ContractRegistry":
        folder = Path(folder)
        found: dict[str, Contract] = {}
        for path in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml")):
            contract = parse(path.read_text(encoding="utf-8"), source_path=path.name)
            if contract.name in found:
                raise ContractError(
                    f"two files define the contract {contract.name!r}: "
                    f"{found[contract.name].source_path} and {path.name}"
                )
            found[contract.name] = contract
        return cls(found)

    def get(self, name: str, version: str | None = None) -> Contract:
        contract = self._contracts.get(name)
        if contract is None:
            known = ", ".join(sorted(self._contracts)) or "none at all"
            raise ContractNotFound(
                f"no contract called {name!r}. This service knows: {known}."
            )
        if version is not None and contract.version != version:
            raise ContractNotFound(
                f"contract {name!r} is version {contract.version} here, "
                f"and {version} was asked for."
            )
        return contract

    def list(self) -> tuple[Contract, ...]:
        return tuple(self._contracts[name] for name in sorted(self._contracts))

    def checksum(self) -> str:
        """One checksum over every contract held, so the service can say
        exactly what it is carrying."""
        joined = "".join(
            f"{c.name}:{c.version}:{c.checksum};" for c in self.list()
        )
        return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def __len__(self) -> int:
        return len(self._contracts)
