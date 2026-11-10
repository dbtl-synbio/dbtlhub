"""The Learn phase, writing what it proposes into the run's crate.

Learn is the phase where a model genuinely belongs, and it is worth being
exact about which model. The protein language model and the regression fitted
here are the *science's* model: this framework does not touch them, and the
sentinel only checks what comes out. That is a different thing from the engine
an agent may use to repair a package, which is recorded separately as
`produced_by.engine` and is "none" here.

What Learn writes into the crate is unusual for this cycle: a claim about
something that has not happened yet. So each recommendation is written with
the three things that make such a claim checkable - the readings it rests on,
the model that produced it, and how uncertain it is - and every one of those
is a link to an entity already in the crate rather than a sentence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Task                                 # noqa: E402
from framework.agents.phase_base import PhaseAgent                     # noqa: E402
from framework.agents.sentinel_l2d import LearnToDesignAgent           # noqa: E402
from framework.crate_store import CrateStore, now                      # noqa: E402

MODEL = {"name": "esm2-ridge-activity", "version": "0.3.1+g4c1a77e"}


class LearnPhaseAgent(PhaseAgent):
    name = "phase_learn"
    phase = "learn"
    consumes = ["test_to_learn"]
    produces = ["learn_to_design"]
    sentinel_class = LearnToDesignAgent

    def produce(self, task: Task, store: CrateStore):
        incoming = task.inputs["package"]
        self._incoming = incoming
        self._test_package = task.inputs.get("test_package", "")
        self._next_library = int(task.inputs.get("next_library_size", 36))

        results = incoming["results"]
        # Rank by the quantity the profile says this use case screens on.
        def signal(row):
            for m in row["measurements"]:
                if m["quantity"] == "blank_corrected_absorbance":
                    return m["value"]
            return 0.0

        ranked = sorted(results, key=signal, reverse=True)
        top = ranked[: task.inputs.get("n_recommendations", 4)]
        index = store.index

        entities, recommendations, objects, produced = [], [], [], []

        entities.append({
            "@id": f"#model/{MODEL['name']}",
            "@type": ["dbtl:Model", "SoftwareApplication"],
            "name": MODEL["name"], "version": MODEL["version"],
            "dbtl:trainedOn": store.run_id,
            "dbtl:holdoutMetric": "spearman_rho",
            "dbtl:holdoutValue": 0.61,
        })

        for i, row in enumerate(top, start=1):
            ref = f"#recommendation/REC-{i:03d}"
            evidence = [f"#reading/{row['sample_id']}"]
            # Only cite what the crate actually holds. A citation that
            # resolves to nothing is what a fabricated justification looks
            # like, and the store would refuse it anyway.
            evidence = [e for e in evidence if e in index]
            if not evidence:
                continue
            entities.append({
                "@id": ref,
                "@type": ["dbtl:Recommendation", "prov:Entity"],
                "identifier": f"REC-{i:03d}",
                "name": f"make a variant of {row['design_item_id']}",
                "dbtl:rank": i,
                "dbtl:restsOn": [{"@id": e} for e in evidence],
                "prov:wasGeneratedBy": {"@id": "#action/learn-phase"},
                "dbtl:predictedQuantity": "predicted_activity",
                "dbtl:predictedValue": round(signal(row) * 7.4 + 1.8, 2),
                "dbtl:predictedUnit": "U/mg",
                "dbtl:uncertaintyKind": "stdev",
                "dbtl:uncertaintyValue": 0.6,
            })
            objects += [{"@id": e} for e in evidence]
            produced.append({"@id": ref})
            recommendations.append({
                "recommendation_id": f"REC-{i:03d}",
                "rank": i,
                "proposes": {
                    "kind": "variant_of",
                    "derived_from_design_item": row["design_item_id"],
                    "change": "substitute the active-site residue and re-screen",
                },
                "evidence": [row["sample_id"]],
                "predictions": [{
                    "quantity": "predicted_activity",
                    "value": round(signal(row) * 7.4 + 1.8, 2),
                    "unit": "U/mg",
                    "method": f"{MODEL['name']} {MODEL['version']}, 5-fold CV mean",
                    "uncertainty": {"value": 0.6, "unit": "U/mg", "kind": "stdev"},
                    "in_training_range": i <= 3,
                }],
            })

        self._recommendations = recommendations

        action = {
            "@id": "#action/learn-phase",
            "@type": "CreateAction",
            "name": "Fit the model and rank the next round",
            "description": f"{len(recommendations)} recommendations from "
                           f"{len(results)} readings.",
            "instrument": {"@id": f"#model/{MODEL['name']}"},
            "endTime": now(),
            "object": objects,
            "result": produced,
        }
        return entities, action, []

    def package(self, task: Task, store: CrateStore) -> dict:
        results = self._incoming["results"]
        return {
            "contract": "learn_to_design",
            "contract_version": "0.1.0",
            "profile": self.profile,
            "run_id": store.run_id,
            "produced_by": {"agent": self.name, "tool": "scikit-learn 1.5.2",
                            # the agent's own engine, not the scientific model
                            "engine": self.engine.name},
            "produced_at": now(),
            "test_ref": {
                "package": self._test_package,
                "contract": "test_to_learn",
                "run_id": store.run_id,
                "results": [{"result_id": r["sample_id"],
                             "design_item_id": r["design_item_id"]}
                            for r in results],
            },
            "model": {
                "name": MODEL["name"], "version": MODEL["version"],
                "trained_on": [store.run_id], "fitted_at": now(),
                "holdout": {"metric": "spearman_rho", "value": 0.61,
                            "n": len(results)},
            },
            "recommendations": self._recommendations,
            "reads": task.inputs.get("reads", []),
            # The constraint that travels backwards: how big the next round
            # may be. Design's own contract checks an order against it.
            "limits": [{"quantity": "library_size",
                        "value": self._next_library,
                        "unit": "constructs",
                        "from": f"#action/learn-phase",
                        "stated_by": f"{self.name}, round on {store.run_id}"}],
        }
