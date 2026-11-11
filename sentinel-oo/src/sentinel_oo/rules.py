"""The rules, and the only component that may decide.

Nothing outside this module produces a verdict. The orchestrator sequences, the
writer writes, the model advises, and the decision is taken here and carried on
the report. If anything downstream ever worked the verdict out for itself from
the findings, that downstream thing would be the one deciding.

At step 3 of the build order the checks come from a contract file and there is
no check written in Python anywhere. The engine below knows how to apply a
requirement; it knows nothing about any particular handover, and there is a
test that fails if a handover is ever named in this package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from .blessing import Verdict
from .contract import Contract, Requirement
from .crate import Crate


class Severity(str, Enum):
    """Two, and only two.

    A third, somewhere between "stop" and "mention", would be a judgement
    nobody can act on.
    """

    REFUSE = "refuse"
    FLAG = "flag"


@dataclass(frozen=True)
class Violation:
    """One requirement, unmet, somewhere nameable."""

    requirement: Requirement
    node: str
    message: str
    value: str | None = None

    @property
    def severity(self) -> Severity:
        return Severity(self.requirement.severity)


# The name carried by the flag raised for a value a model recovered. It is
# not a requirement anybody wrote in a contract, so it is named here rather
# than coming from a file, and it reads as a sentence in a report.
RECOVERED_VALUE = "a value was recovered by a model, not recorded"


def flag_for(change) -> "Violation":
    """One flag describing one value a model recovered.

    Decided by Neil on 11 November 2026, after the RunPod test showed a
    crate going from REFUSED to ACCEPTED with nothing in the verdict saying
    a model had supplied the missing value. The crate's own record already
    says a value read out of prose is less trustworthy than one somebody
    wrote down. The verdict now says the same thing instead of contradicting
    it.

    The handover is not blocked. A flag means somebody should look, and the
    person worth telling is the producing team, because a step relying on a
    model to recover what it should be recording is a defect upstream.
    """
    sentence = (
        f"The {change.reads} was not recorded on this entity. The value "
        f"{change.after!r} was recovered from the text already in the crate "
        f"by {change.proposed_by}, and confirmed by the requirement "
        f"{change.confirmed_by}. A value somebody wrote down and a value "
        "something read out of prose are not equally trustworthy, so "
        "somebody should check it and ask the producing step to record it "
        "properly."
    )
    requirement = Requirement(
        name=RECOVERED_VALUE,
        applies_to=change.node,
        property=None,
        named_value=change.reads,
        must="be recorded",
        severity=Severity.FLAG.value,
        message=sentence,
    )
    return Violation(
        requirement=requirement,
        node=change.node,
        message=sentence,
        value=change.after,
    )


def with_flags_for(report: "Report", changes) -> "Report":
    """The same report, plus one flag for each value a model recovered.

    A fresh report is built rather than the verdict being set, because a
    report settles its own verdict when it is made and there is no way to
    set it afterwards. That property is worth more than the convenience of
    editing one.
    """
    if not changes:
        return report
    return Report(
        violations=tuple(report.violations) + tuple(flag_for(c) for c in changes)
    )


@dataclass(frozen=True)
class Report:
    """What the rules found, and the verdict.

    The verdict is settled when the report is made and there is no way to set
    it afterwards.
    """

    violations: tuple[Violation, ...] = field(default_factory=tuple)
    verdict: Verdict = field(init=False)

    def __post_init__(self):
        if any(v.severity is Severity.REFUSE for v in self.violations):
            decided = Verdict.REFUSED
        elif self.violations:
            decided = Verdict.ACCEPTED_WITH_FLAGS
        else:
            decided = Verdict.ACCEPTED
        object.__setattr__(self, "verdict", decided)

    @property
    def ok(self) -> bool:
        return self.verdict is not Verdict.REFUSED

    @property
    def blocking(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.severity is Severity.REFUSE)

    @property
    def flags(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.severity is Severity.FLAG)

    @property
    def repairable(self) -> tuple[Violation, ...]:
        """Those a repair may be attempted on. The rest are for a person.

        The test is not whether a fix is hard. It is whether making it would
        assert something nobody observed.
        """
        return tuple(v for v in self.violations if v.requirement.repairable)


class RuleEngine(ABC):
    """The only component that may decide whether a package is acceptable."""

    @abstractmethod
    def validate(self, subject, contract: Contract | None = None) -> Report:
        ...


def values_of(entity, prop: str) -> tuple[str, ...]:
    """Everything an entity records under one property, as text.

    A property is written several ways in crates that exist: one reference, a
    list of them, a plain string, a number, or a list mixing those. All of them
    mean "this entity records these values", and a check that understood only
    one of the shapes would pass crates it should not.
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
        if hasattr(item, "keys"):
            target = item.get("@id")
            if target:
                out.append(str(target))
        elif item is not None and str(item).strip():
            out.append(str(item))
    return tuple(out)


