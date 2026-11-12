"""Ingredient 4 of the Architect: what happens next.

After every check the Architect has four moves and must pick one: GO_ON,
GO_BACK, ASK, STOP. This file is the whole policy and nothing else, because
this is the piece a group will want to argue about. You should be able to read
it, disagree with it, and change it without reading the rest of the system.

The shape of the policy is a short ordered list of rules. Each rule is a small
function that either claims the situation and returns a Decision, or returns
None and lets the next rule look. The reason the rule exists is written beside
it, in the `because` of the Decision it returns, so the reason ends up in the
ledger rather than only in this file.

What this file does not do:

  * It does not word the question. Deciding that a person is needed is routing;
    turning a finding into something a person can answer is Conversation's job
    (contract.py, part 3). An ASK from here carries the findings and says what
    the question is about, with `question=None` for Conversation to fill.
  * It does not validate. A sentinel already did; its answer arrives as
    `Checked`.
  * It does not touch the crate. GO_BACK says which phase runs again and what
    survives; Memory carries that out.

Standard library only. No network, no model, no I/O.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

if __package__:
    from .contract import (HANDOVERS, PHASES, Checked, Decision, Finding, Move,
                           Specification, Step, Verdict)
else:  # run directly: python3 architect/route.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from architect.contract import (HANDOVERS, PHASES, Checked, Decision,  # noqa: E402
                                    Finding, Move, Specification, Step, Verdict)


# --------------------------------------------------------------------------- #
#  The numbers, named, with the reason for each
# --------------------------------------------------------------------------- #

MAX_RERUNS_PER_FINDING: int = 1
"""How many times one phase may be sent back for the same finding code.

One. A phase that produced a bad package deserves exactly one honest second
attempt - the first run may have hit a transient fault, a half-written file, a
stale input. If the same code comes back from the same phase after that, the
phase is deterministic about this and re-running it a third time is a loop that
burns a researcher's afternoon while looking busy. One is the smallest number
that still allows a genuine retry.
"""

MAX_ASKS_PER_FINDING: int = 1
"""How many times the researcher may be asked about the same finding code.

One. The second time you ask the same question you are not asking, you are
stalling. If a finding survives a question that was already put to a person,
the run has nothing left to try by itself: STOP, and let whoever reads the
ledger decide with the whole picture in front of them.
"""

MAX_GO_BACKS_PER_RUN: int = 6
"""Total re-runs allowed in one run, across all phases and all codes.

Six: enough for each of the four phases to be sent back once with room for two
genuine retries, and small enough that a run which is thrashing between phases
with always-new finding codes - a case the per-finding guard above cannot see -
still ends rather than grinding. A run that hits this ceiling is not failing on
one defect; it is not converging, and that is a STOP.
"""


# --------------------------------------------------------------------------- #
#  Which findings a re-run can fix, and which need a person
# --------------------------------------------------------------------------- #

NEEDS_A_PERSON: frozenset[str] = frozenset({
    # A measurement nobody took. Running Test again does not make a reading
    # that was never recorded appear; it makes a different reading.
    "missing_quantity",
    "unusable_reading",
    # A sample or a file with no recorded origin. The data is either found
    # outside this system or the item is withdrawn. Both are human acts.
    "missing_file",
    "unaccounted_item",
    "unknown_design_item",
    "unsupported_recommendation",
    # The crate is telling the truth and the truth is inconvenient. Carrying on
    # anyway is a scientific choice, not a repair.
    "flagged_entity",
    "exceeds_stated_limit",
    # Either the crate changed after the checksum was taken or the checksum was
    # fabricated. Which of those it is cannot be decided from inside the run.
    "checksum_mismatch",
})

FIXABLE_BY_RERUN: frozenset[str] = frozenset({
    # Bookkeeping the producing phase owns and can redo with no new facts:
    # collisions, duplicates, dangling internal references, missing links
    # between things that are both already present.
    "double_booked_position",
    "double_booked_location",
    "duplicate_order_item",
    "duplicate_sample_id",
    "duplicate_recommendation_id",
    "duplicate_rank",
    "unbound_order_item",
    "missing_crate_entity",
    "missing_provenance",
    "broken_provenance_chain",
    "unaligned_key",
})

HINTS_THAT_MEAN_A_PERSON: tuple[str, ...] = (
    "cannot be supplied",
    "cannot create",
    "an agent cannot",
    "is reported as incomplete",
    "scientific choice",
)
"""Phrases in a contract's own `fix_hint` that say no re-run will help.

