"""Crate -> graph: the mechanics.

Read this first, because it decides how much of the agent is actually an agent:

    An RO-Crate metadata descriptor is JSON-LD. JSON-LD *is* RDF. Turning a
    crate into a graph is therefore a parser, not an inference:

        rdflib.Graph().parse("ro-crate-metadata.json", format="json-ld")

    One line, and it is already a knowledge graph.

So the agent does not "build the graph". It does the three things the parser
cannot:

    1. align     the lab wrote `freezer_temp`; no query can use that. Map local
                 keys onto terms that resolve (vocabulary/core.json). This is the
                 part that needs judgement, and the part a model can help with.
    2. normalise fold a bare value + unit into the same measurement shape the
                 other three contracts use, so one query works across phases.
    3. verify    walk the graph and prove every ordered sequence is connected to
                 a physical sample. That lives in the validator, as a check.

The lifting below is a dependency-free N-Triples writer so the skeleton runs on
any laptop in the room. In the real stack, replace `lift` with rdflib and
`framework/contracts/shapes/` with pyshacl - the vocabulary and the shapes are
the deliverable, not this file.
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.vocab import DEFAULT, Vocabulary

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
STORAGE_TEMP = "dbtl:storageTemperature"
STORAGE_AT = "dbtl:storageCondition"


# --------------------------------------------------------------------------- #
# 1. alignment
# --------------------------------------------------------------------------- #

def align_crate(crate: dict, vocab: Vocabulary | None = None) -> tuple[dict, dict]:
    """Rewrite local keys to agreed terms. Returns (aligned crate, report).

    Nothing is dropped and nothing is guessed: a key with no decision behind it
    survives untouched and is listed in `unaligned`, which the contract requires
    to be empty. A silent drop would be the worst possible behaviour here - the
    metadata would be gone and the handover would pass.
    """
    vocab = vocab or DEFAULT
    out_nodes, confirmed, proposed, missing = [], set(), set(), set()

    for node in crate.get("@graph", []):
        if not isinstance(node, dict):
            continue
        missing.update(vocab.unaligned(node.keys()))
        new: dict = {}
        for key, value in node.items():
            if key.startswith("@") or ":" in key:
                new[key] = value
                continue
            decision = vocab.align(key)
            if decision is None:
                new[key] = value                      # kept, and reported
                continue
            bucket = confirmed if decision["status"] == "confirmed" else proposed
            bucket.add(f"{key} -> {decision['term']}  [{decision['source']}]")
            new[decision["term"]] = value
        out_nodes.append(_fold_measurements(new))

    return ({"@context": crate.get("@context"), "@graph": out_nodes},
            {"confirmed": sorted(confirmed), "proposed": sorted(proposed),
             "unaligned": sorted(missing),
             "vocabulary": ["core", *vocab.labs]})


def _fold_measurements(node: dict) -> dict:
    """A bare number plus a stray `unit` key is not a measurement.

    The other three contracts all demand `quantity + value + unit + method`. If
    the storage temperature arrives as `-80` with a `unit` field beside it, fold
    it into that same shape, so one query answers "give me every measurement in
    this run" across all four handovers.
    """
    if STORAGE_TEMP not in node:
        return node
    unit = node.get("qudt:unit", "degC")
    node[STORAGE_AT] = [{
        "quantity": "storage_temperature", "value": node.pop(STORAGE_TEMP),
        "unit": unit, "method": "freezer log",
    }]
    node.pop("qudt:unit", None)
    return node


# --------------------------------------------------------------------------- #
# 2. lifting to triples
# --------------------------------------------------------------------------- #

def iri(ref: str) -> str:
    """Local crate ids are relative. A graph two teams can merge has no relative ids."""
    if ref.startswith(("http://", "https://")):
        return ref
    prefix, sep, local = ref.partition(":")
    if sep and prefix in DEFAULT.prefixes:
        return DEFAULT.expand(ref)
    return DEFAULT.base + "crate/" + ref.lstrip("#./")


def _predicate(key: str) -> str:
    """A key becomes a predicate IRI, and the route it takes is the audit trail.

    `dwc:eventDate` was aligned by a decision. `hasPart` was resolved by the
    crate's own context, which is what declaring a context is for. Anything left
    lands in a local namespace where it is visible as unfinished work rather than
    disguised as a term - and the contract fails on it anyway.
    """
    if ":" in key:
        return iri(key)
    if key in DEFAULT.context_terms:
        return DEFAULT.prefixes["schema"] + key
    if key in DEFAULT.measurement_terms:
        return DEFAULT.expand(DEFAULT.measurement_terms[key])
    return DEFAULT.base + "local/" + key


# The measurement shape - quantity, value, unit, method - is the same in all
# four contracts, so it is mapped once in vocabulary/core.json rather than per
# use case. QUDT, because it is what an engineer reviewing a unit recognises.


def lift(crate: dict) -> list[tuple[str, str, str]]:
    """Crate -> triples. Objects are '<iri>' or a literal in quotes."""
    triples: list[tuple[str, str, str]] = []
    counter = [0]

    def emit_node(node: dict, subject: str) -> None:
        for key, value in node.items():
            if key == "@id":
                continue
            if key == "@type":
                for t in ([value] if isinstance(value, str) else value):
                    triples.append((subject, RDF_TYPE, f"<{iri(t)}>"))
                continue
            emit_value(subject, _predicate(key), value)

    def emit_value(subject: str, predicate: str, value) -> None:
        if isinstance(value, list):
            for v in value:
                emit_value(subject, predicate, v)
        elif isinstance(value, dict) and "@id" in value:
            triples.append((subject, predicate, f"<{iri(value['@id'])}>"))
        elif isinstance(value, dict):
            counter[0] += 1
            bnode = f"_:b{counter[0]}"
            triples.append((subject, predicate, bnode))
            emit_node(value, bnode)
        elif isinstance(value, bool):
            triples.append((subject, predicate,
                            f'"{str(value).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean>'))
        elif isinstance(value, (int, float)):
            triples.append((subject, predicate,
                            f'"{value}"^^<http://www.w3.org/2001/XMLSchema#decimal>'))
        elif isinstance(value, str):
            looks_like_term = ":" in value and value.partition(":")[0] in DEFAULT.prefixes
            if value.startswith(("http://", "https://")) or looks_like_term:
                triples.append((subject, predicate, f"<{iri(value)}>"))
            else:
                triples.append((subject, predicate, f'"{_escape(value)}"'))

    for node in crate.get("@graph", []):
        if isinstance(node, dict) and "@id" in node:
            emit_node(node, f"<{iri(node['@id'])}>")
    return triples


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def to_ntriples(triples) -> str:
    return "".join(f"{s} <{p}> {o} .\n" for s, p, o in triples)


def write_graph(triples, path: str | Path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_ntriples(triples))
    return str(path)


# --------------------------------------------------------------------------- #
# 3. asking the graph something
# --------------------------------------------------------------------------- #

def provenance_of(crate: dict, entity: str,
                  follow=("prov:wasDerivedFrom", "prov:wasGeneratedBy", "prov:used")
                  ) -> list[dict]:
    """The chain behind one sequence, nearest first.

    This is the answer to the only question that matters in six months: where did
    this come from? With the graph it is a traversal. Without it, it is an email
    to whoever ran the pipeline, if they still work here.
    """
    index = {n["@id"]: n for n in crate.get("@graph", [])
             if isinstance(n, dict) and "@id" in n}
    chain, seen, queue = [], {entity}, [entity]
    while queue:
        node = index.get(queue.pop(0))
        if node is None:
            continue
        types = node.get("@type")
        chain.append({"id": node["@id"], "name": node.get("name", ""),
                      "type": types if isinstance(types, str) else "/".join(types or [])})
        for prop in follow:
            ref = node.get(prop)
            for target in ([ref] if isinstance(ref, dict) else (ref or [])):
                tid = target.get("@id") if isinstance(target, dict) else target
                if tid and tid not in seen:
                    seen.add(tid)
                    queue.append(tid)
    return chain


# The same questions as SPARQL, for when the graph goes into a real store
# (oxigraph is one pip install and one file, and speaks SPARQL 1.1).
SPARQL = {
    "origin_of_a_sequence": """
      PREFIX prov: <http://www.w3.org/ns/prov#>
      PREFIX dwc:  <http://rs.tdwg.org/dwc/terms/>
      SELECT ?sample ?lat ?long ?date WHERE {
        <SEQ> (prov:wasDerivedFrom|prov:wasGeneratedBy|prov:used)+ ?sample .
        ?sample a <https://bioschemas.org/BioSample> ;
                prov:wasGeneratedBy/<http://schema.org/location> ?site .
        ?site dwc:decimalLatitude ?lat ; dwc:decimalLongitude ?long .
        OPTIONAL { ?sample dwc:eventDate ?date }
      }""",
    "every_tool_that_touched_a_candidate": """
      PREFIX prov: <http://www.w3.org/ns/prov#>
      PREFIX schema: <http://schema.org/>
      SELECT DISTINCT ?tool ?biotools WHERE {
        <SEQ> (prov:wasDerivedFrom|prov:wasGeneratedBy|prov:used)+ ?e .
        ?e prov:wasGeneratedBy? ?act . ?act schema:instrument ?tool .
        OPTIONAL { ?act <http://edamontology.org/has_identifier> ?biotools }
      }""",
    "sequences_with_no_physical_origin": """
      PREFIX prov: <http://www.w3.org/ns/prov#>
      SELECT ?seq WHERE {
        ?seq a <http://schema.org/MediaObject> .
        FILTER NOT EXISTS {
          ?seq (prov:wasDerivedFrom|prov:wasGeneratedBy|prov:used)+ ?s .
          ?s a <https://bioschemas.org/BioSample> .
        }
      }""",
}


def load_crate(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def crate_checksum(crate: dict) -> str:
    import hashlib
    blob = json.dumps(crate, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()
