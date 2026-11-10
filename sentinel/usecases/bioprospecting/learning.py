"""Simulated Learn -> Design packages for the bioprospecting use case.

Everything here is invented. The point is not the numbers, it is that the
package has the shape Handover 4 requires, and that the faults are ones that
happen for real:

    orphan_evidence   a recommendation cites a measurement that is not in the
                      data the model was given. This is what a hallucinated
                      justification looks like in a package, and it is the
                      failure the handover exists to catch.
    tied_rank         two recommendations claim the same place in the order.
    point_estimate    a prediction with no uncertainty - a ranked list of bare
                      numbers, which Design cannot use to decide where to
                      spend a plate.
    no_prediction     the quantity the profile requires was never predicted.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

RUN = "bp-round-1"


def _result_id(i: int) -> str:
    return f"RES-{i:03d}"


def test_ref(n: int = 6) -> dict:
    """What Test handed Learn: the results the model was fitted on."""
    return {
        "package": f"runs/{RUN}/test_to_learn.json",
        "results": [{"result_id": _result_id(i + 1),
                     "design_item_id": f"CAND-{i + 1:03d}"} for i in range(n)],
    }


def recommendations(n: int = 4, seed: int = 7, faults: set[str] | None = None,
                    n_results: int = 6) -> dict:
    """A Learn -> Design package. With `faults`, a deliberately broken one."""
    faults = faults or set()
    rng = random.Random(seed)
    refs = test_ref(n_results)
    known = [r["result_id"] for r in refs["results"]]

    recs = []
    for i in range(n):
        item = f"CAND-{i + 1:03d}"
        cited = [known[i], known[(i + 1) % len(known)]]
        if "orphan_evidence" in faults and i == 1:
            # The model justified this one with a measurement nobody took.
            cited = [known[i], "RES-099"]

        predictions = [{
            "quantity": "predicted_activity",
            "value": round(rng.uniform(1.8, 9.4), 2),
            "unit": "U/mg",
            "method": "ESM-2 embeddings + ridge regression, 5-fold CV mean",
            "uncertainty": {"value": round(rng.uniform(0.3, 1.9), 2),
                            "unit": "U/mg", "kind": "stdev"},
            "in_training_range": i < 3,
        }]
        if "point_estimate" in faults and i == 0:
            predictions[0].pop("uncertainty")
        if "no_prediction" in faults and i == 2:
            predictions = [{
                "quantity": "predicted_solubility",
                "value": 0.62, "unit": "dimensionless",
                "method": "ESM-2 embeddings + ridge regression",
                "uncertainty": {"value": 0.08, "unit": "dimensionless",
                                "kind": "stdev"},
            }]

        rank = i + 1
        if "tied_rank" in faults and i == 3:
            rank = 1

        recs.append({
            "recommendation_id": f"REC-{i + 1:03d}",
            "rank": rank,
            "proposes": {
                "kind": "variant_of",
                "derived_from_design_item": item,
                "change": rng.choice([
                    "substitute the active-site threonine for serine",
                    "truncate the N-terminal signal peptide",
                    "swap the linker for the 12-residue flexible variant",
                    "codon-optimise for Pichia rather than E. coli",
                ]),
            },
            "evidence": cited,
            "predictions": predictions,
        })

    return {
        "contract": "learn_to_design",
        "contract_version": "0.1.0",
        "profile": "bioprospecting",
        "run_id": RUN,
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": {"agent": "phase_learn", "tool": "scikit-learn 1.5.2",
                        "engine": "none"},
        "test_ref": refs,
        "model": {
            "name": "esm2-ridge-activity",
            "version": "0.3.1+g4c1a77e",
            "trained_on": [RUN],
            "fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "holdout": {"metric": "spearman_rho", "value": 0.61, "n": 12},
        },
        "recommendations": recs,
    }
