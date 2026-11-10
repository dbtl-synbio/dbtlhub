"""The Design phase agent.

In bioprospecting, Design is where almost all the metadata is created and almost
none of it is needed downstream - which is exactly why it gets lost. The agent
runs the (simulated) pipeline and emits two things that must stay joined: the
candidate list, and the crate that says where each candidate came from.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Agent, Result, Task                  # noqa: E402
from usecases.bioprospecting import sampling                           # noqa: E402


class DesignAgent(Agent):
    name = "phase_design"
    phase = "design"
    produces = ["design_to_build"]

    def handle(self, task: Task) -> Result:
        n = task.inputs.get("n", 6)
        faults = task.inputs.get("faults")
        crate, items = sampling.design_crate(n=n, faults=faults)
        return Result(
            status="ok",
            outputs={"crate": crate, "items": items},
            notes=[f"selected {len(items)} candidates over "
                   f"{len(crate['@graph'])} recorded entities",
                   "the crate is written with the lab's own keys; aligning them "
                   "is the next agent's job, not the technician's"],
        )
