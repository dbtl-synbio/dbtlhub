"""The Design phase, writing into the run's one crate.

The difference from `phase_design.py` is the whole point of the new
arrangement. There, Design produced a crate of its own and handed it on, and
the crate for the next handover was somebody else's problem. Here Design
writes its part into the single crate that the whole run shares, and then
submits the handover to the sentinel.

The entities it writes are the ones the use case's own specification names as
"what is handed over", which Process Run Crate deliberately does not define:
the Plate, the Proteins, the Constructs. The actions it writes are the eleven
steps that produced them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Task                                 # noqa: E402
from framework.agents.phase_base import PhaseAgent                     # noqa: E402
from framework.agents.sentinel_d2b import DesignToBuildAgent           # noqa: E402
from framework.crate_store import CrateStore, now                      # noqa: E402
from framework.kg import align_crate, crate_checksum                   # noqa: E402
from framework.vocab import load_vocabulary                           # noqa: E402
from usecases.bioprospecting import sampling                           # noqa: E402

CONFORMS_TO = ["https://w3id.org/ro/crate/1.1",
               "https://w3id.org/ro/wfrun/process/0.6"]


class DesignPhaseAgent(PhaseAgent):
    name = "phase_design"
    phase = "design"
    produces = ["design_to_build"]
    sentinel_class = DesignToBuildAgent

    def produce(self, task: Task, store: CrateStore):
        n = task.inputs.get("n", 6)
        faults = task.inputs.get("faults")
        crate, items = sampling.design_crate(n=n, faults=faults)
        self._items = items

        # Align BEFORE writing. The lab writes freezer_temp and gps_lat; those
        # are this site's words, and the shared crate is not the place for
        # them. Under the old arrangement the next agent aligned what it was
        # given; now the phase that owns the words resolves them itself, which
        # is both earlier and more honest - nobody else can know what the
        # technician meant.
        vocab = load_vocabulary(*( [self.lab] if self.lab else [] ))
        crate, alignment = align_crate(crate, vocab)
        self._alignment = alignment

        # Everything the pipeline recorded, minus the two entries that
        # describe the crate itself - the store owns those, because the crate
        # belongs to the run and not to this phase.
        entities = [e for e in crate["@graph"]
                    if isinstance(e, dict)
                    and e.get("@id") not in ("ro-crate-metadata.json", "./")]

        action = {
            "@id": "#action/design-phase",
            "@type": "CreateAction",
            "name": "Run the Design phase",
            "description": f"Selected {len(items)} candidates from the "
                           f"metagenome assembly.",
            "instrument": {"@id": "#tool/design-pipeline"},
            "endTime": now(),
            "result": [{"@id": it["crate_entity"]} for it in items],
        }
        entities.append({"@id": "#tool/design-pipeline",
                         "@type": "SoftwareApplication",
                         "name": "bioprospecting design pipeline (simulated)",
                         "version": "0.1.0"})
        return entities, action, []

    def package(self, task: Task, store: CrateStore) -> dict:
        """The Design to Build handover, built from the crate just written."""
        items = self._items
        return {
            "contract": "design_to_build",
            "contract_version": "0.1.0",
            "profile": self.profile,
            "run_id": store.run_id,
            "produced_by": {"agent": self.name, "tool": "design pipeline",
                            "engine": self.engine.name},
            "produced_at": now(),
            "crate_ref": {
                "path": str(store.path.relative_to(Path(__file__).resolve()
                                                   .parent.parent.parent)),
                "conforms_to": list(CONFORMS_TO),
                "root": "./",
                "checksum": crate_checksum(store.crate),
            },
            "crate": store.crate,
            "crate_ref_missing_files": [],
            "order": sampling.order_from_crate(
                items, container=task.inputs.get("container", "ORDPLATE-1")),
            "bindings": [{"design_item_id": it["design_item_id"],
                          "crate_entity": it["crate_entity"]} for it in items],
            "alignment": self._alignment,
            "reads": task.inputs.get("reads", []),
            "limits": task.inputs.get("limits", []),
        }