def named_values_of(entity, wanted: str, crate) -> tuple[str, ...]:
    """Every value hanging off an entity under a given name.

    Crates following the Process Run Crate profile record most numbers and
    strings this way: the value is a separate entity carrying a name and a
    value, which the thing it describes points at. Reading them is therefore
    not a nicety, it is how such a crate is read at all.

    Every reference the entity makes is followed, not one chosen property. A
    recipe hangs its values off `additionalProperty`, while a step hangs
    the setting it ran with off `object`, because that is what the profile
    says a parameter is. A reader that knew only one of those would see half
    the crate.

    A reference that does not resolve is skipped rather than raising. That the
    reference is broken is a fault in its own right, and one a requirement can
    be written for; it is not this function's business to decide.
    """
    out = []
    for key in entity:
        if key.startswith("@"):
            continue
        for reference in values_of(entity, key):
            carrier = crate.get(reference)
            if carrier is None:
                continue
            if "PropertyValue" not in types_of(carrier):
                continue
            if str(carrier.get("name", "")) == wanted:
                out.extend(values_of(carrier, "value"))
    return tuple(out)


def types_of(entity) -> tuple[str, ...]:
    """Every kind this entity says it is.

    A known limitation, written down so nobody assumes otherwise: these are
    compared as plain text and nothing here knows that schema.org considers a
    Hotel to be a kind of LodgingBusiness. A requirement asking for one will
    not accept the other. Teaching it the hierarchy means giving it the whole
    of schema.org, which is a real piece of work and not a small one.
    """
    raw = entity.get("@type")
    if raw is None:
        raw = []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    # `additionalType` counts as a kind too. Schema.org has no word for an
    # coating recipe, and without this a rule could not say "every
    # recipe" at all: recipes and racks are both CreativeWork.
    return tuple(str(t) for t in raw) + values_of(entity, "additionalType")


