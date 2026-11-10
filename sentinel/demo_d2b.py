#!/usr/bin/env python3
"""The Design -> Build handover, end to end.

    python3 demo_d2b.py

No dependencies, no API key, no network.

What it demonstrates, in order:

  1. clean run    the crate is aligned, lifted to triples, and the order is
                  projected. The question "where did this sequence come from?"
                  becomes a traversal.
  2. provider     what actually leaves the building: sequences and wells. The
                  coordinates, the freezer and the technician stay with us.
  3. broken run   three failures that happen for real, none auto-fixable:
                  no coordinates, a sequence with no origin, a key nobody mapped.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from framework.agents.base import Task
from framework.agents.coordinator import Coordinator
from framework.agents.sentinel_d2b import DesignToBuildAgent
from framework.agents.phase_design import DesignAgent
from framework.kg import provenance_of

TARGETS = [{"name": "4-nitrophenyl-beta-D-glucopyranoside",
            "inchikey": "IQFYYKKMVGJFEH-XLPZGREQSA-N", "role": "substrate"}]


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def show(result, label: str) -> None:
    print(f"\n[{label}] -> {result.status.upper()}")
    for note in result.notes:
        print(f"    {note}")
    for err in result.errors:
        print(f"    ! {err}")


def run(run_id: str, faults: set[str] | None = None):
    coord = Coordinator(run_id)
    design = coord.step(DesignAgent(),
                        Task(goal="select a candidate panel",
                             inputs={"n": 6, "faults": faults}),
                        label="design")
    show(design, "phase_design")

    agent = DesignToBuildAgent(profile="bioprospecting", lab="newcastle")
    handover = coord.step(
        agent,
        Task(goal="hand over to Build",
             inputs={"crate": design.outputs["crate"],
                     "items": design.outputs["items"],
                     "run_id": run_id, "target_list": TARGETS},
             max_repairs=2),
        label="handover d2b", store_as="d2b")
    show(handover, "sentinel_d2b")
    return coord, agent, handover


def main() -> None:
    rule("1. CLEAN RUN - a crate that can answer for itself")
    coord, agent, handover = run("d2b-clean")
    package = handover.outputs["package"]

    print("\n  The traversal that is the whole point. One ordered sequence,")
    print("  walked back to the sediment it came out of:\n")
    entity = package["bindings"][0]["crate_entity"]
    for i, step in enumerate(provenance_of(package["crate"], entity)):
        print(f"    {'  ' * 0}{i:>2}. {step['id']:<28} {step['name'][:42]}")

    rule("2. WHAT LEAVES THE BUILDING")
    view = agent.provider_view(package)
    print(f"\n  to {view['provider']}, {view['format']}, plate "
          f"{view['container_id']}\n")
    for item in view["items"][:3]:
        print(f"    {item['order_item_id']}  {item['position']:<4} "
              f"{item['length_bp']:>5} bp  {item['sequence_sha256'][:23]}...")
    print(f"    ... {len(view['items'])} lines in total\n")
    sent = set(view["items"][0])
    kept = set(package["crate"]["@graph"][3]) | set(package["crate"]["@graph"][2])
    print(f"  fields sent per line:   {len(sent)}")
    print(f"  fields kept on the sample and site records alone: {len(kept)}")
    print("  The order is poor on purpose. The contract's job is to guarantee")
    print("  that what we stripped is still attached to what we sent.")

    rule("3. BROKEN RUN - three failures, none of them mechanical")
    print("   missing_geo    the field form came back without coordinates")
    print("   orphan_fasta   a sequence appears with no link to what produced it")
    print("   unaligned_key  a technician wrote 'box_temp_c' for the freezer")
    _, _, broken = run("d2b-broken",
                       faults={"missing_geo", "orphan_fasta", "unaligned_key"})

    rule("WHAT THIS SHOWS")
    print(f"""
  The clean run produced a graph, not a document:
      {coord.ledger.dir / 'graph' / 'design.nt'}

  Of the failures in run 3, exactly zero could be repaired, and the one
  repair the contract does allow - the crate checksum - fired in the clean
  run, because a checksum is derivable and a provenance step is not.

  That is the claim worth reporting:

    - a JSON Schema can check that a crate HAS entities. Only a traversal
      can check that a sequence is CONNECTED to the thing it came from, and
      that is the failure that matters. The contracts therefore carry graph
      checks, not just field checks.
    - the only step in the whole handover where a model is clearly better
      than a rule is mapping an invented key onto a term. Everything else
      should stay deterministic, and does.

  Ledger: {coord.ledger.path}
""")


if __name__ == "__main__":
    main()
