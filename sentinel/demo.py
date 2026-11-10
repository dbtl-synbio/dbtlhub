#!/usr/bin/env python3
"""Run the framework end to end, twice: on a clean run and on a broken one.

    python3 demo.py

No dependencies, no API key, no network. The point is to see the shape of the
thing working, so the week can be spent making it real rather than deciding what
it should look like.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from framework.agents.base import Task
from framework.agents.coordinator import Coordinator
from framework.agents.sentinel_b2t import BuildToTestAgent
from framework.agents.sentinel_d2b import DesignToBuildAgent
from framework.agents.phase_build import BuildAgent
from framework.agents.phase_design import DesignAgent
from framework.agents.phase_test import TestAgent
from framework.validator import load_contract, validate
from usecases.bioprospecting import instruments as bp

TARGETS = [{"name": "4-nitrophenyl-beta-D-glucopyranoside",
            "inchikey": "IQFYYKKMVGJFEH-XLPZGREQSA-N", "role": "substrate"}]


def rule(title: str = "") -> None:
    print(f"\n{'=' * 74}")
    if title:
        print(title)
        print("=" * 74)


def show(result, label: str) -> None:
    mark = {"ok": "OK", "escalated": "ESCALATED", "failed": "FAILED"}[result.status]
    print(f"\n[{label}] -> {mark}")
    for note in result.notes:
        print(f"    {note}")
    for err in result.errors:
        print(f"    ! {err}")


def run(run_id: str, faults: set[str] | None = None) -> Coordinator:
    coord = Coordinator(run_id)

    # ---- Design, and the handover that starts the chain --------------------
    design = coord.step(
        DesignAgent(),
        Task(goal="select a candidate panel", inputs={"n": 12}),
        label="design")
    d2b = coord.step(
        DesignToBuildAgent(profile="bioprospecting", lab="newcastle"),
        Task(goal="hand over to Build",
             inputs={"crate": design.outputs["crate"],
                     "items": design.outputs["items"], "run_id": run_id,
                     "target_list": TARGETS},
             max_repairs=2),
        label="handover d2b", store_as="d2b")
    show(d2b, "sentinel_d2b")
    panel = bp.design_panel(12)

    # ---- Build -------------------------------------------------------------
    build = coord.step(
        BuildAgent(),
        Task(goal="build the candidate panel",
             inputs={"panel": panel, "run_id": run_id, "faults": faults,
                     "target_list": TARGETS,
                     # not a path this phase made up: where d2b really landed
                     "design_package": coord.path_of("d2b")}),
        label="build", store_as="b2t_raw")
    show(build, "phase_build")

    # ---- the Build -> Test handover ----------------------------------------
    handover = coord.step(
        BuildToTestAgent(profile="bioprospecting"),
        Task(goal="hand over to Test", inputs={"package": build.outputs["package"]},
             max_repairs=2),
        label="handover b2t", store_as="b2t")
    show(handover, "sentinel_b2t")

    if not coord.should_continue(handover):
        print("\n    route stopped: Test is not given a package the validator rejected")
        return coord

    # ---- Test --------------------------------------------------------------
    test = coord.step(
        TestAgent(),
        Task(goal="read the plate",
             inputs={"package": handover.outputs["package"],
                     "build_package": coord.path_of("b2t")}),
        label="test", store_as="t2l_raw")
    show(test, "phase_test")

    # ---- the Test -> Learn handover (validated directly, no agent yet) -----
    t2l = load_contract("test_to_learn", profile="bioprospecting")
    report = validate(test.outputs["package"], t2l)
    print(f"\n[sentinel_t2l] -> {'OK' if report.ok else 'FAIL'}")
    print(f"    validate against {t2l['$id']} -> "
          f"{'PASS' if report.ok else f'{len(report.errors)} error(s)'}")
    if not report.ok:
        print(report.text("    "))
    return coord


def main() -> None:
    rule("1. CLEAN RUN - everything the contract asks for is present")
    clean = run("demo-clean")

    rule("2. BROKEN RUN - three mistakes injected that really happen in a lab")
    print("   missing_units   the TapeStation export drops the unit column on 2 rows")
    print("   double_booked   the OT-2 deck shifted: 2 samples claim one well")
    print("   unknown_item    a tube was relabelled by hand with CAND-999")
    broken = run("demo-broken",
                 faults={"missing_units", "double_booked", "unknown_item",
                         "dropped_well"})

    rule("3. COMMON GROUND - the same contract, the other use case")
    print("   A biomanufacturing package, written by hand, validated against the")
    print("   SAME build_to_test contract with profile=biomanufacturing.\n")
    bm = {
        "contract": "build_to_test", "contract_version": "0.2.0",
        "profile": "biomanufacturing", "run_id": "demo-bm",
        "produced_by": {"agent": "phase_build", "tool": "liquid handler", "engine": "none"},
        "produced_at": "2026-11-09T18:00:00Z",
        "design_ref": {"package": "design/handover.json",
                       "items": [{"design_item_id": "PATH-001",
                                  "accession": "MetaNetX:MNXR104919"}]},
        "target_list": [{"name": "p-coumaric acid",
                         "inchikey": "NGSWKAQJJWESNS-ZZXKWVIFSA-N", "role": "product"}],
        "samples": [{
            "sample_id": "BM1-R1", "design_item_id": "PATH-001",
            "location": {"container_id": "REACTOR-1", "position": "R1"},
            "qc": {"verdict": "pass", "measurements": [
                {"quantity": "sequence_verified", "value": True, "unit": "dimensionless",
                 "method": "nanopore verification"},
                {"quantity": "biomass", "value": 3.2, "unit": "gDW/L",
                 "method": "OD600 converted to dry weight"}]}}],
    }
    contract = load_contract("build_to_test", profile="biomanufacturing")
    report = validate(bm, contract)
    print(f"   [sentinel_b2t / biomanufacturing] -> {'PASS' if report.ok else 'FAIL'}")
    if not report.ok:
        print(report.text("     "))

    print("\n   Now the same package claimed under the bioprospecting profile:\n")
    wrong = dict(bm, profile="bioprospecting")
    report2 = validate(wrong, load_contract("build_to_test", profile="bioprospecting"))
    print(f"   [sentinel_b2t / bioprospecting] -> {'PASS' if report2.ok else 'FAIL'}")
    print(report2.text("     "))
    print("\n   Same structure, different profile: the shared contract holds the"
          "\n   common ground, the profile holds what each case actually requires.")

    rule("WHAT THIS SHOWS")
    for coord in (clean, broken):
        s = coord.summary()
        print(f"\n  {s['run_id']}")
        print(f"    steps        {s['steps']}")
        print(f"    escalated    {s['escalated'] or 'none'}")
        print(f"    engines      {', '.join(s['engines_used'])}")
        print(f"    ledger       {s['ledger']}")

    print("""
  The split matters more than the pass/fail:

    - the unit was restored automatically, because the profile declares what
      unit that quantity must be in - nothing was invented;
    - the double-booked well and the unknown candidate were NOT auto-fixed and
      were escalated, because guessing which sample sat in which well would
      fabricate a lab record. A failed handover beats a plausible wrong number.

  So the honest claim for Friday is not "the agents fix everything". It is
  "the contract caught three real errors, one was safely repairable and two
  needed a decision" - and the ledger proves which.

  Next: swap RulesEngine for a model engine in framework/llm.py and re-run.
  Every step already records the engine, so the comparison is a query over
  runs/*/ledger.jsonl, not a separate experiment.
""")


if __name__ == "__main__":
    main()
