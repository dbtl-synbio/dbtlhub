#!/usr/bin/env python3
"""Workflows: the steps a lab actually performs, and where the handovers fall.

    python3 architect/workflows/loader.py

WHAT A WORKFLOW IS, AND WHAT IT IS NOT
A contract says what must travel between two phases. A workflow says what the
lab does in each phase and which step the handover follows. They are different
documents and they need each other: a contract with no workflow is a rule with
nothing to apply to, and a workflow with no contract is a list of good
intentions.

The format came out of Anil Wipat's bioprospecting cycle, and the shape of
that file is the shape of all of them: a numbered step, the phase it belongs
to, and - where they exist - the three things that turned out to matter most
when a handover was written against real work.

    count_observed   how many things still exist after this step. 96 -> 86 ->
                     75 in the worked cycle. The gap between two numbers is
                     exactly what a Build handover has to be able to explain,
                     and it only ever goes down.
    manual_parts     the parts a person does by hand. "Any handover contract
                     has to represent a manual step as a first-class thing."
    routes           where the cycle can go two ways. Cell-free and
                     fermentation differ by a factor of about 120 in time, and
                     downstream nothing can tell which one happened unless the
                     route travels with the sample.

A WORKFLOW IS VALIDATED, LIKE EVERYTHING ELSE HERE
`problems()` checks a workflow the way a sentinel checks a handover, and for
the same reason: this system's whole claim is that an agreement nobody checks
is not an agreement. A researcher writing their own workflow gets the same
discipline the contracts get, in the same words.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHASES = ("design", "build", "test", "learn")
HANDOVER_AFTER = {"design": "design_to_build", "build": "build_to_test",
                  "test": "test_to_learn", "learn": "learn_to_design"}
HANDOVER_NUMBER = {"design_to_build": 1, "build_to_test": 2,
                   "test_to_learn": 3, "learn_to_design": 4}


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    phase: str
    note: str = ""
    count_observed: int | None = None
    manual_parts: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()
    handover_after: str = ""
    handover_number: int | None = None
    carried_out: bool = True

    @property
    def is_handover(self) -> bool:
        return bool(self.handover_after)


@dataclass
class Workflow:
    name: str
    title: str = ""
    use_case: str = "any"
    based_on: str = ""
    source: str = ""
    description: str = ""
    steps: list[Step] = field(default_factory=list)
    path: Path | None = None

    # ---- reading it ------------------------------------------------------
    def by_phase(self) -> dict[str, list[Step]]:
        return {p: [s for s in self.steps if s.phase == p] for p in PHASES}

    def handover_step(self, handover: str) -> Step | None:
        return next((s for s in self.steps if s.handover_after == handover), None)

    def attrition(self) -> list[tuple[Step, int, int | None]]:
        """Every counted step, with how many were lost since the one before.

        The lost figure is the point. A workflow that records 96 and then 86
        has said that ten things disappeared, and a Build handover that cannot
        say why is incomplete - which is a thing worth being able to see
        before the run rather than after it.
        """
        out, previous = [], None
        for step in self.steps:
            if step.count_observed is None:
                continue
            lost = None if previous is None else previous - step.count_observed
            out.append((step, step.count_observed, lost))
            previous = step.count_observed
        return out

    def manual_steps(self) -> list[Step]:
        return [s for s in self.steps if s.manual_parts]

    def forked_steps(self) -> list[Step]:
        return [s for s in self.steps if s.routes]

    def starting_count(self) -> int | None:
        """The first number the workflow commits to, which is how big a run is."""
        for step in self.steps:
            if step.phase == "design" and step.count_observed is not None:
                return step.count_observed
        return next((s.count_observed for s in self.steps
                     if s.count_observed is not None), None)

    def to_inputs(self) -> dict:
        """What the phase agents need from this workflow.

        Deliberately small. The workflow decides how many things a run is
        about and nothing else - the science stays in the use case module, and
        a workflow that started configuring the agents would quietly become a
        second place where the experiment is defined.
        """
        n = self.starting_count()
        return {"n": n} if n else {}

    # ---- checking it -----------------------------------------------------
    def problems(self) -> list[str]:
        """What is wrong with this workflow, in the order it would be met.

        Empty means it holds together. These are the same five things the
        format exists to guarantee, and a researcher's own workflow is held to
        them exactly as these four are.
        """
        bad: list[str] = []
        if not self.steps:
            return ["no steps: a workflow with no steps is a title"]

        numbers = [s.number for s in self.steps]
        if numbers != list(range(1, len(numbers) + 1)):
            bad.append(f"the steps are numbered {numbers}, and they have to run "
                       f"1..{len(numbers)} with no gaps and no repeats")

        seen = [s.phase for s in self.steps]
        unknown = sorted({p for p in seen if p not in PHASES})
        if unknown:
            bad.append(f"unknown phase(s) {unknown}: the four are {list(PHASES)}")
        order = [p for i, p in enumerate(seen) if i == 0 or p != seen[i - 1]]
        wanted = [p for p in PHASES if p in seen]
        if order != wanted:
            bad.append(f"the phases run {order}, and they have to run "
                       f"{list(PHASES)} once each, contiguously")
        for phase in PHASES:
            if phase not in seen:
                bad.append(f"no {phase} step: a cycle with a missing phase is "
                           f"not a cycle")

        for phase in PHASES:
            in_phase = [s for s in self.steps if s.phase == phase]
            if not in_phase:
                continue
            marked = [s for s in in_phase if s.handover_after]
            wanted_name = HANDOVER_AFTER[phase]
            if not marked:
                bad.append(f"no step is marked `handover_after: {wanted_name}`: "
                           f"four phases have four boundaries, and an unmarked "
                           f"one is a handover nobody checks")
            elif len(marked) > 1:
                bad.append(f"{len(marked)} steps claim to end {phase}; only the "
                           f"last one can")
            else:
                step = marked[0]
                if step.number != in_phase[-1].number:
                    bad.append(f"step {step.number} is marked `{wanted_name}` "
                               f"but {phase} ends at step {in_phase[-1].number}")
                if step.handover_after != wanted_name:
                    bad.append(f"step {step.number} is a {phase} step marked "
                               f"`{step.handover_after}`, which is not "
                               f"{phase}'s handover")
                elif step.handover_number != HANDOVER_NUMBER[wanted_name]:
                    bad.append(f"step {step.number} is {wanted_name}, which is "
                               f"handover {HANDOVER_NUMBER[wanted_name]}, not "
                               f"{step.handover_number}")

        previous, where = None, None
        for step, count, _ in [(s, s.count_observed, None) for s in self.steps
                               if s.count_observed is not None]:
            if previous is not None and count > previous:
                bad.append(f"step {step.number} counts {count} after step "
                           f"{where} counted {previous}: attrition only goes "
                           f"one way, and a cycle that gains things between "
                           f"two steps has not said where they came from")
            previous, where = count, step.number
        return bad

    @property
    def ok(self) -> bool:
        return not self.problems()


# --------------------------------------------------------------------------- #
#  Reading them off disk
# --------------------------------------------------------------------------- #
def _read(path: Path) -> dict:
    """YAML if PyYAML is here, and a plain refusal if it is not.

    Unlike the contracts, a workflow has no JSON twin: a contract must be
    readable with the standard library alone because the validator is the one
    thing that may never need an install, and a workflow is not that.
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml                                        # noqa: PLC0415
    except ImportError as exc:                             # pragma: no cover
        raise RuntimeError(
            f"{path.name} is YAML and PyYAML is not installed. The framework "
            f"itself runs on the standard library alone; the workflows do not. "
            f"`pip install 'PyYAML>=5.1'`") from exc
    return yaml.safe_load(text) or {}


