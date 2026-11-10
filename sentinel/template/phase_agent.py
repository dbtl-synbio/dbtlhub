"""Copy me to write a phase agent.

    cp template/phase_agent.py framework/agents/phase_test_crate.py

A phase agent does the science, writes what it produced into the run's one
crate, and then submits the handover to a sentinel. Three methods, and only
the first one is yours to think about.

If you are writing the *check* at a boundary rather than the work inside a
phase, you want `template/handover_agent.py` instead. The two are different
jobs and it is worth keeping the names apart:

    phase agent     does the work, writes the crate, may be clever
    sentinel agent  checks what crosses a boundary, may refuse

The phase agent is in charge and the sentinel is a submodule it submits to.
That ordering is deliberate: it is what lets a phase agent choose which assays
to run or optimise a library under a budget, because whatever it decides still
has to survive a check somebody else wrote.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from framework.agents.base import Task                                 # noqa: E402
from framework.agents.phase_base import PhaseAgent                     # noqa: E402
from framework.crate_store import CrateStore, now                      # noqa: E402

# TODO import the sentinel this phase hands over to, e.g.
# from framework.agents.sentinel_t2l import TestToLearnAgent


class TODOPhaseAgent(PhaseAgent):
    # TODO name it after the phase, not after the handover.
    name = "phase_TODO"
    phase = "TODO"                      # design | build | test | learn
    consumes = ["TODO_incoming_contract"]
    produces = ["TODO_outgoing_contract"]
    sentinel_class = None               # TODO the sentinel class, or None

    # ---- 1. the science ----------------------------------------------------
    def produce(self, task: Task, store: CrateStore):
        """Run the phase. Return (entities, action, files).

        This is the only method with anything interesting in it, and it is the
        only one that differs between phases. Be as clever here as the science
        needs: choose, rank, optimise, call a model. What you decide will be
        checked, which is what makes it safe to decide.

        Three rules for what you write:

        1. RESOLVE YOUR OWN VOCABULARY FIRST. If your instrument exports
           `od_600` and the agreed term is something else, map it here, before
           writing. Nobody downstream can know what your technician meant.

        2. LOOK UP an identifier, never construct one. The crate already holds
           what the earlier phases wrote; find the entity you mean by what it
           says about itself. A constructed `@id` that is almost right is a
           join to nothing, and in one shared crate it is silent.

        3. ADD what only you know. Do not describe something an earlier phase
           already described. You may fill a gap in its entity; you may not
           change a value it recorded, and the store will refuse if you try.
        """
        # TODO run the phase and keep whatever the package below needs
        results = task.inputs["TODO"]

        entities = [
            # TODO one entry per thing this phase produced.
            {
                "@id": "#TODO/ID",
                "@type": ["TODO:Type"],
                "identifier": "TODO",
                # the join back into what an earlier phase wrote, looked up:
                "prov:wasDerivedFrom": {"@id": "#TODO/the-entity-you-found"},
            },
        ]

        action = {
            # One CreateAction for this phase's run. `object` is what it
            # consumed, `result` is what it produced, and both must already be
            # in the crate.
            "@id": f"#action/{self.phase}-phase",
            "@type": "CreateAction",
            "name": "TODO what ran",
            "instrument": {"@id": "#tool/TODO"},
            "endTime": now(),
            "object": [],
            "result": [],
        }
        entities.append({"@id": "#tool/TODO", "@type": "SoftwareApplication",
                         "name": "TODO", "version": "TODO"})

        files: list[str] = []          # TODO relative paths actually present
        return entities, action, files

    # ---- 2. what the next phase is given -----------------------------------
    def package(self, task: Task, store: CrateStore) -> dict | None:
        """Build the handover package, or return None if this phase hands over
        nothing. Keep the envelope exactly as the contract scaffolds it."""
        return {
            "contract": "TODO_outgoing_contract",
            "contract_version": "0.1.0",
            "profile": self.profile,
            "run_id": store.run_id,
            "produced_by": {"agent": self.name, "tool": "TODO",
                            "engine": self.engine.name},
            "produced_at": now(),
            # TODO the backlink, named after the phase before this one, and
            # filled from coord.path_of(...) - never a path you built yourself.
            "TODO_ref": {"package": task.inputs["TODO_package"],
                         "contract": "TODO", "run_id": store.run_id},
            # TODO the payload
            "reads": task.inputs.get("reads", []),
            "limits": task.inputs.get("limits", []),
        }

    # ---- 3. nothing. The base class does the rest. -------------------------
    # Writing to the crate, reporting what changed, refusing an overwrite or a
    # dangling reference, and submitting to the sentinel are all in
    # framework/agents/phase_base.py. Do not reimplement them here.
