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
            ("model engine", self.engine_used),
            ("checksum of the crate as received", self.input_checksum),
        ]

    def verdict_text(self) -> str:
        if self.verdict is None:
            return "NOT CHECKED: no contract was applied to this crate"
        return self.verdict.value