def from_dict(raw: dict, path: Path | None = None) -> Workflow:
    steps = []
    for item in raw.get("steps") or []:
        steps.append(Step(
            number=int(item.get("number", 0)),
            name=str(item.get("name", "")),
            phase=str(item.get("phase", "")),
            note=str(item.get("note", "") or "").strip(),
            count_observed=(int(item["count_observed"])
                            if item.get("count_observed") is not None else None),
            manual_parts=tuple(item.get("manual_parts") or ()),
            routes=tuple(item.get("routes") or ()),
            handover_after=str(item.get("handover_after", "") or ""),
            handover_number=(int(item["handover_number"])
                             if item.get("handover_number") is not None else None),
            carried_out=bool(item.get("carried_out", True)),
        ))
    return Workflow(
        name=str(raw.get("name") or (path.stem if path else "untitled")),
        title=str(raw.get("title", "")),
        use_case=str(raw.get("use_case", "any")),
        based_on=str(raw.get("based_on", "")),
        source=str(raw.get("source", "") or "").strip(),
        description=str(raw.get("description", "") or "").strip(),
        steps=steps, path=path)


def load_file(path: Path | str) -> Workflow:
    path = Path(path)
    return from_dict(_read(path), path)


def available() -> list[str]:
    """Every workflow on disk, with the one they are all modelled on first."""
    names = sorted(p.stem for p in HERE.glob("*.yaml"))
    first = [n for n in ("bioprospecting",) if n in names]
    return first + [n for n in names if n not in first]


