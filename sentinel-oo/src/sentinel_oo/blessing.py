"""The record that gets written into the returned crate.

A blessing is pure data. It holds what was checked, against which rules, by
which build of this service, with which model, and what was found. Turning it
into crate entities is the provenance writer's job, not this module's: a value
object that knows how to write itself into a particular shape of record stops
being a value object the first time the shape changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .identity import BuildIdentity


class Verdict(str, Enum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_FLAGS = "ACCEPTED_WITH_FLAGS"
    REFUSED = "REFUSED"


class ContractSource(str, Enum):
    """Where the rules came from.

    "Checked against the published rules" and "checked against rules the sender
    supplied" are different claims about a crate, and they must not look alike
    to anybody reading the record afterwards.
    """

    REGISTRY = "registry"
    SUPPLIED_BY_REQUESTER = "supplied by requester"
    NONE = "none"


NO_ENGINE = "none"


@dataclass(frozen=True)
class Blessing:
    """What this service did to one crate, on one run."""

    run_id: str
    build: BuildIdentity
    input_checksum: str
    started: str
    ended: str

    contract_name: str | None = None
    contract_version: str | None = None
    contract_checksum: str | None = None
    contract_source: ContractSource = ContractSource.NONE
    engine_used: str = NO_ENGINE

    # What actually happened with the model, which is three separate facts.
    #
    # Before 12 November 2026 the record carried only the engine's name, and
    # wrote it whether the model had answered, had never been asked, or could
    # not be reached. A crate refused on a repairable requirement, with no
    # model anywhere, carried "model engine: qwen2.5:14b at
    # http://model:11434" and "0 change(s)". Anybody reading that later would
    # conclude a model looked for the value and found nothing. No model was
    # reached and the sentence holding the value was never read.
    #
    # The record is the thing this service exists to produce and the thing
    # people are asked to trust. It must not say that.
    #
    # Reachable and asked are different. A model can be there and never asked,
    # because no failing requirement was marked repairable, and that is a
    # perfectly good run.
    model_reachable: bool | None = None
    model_asked: int = 0
    model_unreachable_detail: str | None = None

    # None means nothing was checked, which is not the same as being accepted.
    # Step 1 of the build order has no rules at all, so every blessing it writes
    # carries None here. Anything that reports a verdict must get it from a
    # report produced by the rule engine, never from this class.
    verdict: Verdict | None = None

    # Every violation the rule engine reported, blocking and flagged alike.
    # Held so the record can name what failed, never so that anything can
    # work the verdict out again from them.
    violations: tuple = field(default_factory=tuple)
    changes: tuple = field(default_factory=tuple)

    def facts(self) -> list[tuple[str, str]]:
        """The record as name and value pairs, in a fixed order.

        Fixed order so that two runs that did the same thing produce records
        that can be compared line by line.
        """
        return [
            ("run identifier", self.run_id),
            ("contract", self.contract_name or "none applied"),
            ("contract version", self.contract_version or "none applied"),
            ("contract checksum", self.contract_checksum or "none applied"),
            ("contract source", self.contract_source.value),
            ("service image tag", self.build.image_tag),
            ("service commit", self.build.git_commit),
            ("rules checksum", self.build.rules_checksum),
            ("model", self.model_text()),
            ("checksum of the crate as received", self.input_checksum),
        ]

    def model_text(self) -> str:
        """What happened with the model, as one line a person can read.

        Four cases, and the fourth is the one the old record could not say.
        """
        if self.engine_used == NO_ENGINE:
            return "none configured"

        if self.model_reachable is False:
            detail = self.model_unreachable_detail or "no reason recorded"
            return (
                f"{self.engine_used}, NOT REACHED: {detail}. "
                "No value was recovered from free text, and nothing it "
                "might have found is in this record"
            )

        if self.model_asked == 0:
            return (
                f"{self.engine_used}, reachable, not asked: no failing "
                "requirement was marked repairable"
            )

        kept = len(self.changes)
        times = "once" if self.model_asked == 1 else f"{self.model_asked} times"
        return (
            f"{self.engine_used}, reachable, asked {times}, "
            f"{kept} change(s) kept"
        )

    def verdict_text(self) -> str:
        if self.verdict is None:
            return "NOT CHECKED: no contract was applied to this crate"
        return self.verdict.value
