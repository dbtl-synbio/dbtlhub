"""Simulated instruments for the bioprospecting use case.

Design is straightforward in silico, so the week focuses on Build -> Test -> Learn.
These three stand in for the wet lab, each emitting what the real device emits:

    OT-2            liquid handling   -> worklist + run log
    TapeStation     PCR product check -> fragment size (bp), concentration (ng/uL)
    CLARIOstar      plate reader      -> absorbance at 510 nm

Every number comes out as a measurement - quantity, value, unit, method - because
that is the shape the contract asks for in both use cases.

Deterministic: same seed, same numbers. `faults` injects the mistakes that really
happen, so the validator has something real to catch.
"""
from __future__ import annotations

import random

WELLS = [f"{row}{col}" for row in "ABCDEFGH" for col in range(1, 13)]
TAPESTATION = "Agilent TapeStation 4200"
READER = "BMG CLARIOstar Plus"


def measurement(quantity, value, unit, method, uncertainty=None) -> dict:
    """The one shape every number travels in."""
    m = {"quantity": quantity, "value": value, "unit": unit, "method": method}
    if uncertainty is not None:
        m["uncertainty"] = {"value": uncertainty, "unit": unit}
    return m


def design_panel(n: int = 12, seed: int = 7) -> list[dict]:
    """The candidate panel Design commits to - here, metagenomic enzyme candidates."""
    rng = random.Random(seed)
    return [{"design_item_id": f"CAND-{i:03d}",
             "accession": f"MGYP:{rng.randrange(10**9, 10**10)}"}
            for i in range(1, n + 1)]


def ot2_worklist(panel: list[dict], container: str = "PLATE-1", seed: int = 7,
                 faults: set[str] | None = None) -> dict:
    """Liquid handling: assign each candidate to a well. Emits worklist + run log."""
    faults = faults or set()
    rows = [{"design_item_id": c["design_item_id"], "container_id": container,
             "position": WELLS[i], "volume_uL": 20.0}
            for i, c in enumerate(panel)]

    log = [f"OT-2 run start, {len(rows)} transfers, {container}"]

    if "double_booked" in faults and len(rows) > 9:
        # The deck shifted and two transfers landed in one well. Recoverable only
        # by re-reading the physical worklist, never by guessing.
        victim, culprit = rows[3], rows[9]
        culprit["position"] = victim["position"]
        log.append(f"WARN tip collision near {victim['position']}, retried")

    # A synthesis that failed, and a worklist that simply does not mention the
    # well. This is the fault nobody sees: every row present is correct, and
    # the plate is one short. Design asked for it, Build never answers for it.
    if "dropped_well" in faults and len(rows) > 4:
        rows.pop(4)

    if "unknown_item" in faults and rows:
        # Build labelled a sample with a candidate Design never committed to.
        # The last row, not a fixed index: `dropped_well` may have removed one
        # already, and a fault injector that crashes on a small panel is a
        # fault injector nobody runs on a small panel.
        rows[-1]["design_item_id"] = "CAND-999"
        log.append("NOTE operator relabelled one tube by hand")

    log.append("OT-2 run complete")
    return {"worklist": rows, "run_log": log}


def tapestation(worklist: list[dict], seed: int = 7,
                faults: set[str] | None = None) -> list[dict]:
    """PCR product check: one QC record per transfer."""
    faults = faults or set()
    rng = random.Random(seed)
    out = []
    for i, row in enumerate(worklist):
        size = rng.choice([1180, 1221, 1240, 1255])
        conc = round(rng.uniform(8.0, 95.0), 1)

        size_m = measurement("fragment_size", size, "bp", TAPESTATION)
        conc_m = measurement("dna_concentration", conc, "ng/uL", TAPESTATION,
                             uncertainty=round(conc * 0.05, 2))

        # The classic export bug: the unit column is dropped on some rows.
        if "missing_units" in faults and i in (2, 7):
            conc_m.pop("unit")

        out.append({
            "design_item_id": row["design_item_id"],
            "container_id": row["container_id"],
            "position": row["position"],
            "measurements": [size_m, conc_m],
            "verdict": "pass" if conc >= 10.0 else "fail",
        })
    return out


def clariostar(samples: list[dict], seed: int = 7) -> list[dict]:
    """Plate reader: absorbance at 510 nm per well, after the enzyme reaction."""
    rng = random.Random(seed + 1)
    out = []
    for s in samples:
        blank = round(rng.uniform(0.03, 0.06), 4)
        signal = round(rng.uniform(0.05, 1.20), 4)
        method = f"{READER}, 510 nm"
        out.append({
            "sample_id": s["sample_id"],
            "location": dict(s["location"]),
            "measurements": [
                measurement("absorbance", signal, "AU", method),
                measurement("blank_absorbance", blank, "AU", method),
            ],
        })
    return out