def load(name: str) -> Workflow:
    path = HERE / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"no workflow named {name!r}. There is: {', '.join(available())}")
    return load_file(path)


def load_all() -> list[Workflow]:
    out = []
    for name in available():
        try:
            out.append(load(name))
        except Exception as exc:                  # noqa: BLE001
            # One unreadable file must not take the list down with it: the
            # interface shows what it has and says what it could not read.
            broken = Workflow(name=name, title=f"could not be read: {exc}")
            out.append(broken)
    return out


# --------------------------------------------------------------------------- #
def main() -> None:
    print(f"\n{'=' * 78}\nWORKFLOWS ON DISK\n{'=' * 78}\n")
    for flow in load_all():
        marks = flow.problems()
        state = "ok" if not marks else f"{len(marks)} problem(s)"
        print(f"  {flow.name:<20}{len(flow.steps):>3} steps   "
              f"{flow.use_case:<18}{state}")
        print(f"      {flow.title}")
        for bad in marks:
            print(f"      ! {bad}")
        print()

    try:
        flow = load("bioprospecting")
    except Exception as exc:                      # noqa: BLE001
        print(f"  bioprospecting could not be read: {exc}\n")
        return

    print(f"{'=' * 78}\nWHAT A WORKFLOW CARRIES, BEYOND ITS STEPS\n{'=' * 78}\n")
    print(f"  {flow.name} - {flow.title}\n")

    print("  the four handovers, and the step each one follows:")
    for handover in HANDOVER_NUMBER:
        step = flow.handover_step(handover)
        print(f"    {HANDOVER_NUMBER[handover]}. {handover:<18}"
              + (f"after step {step.number}, {step.name}" if step
                 else "NOT MARKED"))

    print("\n  attrition, and what nobody has explained:")
    for step, count, lost in flow.attrition():
        tail = "" if lost is None else f"   {lost} lost since the last count"
        print(f"    step {step.number:>2}  {count:>4} remain{tail}")

    print("\n  the parts a person does by hand:")
    for step in flow.manual_steps():
        print(f"    step {step.number:>2}  {', '.join(step.manual_parts)}")

    print("\n  where the cycle can go two ways:")
    for step in flow.forked_steps():
        print(f"    step {step.number:>2}  {' or '.join(step.routes)}")

    print(f"\n  a run from this workflow would be about "
          f"{flow.starting_count()} things: {flow.to_inputs()}\n")


if __name__ == "__main__":
    main()
