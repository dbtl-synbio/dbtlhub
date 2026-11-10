#!/usr/bin/env python3
"""One crate for the whole run, grown by the phases that produce the work.

    python3 demo_cycle.py

No dependencies, no API key, no network.

The arrangement this demonstrates:

  * there is ONE crate per run, and it is the knowledge graph. Nothing is
    joined afterwards because nothing was ever separate.
  * a PHASE AGENT does the science, then writes what it produced into that
    crate, with the action that produced it.
  * the SENTINEL is a submodule it submits to, not a wrapper around it. The
    phase agent is in charge; the check is something it has to survive.

Two refusals have nothing to do with contracts and belong to the crate itself,
because they only exist once the crate is shared:

  * a phase may fill a gap in an entity another phase wrote. It may not
    overwrite a recorded value.
  * a phase may not write a reference to an entity the crate does not hold.
    In one shared crate that is a join to nothing, and it is silent.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from framework.agents.base import Task                                # noqa: E402
from framework.agents.coordinator import Coordinator                  # noqa: E402
from framework.agents.phase_build_crate import BuildPhaseAgent        # noqa: E402
from framework.agents.phase_design_crate import DesignPhaseAgent      # noqa: E402
from framework.agents.phase_learn_crate import LearnPhaseAgent        # noqa: E402
from framework.agents.phase_test_crate import TestPhaseAgent          # noqa: E402
from framework.crate_store import CrateStore                          # noqa: E402
from framework.kg import provenance_of                                # noqa: E402
from usecases.bioprospecting import instruments as bp                 # noqa: E402

RUN = "cycle"
DIM_ARROW = "\u21b3"


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def show(result, label: str) -> None:
    print(f"\n[{label}] -> {result.status.upper()}")
    for note in result.notes:
        print(f"    {note}")
    for err in result.errors[:6]:
        print(f"    ! {err}")


def main() -> None:
    import shutil
    shutil.rmtree(Path(__file__).parent / "runs" / RUN, ignore_errors=True)

    coord = Coordinator(RUN)

    rule("1. DESIGN - produces the science, then writes the crate")
    design = coord.step(
        DesignPhaseAgent(profile="bioprospecting", lab="newcastle"),
        Task(goal="select a candidate panel",
             inputs={"n": 6, "run_id": RUN}, max_repairs=2),
        label="design", store_as="d2b")
    show(design, "phase_design")

    rule("2. BUILD - writes into the SAME crate")
    build = coord.step(
        BuildPhaseAgent(profile="bioprospecting"),
        Task(goal="build the panel",
             inputs={"panel": bp.design_panel(6), "run_id": RUN,
                     "design_package": coord.path_of("d2b")}, max_repairs=2),
        label="build", store_as="b2t")
    show(build, "phase_build")

    rule("3. TEST - adds what only the instrument knows")
    test = coord.step(
        TestPhaseAgent(profile="bioprospecting"),
        Task(goal="read the plate",
             inputs={"package": build.outputs["package"], "run_id": RUN,
                     "build_package": coord.path_of("b2t")}, max_repairs=2),
        label="test", store_as="t2l")
    show(test, "phase_test")

    rule("4. LEARN - adds a claim about what has not happened yet")
    learn = coord.step(
        LearnPhaseAgent(profile="bioprospecting"),
        Task(goal="rank the next round",
             inputs={"package": test.outputs["package"], "run_id": RUN,
                     "test_package": coord.path_of("t2l"),
                     "next_library_size": 36}, max_repairs=2),
        label="learn", store_as="l2d")
    show(learn, "phase_learn")

    store = CrateStore(RUN)
    rule("5. ONE CRATE, ONE GRAPH")
    print(f"""
  crate   {store.path}
  graph   {store.graph_path}
  {len(store)} entities, {sum(1 for _ in open(store.graph_path))} triples

  No phase described what an earlier one had already described. Each added
  only what it alone knew: Design the derivation, Build the well, Test the
  reading, Learn the claim. So the whole cycle is one traversal, with no
  backlink to follow and no second file to open:
""")
    follow = ("prov:wasDerivedFrom", "prov:wasGeneratedBy", "prov:used",
              "dbtl:restsOn", "object")
    chain = provenance_of(store.crate, "#recommendation/REC-001", follow=follow)
    i = 0
    while i < len(chain):
        node = chain[i]
        prefix = node["id"].rsplit("/", 1)[0]
        run = 1
        while i + run < len(chain) and chain[i + run]["id"].startswith(prefix + "/"):
            run += 1
        print(f"      {i:>2}. {node['id']:<28} {str(node.get('name'))[:42]}")
        if run > 1:
            print(f"          {DIM_ARROW} and {run - 1} sibling"
                  f"{'s' if run > 2 else ''} of the same kind")
        i += run
    print(f"\n      {len(chain)} nodes, from what to make next back to the "
          f"ground it came out of.")

    rule("6. WHAT THE SHARED CRATE REFUSES")
    print("\n  A later phase tries to change a coordinate Design recorded:")
    before = store.index["#site/NS-01"].get("dwc:decimalLatitude")
    report = store.add("test", [{"@id": "#site/NS-01", "dwc:decimalLatitude": 0.0}])
    print(f"      {report.summary()}  ->  {report.conflicts}")
    print(f"      nothing written; the crate still says {before}")

    print("\n  A later phase writes a reference to something not in the crate:")
    report = store.add("test", [{"@id": "#reading/R1", "@type": "dbtl:Reading",
                                 "prov:wasDerivedFrom": {"@id": "#sample/NOPE"}}])
    print(f"      {report.summary()}  ->  {report.dangling}")
    print("      nothing written; a join to nothing is not a forward reference")

    rule("WHAT THIS SHOWS")
    print("""
  The phase agent is in charge and the sentinel is a submodule it submits
  to. That ordering is what lets a phase agent be clever - choosing assays,
  optimising a library under a budget - because whatever it decides still
  has to survive the same check, written by somebody else.

  Writing the crate is the phase's own job and not an afterthought. Design
  resolves its own vocabulary before writing, because nobody else can know
  what the technician meant by freezer_temp. A phase that produces results
  and leaves the describing to somebody later is how the description ends
  up being written by whoever is least able to write it.

  And the two refusals above are not contract failures. No contract can
  settle two phases disagreeing about what happened, or notice a reference
  that points at nothing. They belong to the crate, and they only exist at
  all because the crate is shared.
""")


if __name__ == "__main__":
    main()
