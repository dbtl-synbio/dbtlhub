#!/usr/bin/env python3
"""Putting the Architect's questions in front of a person.

    python3 architect/interface.py

The Architect produces `Question` objects and consumes `Answer` objects as
plain values. This is the thin layer that shows one to a researcher and reads
the other back. It is a terminal, because a terminal needs nothing installed
and the architecture does not depend on which surface is used.

Two rules it will not bend.

**Nothing is ever answered on the researcher's behalf.** There is no default
on Enter, and a recommendation is shown and still has to be chosen. A system
that accepts silence as agreement produces a record of decisions nobody made.

**An answer that cannot be read is never guessed at.** `Answer.chosen` must
carry the option's exact text, because that is what `consultation.apply`
matches on; a near miss mapped onto the wrong option is worse than asking
again.

Three ways out are always available and are not options in the list, because
they are not things the Architect would carry out - they are things the
researcher does about the question itself:

    why     say more, then ask again
    skip    leave it unresolved, and record that it was skipped
    stop    end the run here
"""
from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from architect.contract import (Answer, Checked, Decision, Move,       # noqa: E402
                                Question, Verdict)

SKIPPED = "__skipped__"
STOPPED = "__stopped__"
WAYS_OUT = {"why", "skip", "stop"}


class Stopped(Exception):
    """The researcher ended the run. Not an error: an answer."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wrap(text: str, indent: str = "    ") -> str:
    return "\n".join(textwrap.fill(line, width=76,
                                   initial_indent=indent,
                                   subsequent_indent=indent)
                     for line in text.splitlines() if line.strip())


@dataclass
class Exchange:
    """One thing asked and what came back, so a run can be written up later."""
    at: str
    asked_by: str
    headline: str
    options: list[str]
    recommended: str | None
    answered: str
    attempts: int = 1
    note: str = ""

    def as_dict(self) -> dict:
        return {"at": self.at, "asked_by": self.asked_by,
                "headline": self.headline, "options": list(self.options),
                "recommended": self.recommended, "answered": self.answered,
                "attempts": self.attempts, "note": self.note}


class Interface:
    """A terminal in front of the Architect.

    `input_fn` and `output_fn` are injected so the whole thing can be driven
    from a list of strings with no terminal at all. That matters more than any
    interactive polish: an interface that cannot be scripted cannot be tested,
    and an untested interface is where a system quietly starts answering for
    people.
    """

    def __init__(self, input_fn: Callable[[str], str] = input,
                 output_fn: Callable[[str], None] = print,
                 researcher: str = "researcher"):
        self._in = input_fn
        self._out = output_fn
        self.researcher = researcher
        self._log: list[Exchange] = []
        self._greeted = False

    # ---- asking ------------------------------------------------------------
    def ask(self, question: Question) -> Answer:
        """Put one question. Returns the researcher's own words, not a guess."""
        self._greet()
        attempts = 0
        self._show_question(question)

        while True:
            attempts += 1
            raw = self._in("  > ").strip()
            word = raw.lower()

            if word == "stop":
                self._record(question, STOPPED, attempts, "ended the run")
                raise Stopped(f"stopped at: {question.headline}")

            if word == "skip":
                self._record(question, SKIPPED, attempts, "left unresolved")
                self._out("    left unresolved. It will show up in what still "
                          "has no answer.\n")
                return Answer(chosen=SKIPPED, note="skipped")

            if word == "why":
                self._out(_wrap(question.because or
                                "No further reason was recorded for this one."))
                self._out("")
                self._show_question(question, repeat=True)
                continue

            chosen = self._match(raw, question.options)
            if chosen is None:
                self._out(f"    {raw!r} is not one of the options. Type a "
                          f"number from 1 to {len(question.options)}, or "
                          f"why / skip / stop.")
                continue

            self._record(question, chosen, attempts)
            self._out(f"    noted: {chosen}\n")
            return Answer(chosen=chosen)

    def ask_all(self, questions: Iterable[Question]) -> list[Answer]:
        """Ask in the order given, which is the order of consequence."""
        answers: list[Answer] = []
        for question in questions:
            try:
                answers.append(self.ask(question))
            except Stopped:
                raise
        return answers

    # ---- showing -----------------------------------------------------------
    def show(self, item: Checked | Decision) -> None:
        """Report a verdict or a decision. Says what it means, not just what it is."""
        self._greet()
        if isinstance(item, Checked):
            self._show_checked(item)
        else:
            self._show_decision(item)

    def confirm(self, text: str) -> bool:
        """A yes or no that has to be typed. No default."""
        self._greet()
        self._out(_wrap(text, indent="  "))
        while True:
            raw = self._in("  yes / no > ").strip().lower()
            if raw in ("y", "yes"):
                return True
            if raw in ("n", "no"):
                return False
            self._out("    type yes or no.")

    def transcript(self) -> list[dict]:
        return [exchange.as_dict() for exchange in self._log]

    # ---- the parts that do the talking ------------------------------------
    def _greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._out(f"\n  {self.researcher}, the Architect has questions.")
        self._out("  Answer with a number. At any point: why (say more), "
                  "skip (leave it open), stop (end the run).")
        self._out("  Nothing is answered for you, and pressing Enter chooses "
                  "nothing.\n")

    def _show_question(self, question: Question, repeat: bool = False) -> None:
        self._out(f"  {question.headline}")
        if question.detail and not repeat:
            self._out(_wrap(question.detail))
        for i, option in enumerate(question.options, start=1):
            mark = "  (recommended)" if option == question.recommended else ""
            self._out(f"    {i}. {option}{mark}")
        if question.recommended:
            self._out("    a recommendation is still a choice; type its number")
        self._out(f"    asked by: {question.asked_by}")

    def _show_checked(self, checked: Checked) -> None:
        word = {Verdict.ACCEPTED: "accepted",
                Verdict.ACCEPTED_WITH_FLAGS: "accepted, with something to read",
                Verdict.REFUSED: "refused"}[checked.verdict]
        self._out(f"\n  {checked.handover}: {word}")
        if checked.blocking:
            self._out(f"    {len(checked.blocking)} thing(s) stop it:")
            for finding in checked.blocking[:5]:
                self._out(f"      - {finding.message}")
        if checked.flags:
            self._out(f"    {len(checked.flags)} flag(s), which do not stop "
                      f"anything and are not errors:")
            for finding in checked.flags[:5]:
                self._out(f"      - {finding.message}")
        self._out("")

    def _show_decision(self, decision: Decision) -> None:
        says = {Move.GO_ON: "the next phase may start",
                Move.GO_BACK: f"{decision.target_phase} runs again",
                Move.ASK: "this one is yours to decide",
                Move.STOP: "the run ends here"}[decision.move]
        self._out(f"\n  {decision.move.value.upper()} - {says}")
        if decision.because:
            self._out(_wrap(decision.because))
        self._out("")

    # ---- reading an answer -------------------------------------------------
    @staticmethod
    def _match(raw: str, options: list[str]) -> str | None:
        """A number, or the option typed out. Never anything close to either.

        Prefix matching was deliberately left out. Two options that share an
        opening word are common, and silently picking the first is exactly the
        failure this interface exists to avoid.
        """
        if not raw:
            return None
        if raw.isdigit():
            index = int(raw)
            return options[index - 1] if 1 <= index <= len(options) else None
        for option in options:
            if raw.strip().lower() == option.strip().lower():
                return option
        return None

    def _record(self, question: Question, answered: str, attempts: int,
                note: str = "") -> None:
        self._log.append(Exchange(
            at=_now(), asked_by=question.asked_by, headline=question.headline,
            options=list(question.options), recommended=question.recommended,
            answered=answered, attempts=attempts, note=note))


