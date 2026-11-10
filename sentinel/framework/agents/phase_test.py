"""The Test phase agent.

Consumes a validated Build -> Test package, runs the plate reader, and emits the
Test -> Learn handover. It only ever sees samples the sentinel agent let through,
which is the point of putting a contract between the phases.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Agent, Result, Task          # noqa: E402
from framework.ledger import now                               # noqa: E402
from usecases.bioprospecting import instruments as bp          # noqa: E402


class TestAgent(Agent):
    name = "phase_test"
    phase = "test"
    consumes = ["build_to_test"]
    produces = ["test_to_learn"]

    def handle(self, task: Task) -> Result:
        incoming = task.inputs["package"]

        # Only samples that passed Build QC are worth reading.
        usable = [s for s in incoming["samples"] if s["qc"]["verdict"] == "pass"]
        readings = bp.clariostar(usable)

        results = []
        for sample, reading in zip(usable, readings):
            by_q = {m["quantity"]: m for m in reading["measurements"]}
            signal = by_q["absorbance"]["value"] - by_q["blank_absorbance"]["value"]
            results.append({
                "sample_id": sample["sample_id"],
                "design_item_id": sample["design_item_id"],
                "location": sample["location"],
                "measurements": reading["measurements"] + [{
                    "quantity": "blank_corrected_absorbance",
                    "value": round(signal, 4),
                    "unit": "AU",
                    "method": "CLARIOstar 510 nm, blank subtracted",
                }],
            })

        package = {
            "contract": "test_to_learn",
            "contract_version": "0.1.0",
            "profile": incoming["profile"],
            "run_id": incoming["run_id"],
            "produced_by": {"agent": self.name, "tool": "CLARIOstar (simulated)",
                            "engine": "none"},
            "produced_at": now(),
            "build_ref": {"package": f"{incoming['run_id']}/b2t/handover.json"},
            "target_list": incoming.get("target_list", []),
            "results": results,
            "provenance": [{"step": "plate read", "tool": "BMG CLARIOstar Plus"}],
        }

        skipped = len(incoming["samples"]) - len(usable)
        return Result(status="ok", outputs={"package": package},
                      notes=[f"{len(results)} samples read"
                             + (f", {skipped} skipped (failed Build QC)" if skipped else "")])
