"""The decision layer, behind one swappable interface.

An engine is asked for *patches* to a package that failed validation. It never
decides whether the result is valid - the validator does, after the patch is
applied. That ordering is what keeps an LLM from talking its way to "fixed".

`RulesEngine` is the default so the framework runs with no API key and no
network. Swap in a model engine later without touching the agents: this is the
same pattern METIS uses (one adapter, provider chosen at runtime), and it is how
the "big model vs small open model" comparison gets run on identical code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Patch:
    path: str                 # e.g. "samples[2].qc.concentration"
    action: str               # "set_field"
    value: Any
    reason: str
    confidence: str = "high"  # high | low


class Engine:
    """Base class. `name` is written into the ledger for every step it touches."""
    name = "none"

    def propose_patches(self, package: dict, report, contract: dict) -> list[Patch]:
        return []

    def propose_terms(self, keys: list[str], crate: dict, vocab=None) -> dict:
        """Map local keys a lab invented onto terms that resolve.

        Returns {key: {"term": curie, "why": str, "confidence": str}}. A proposal
        is a suggestion for a human, never an edit: the caller records it and
        leaves the key unaligned, so the handover still fails until somebody
        confirms it into vocabulary/core.json or a lab file.

        This is the one task in the framework where a model is clearly better
        than rules, which makes it the honest place to measure one.
        """
        return {}


class RulesEngine(Engine):
    """Deterministic repairs, no model, no network.

    Only fixes what can be fixed without inventing data. Everything else is left
    for escalation on purpose - guessing which well a sample really sat in would
    be fabricating a lab record, which is worse than a failed handover.
    """
    name = "rules"

    def propose_patches(self, package: dict, report, contract: dict) -> list[Patch]:
        profile = contract.get("x-dbtl-profile", {})
        # required_quantities is keyed by contract, so the same profile serves
        # every handover of a use case.
        name = contract.get("properties", {}).get("contract", {}).get("const", "")
        wanted = (profile.get("required_quantities") or {}).get(name, [])
        expected = {q["quantity"]: q for q in wanted}
        patches: list[Patch] = []

        for err in report.errors:
            # A measurement lost its unit in the instrument export. The profile
            # declares the unit that quantity must be in, so it can be restored
            # without inventing anything.
            if err.code == "missing_field" and err.path.endswith(".unit"):
                holder = _resolve(package, _split(err.path)[:-1])
                quantity = holder.get("quantity") if isinstance(holder, dict) else None
                want = expected.get(quantity)
                if want and want.get("unit"):
                    patches.append(Patch(
                        path=err.path, action="set_field", value=want["unit"],
                        reason=f"profile '{profile.get('name')}' fixes {quantity} in "
                               f"{want['unit']}; the export dropped the column",
                        confidence="high"))

            # The crate's checksum is derivable from the crate. Computing it
            # invents nothing - it is the one repair the Design -> Build handover
            # genuinely allows, and it is worth having precisely because it shows
            # how few of that handover's failures are mechanical.
            if err.code == "missing_field" and err.path == "crate_ref.checksum":
                crate = package.get("crate")
                if crate:
                    from framework.kg import crate_checksum
                    patches.append(Patch(
                        path="crate_ref.checksum", action="set_field",
                        value=crate_checksum(crate),
                        reason="computed over the inlined crate; the descriptor is "
                               "its own evidence",
                        confidence="high"))
        return patches

    def propose_terms(self, keys: list[str], crate: dict, vocab=None) -> dict:
        """Synonym matching, and nothing more.

        A rules engine can recognise that `storage_temperature_c` is the key it
        already knows as `freezer_temp`. It cannot look at `box_temp_c`, work out
        that a box is a freezer rack, and decide whether ENVO, OBI or a minted
        term is the right home for it. That gap is the argument for a model here,
        and the ledger will show exactly how often it mattered.
        """
        from framework.vocab import DEFAULT
        alignment = (vocab or DEFAULT).alignment

        def norm(key: str) -> str:
            text = "".join(c for c in key.lower() if c.isalnum())
            for suffix in ("degc", "celsius", "c", "m", "id"):
                if text.endswith(suffix) and len(text) > len(suffix) + 2:
                    text = text[: -len(suffix)]
            return text

        known = {norm(k): (k, v) for k, v in alignment.items()}
        out = {}
        for key in keys:
            hit = known.get(norm(key))
            if hit:
                out[key] = {"term": hit[1]["term"], "confidence": "high",
                            "why": f"string match on the known key {hit[0]!r}"}
        return out


def _resolve(package: dict, parts: list):
    cur: Any = package
    for part in parts:
        try:
            cur = cur[part]
        except (KeyError, IndexError, TypeError):
            return None
    return cur


def apply_patch(package: dict, patch: Patch) -> bool:
    """Apply a patch in place. Returns False if the path does not resolve."""
    cur: Any = package
    parts = _split(patch.path)
    for part in parts[:-1]:
        if isinstance(part, int):
            if not isinstance(cur, list) or part >= len(cur):
                return False
            cur = cur[part]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return False
            cur = cur[part]
    last = parts[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last >= len(cur):
            return False
        cur[last] = patch.value
    else:
        if not isinstance(cur, dict):
            return False
        cur[last] = patch.value
    return True


def _split(path: str) -> list:
    """'samples[2].qc.unit' -> ['samples', 2, 'qc', 'unit']"""
    out: list = []
    for chunk in path.split("."):
        name, _, rest = chunk.partition("[")
        if name:
            out.append(name)
        while rest:
            idx, _, rest = rest.partition("]")
            if idx:
                out.append(int(idx))
            rest = rest.lstrip("[")
    return out
