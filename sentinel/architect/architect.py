#!/usr/bin/env python3
"""The Architect: the five parts, wired together.

    python3 architect/architect.py

The agreed picture has eight agents around a centre. Four do the work and may
be people rather than programs. Four check what the first four produced and
may refuse it. The Architect is the centre, and it does neither job: it talks
with the researcher, holds what was agreed, decides what happens after each
verdict, and keeps the one crate that grows.

This file is deliberately thin. Every decision it makes is made somewhere
else, and it says which:

    consultation   getting to a first design, with the researcher
    specification  what was agreed, and what the process requires regardless
    conversation   what to say when a check fails
    route          go on, go back, ask, stop
    memory         the crate that grows, including one it adopted

If a question about behaviour can be answered by reading this file, something
has leaked into it that belongs in one of the five.

WHAT THIS IS NOT, YET
It runs the loop and it records what happened. It does not start a phase agent
by itself - `run_phase` takes a callable, and in a real deployment that
callable is a phase agent, a container, or an email to a person. Keeping that
seam explicit is the point: a phase agent may be a human workflow, and a
centre that can only call Python functions cannot admit one.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from architect.contract import (Answer, Checked, Decision, Finding,  # noqa: E402
                                Move, PHASES, Question, Step, Verdict)
from architect.consultation import ArchitectConsultation              # noqa: E402
from architect.conversation import ArchitectConversation              # noqa: E402
from architect.memory import Memory                                   # noqa: E402
from architect.route import Policy, note_for                          # noqa: E402

HANDOVER_OF = {"design": "design_to_build", "build": "build_to_test",
               "test": "test_to_learn", "learn": "learn_to_design"}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
#  What a phase hands back
# --------------------------------------------------------------------------- #
@dataclass
class PhaseResult:
    """What running one phase produced, however it was run.

    `entities` and `action` go into the crate. `package` is what the sentinel
    will check. A phase run by a person fills the same fields - that is the
    whole reason this is a plain dataclass and not an agent interface.
    """
    entities: list[dict] = field(default_factory=list)
    action: dict | None = None
    package: dict | None = None
    by: str = "unknown"
    notes: list[str] = field(default_factory=list)


Runner = Callable[[str, "Architect"], PhaseResult]
Checker = Callable[[str, dict, "Architect"], Checked]


# --------------------------------------------------------------------------- #
class Architect:
    """Holds the five parts. Owns the loop and the ledger, and nothing else."""

    def __init__(self, run_id: str, *, researcher: str = "researcher",
                 root: Path | str | None = None):
        self.run_id = run_id
        self.researcher = researcher
        self.consultation = ArchitectConsultation(researcher=researcher)
        self.conversation = ArchitectConversation()
        self.policy = Policy()
        self.memory = Memory(run_id, root=root)
        self.spec: Any = None
        self.history: list[Step] = []
        self.open_questions: list[Question] = []
        self.ledger: list[dict] = []

    # ---- 1. agreeing what to do -------------------------------------------
    def consult(self, *, objective: str | None = None,
                workflow: dict | str | None = None) -> list[Question]:
        """Open the conversation, and return what still has to be decided."""
        self.spec = self.consultation.open(objective=objective, workflow=workflow)
        questions = self.consultation.propose_changes(self.spec)
        self.open_questions = list(questions)
        self._record("consult", actor=self.researcher,
                     notes=[f"{len(questions)} question(s) outstanding"]
                           + [f"unresolved: {u}" for u in self._unresolved()[:4]])
        return questions

    def answer(self, answers: list[Answer]) -> None:
        self.spec = self.consultation.apply(self.spec, answers)
        self.open_questions = self.consultation.propose_changes(self.spec)
        self._record("consult", actor=self.researcher,
                     notes=[f"{len(answers)} answer(s) applied",
                            f"{len(self.open_questions)} still open"])

    # ---- 2. adopting a crate somebody else wrote --------------------------
    def adopt(self, crate: dict | str):
        """Continue from a crate that already exists. Reports what it took on."""
        adoption = self.memory.adopt(crate)
        self._record("memory", actor="architect",
                     notes=[str(adoption)] if adoption else ["adopted"])
        return adoption

    # ---- 3. one phase, then its check -------------------------------------
    def run_phase(self, phase: str, runner: Runner, checker: Checker | None = None
                  ) -> Decision:
        """Run one phase, record what it made, have it checked, decide.

        `runner` is whatever actually does the work: a phase agent, a shell
        command, a person who was emailed and typed the answer back. The
        Architect does not care, and must not.
        """
        if phase not in PHASES:
            raise ValueError(f"{phase!r} is not one of {PHASES}")

        result = runner(phase, self)
        if result.entities or result.action:
            report = self.memory.record(phase, result.entities, result.action)
            if report is not None and not getattr(report, "ok", True):
                # The crate refused the addition. That is not a failed check -
                # it is two phases disagreeing about what happened, or a join
                # to nothing, and no contract can settle either.
                decision = Decision(
                    move=Move.ASK, target_phase=phase,
                    because=f"the crate refused what {phase} wrote: "
                            f"{report.summary()}. A contract cannot settle this")
                self._step(phase, result.by, None, decision,
                           notes=[str(report.summary())])
                return decision

        if result.package is None or checker is None:
            decision = Decision(move=Move.GO_ON, target_phase=phase,
                                because=f"{phase} produced no package to check")
            self._step(phase, result.by, None, decision, notes=result.notes)
            return decision

        checked = checker(HANDOVER_OF[phase], result.package, self)
        decision = self.policy.decide(checked, self.spec, self.history)

        # The question is Conversation's to word, not the policy's.
        if decision.move is Move.ASK and decision.question is None:
            decision.question = self.conversation.explain(checked, self.spec)
            self.open_questions.append(decision.question)

        self._step(phase, result.by, checked.verdict, decision,
                   notes=result.notes + note_for(decision, checked))
        return decision

    # ---- 4. what it would say, unprompted ---------------------------------
    def advice(self) -> list[str]:
        return self.conversation.advise(self.spec, self.history)

    # ---- the record --------------------------------------------------------
    def _step(self, phase: str, actor: str, verdict: Verdict | None,
              decision: Decision, notes: list[str] | None = None) -> None:
        step = Step(phase=phase, actor=actor, verdict=verdict,
                    decision=decision, at=now(), notes=list(notes or []))
        self.history.append(step)
        self._record(phase, actor=actor, verdict=verdict, decision=decision,
                     notes=step.notes)

    def _record(self, phase: str, *, actor: str, verdict: Verdict | None = None,
                decision: Decision | None = None,
                notes: list[str] | None = None) -> None:
        self.ledger.append({
            "at": now(), "run_id": self.run_id, "phase": phase, "actor": actor,
            "verdict": verdict.value if verdict else None,
            "move": decision.move.value if decision else None,
            "target": decision.target_phase if decision else None,
            "because": decision.because if decision else "",
            "notes": list(notes or []),
        })

    def _unresolved(self) -> list[str]:
        try:
            return list(self.spec.unresolved())
        except Exception:
            return []

    def write_ledger(self, path: Path | str | None = None) -> str:
        path = Path(path or (ROOT / "runs" / self.run_id / "architect.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as handle:
            for row in self.ledger:
                handle.write(json.dumps(row) + "\n")
        return str(path)

    def summary(self) -> str:
        moves = [r["move"] for r in self.ledger if r["move"]]
        return (f"{self.run_id}: {len(self.history)} step(s), "
                f"moves {', '.join(moves) or 'none'}, "
                f"{len(self.open_questions)} open question(s), "
                f"crate {len(self.memory.snapshot().get('@graph', []))} entities")


# --------------------------------------------------------------------------- #
#  A demonstration with no real phase agents, so the loop is visible
# --------------------------------------------------------------------------- #
def _rule(title: str) -> None:
    print(f"\n{'=' * 76}\n{title}\n{'=' * 76}")


def _scripted_runner(phase: str, arch: "Architect") -> PhaseResult:
    """Stands in for a phase agent. In a real run this is one, or a person."""
    made = {"design": ("#candidate/C1", "bioschemas:Protein"),
            "build": ("#sample/S1", "bioschemas:BioSample"),
            "test": ("#reading/R1", "dbtl:Reading"),
            "learn": ("#recommendation/REC-001", "dbtl:Recommendation")}[phase]
    return PhaseResult(
        entities=[{"@id": made[0], "@type": made[1], "name": f"{phase} output"}],
        action={"@id": f"#action/{phase}", "@type": "CreateAction",
                "name": f"the {phase} phase ran", "result": [{"@id": made[0]}]},
        package={"contract": HANDOVER_OF[phase]},
        by=f"phase agent ({phase})",
        notes=[f"{phase} produced 1 entity"])


def _scripted_checker(script: list[Checked]):
    """Stands in for the four sentinels, so the loop can be seen end to end."""
    queue = list(script)

    def check(handover: str, package: dict, arch: "Architect") -> Checked:
        return queue.pop(0) if queue else Checked(handover, Verdict.ACCEPTED)
    return check


def main() -> None:
    import shutil
    shutil.rmtree(ROOT / "runs" / "architect-demo", ignore_errors=True)
    arch = Architect("architect-demo", researcher="Marco")

    _rule("1. THE ARCHITECT OPENS THE CONVERSATION")
    questions = arch.consult(objective="find thermostable ene-reductases "
                                       "in hot spring sediment")
    print(f"\n  {len(questions)} question(s). The first two, in order of consequence:\n")
    for q in questions[:2]:
        print(f"    {q.headline}")
        for option in q.options[:3]:
            mark = " (recommended)" if option == q.recommended else ""
            print(f"       - {option}{mark}")
        if q.because:
            print(f"       why it is asked first: {q.because[:96]}")
        print()

    _rule("2. THE CYCLE, WITH THE VERDICTS SCRIPTED")
    script = [
        Checked("design_to_build", Verdict.ACCEPTED),
        Checked("build_to_test", Verdict.REFUSED, findings=[
            Finding("double_booked_location", "samples[3].location",
                    "two samples claim the same well", blocking=True,
                    fix_hint="not auto-fixable: re-read the liquid handler worklist")]),
        Checked("build_to_test", Verdict.ACCEPTED_WITH_FLAGS, findings=[
            Finding("flagged_entity", "bindings[2]", "ENR-003 is a right partial",
                    blocking=False)]),
        Checked("test_to_learn", Verdict.REFUSED, findings=[
            Finding("missing_quantity", "results[1].measurements",
                    "the profile requires blank_corrected_absorbance", blocking=True,
                    fix_hint="not auto-fixable: a measurement nobody took")]),
    ]
    check = _scripted_checker(script)

    for phase in ("design", "build", "build", "test"):
        decision = arch.run_phase(phase, _scripted_runner, check)
        print(f"\n  {phase:<6} -> {decision.move.value.upper()}"
              + (f" ({decision.target_phase})" if decision.target_phase else ""))
        print(f"         {decision.because[:150]}")
        if decision.question is not None:
            print(f"         asks: {decision.question.headline[:120]}")

    _rule("3. WHAT IT WOULD SAY WITHOUT BEING ASKED")
    advice = arch.advice()
    print()
    for line in advice or ["  (nothing: silence is a valid answer)"]:
        print(f"  {line}")

    _rule("4. THE RECORD")
    print(f"\n  {arch.summary()}")
    print(f"  ledger: {arch.write_ledger()}")
    print(f"""
  Every decision above was made somewhere else. The Architect chose nothing:
  route.py decided the move and wrote the reason, conversation.py worded the
  question, specification.py said what was agreed and what cannot be, and the
  crate store refused what it had to. This file ran the loop and wrote it down.
""")


if __name__ == "__main__":
    main()
