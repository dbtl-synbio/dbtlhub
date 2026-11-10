"""The vocabulary: three layers, and only one of them is code.

A lab writes `freezer_temp: -80`. Nobody can query that, because `freezer_temp`
is a string a technician invented. Mapping it onto a term that resolves is the
one genuinely hard decision in this handover - so the question is *who decides*,
and the answer is deliberately not "the agent, at runtime".

A mapping decided by a model at runtime is not reproducible: run it twice, get
two answers, and two teams checking the same crate reach different verdicts. A
contract that does that is not a contract. So the mapping is a **file**, and the
engine may only propose lines to add to it.

    vocabulary/core.json          the terms this project has agreed on, and the
                                  common keys that map to them. Reviewed in pull
                                  requests. This is the shared deliverable.

    vocabulary/labs/<lab>.json    how one site spells things. It may ONLY point
                                  at terms already declared in core.json - a lab
                                  renames, it does not coin. Without that rule,
                                  three labs means three vocabularies and the
                                  graphs stop merging.

    Engine.propose_terms()        for a key neither file covers. Reported, never
                                  applied: the key stays unaligned and the
                                  handover fails until a human adds the line.

That last layer is the only place a model touches the vocabulary, and it touches
it as a suggestion in a report, not as an edit to a graph.

    vocab = load_vocabulary("newcastle")
    vocab.align("freezer_temp")      -> {"term": "dbtl:storageTemperature", ...}
    vocab.unaligned(crate_node_keys) -> keys nobody has decided on
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

VOCAB_DIR = Path(__file__).resolve().parent / "vocabulary"


class VocabularyError(ValueError):
    """A lab file broke the one rule that keeps the vocabulary shared."""


@dataclass
class Vocabulary:
    prefixes: dict
    base: str
    context_terms: set
    measurement_terms: dict
    terms: dict
    alignment: dict                     # local key -> {"term", "status", "source"}
    labs: list = field(default_factory=list)

    # -- lookups ------------------------------------------------------------
    def align(self, key: str) -> dict | None:
        """What term does this local key mean? None = nobody has decided yet."""
        return self.alignment.get(key)

    def unaligned(self, keys) -> list[str]:
        """Keys a crate uses that no file covers. These are the agent's work."""
        return sorted({k for k in keys
                       if not k.startswith("@") and ":" not in k
                       and k not in self.context_terms
                       and k not in self.alignment})

    def expand(self, curie: str) -> str:
        """'dwc:eventDate' -> the full IRI. Unknown prefixes are left alone."""
        if curie.startswith(("http://", "https://", "_:")):
            return curie
        prefix, sep, local = curie.partition(":")
        base = self.prefixes.get(prefix)
        return base + local if sep and base else curie

    def proposed_terms(self) -> list[str]:
        """Terms we minted ourselves and nobody outside has reviewed yet."""
        return sorted(t for t, meta in self.terms.items()
                      if meta.get("status") == "proposed")


def load_vocabulary(*labs: str) -> Vocabulary:
    """Load core.json, then overlay each lab's spellings on top.

    Raises VocabularyError if a lab file points at a term core.json does not
    declare. That check is the whole mechanism: it lets a site name things its
    own way while keeping one vocabulary underneath, so two labs' graphs still
    merge. Dropping it would be easier and would quietly defeat the point.
    """
    core = json.loads((VOCAB_DIR / "core.json").read_text())
    terms = core["terms"]

    alignment = {
        key: {"term": term, "status": terms.get(term, {}).get("status", "unknown"),
              "source": "core"}
        for key, term in core["aliases"].items()
    }

    loaded = []
    for lab in labs:
        if not lab:
            continue
        path = VOCAB_DIR / "labs" / f"{lab}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"no vocabulary for lab {lab!r} in {VOCAB_DIR / 'labs'}. "
                f"Known: {sorted(p.stem for p in (VOCAB_DIR / 'labs').glob('*.json'))}")
        data = json.loads(path.read_text())
        for key, term in (data.get("aliases") or {}).items():
            if term not in terms:
                raise VocabularyError(
                    f"{path.name}: {key!r} points at {term!r}, which core.json does "
                    f"not declare. A lab may rename a term, not coin one - add it to "
                    f"core.json in a pull request so everyone gets it.")
            alignment[key] = {"term": term,
                              "status": terms[term].get("status", "unknown"),
                              "source": lab}
        loaded.append(data.get("lab", lab))

    return Vocabulary(
        prefixes=core["prefixes"], base=core["base"],
        context_terms=set(core["context_terms"]),
        measurement_terms=core["measurement_terms"],
        terms=terms, alignment=alignment, labs=loaded,
    )


# A default instance, so code that does not care about a specific lab still
# works. Anything checking a real crate should load that crate's lab.
DEFAULT = load_vocabulary()

PREFIXES = DEFAULT.prefixes
BASE = DEFAULT.base
CONTEXT_TERMS = DEFAULT.context_terms
MEASUREMENT_TERMS = DEFAULT.measurement_terms
ALIGNMENT = DEFAULT.alignment


def expand(curie: str) -> str:
    return DEFAULT.expand(curie)


def align(key: str) -> dict | None:
    return DEFAULT.align(key)


def unaligned(keys) -> list[str]:
    return DEFAULT.unaligned(keys)