# --------------------------------------------------------------------------- #
#  Two scripted runs, so this is exercised without a person present
# --------------------------------------------------------------------------- #
def _scripted(answers: list[str]):
    queue = list(answers)

    def read(prompt: str) -> str:
        value = queue.pop(0) if queue else "stop"
        print(f"{prompt}{value}")
        return value
    return read


def _rule(title: str) -> None:
    print(f"\n{'=' * 76}\n{title}\n{'=' * 76}")


def main() -> None:
    from architect.consultation import ArchitectConsultation

    consultation = ArchitectConsultation(researcher="Marco")
    spec = consultation.open(objective="find thermostable ene-reductases "
                                       "in hot spring sediment")
    questions = consultation.propose_changes(spec)[:3]

    _rule("1. THE STRAIGHTFORWARD PATH")
    ui = Interface(input_fn=_scripted(["1", "2", "1"]), researcher="Marco")
    answers = ui.ask_all(questions)
    spec = consultation.apply(spec, answers)
    print(f"  {len(answers)} answered; "
          f"{len(consultation.propose_changes(spec))} still open")

    _rule("2. THE AWKWARD PATH - a typo, a why, a skip, then a real answer")
    ui2 = Interface(input_fn=_scripted(["banana", "", "why", "1", "skip", "2"]),
                    researcher="Marco")
    ui2.ask_all(questions[:2])

    _rule("3. THE TRANSCRIPT")
    print()
    for row in ui2.transcript():
        answered = {SKIPPED: "(skipped)", STOPPED: "(stopped)"}.get(
            row["answered"], row["answered"])
        print(f"  {row['at']}  {row['attempts']} attempt(s)")
        print(f"     asked : {row['headline'][:66]}")
        print(f"     answer: {answered[:66]}")
    print("""
  A run that cannot be reconstructed afterwards is a run nobody can defend.
  The transcript is the record of what was put to a person and what they
  said - not what the system decided they meant.
""")


if __name__ == "__main__":
    main()
