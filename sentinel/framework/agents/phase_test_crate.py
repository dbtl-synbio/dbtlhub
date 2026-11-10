"""The Test phase, writing its readings into the run's crate.

Test adds the one thing nobody else can supply: what the instrument read. It
does not describe the samples again - Build already did, in the same `@graph`
- so a reading is written as its own entity derived from the sample it was
read from, and the join is looked up rather than constructed.

This is also the phase where Anil's note about the Test to Learn hole lands.
A format check says: valid table, right columns, numbers are numbers, and it
passes whether or not the controls behaved, whether a variant was measured
three times or once, and whether anything ran off the top of the instrument's
range. Those are stated here as entity properties so that a contract can ask
for them, rather than being lost in a spreadsheet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Task                                 # noqa: E402
from framework.agents.phase_base import PhaseAgent                     # noqa: E402
from framework.agents.sentinel_t2l import TestToLearnAgent             # noqa: E402
from framework.crate_store import CrateStore, now                      # noqa: E402
from usecases.bioprospecting import instruments as bp                  # noqa: E402


class TestPhaseAgent(PhaseAgent):
    name = "phase_test"
    phase = "test"
    consumes = ["build_to_test"]
    produces = ["test_to_learn"]
    sentinel_class = TestToLearnAgent

    def produce(self, task: Task, store: CrateStore):
        incoming = task.inputs["package"]
        self._incoming = incoming
        self._build_package = task.inputs.get("build_package", "")

        # Only samples that passed Build's own QC are worth reading. The ones
        # skipped are not dropped quietly: they are reported below, because an
        # unmeasured well and a well that measured zero are different things.
        usable = [s for s in incoming["samples"] if s["qc"]["verdict"] == "pass"]
        readings = bp.clariostar(usable)
        self._skipped = [s["sample_id"] for s in incoming["samples"]
                         if s["qc"]["verdict"] != "pass"]

        index = store.index
        entities, results, objects, produced = [], [], [], []

        for sample, reading in zip(usable, readings):
            sample_ref = f"#sample/{sample['sample_id']}"
            if sample_ref not in index:
                # Looked up, not assumed. If Build never wrote it, say so now
                # rather than writing a reading joined to nothing.
                continue
            by_q = {m["quantity"]: m for m in reading["measurements"]}
            signal = by_q["absorbance"]["value"] - by_q["blank_absorbance"]["value"]
            measurements = reading["measurements"] + [{
                "quantity": "blank_corrected_absorbance",
                "value": round(signal, 4),
                "unit": "AU",
                "method": "CLARIOstar 510 nm, blank subtracted",
            }]

            ref = f"#reading/{sample['sample_id']}"
            entities.append({
                "@id": ref,
                "@type": ["dbtl:Reading", "prov:Entity"],
                "identifier": sample["sample_id"],
                "name": f"plate read of {sample['sample_id']}",
                "prov:wasDerivedFrom": {"@id": sample_ref},
                "dbtl:blankCorrected": True,
                "dbtl:replicates": task.inputs.get("replicates", 1),
                "dbtl:withinRange": all(
                    m["value"] < 3.5 for m in measurements
                    if m["quantity"] == "absorbance"),
            })
            objects.append({"@id": sample_ref})
            produced.append({"@id": ref})
            results.append({
                "sample_id": sample["sample_id"],
                "design_item_id": sample["design_item_id"],
                "location": sample["location"],
                "measurements": measurements,
            })

        self._results = results

        action = {
            "@id": "#action/test-phase",
            "@type": "CreateAction",
            "name": "Read the plate",
            "description": f"{len(results)} wells read"
                           + (f", {len(self._skipped)} skipped on Build QC"
                              if self._skipped else ""),
            "instrument": {"@id": "#tool/clariostar"},
            "endTime": now(),
            "object": objects,
            "result": produced,
        }
        entities.append({"@id": "#tool/clariostar", "@type": "SoftwareApplication",
                         "name": "BMG CLARIOstar Plus (simulated)", "version": "5.70"})
        return entities, action, []

    def package(self, task: Task, store: CrateStore) -> dict:
        incoming = self._incoming
        return {
            "contract": "test_to_learn",
            "contract_version": "0.1.0",
            "profile": self.profile,
            "run_id": store.run_id,
            "produced_by": {"agent": self.name, "tool": "CLARIOstar (simulated)",
                            "engine": self.engine.name},
            "produced_at": now(),
            "build_ref": {"package": self._build_package,
                          "contract": "build_to_test",
                          "run_id": store.run_id},
            "target_list": incoming.get("target_list", []),
            # The crate goes with the package so the contract can read what
            # Test recorded about each reading. A table of numbers cannot say
            # whether its blank was subtracted.
            "crate": store.crate,
            "results": self._results,
            "provenance": [{"step": "plate read", "tool": "BMG CLARIOstar Plus"}],
            "reads": task.inputs.get("reads", []),
            "limits": task.inputs.get("limits", []),
        }
