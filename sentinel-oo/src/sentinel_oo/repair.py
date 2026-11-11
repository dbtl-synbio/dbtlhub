"""Applying a proposed value, and never deciding whether the result is right.

The rule engine decides. This takes a value something proposed, writes it at
the one location the rules named, and hands the result back for the rules to
rule on. If the requirement still fails afterwards, the change is discarded
and the crate is left as it was.

Three things this must never do, each enforced here rather than asked for:

  Touch a violation the contract says may not be repaired automatically.
  Those are filtered out before the model is called, so it never sees them.

  Write anywhere other than the entity the rules named. A model answering a
  double-booked slot by renaming the slot would pass the re-check, because
  renaming does make the identifier unique, and would have written a record
  of something that never happened.

  Keep a change the rules do not then accept.
"""

from __future__ import annotations

from dataclasses import dataclass

from .crate import Crate


@dataclass(frozen=True)
class Change:
    """One value written, and everything needed to judge it afterwards."""

    node: str
    reads: str
    before: str | None
    after: str
    proposed_by: str
    confirmed_by: str

    def describe(self) -> str:
        was = self.before if self.before is not None else "absent"
        return (
            f"{self.reads} on {self.node}: {was} -> {self.after} "
            f"(proposed by {self.proposed_by}, confirmed by {self.confirmed_by})"
        )


class Repairer:
    """Applies changes to a copy. Never decides whether the result is
    acceptable."""

    def __init__(self, rules):
        # Held so that each change can be put back to the rules on its own.
        # Nothing here reads the report to form a view: it asks.
        self.rules = rules

    def repair(self, crate: Crate, report, contract, engine, budget: int):
        """Try to repair up to `budget` violations.

        Returns the crate, the changes that survived, and how many times the
        model was asked anything.

        The count is not the same as the number of changes. A model can be
        asked and answer nothing, or answer something the rules then throw
        away. The record has to be able to say "asked three times, kept
        nothing", which is a different run from "never asked".
        """
        if budget <= 0 or engine is None:
            return crate, (), 0

        changes = []
        asked = 0
        working = crate

        for violation in report.violations:
            if len(changes) >= budget:
                break
            # The contract decides what may be repaired at all. Anything else
            # is never shown to the model.
            if not violation.requirement.repairable:
                continue

            asked += 1
            proposed = engine.propose_value(working, violation, contract)
            if proposed is None:
                continue

            candidate = self._write(working, violation, proposed)
            if candidate is None:
                continue

            # The rules rule, and on two counts.
            #
            # The first is that the requirement being repaired must now pass.
            #
            # The second was found by trying it: a model asked for the gene
            # calling setting answered with a phrase that was not one of the
            # permitted values. That satisfied "the setting must be recorded"
            # and failed "the setting must be one of these", so the handover
            # was refused and the invented phrase was written into the crate
            # anyway. A refusal carrying a fabricated value is worse than a
            # refusal.
            #
            # So a change is kept only if it leaves the crate no worse: the
            # targeted violation gone, and nothing new appearing that was not
            # there before.
            after = self.rules.validate(candidate, contract)
            if self._value_still_faulted(after, violation):
                continue
            if self._new_faults(before=report, after=after):
                continue

            changes.append(Change(
                node=violation.node,
                reads=violation.requirement.named_value
                or violation.requirement.property,
                before=violation.value,
                after=proposed,
                proposed_by=engine.name,
                confirmed_by=violation.requirement.name,
            ))
            working = candidate

        return working, tuple(changes), asked

    # ----------------------------------------------------------- writing

    @staticmethod
    def _new_faults(before, after) -> bool:
        """Did this change break something that was not broken before?"""
        was = {(v.requirement.name, v.node) for v in before.violations}
        now = {(v.requirement.name, v.node) for v in after.violations}
        return bool(now - was)

    @staticmethod
    def _reads(requirement) -> str:
        return requirement.named_value or requirement.property

    @classmethod
    def _value_still_faulted(cls, report, violation) -> bool:
        """Is anything still wrong with the value that was just written?

        Every requirement reading that value at that place has to be
        satisfied, not only the one being repaired. Checking only the one
        being repaired lets a model answer "the setting must be recorded"
        with a phrase that is not a permitted setting: the first requirement
        passes, the second still fails, the handover is refused, and an
        invented phrase has been written into the record anyway. A refusal
        carrying a fabricated value is worse than a refusal.
        """
        reads = cls._reads(violation.requirement)
        return any(
            v.node == violation.node and cls._reads(v.requirement) == reads
            for v in report.violations
        )

    def _write(self, crate: Crate, violation, value: str) -> Crate | None:
        """Write the value at the one place the rules named, or nothing."""
        entity = crate.get(violation.node)
        if entity is None:
            # The rules named somewhere that is not in the crate. Nothing can
            # be written there, and inventing the entity would be inventing
            # the thing it describes.
            return None

        requirement = violation.requirement
        updated = dict(entity)

        if requirement.property is not None:
            updated[requirement.property] = value
            return crate.with_entity(updated)

        # A named value hangs off the entity as a separate entity of its own.
        # Writing one means adding that entity and pointing at it.
        carrier_id = f"{violation.node}/recovered/{_slug(requirement.named_value)}"
        carrier = {
            "@id": carrier_id,
            "@type": "PropertyValue",
            "name": requirement.named_value,
            "value": value,
            "description": (
                "Recovered from the text of this record rather than stated "
                "outright. A value somebody wrote down and a value something "
                "read out of prose are not equally trustworthy."
            ),
        }
        references = list(_as_references(updated.get("additionalProperty")))
        if not any(r.get("@id") == carrier_id for r in references):
            references.append({"@id": carrier_id})
        updated["additionalProperty"] = references

        return crate.with_entities([carrier, updated])


def _as_references(value):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    out = []
    for item in value:
        if hasattr(item, "keys"):
            out.append(dict(item))
        elif isinstance(item, str):
            out.append({"@id": item})
    return out


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