class ContractChecks(RuleEngine):
    """Applies whatever a contract says. Knows no handover by name.

    `subject` is a crate. It becomes a graph store at the step that introduces
    one, and the requirement vocabulary is deliberately small so that the move
    is a rewrite of this class alone.
    """

    def validate(self, subject: Crate, contract: Contract | None = None) -> Report:
        if contract is None:
            return Report()

        found: list[Violation] = list(self._expected_types(contract, subject))
        for requirement in contract.requirements:
            found.extend(self._apply(requirement, subject))
        return Report(violations=tuple(found))

    # ------------------------------------------------- is this crate ours?

    @staticmethod
    def _expected_types(contract: Contract, crate: Crate) -> list[Violation]:
        """Refuse a crate that contains none of what this contract is for.

        Found on 11 November 2026 by deploying two instances and posting a
        crate to the wrong one. A requirement whose `applies_to` type is
        absent from the crate matches nothing and passes, which is right on
        its own and disastrous in aggregate: 12 of 18 requirements passed
        that way and the verdict was ACCEPTED with no findings on a crate
        from an unrelated domain.

        Blessing a crate that was never checked is worse than refusing a
        good one, so a contract may now say what it is for, and this is where
        that is enforced. One violation per absent type, because which type
        is missing is the actionable part.
        """
        if not contract.expects:
            return []

        present: set[str] = set()
        for entity in crate:
            present.update(types_of(entity))

        out = []
        for wanted in contract.expects:
            if wanted in present:
                continue
            out.append(Violation(
                requirement=Requirement(
                    name=f"crate_contains_{wanted}",
                    applies_to="root",
                    property=f"an entity of type {wanted}",
                    named_value=None,
                    must="be recorded",
                    severity="refuse",
                    message=(
                        f"This crate contains nothing of type {wanted}, which "
                        f"the contract {contract.name} is written for. Every "
                        "requirement about that type would match nothing and "
                        "pass, so the handover would be accepted without "
                        "having been checked. Either this crate came from a "
                        "different phase, or a type name in it has been "
                        "changed."
                    ),
                ),
                node="./",
                message=(
                    f"nothing of type {wanted} is in this crate, and the "
                    f"contract {contract.name} is written for crates that "
                    "contain it"
                ),
            ))
        return out

    # ------------------------------------------------------------ one rule

    def _apply(self, requirement: Requirement, crate: Crate) -> list[Violation]:
        targets = self._targets(requirement.applies_to, crate)

        if requirement.must == "be recorded":
            return self._must_be_recorded(requirement, targets, crate)
        if requirement.must == "be unique":
            return self._must_be_unique(requirement, targets, crate)
        if requirement.must == "point at something in the crate":
            return self._must_point_somewhere(requirement, targets, crate)
        if requirement.must == "be a number between":
            return self._must_be_in_range(requirement, targets, crate)
        if requirement.must == "hold data":
            return self._must_hold_data(requirement, targets, crate)

        # Unreachable: the contract reader refuses anything not listed above,
        # and this is here so that adding a demand there without adding it here
        # fails loudly rather than passing everything silently.
        raise NotImplementedError(
            f"the contract asks for {requirement.must!r} and this engine does "
            "not know how to check it"
        )

    def _must_hold_data(self, requirement, targets, crate) -> list[Violation]:
        """The file this entity stands for exists and is not empty.

        Neil's requirement, 11 November 2026: one of the basic things a
        sentinel should check is that data has actually been produced by
        every step in the workflow. Everything else in this language reads
        the description. A description can be perfectly correct about a file
        that is empty, which is what happens when a step runs, writes
        nothing, and exits successfully.

        Whether the data is RIGHT is not this service's job. That belongs to
        the architect.

        WHEN THE DATA NEVER ARRIVED, this refuses rather than passing. A
        crate posted to the web interface is its description and nothing
        else, so a contract that checks data cannot be answered from it. A
        check that could not run must never look like a check that passed,
        which is the lesson of every fault found in this service so far.

        A file identified by a URL is not looked at. The crate does not
        carry it, fetching it is a different act with different
        consequences, and this says so rather than guessing.
        """
        found = []
        for entity in targets:
            identifier = str(entity.get("@id", ""))

            if identifier.startswith(("http://", "https://")):
                # A file the crate does not carry. Nothing about it changes
                # when the crate arrives without its data, so this test has
                # to come first. It did not until 11 November 2026, and a
                # crate posted as its description alone was refused once for
                # every file that lives elsewhere, none of which it was ever
                # going to carry.
                continue

            if crate.folder is None:
                # Without this the reply carried the author's sentence,
                # "this file holds nothing, so the step produced no data",
                # when in fact the data files were never sent. Found on
                # 11 November 2026 by posting a crate's description file on
                # its own to the web interface.
                found.append(self._fault(
                    requirement, entity,
                    value="the data did not arrive with this crate",
                    message=(
                        f"The data file {identifier!r} was not sent, so "
                        "whether it holds anything could not be checked, "
                        "and a check that could not run is refused rather "
                        "than passed. Send the whole crate as a zip rather "
                        "than ro-crate-metadata.json on its own. The "
                        "requirement says: " + requirement.message
                    ),
                ))
                continue

            path = crate.folder / identifier
            try:
                if not path.is_file():
                    found.append(self._fault(requirement, entity,
                                             value="no such file"))
                elif path.stat().st_size == 0:
                    found.append(self._fault(requirement, entity,
                                             value="the file is empty"))
            except OSError as exc:
                found.append(self._fault(requirement, entity,
                                         value=f"cannot be read: {exc}"))
        return found

    @staticmethod
    def _read(requirement: Requirement, entity, crate) -> tuple[str, ...]:
        """What this requirement looks at on one entity.

        Either a property written on the entity, or a value hanging off it.
        Everything above this line is the same whichever it is.
        """
        if requirement.property is not None:
            return values_of(entity, requirement.property)
        return named_values_of(entity, requirement.named_value, crate)

    def _fault(self, requirement, entity, value=None,
               message=None) -> Violation:
        """One failure of one requirement by one entity.

        The sentence a person reads is the contract author's own, which is
        the point of writing it in the contract. `message` overrides it for
        the one case where the author's sentence would mislead: the check
        could not run at all, so saying what the author said about failing
        it would describe something that was never looked at.
        """
        return Violation(
            requirement=requirement,
            node=entity["@id"],
            message=message or requirement.message,
            value=value,
        )

    def _must_be_recorded(self, requirement, targets, crate) -> list[Violation]:
        out = []
        for entity in targets:
            recorded = self._read(requirement, entity, crate)
            if not recorded:
                out.append(self._fault(requirement, entity))
            elif requirement.one_of:
                for value in recorded:
                    if value not in requirement.one_of:
                        out.append(self._fault(requirement, entity, value))
        return out

    def _must_be_unique(self, requirement, targets, crate) -> list[Violation]:
        """No two entities may record the same value.

        Absence is not a fault here. "It must be present" and "it must not be
        shared" are two requirements, and a rule doing both would make one of
        them unsayable.

        Every entity holding a shared value is reported, not just the second
        one, because a person fixing it needs to see both ends of the clash.
        """
        holders: dict[str, list] = {}
        for entity in targets:
            for value in self._read(requirement, entity, crate):
                holders.setdefault(value, []).append(entity)

        out = []
        for value, sharing in holders.items():
            if len(sharing) > 1:
                for entity in sharing:
                    out.append(self._fault(requirement, entity, value))
        return out

    def _must_point_somewhere(self, requirement, targets, crate) -> list[Violation]:
        """Every value must name an entity that is really in the crate.

        A reference to something absent is one of the faults no validator
        catches, and it is how a handover looks complete while being broken.
        """
        out = []
        for entity in targets:
            for value in self._read(requirement, entity, crate):
                target = crate.get(value)
                if target is None:
                    out.append(self._fault(requirement, entity, value))
                elif requirement.of_type and requirement.of_type not in types_of(target):
                    out.append(self._fault(requirement, entity, value))
        return out

    def _must_be_in_range(self, requirement, targets, crate) -> list[Violation]:
        """Every value must be a number, and within the range given.

        A value that is not a number at all is a fault of the same kind: the
        requirement cannot be satisfied by it.
        """
        low, high = requirement.between
        out = []
        for entity in targets:
            for value in self._read(requirement, entity, crate):
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    out.append(self._fault(requirement, entity, value))
                    continue
                if not low <= number <= high:
                    out.append(self._fault(requirement, entity, value))
        return out

    @staticmethod
    def _targets(applies_to: str, crate: Crate):
        """Which entities a requirement is about.

        `root` and `descriptor` name the two entities every crate has. Anything
        else is read as a type, and a crate holding no entity of that type has
        nothing to check rather than something to complain about: "there are no
        readings here" is a different requirement from "every reading must
        record its length", and conflating them would make one unsayable.
        """
        if applies_to == "root":
            return [crate.root]
        if applies_to == "descriptor":
            return [crate.descriptor]
        wanted = applies_to.split(":", 1)[1] if applies_to.startswith("type:") else applies_to
        return [e for e in crate if wanted in types_of(e)]