The code tables above are the fast path and cover the contracts as they stand.
A new contract will arrive with a code this file has never seen, and when it
does the decision should come from the prose a reviewer actually read, not from
a Python set only this file's author knows about. Same principle the sentinel
uses for auto-repair, different question.
"""

UNKNOWN_FINDINGS_GO_TO_A_PERSON: bool = True
"""What to do with a blocking finding this file cannot classify.

ASK. The two wrong answers are GO_ON, which carries a defect the validator
refused into the next phase, and GO_BACK, which guesses that a re-run helps and
may loop. Asking costs a researcher one minute and loses nothing.
"""


# --------------------------------------------------------------------------- #
#  Reading the history: what has already been tried
# --------------------------------------------------------------------------- #

RERUN_NOTE = "rerun:"   # rerun:<phase>:<code>  - this phase was sent back for this code
ASKED_NOTE = "asked:"   # asked:<code>          - a person was asked about this code
FLAG_NOTE = "flag:"     # flag:<code>           - this flag was shown to the researcher


def note_for(decision: Decision, checked: Checked) -> list[str]:
    """The notes the caller must record on the Step, so the guard can see them.

    The loop guard can only work if what was tried is written down. Rather than
    have the guard re-derive it by parsing prose, Route states it: whoever
    records the step copies these notes onto it verbatim. One function, so the
    writer and the reader of this convention cannot drift apart.
    """
    codes = sorted({f.code for f in checked.findings})
    if decision.move is Move.GO_BACK:
        return [f"{RERUN_NOTE}{decision.target_phase}:{c}" for c in codes]
    if decision.move is Move.ASK:
        return [f"{ASKED_NOTE}{c}" for c in codes]
    if decision.move is Move.GO_ON and checked.flags:
        # Going on with flags means the flags travelled. They are now seen.
        return [f"{FLAG_NOTE}{f.code}" for f in checked.flags]
    return []


def _notes(history: list[Step]) -> list[str]:
    return [n for step in history for n in step.notes]


def reruns_of(history: list[Step], phase: str, code: str) -> int:
    """How many times `phase` has already been sent back for `code`."""
    want = f"{RERUN_NOTE}{phase}:{code}"
    counted = sum(1 for n in _notes(history) if n == want)
    if counted:
        return counted
    # Fallback for a history recorded by something that did not use note_for:
    # Route always names the phase and the codes in `because`, so the decision
    # itself is still readable. Less exact than the note, better than blind.
    return sum(1 for step in history
               if step.decision is not None
               and step.decision.move is Move.GO_BACK
               and step.decision.target_phase == phase
               and code in step.decision.because)


def asks_about(history: list[Step], code: str) -> int:
    """How many times a person has already been asked about `code`."""
    want = f"{ASKED_NOTE}{code}"
    counted = sum(1 for n in _notes(history) if n == want)
    if counted:
        return counted
    return sum(1 for step in history
               if step.decision is not None
               and step.decision.move is Move.ASK
               and code in step.decision.because)


def total_go_backs(history: list[Step]) -> int:
    return sum(1 for step in history
               if step.decision is not None and step.decision.move is Move.GO_BACK)


def flag_is_new(history: list[Step], code: str) -> bool:
    """True if this flag code has never been put in front of the researcher."""
    if f"{FLAG_NOTE}{code}" in _notes(history):
        return False
    return asks_about(history, code) == 0


def producer_of(handover: str) -> str | None:
    """The phase whose package this handover checks.

    Named so that GO_BACK sends work to the phase that made the package and not
    to the beginning of the cycle. Re-running Design because Test produced a
    bad package would discard three phases of correct work.
    """
    for phase, name in HANDOVERS.items():
        if name == handover:
            return phase
    return None


def needs_a_person(finding: Finding) -> bool:
    """Can any re-run of any phase fix this, or does it need a human act?"""
    if finding.code in NEEDS_A_PERSON:
        return True
    if finding.code in FIXABLE_BY_RERUN:
        return False
    hint = (finding.fix_hint or "").lower()
    if any(phrase in hint for phrase in HINTS_THAT_MEAN_A_PERSON):
        return True
    return UNKNOWN_FINDINGS_GO_TO_A_PERSON


# --------------------------------------------------------------------------- #
#  What survives a rewind
# --------------------------------------------------------------------------- #

@dataclass
class RewindPlan:
    """Which phase runs again, and what of the crate is still there afterwards.

    The rule, stated once: nothing is deleted. A rewind adds; it never removes.
    An earlier phase's record of what happened is not invalidated by a later
    phase failing - Build really did run, on that day, with those inputs - and
    deleting that record to make the crate look tidy would destroy the evidence
    that explains the failure. So the re-run writes a new package beside the old
    one, and the old one is marked superseded, with the finding that superseded
    it. Someone reading the crate afterwards can see both and see why.
    """
    target: str
    keeps: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    because: str = ""


def rewind_plan(decision: Decision, history: list[Step]) -> RewindPlan | None:
    """Work out the above for one GO_BACK decision."""
    if decision.move is not Move.GO_BACK or decision.target_phase is None:
        return None

    target = decision.target_phase
    order = list(PHASES)
    cut = order.index(target)

    return RewindPlan(
        target=target,
        # Phases before the target: untouched, and still valid inputs. Their
        # packages passed their own checks and nothing here says otherwise.
        keeps=order[:cut] + ["ledger", "graph", "crate history"],
        # The target's own previous package: kept, marked superseded, not
        # deleted. It is the thing the finding is about.
        supersedes=[f"{target} package"],
        # Phases after the target: their records stay - they happened - but
        # their packages are no longer anyone's input until they run again.
        # Stale, not gone. Removing them would hide a run that really occurred.
        stale=[p for p in order[cut + 1:] if _has_run(history, p)],
        because=("nothing is deleted on a rewind: earlier records stay valid, the "
                 "superseded package stays as evidence, later packages are marked "
                 "stale rather than removed"),
    )


def _has_run(history: list[Step], phase: str) -> bool:
    return any(step.phase == phase for step in history)


# --------------------------------------------------------------------------- #
#  The policy: an ordered list of rules, first match wins
# --------------------------------------------------------------------------- #

@dataclass
class Situation:
    """Everything a rule is allowed to look at, with the derived bits done once."""
    checked: Checked
    spec: Specification
    history: list[Step]

    @property
    def phase(self) -> str:
        return producer_of(self.checked.handover) or "design"

    @property
    def human(self) -> list[Finding]:
        return [f for f in self.checked.blocking if needs_a_person(f)]

    @property
    def rerunnable(self) -> list[Finding]:
        return [f for f in self.checked.blocking if not needs_a_person(f)]

    @property
    def looping(self) -> list[Finding]:
        return [f for f in self.rerunnable
                if reruns_of(self.history, self.phase, f.code) >= MAX_RERUNS_PER_FINDING]


# Quoted: a type alias is evaluated when the module loads, and `X | None`
# outside an annotation is only a type there from Python 3.10. Quoting it
# keeps this readable and keeps the module importable on older Pythons.
Rule = Callable[[Situation], "Decision | None"]


def _codes(findings: list[Finding]) -> str:
    return ", ".join(sorted({f.code for f in findings})) or "none"


def rule_accepted(s: Situation) -> Decision | None:
    """1. ACCEPTED: go on. The check is the authority and it said yes."""
    if s.checked.verdict is Verdict.ACCEPTED and not s.checked.findings:
        return Decision(move=Move.GO_ON, because=(
            f"{s.checked.handover} accepted with nothing to report; the next "
            f"phase may start"))
    return None


def rule_new_flag(s: Situation) -> Decision | None:
    """2. A flag the researcher has not seen before is worth asking about.

    A flag is not a defect - it is something true about the data that the next
    phase has to be told. Told to a machine, that is a field. The first time it
    reaches a person it is news, and a researcher who finds out at the end that
    every plate carried a flag nobody mentioned is right to be angry. Once
    seen, the same flag is not news again (rule 3).
    """
    if s.checked.verdict is not Verdict.ACCEPTED_WITH_FLAGS:
        return None
    new = [f for f in s.checked.flags if flag_is_new(s.history, f.code)]
    if not new:
        return None
    return Decision(move=Move.ASK, target_phase=s.phase, because=(
        f"{s.checked.handover} is valid and may go on, but carries flag(s) the "
        f"researcher has not seen before ({_codes(new)}); going on in silence "
        f"would be the Architect deciding something that is not its to decide. "
        f"The question itself is Conversation's to word."))


def rule_accepted_with_seen_flags(s: Situation) -> Decision | None:
    """3. ACCEPTED_WITH_FLAGS, all already seen: go on, and the flags travel.

    They travel in `because`, which goes into the ledger verbatim, so the next
    phase and anyone reading later receives what the package is carrying.
    """
    if s.checked.verdict is not Verdict.ACCEPTED_WITH_FLAGS:
        return None
    return Decision(move=Move.GO_ON, because=(
        f"{s.checked.handover} accepted with flag(s) {_codes(s.checked.flags)}, "
        f"all previously shown to the researcher; the next phase may start and "
        f"is told what it is receiving"))


def rule_refused_without_reason(s: Situation) -> Decision | None:
    """4. REFUSED with no blocking finding: ask, because it cannot be acted on.

    Nothing to re-run and nothing to fix, only a refusal. Rather than guess,
    put the sentinel's trace in front of a person. This should never fire; if it
    does, something upstream is broken and quiet is the worst response.
    """
    if s.checked.verdict is not Verdict.REFUSED or s.checked.blocking:
        return None
    return Decision(move=Move.ASK, target_phase=s.phase, because=(
        f"{s.checked.handover} was refused but reported no blocking finding, so "
        f"there is nothing to send back and nothing to repair; a person has to "
        f"read the sentinel's trace"))


def rule_exhausted(s: Situation) -> Decision | None:
    """5. Already asked about this and it is still here: stop.

    Before STOP: the same code has come back after a person was asked about it
    MAX_ASKS_PER_FINDING times. Asking again is a stall, and re-running is a
    loop. The honest outcome is to end the run with the reason recorded.
    """
    if s.checked.verdict is not Verdict.REFUSED:
        return None
    stuck = [f for f in s.checked.blocking
             if asks_about(s.history, f.code) >= MAX_ASKS_PER_FINDING]
    if not stuck:
        return None
    return Decision(move=Move.STOP, target_phase=s.phase, because=(
        f"{_codes(stuck)} is still blocking {s.checked.handover} after the "
        f"researcher was already asked about it; asking the same question twice "
        f"is a stall and re-running is a loop, so the run ends here with the "
        f"finding recorded"))


def rule_out_of_budget(s: Situation) -> Decision | None:
    """6. The run has used its re-runs: stop.

    The per-finding guard cannot see a run that thrashes between phases with a
    new code each time. This ceiling can. Hitting it means the run is not
    converging, which is a different failure from any one defect.
    """
    if s.checked.verdict is not Verdict.REFUSED:
        return None
    if total_go_backs(s.history) < MAX_GO_BACKS_PER_RUN:
        return None
    return Decision(move=Move.STOP, target_phase=s.phase, because=(
        f"{MAX_GO_BACKS_PER_RUN} re-runs already used in this run and "
        f"{s.checked.handover} is still refused ({_codes(s.checked.blocking)}); "
        f"the run is not converging, so it ends here rather than grinding"))


def rule_needs_a_person(s: Situation) -> Decision | None:
    """7. REFUSED with a finding no re-run can fix: ask.

    A measurement nobody took, a sample with no recorded origin, a limit that
    can only be exceeded knowingly. Re-running the phase would produce the same
    gap, or worse, a different number. These need a person. What that person is
    asked is Conversation's job; this rule says only that an ASK is needed and
    what it is about.
    """
    if s.checked.verdict is not Verdict.REFUSED or not s.human:
        return None

    # Two ways to land here, and they are not the same thing to a reader of the
    # ledger: this file knows the finding needs a person, or this file does not
    # recognise the finding at all. Say which.
    known = [f for f in s.human
             if f.code in NEEDS_A_PERSON
             or any(p in (f.fix_hint or "").lower() for p in HINTS_THAT_MEAN_A_PERSON)]
    unknown = [f for f in s.human if f not in known]

    parts: list[str] = []
    if known:
        parts.append(
            f"{_codes(known)}, which no re-run of {s.phase} can fix - the data "
            f"was never recorded, or carrying on is a scientific choice")
    if unknown:
        parts.append(
            f"{_codes(unknown)}, which this policy does not classify, so it goes "
            f"to a person rather than past one")

    return Decision(move=Move.ASK, target_phase=s.phase, because=(
        f"{s.checked.handover} refused on " + "; and on ".join(parts)
        + ". A person has to decide; Conversation words the question"))


def rule_loop(s: Situation) -> Decision | None:
    """8. The same phase, the same code, again: do not send it back.

    This is the loop guard. `MAX_RERUNS_PER_FINDING` re-runs have already been
    spent on this exact code in this exact phase and it is back, so the phase is
    deterministic about it and a third attempt changes nothing. The honest move
    is to ask - the researcher has not been asked yet, or rule 5 would have
    stopped the run - and if nobody can be asked, rule 5 ends it next time.
    """
    if s.checked.verdict is not Verdict.REFUSED or not s.looping:
        return None
    return Decision(move=Move.ASK, target_phase=s.phase, because=(
        f"{s.phase} has already been re-run {MAX_RERUNS_PER_FINDING}x for "
        f"{_codes(s.looping)} and the same finding came back; sending it back "
        f"again is a loop, not progress, so a person is asked instead"))


def rule_go_back(s: Situation) -> Decision | None:
    """9. REFUSED, fixable by running again, not yet tried: go back.

    To the phase that produced the package, named, not to the beginning. The
    other three phases did their work and their records stand (see RewindPlan).
    """
    if s.checked.verdict is not Verdict.REFUSED or not s.rerunnable:
        return None
    return Decision(move=Move.GO_BACK, target_phase=s.phase, because=(
        f"{s.checked.handover} refused on {_codes(s.rerunnable)}, which {s.phase} "
        f"can fix by running again with no new facts; {s.phase} runs again "
        f"(attempt {reruns_of(s.history, s.phase, s.rerunnable[0].code) + 2}), "
        f"the earlier phases are untouched"))


def rule_last_resort(s: Situation) -> Decision | None:
    """10. Anything this file did not foresee: ask.

    A policy with no last rule falls through to whatever the caller does with
    None, which is the one outcome nobody designed. This rule exists so that
    `decide` always returns a Decision.
    """
    return Decision(move=Move.ASK, target_phase=s.phase, because=(
        f"{s.checked.handover} returned {s.checked.verdict.value} with "
        f"{_codes(s.checked.findings)}, which this policy does not classify; "
        f"an unclassified result goes to a person rather than past one"))


POLICY: tuple[Rule, ...] = (
    rule_accepted,                   # 1  accepted -> go on
    rule_new_flag,                   # 2  unseen flag -> ask
    rule_accepted_with_seen_flags,   # 3  seen flags -> go on, flags travel
    rule_refused_without_reason,     # 4  refused, no finding -> ask
    rule_exhausted,                  # 5  already asked, still here -> stop
    rule_out_of_budget,              # 6  run out of re-runs -> stop
    rule_needs_a_person,             # 7  no re-run can fix it -> ask
    rule_loop,                       # 8  same phase, same code again -> ask
    rule_go_back,                    # 9  a re-run can fix it -> go back
    rule_last_resort,                # 10 anything else -> ask
)


# --------------------------------------------------------------------------- #
#  The Route implementation
# --------------------------------------------------------------------------- #

class Policy:
    """Implements contract.Route. The policy is POLICY above; this just runs it.

    Stateless on purpose: everything it knows about what has been tried comes
    from `history`, which is the thing the ledger already persists. Two Policy
    objects given the same history decide the same way, and a run can be
    replayed from its ledger to see why it went where it went.
    """

    name = "route"
    rules: tuple[Rule, ...] = POLICY

    def decide(self, checked: Checked, spec: Specification,
               history: list[Step]) -> Decision:
        situation = Situation(checked=checked, spec=spec, history=list(history))
        for rule in self.rules:
            decision = rule(situation)
            if decision is not None:
                return decision
        # rule_last_resort always returns, so this is unreachable unless someone
        # replaces `rules` with a list that can fall through. Say so loudly.
        raise AssertionError(
            "the rule list fell through: every policy needs a last rule that "
            "always decides, or the caller is handed the one outcome nobody "
            "designed")

    def rewind_to(self, decision: Decision, history: list[Step]) -> str | None:
        """Which phase runs again. None for any move that is not GO_BACK.

        What survives is not a side question, so it has a value of its own:
        `rewind_plan(decision, history)` returns the same target plus what is
        kept, what is superseded and what is stale. The rule, in one line:
        nothing is deleted - an earlier phase's record of what happened is not
        invalidated by a later phase failing, and deleting it would destroy the
        evidence that explains the failure.
        """
        plan = rewind_plan(decision, history)
        return plan.target if plan else None


# --------------------------------------------------------------------------- #
#  Run the policy over a scripted sequence
# --------------------------------------------------------------------------- #

if __name__ == "__main__":

    @dataclass
    class _Spec:
        """The smallest thing that satisfies contract.Specification, for the demo."""
        agreed: dict = field(default_factory=lambda: {"target": "demo"})
        limits: list[dict] = field(default_factory=list)

        def requirements_for(self, phase: str) -> dict: return {}
        def limits_for(self, phase: str) -> list[dict]: return []
        def unresolved(self) -> list[str]: return []

    def f(code: str, *, blocking: bool = True, hint: str = "") -> Finding:
        return Finding(code=code, path=f"/{code}", message=code.replace("_", " "),
                       blocking=blocking, fix_hint=hint)

    script: list[tuple[str, Checked]] = [
        ("clean design handover",
         Checked("design_to_build", Verdict.ACCEPTED)),

        ("build flags a sample the crate already doubted",
         Checked("build_to_test", Verdict.ACCEPTED_WITH_FLAGS,
                 [f("flagged_entity", blocking=False)])),

        ("the same flag, second time round",
         Checked("build_to_test", Verdict.ACCEPTED_WITH_FLAGS,
                 [f("flagged_entity", blocking=False)])),

        ("design double-books a plate position",
         Checked("design_to_build", Verdict.REFUSED,
                 [f("double_booked_position")])),

        ("design double-books it again - this is the loop",
         Checked("design_to_build", Verdict.REFUSED,
                 [f("double_booked_position")])),

        ("and a third time, after a person was already asked",
         Checked("design_to_build", Verdict.REFUSED,
                 [f("double_booked_position")])),

        ("test has no reading for a well",
         Checked("test_to_learn", Verdict.REFUSED,
                 [f("missing_quantity",
                    hint="not auto-fixable: a measurement that was never taken "
                         "cannot be supplied")])),

        ("learn refuses with a code this file has never seen",
         Checked("learn_to_design", Verdict.REFUSED,
                 [f("some_future_contract_code")])),

        ("build refuses with nothing to show for it",
         Checked("build_to_test", Verdict.REFUSED)),
    ]

    route = Policy()
    spec = _Spec()
    history: list[Step] = []

    print("Route policy over a scripted run")
    print("=" * 78)

    for n, (label, checked) in enumerate(script, start=1):
        decision = route.decide(checked, spec, history)
        target = route.rewind_to(decision, history)

        print(f"\n{n}. {label}")
        print(f"   check    {checked.handover} -> {checked.verdict.value}"
              + (f" [{_codes(checked.findings)}]" if checked.findings else ""))
        print(f"   move     {decision.move.value.upper()}"
              + (f" -> {decision.target_phase}"
                 if decision.target_phase and decision.move is not Move.GO_ON else ""))
        print(f"   because  {decision.because}")

        if target:
            plan = rewind_plan(decision, history)
            assert plan is not None
            print(f"   rewind   {plan.target} runs again")
            print(f"   keeps    {', '.join(plan.keeps)}")
            print(f"   marks    {', '.join(plan.supersedes)} superseded"
                  + (f"; {', '.join(plan.stale)} stale" if plan.stale else ""))
            print(f"   rule     {plan.because}")

        history.append(Step(
            phase=producer_of(checked.handover) or "design",
            actor="sentinel", verdict=checked.verdict, decision=decision,
            at=f"t{n}", notes=note_for(decision, checked),
        ))

    # The three things the demo is here to prove.
    moves = [step.decision.move for step in history if step.decision]
    assert moves[0] is Move.GO_ON, "a clean handover goes on"
    assert moves[1] is Move.ASK, "an unseen flag is asked about"
    assert moves[2] is Move.GO_ON, "a flag already seen is not news again"
    assert moves[3] is Move.GO_BACK, "a re-runnable finding goes back once"
    assert moves[4] is Move.ASK, "the repeat is caught as a loop, not sent back"
    assert moves[5] is Move.STOP, "asked and still here: the run ends"
    assert moves[6] is Move.ASK, "a measurement nobody took needs a person"
    assert moves[7] is Move.ASK, "an unclassified finding goes to a person"
    assert moves[8] is Move.ASK, "a refusal with no finding cannot be acted on"
    assert Move.STOP in moves, "STOP is reachable"

    print("\n" + "=" * 78)
    print("9 decisions: "
          + ", ".join(m.value for m in moves))
    print("loop caught at step 5, run stopped at step 6. Policy held.")
