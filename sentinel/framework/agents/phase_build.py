"""The Build phase agent.

It knows the tools of its phase, runs them, and wraps what they emit into a
handover package for the next contract. It does not judge its own output - the
sentinel agent and the validator do that.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Agent, Result, Task          # noqa: E402
from framework.ledger import now                               # noqa: E402
from usecases.bioprospecting import instruments as bp          # noqa: E402


class BuildAgent(Agent):
    name = "phase_build"
    phase = "build"
    consumes = ["design_to_build"]
    produces = ["build_to_test"]

    def handle(self, task: Task) -> Result:
        panel = task.inputs["panel"]
        run_id = task.inputs["run_id"]
        faults = set(task.inputs.get("faults") or [])
        container = task.inputs.get("container", "PLATE-1")

        # --- run the phase's instruments ---
        ot2 = bp.ot2_worklist(panel, container=container, faults=faults)
        qc_rows = bp.tapestation(ot2["worklist"], faults=faults)

        # --- wrap into the handover package ---
        samples = []
        for row in qc_rows:
            pos = row["position"]
            samples.append({
                "sample_id": f"BP1-{pos[0]}{int(pos[1:]):02d}",
                "design_item_id": row["design_item_id"],
                "location": {"container_id": row["container_id"], "position": pos},
                "qc": {"measurements": row["measurements"], "verdict": row["verdict"]},
            })

        package = {
            "contract": "build_to_test",
            "contract_version": "0.2.0",
            "profile": "bioprospecting",
            "run_id": run_id,
            "produced_by": {"agent": self.name, "tool": "OT-2 + TapeStation (simulated)",
                            "engine": "none"},
            "produced_at": now(),
            "design_ref": {"package": task.inputs.get("design_package", "design/handover.json"),
                           "items": panel},
            "target_list": task.inputs.get("target_list", []),
            "samples": samples,
            "provenance": [
                {"step": "liquid handling", "tool": "Opentrons OT-2", "ref": "run_log"},
                {"step": "product QC", "tool": "Agilent TapeStation 4200"},
            ],
        }

        return Result(status="ok", outputs={"package": package},
                      evidence=ot2["run_log"],
                      notes=[f"{len(samples)} samples built"] +
                            ([f"faults injected: {', '.join(sorted(faults))}"] if faults else []))
