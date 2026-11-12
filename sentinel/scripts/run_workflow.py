#!/usr/bin/env python3
"""One turn of a workflow, start to finish, with no browser and no model.

    python3 scripts/run_workflow.py                         # bioprospecting
    python3 scripts/run_workflow.py directed_evolution
    python3 scripts/run_workflow.py --list

This is the same path the web interface takes - the same Architect, the same
one sentinel, the same crate - with the browser replaced by a stated answer
policy. It exists so that "reproduce the example" is one command rather than
thirty form fields, and so that what the interface does can be checked by a
test and by a person who has not got the interface open.

WHAT IT PROVES, AND IT IS THE WHOLE CLAIM
  1. a specification is agreed before anything runs
  2. the workflow decides how big the run is - 96 candidates, not a default
  3. a sentinel checks every handover and may refuse it
  4. ONE crate grows across the whole cycle and is the knowledge graph

THE ANSWER POLICY, SAID OUT LOUD
When a sentinel refuses and the Architect asks, somebody has to answer. A
script cannot be that somebody, so it does not pretend to be: by default it
skips, which leaves the question in `what has no answer` and is exactly what a
researcher who walked away would leave behind. `--answer <n>` picks option n
instead, and whichever is used is printed and written to the ledger. Nothing
here answers on a researcher's behalf without saying so.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from architect.architect import Architect                           # noqa: E402
from architect.contract import Move, PHASES                         # noqa: E402
from architect.interface import SKIPPED, Interface                  # noqa: E402
from architect.wiring import phase_runner, sentinel_checker         # noqa: E402
from architect.workflows import loader as workflows                 # noqa: E402


def banner(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}\n")


def run(name: str, answer: str, run_id: str, fresh: bool) -> int:
    try:
        flow = workflows.load(name)
    except Exception as exc:                                   # noqa: BLE001
        print(f"  {exc}")
        return 2
    problems = flow.problems()
    if problems:
        # A workflow that does not hold together would check the wrong
        # boundary, or none. Refusing here is the same refusal the interface
        # gives, in the same words.
        print(f"  {name} does not pass its own rules, so it is not run:")
        for bad in problems:
            print(f"    ! {bad}")
        return 1

    if fresh:
        shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)

    banner(f"{flow.title.upper()}")
    print(f"  workflow   {flow.name}, {len(flow.steps)} steps")
    print(f"  source     {flow.source[:100]}")
    print(f"  run        {run_id}\n")

    for handover in ("design_to_build", "build_to_test",
                     "test_to_learn", "learn_to_design"):
        step = flow.handover_step(handover)
        print(f"  handover {step.handover_number}  {handover:<17}"
              f"after step {step.number}, {step.name}")
    counted = flow.attrition()
    if counted:
        print()
        for step, count, lost in counted:
            tail = "" if lost is None else f"  ({lost} lost)"
            print(f"  step {step.number:>2}     {count:>5} remain{tail}")

    # ---- the run ----------------------------------------------------------
    size = flow.starting_count()
    banner("THE CYCLE")
    arch = Architect(run_id, researcher="the workflow runner")
    arch.consult(objective=f"one turn of {flow.name}")

    # The plan goes into the crate BEFORE the run it is a plan for. A workflow
    # added afterwards would be a claim about what was intended, written by
    # somebody who already knew what happened.
    landed = workflows.record_in(arch.memory.store, flow, by="the workflow runner")
    print(f"  the plan is in the crate: {len(flow.to_crate())} entities "
          f"({flow.crate_id()}), as schema:HowTo and prov:Plan")
    if getattr(landed, "conflicts", None) or getattr(landed, "collisions", None):
        print(f"  the store had something to say about it: {landed}")

    # THE DATA IS THE SAME WHICHEVER WORKFLOW IS CHOSEN, AND THAT IS ON PURPOSE.
    # The four phase agents are the bioprospecting ones, producing simulated
    # candidates, plates and readings. A workflow supplies the SHAPE of a run -
    # how many things, which step each handover follows, where the manual work
    # and the forks are - and the dummy agents supply the data. Pretending a
    # directed-evolution workflow produced directed-evolution data would be the
    # one lie this whole system exists to make impossible.
    from usecases.bioprospecting import instruments as bp         # noqa: PLC0415
    inputs = dict(flow.to_inputs())
    # The simulated plate is a real 96-well plate and holds 96 things. A
    # workflow may honestly count more than that - directed evolution ranks
    # 256 variants before building any - and the run is then capped and says
    # so, rather than quietly overflowing the plate or pretending the number
    # was smaller than the workflow states.
    capacity = len(bp.WELLS)
    panel_size = min(size or 6, capacity)
    capped = bool(size and size > capacity)
    inputs["n"] = panel_size
    inputs["panel"] = bp.design_panel(panel_size)
    print(f"  the run is about {panel_size} things, "
          + (f"from the {flow.name} workflow" if size else
             "from the phase agent's own default: this workflow commits to no "
             "count"))
    if capped:
        print(f"  the workflow counts {size}, and the simulated plate holds "
              f"{capacity}: capped, not silently reduced")
    print(f"  the data is simulated bioprospecting data whichever workflow "
          f"is chosen;\n  the workflow gives the shape, not the science\n")

    runner = phase_runner(profile="bioprospecting", lab="newcastle", **inputs)
    checker = sentinel_checker(profile="bioprospecting")

    said: list[str] = []
    ui = Interface(input_fn=lambda prompt: _answer(prompt, answer, said),
                   output_fn=lambda text="": None,
                   researcher="the workflow runner")

    order, index, guard, growth = list(PHASES), 0, 0, []
    while index < len(order) and guard < 2 * len(order) + 4:
        guard += 1
        phase = order[index]
        decision = arch.run_phase(phase, runner, checker)
        step = arch.history[-1]
        verdict = step.verdict.value if step.verdict else "nothing handed over"

        total = len(arch.memory.snapshot().get("@graph", []))
        added = total - (growth[-1] if growth else 0)
        growth.append(total)

        print(f"  {phase:<7} {verdict:<20} -> {decision.move.value.upper():<8}"
              f"crate {total:>4} (+{added})")
        print(f"          {decision.because[:150]}")

        if decision.move is Move.STOP:
            break
        if decision.move is Move.GO_BACK and decision.target_phase in order:
            index = order.index(decision.target_phase)
            continue
        if decision.move is Move.ASK and decision.question is not None:
            print(f"          asks: {decision.question.headline[:110]}")
            given = ui.ask(decision.question)
            print(f"          answered: "
                  + ("skipped, and it stays in what has no answer"
                     if given.chosen == SKIPPED else given.chosen[:100]))
        index += 1
        print()

    # ---- what is left on disk ---------------------------------------------
    crate = arch.memory.snapshot()
    banner("WHAT IS ON DISK NOW")
    print(f"  one crate, {len(crate['@graph'])} entities, which grew "
          f"{' -> '.join(str(g) for g in growth)}")
    checks = [e for e in crate["@graph"]
              if str(e.get("@id", "")).startswith("#check/")]
    print(f"  {len(checks)} sentinel act(s) recorded inside the crate itself")
    for act in checks:
        if act.get("@type") == "CreateAction":
            print(f"    {act.get('dbtl:verdict','?'):<20}"
                  f"{act.get('dbtl:contract','?')}")
    print(f"\n  {arch.summary()}")
    print(f"  ledger     {arch.write_ledger()}")
    print(f"  crate      runs/{run_id}/ro-crate-metadata.json")
    print(f"  graph      runs/{run_id}/graph/\n")
    return 0


def _answer(prompt: str, policy: str, said: list[str]) -> str:
    """The one place a question is answered, and it says what it did."""
    said.append(prompt)
    return policy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one turn of a workflow, with no browser and no model.")
    parser.add_argument("workflow", nargs="?", default="bioprospecting",
                        help="which workflow (default: bioprospecting)")
    parser.add_argument("--list", action="store_true",
                        help="show the workflows on disk and stop")
    parser.add_argument("--answer", default="skip",
                        help="what to answer when the Architect asks: `skip` "
                             "(the default, leaves it unresolved), `stop`, or "
                             "the number of an option")
    parser.add_argument("--run-id", default=None,
                        help="name the run (default: wf-<workflow>)")
    parser.add_argument("--keep", action="store_true",
                        help="add to an existing run instead of starting clean")
    args = parser.parse_args()

    if args.list:
        banner("WORKFLOWS ON DISK")
        for flow in workflows.load_all():
            marks = flow.problems()
            print(f"  {flow.name:<20}{len(flow.steps):>3} steps   "
                  f"{'ok' if not marks else str(len(marks)) + ' problem(s)'}")
            print(f"      {flow.title}\n")
        return

    sys.exit(run(args.workflow, args.answer,
                 args.run_id or f"wf-{args.workflow}", not args.keep))


if __name__ == "__main__":
    main()
