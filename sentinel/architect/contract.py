"""The seams between the Architect's five parts.

Nothing here does any work. It fixes the shape of the five pieces so they can
be written separately and still fit together, which is the only reason this
file exists before the others.

The Architect is the centre of the agreed picture: eight agents around it,
four that do the work and four that check it, a researcher it talks with, and
one crate that grows. It owns five things and no more:

    1. Consultation   helping the researcher arrive at a first design, or
                      taking the workflow they already have and reshaping it
    2. Specification  what was agreed, plus what the whole process requires
    3. Conversation   what to say when a check fails, or when it is unsure
    4. Route          what happens next: go on, go back, ask
    5. Memory         the crate that grows, and the graph over it

Everything else it delegates. It does not validate - a sentinel does. It does
not do science - a phase agent does, and that agent may be a person.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


# --------------------------------------------------------------------------- #
#  Shared vocabulary
# --------------------------------------------------------------------------- #
class Verdict(str, Enum):
    """What a sentinel decided. The three the group has converged on."""
    ACCEPTED = "accepted"
    ACCEPTED_WITH_FLAGS = "accepted_with_flags"
    REFUSED = "refused"


class Move(str, Enum):
    """What the Architect decided to do about it."""
    GO_ON = "go_on"          # the next phase may start
    GO_BACK = "go_back"      # an earlier phase runs again
    ASK = "ask"              # the researcher has to decide
    STOP = "stop"            # the run ends here


PHASES = ("design", "build", "test", "learn")
HANDOVERS = {"design": "design_to_build", "build": "build_to_test",
             "test": "test_to_learn", "learn": "learn_to_design"}


@dataclass
class Finding:
    """One thing a sentinel reported, in the Architect's own terms."""
    code: str
    path: str
    message: str
    blocking: bool
    fix_hint: str = ""


@dataclass
class Checked:
    """A sentinel's answer about one handover."""
    handover: str
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def flags(self) -> list[Finding]:
        return [f for f in self.findings if not f.blocking]


@dataclass
class Question:
    """Something put to the researcher. Never rhetorical: every option is one
    the Architect is able to carry out."""
    asked_by: str
    headline: str
    detail: str
    options: list[str]
    recommended: str | None = None
    because: str = ""


@dataclass
class Answer:
    chosen: str
    note: str = ""


@dataclass
class Decision:
    """What the Architect decided, and why. Goes into the ledger verbatim."""
    move: Move
    target_phase: str | None = None
    because: str = ""
    question: Question | None = None


# --------------------------------------------------------------------------- #
#  The five parts
# --------------------------------------------------------------------------- #
class Consultation(Protocol):
    """1. Getting to a first design, with the researcher in the room.

    Two ways in, and both have to work. Either the researcher has nothing and
    is helped to a first specification, or they already have a workflow and it
    is read, explained back to them, and offered with changes. The second is
    not a lesser case: most groups already have a protocol, and a system that
    only works for people starting from nothing is a system nobody starts.
    """

    def open(self, *, objective: str | None = None,
             workflow: dict | str | None = None) -> "Specification": ...

    def propose_changes(self, spec: "Specification") -> list[Question]:
        """What the Architect would change, as questions rather than edits."""

    def apply(self, spec: "Specification", answers: list[Answer]) -> "Specification": ...


class Specification(Protocol):
    """2. What was agreed, and what the process requires regardless.

    Two kinds of statement live here and must not be confused. What the
    researcher decided - the target, the equipment on hand, the budget - and
    what the process requires of anybody, which they did not decide and cannot
    waive. A specification that cannot tell the two apart will let somebody
    negotiate away a requirement by accident.
    """

    agreed: dict[str, Any]
    limits: list[dict]

    def requirements_for(self, phase: str) -> dict: ...
    def limits_for(self, phase: str) -> list[dict]: ...
    def unresolved(self) -> list[str]:
        """What still has no answer. A run may start anyway; it may not finish."""


class Conversation(Protocol):
    """3. What to say when a check fails, or when the Architect is unsure.

    The hard part is not detecting the failure, which the sentinel already did.
    It is turning a finding into something a person can decide about: what
    happened, what it costs, and the two or three things that can be done -
    each one a thing the Architect can actually carry out.
    """

    def explain(self, checked: Checked, spec: Specification) -> Question: ...
    def advise(self, spec: Specification, history: list["Step"]) -> list[str]:
        """Unprompted observations. Silence is a valid answer."""


class Route(Protocol):
    """4. Going on, going back, or asking.

    The policy, separated from everything else on purpose: this is the one
    piece a group will want to argue about and change, and it should be
    readable without reading anything else.
    """

    def decide(self, checked: Checked, spec: Specification,
               history: list["Step"]) -> Decision: ...

    def rewind_to(self, decision: Decision, history: list["Step"]) -> str | None:
        """Which phase runs again, and what of the crate survives."""


class Memory(Protocol):
    """5. The crate that grows, and the graph over it.

    It may be a crate this system created, or one that already existed and was
    handed to it. Both have to work: a use case with its own crate is not going
    to adopt a new one to be allowed to use this.
    """

    def adopt(self, crate: dict | str) -> None:
        """Take an existing crate as the starting point."""

    def record(self, phase: str, entities: list[dict], action: dict | None = None): ...
    def snapshot(self) -> dict: ...
    def ask(self, entity: str) -> list[dict]:
        """Walk back from one thing to where it came from."""


@dataclass
class Step:
    """One thing that happened, as the Architect will recount it later."""
    phase: str
    actor: str
    verdict: Verdict | None = None
    decision: Decision | None = None
    at: str = ""
    notes: list[str] = field(default_factory=list)
