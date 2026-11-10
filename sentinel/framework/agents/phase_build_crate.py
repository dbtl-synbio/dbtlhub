"""The Build phase, writing into the same crate Design wrote.

This is where the single-crate arrangement earns itself. Build does not
describe the constructs again - Design already did, in the same `@graph`. It
adds what it alone knows: which well each construct went into, what the QC
instrument read, and which ones never arrived. The construct entity gains a
well position; it is not replaced.

The store refuses an overwrite. If Build tried to record a different sequence
for a construct Design had already described, that is not a validation failure
to be repaired - it is two phases disagreeing about what exists, and it
escalates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Task                                 # noqa: E402
from framework.agents.phase_base import PhaseAgent                     # noqa: E402
from framework.agents.sentinel_b2t import BuildToTestAgent             # noqa: E402
from framework.crate_store import CrateStore, now                      # noqa: E402
from usecases.bioprospecting import instruments as bp                  # noqa: E402


class BuildPhaseAgent(PhaseAgent):
    name = "phase_build"
    phase = "build"
    consumes = ["design_to_build"]
    produces = ["build_to_test"]
    sentinel_class = BuildToTestAgent

    def produce(self, task: Task, store: CrateStore):
        faults = set(task.inputs.get("faults") or [])
        container = task.inputs.get("container", "PLATE-1")
        panel = task.inputs["panel"]

        ot2 = bp.ot2_worklist(panel, container=container, faults=faults)
        qc_rows = bp.tapestation(ot2["worklist"], faults=faults)
        self._panel = panel
        self._qc = qc_rows
        self._design_package = task.inputs.get("design_package", "")

        # Look the Design entity up in the shared crate; do not construct its
        # identifier. Guessing an @id is how a join to nothing gets written,
        # and in one crate that mistake is silent.
        made = self._design_entities(store)

        entities = [{"@id": f"#plate/{container}", "@type": "dbtl:Plate",
                     "identifier": container, "dbtl:format": "96 wells"}]
        for row in qc_rows:
            pos = row["position"]
            sample = f"BP1-{pos[0]}{int(pos[1:]):02d}"
            entities.append({
                "@id": f"#sample/{sample}",
                "@type": ["bioschemas:BioSample", "dbtl:BuiltSample"],
                "identifier": sample,
                "dbtl:storageContainer": row["container_id"],
                "dbtl:storagePosition": pos,
                # The join back into what Design wrote, in the same graph.
                "prov:wasDerivedFrom": {"@id": made[row["design_item_id"]]},
                "dbtl:verdict": row["verdict"],
            })

        action = {
            "@id": "#action/build-phase",
            "@type": "CreateAction",
            "name": "Build the candidate panel",
            "description": f"Liquid handling and QC over {len(qc_rows)} wells.",
            "instrument": {"@id": "#tool/ot2"},
            "endTime": now(),
            "object": [{"@id": made[r["design_item_id"]]} for r in qc_rows],
            "result": [{"@id": f"#sample/BP1-{r['position'][0]}"
                               f"{int(r['position'][1:]):02d}"} for r in qc_rows],
        }
        entities += [
            {"@id": "#tool/ot2", "@type": "SoftwareApplication",
             "name": "Opentrons OT-2 (simulated)", "version": "7.0"},
            {"@id": "#tool/tapestation", "@type": "SoftwareApplication",
             "name": "Agilent TapeStation 4200 (simulated)", "version": "4200"},
        ]
        return entities, action, []

    @staticmethod
    def _design_entities(store: CrateStore) -> dict:
        """design_item_id -> the @id Design actually used for the thing built.

        The construct that goes into a well is the codon-optimised sequence,
        not the protein it was predicted from, so this picks the entity whose
        name says so rather than the first match.
        """
        out = {}
        for entity in store.crate["@graph"]:
            ref = entity.get("@id", "")
            if not ref.startswith("#seq/"):
                continue
            item = ref[len("#seq/"):].replace("-opt", "")
            if ref.endswith("-opt") or item not in out:
                out[item] = ref
        return out

    def package(self, task: Task, store: CrateStore) -> dict:
        samples = []
        for row in self._qc:
            pos = row["position"]
            samples.append({
                "sample_id": f"BP1-{pos[0]}{int(pos[1:]):02d}",
                "design_item_id": row["design_item_id"],
                "location": {"container_id": row["container_id"], "position": pos},
                "qc": {"measurements": row["measurements"], "verdict": row["verdict"]},
            })
        return {
            "contract": "build_to_test",
            "contract_version": "0.2.0",
            "profile": self.profile,
            "run_id": store.run_id,
            "produced_by": {"agent": self.name,
                            "tool": "OT-2 + TapeStation (simulated)",
                            "engine": self.engine.name},
            "produced_at": now(),
            "design_ref": {"package": self._design_package,
                           "contract": "design_to_build",
                           "run_id": store.run_id,
                           "items": self._panel},
            "target_list": task.inputs.get("target_list", []),
            "samples": samples,
            "not_delivered": task.inputs.get("not_delivered", []),
            "provenance": [
                {"step": "liquid handling", "tool": "Opentrons OT-2", "ref": "run_log"},
                {"step": "product QC", "tool": "Agilent TapeStation 4200"},
            ],
            "reads": task.inputs.get("reads", []),
            "limits": task.inputs.get("limits", []),
        }
