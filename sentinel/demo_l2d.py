#!/usr/bin/env python3
"""Handover 4, Learn -> Design: the cycle closes, or it does not.

    python3 demo_l2d.py

No dependencies, no API key, no network.

Handover 4 carries the one thing in the cycle that is not a measurement of
something that happened: a claim about something that has not happened yet.
So the contract asks the three questions that make such a claim checkable -
which measurements does it rest on, which model produced it, and how uncertain
is it - and refuses a recommendation that cannot answer them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from framework.agents.base import Task                                # noqa: E402
from framework.agents.coordinator import Coordinator                  # noqa: E402
from framework.agents.sentinel_l2d import LearnToDesignAgent          # noqa: E402
from usecases.bioprospecting.learning import recommendations          # noqa: E402

FAULTS = {"orphan_evidence", "tied_rank", "point_estimate", "no_prediction"}


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def run(run_id: str, faults: set[str] | None = None):
    package = recommendations(n=4, faults=faults)
    coord = Coordinator(run_id)
    agent = LearnToDesignAgent(profile="bioprospecting")
    result = coord.step(agent,
                        Task(goal="hand the next round back to Design",
                             inputs={"package": package}, max_repairs=2),
                        label="handover l2d", store_as="l2d")
    print(f"\n[{agent.name}] -> {result.status.upper()}")
    for note in result.notes:
        print(f"    {note}")
    for err in result.errors:
        print(f"    ! {err}")
    return result


def main() -> None:
    rule("1. A ROUND THAT CLOSES - four recommendations Design can act on")
    good = run("l2d-clean")
    package = recommendations(n=4)
    top = package["recommendations"][0]
    print("\n  What Design receives, for the top-ranked recommendation:")
    print(f"    {top['recommendation_id']}  rank {top['rank']}")
    print(f"    make        : {top['proposes']['kind']} of "
          f"{top['proposes']['derived_from_design_item']}")
    print(f"                  {top['proposes']['change']}")
    print(f"    because of  : {', '.join(top['evidence'])}  "
          f"(measurements in test_ref, not prose)")
    pred = top["predictions"][0]
    print(f"    expect      : {pred['value']} ± {pred['uncertainty']['value']} "
          f"{pred['unit']}  ({pred['uncertainty']['kind']})")
    print(f"    from model  : {package['model']['name']} "
          f"{package['model']['version']}, "
          f"holdout {package['model']['holdout']['metric']} "
          f"{package['model']['holdout']['value']}")

    rule("2. A ROUND THAT DOES NOT - four failures that happen for real")
    bad = run("l2d-broken", faults=FAULTS)

    rule("WHAT THIS SHOWS")
    print(f"""
  Clean run: {good.status}.  Broken run: {bad.status}, {len(bad.errors)} error(s),
  of which {len(bad.errors)} needed a human.

  The four injected faults are the ones that matter here:

    orphan_evidence   a recommendation cites a measurement that is not in the
                      data the model was given. That is what a fabricated
                      justification looks like inside a package, and no other
                      check in the cycle would catch it.
    point_estimate    a prediction with no uncertainty. The schema refuses it,
                      because a ranked list of bare numbers cannot tell Design
                      where to spend the next plate.
    no_prediction     the quantity this use case requires was never predicted.
    tied_rank         two recommendations claim first place.

  None of them is auto-fixable, and the reason is the same every time:
  supplying the missing piece would invent a scientific claim rather than
  repair a formatting slip.

  Note what the contract does NOT do. It does not ask whether the
  recommendation is any good - that is the next round's job, and the holdout
  metric is carried so the two can be compared. It asks whether the claim can
  be traced, reproduced and weighed. Those are checkable; being right is not.
""")


if __name__ == "__main__":
    main()
