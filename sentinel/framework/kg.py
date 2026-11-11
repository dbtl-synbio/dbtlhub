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


BASE = DEFAULT.base


def append_graph(triples, path: str | Path) -> str:
    """Add triples to a graph that already exists, or start one.

    Append-only, like the ledger. A run's graph is written by every step that
    produces something, so by the end of the cycle one file spans Design to
    Learn and a question can be asked once instead of hopping between files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(to_ntriples(triples))
    return str(path)


def lift_package(package: dict, stored_at: str | None = None
                 ) -> list[tuple[str, str, str]]:
    """A handover package -> triples, so the cycle is one graph and not four.

    Deliberately few. The crate already carries the deep provenance of the
    Design phase; what is missing from the graph is the spine that joins the
    handovers to each other and to the things they carry, so that is all this
    adds: the package, what produced it, what it was built from, and one node
    per item with a link to the item upstream that it answers for.

    Without this the chain exists only as file paths in a ledger, and
    "which sediment core is behind this recommendation" is a walk, not a query.
    """
    name = package.get("contract", "package")
    run = package.get("run_id", "adhoc")
    subject = f"<{BASE}run/{run}/{name}>"
    triples: list[tuple[str, str, str]] = [
        (subject, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
         f"<{BASE}Handover>"),
        (subject, f"{BASE}contract", f'"{name}"'),
        (subject, f"{BASE}run", f'"{run}"'),
    ]
    made = package.get("produced_by") or {}
    for key in ("agent", "tool", "engine"):
        if made.get(key):
            triples.append((subject, f"{BASE}{key}", f'"{_escape(made[key])}"'))
    if package.get("produced_at"):
        triples.append((subject, "http://www.w3.org/ns/prov#generatedAtTime",
                        f'"{package["produced_at"]}"'))
    if stored_at:
        triples.append((subject, f"{BASE}storedAt", f'"{_escape(stored_at)}"'))

    # The spine: this package was built from the one before it.
    for field in ("design_ref", "build_ref", "test_ref"):
        ref = package.get(field)
        if isinstance(ref, dict) and ref.get("contract"):
            triples.append((subject, "http://www.w3.org/ns/prov#wasDerivedFrom",
                            f"<{BASE}run/{ref.get('run_id', run)}/"
                            f"{ref['contract']}>"))
    crate_ref = package.get("crate_ref")
    if isinstance(crate_ref, dict) and crate_ref.get("path"):
        triples.append((subject, f"{BASE}crate",
                        f'"{_escape(crate_ref["path"])}"'))

    # One node per thing carried, joined to what it answers for upstream.
    carried = {
        "design_to_build": ("bindings", "design_item_id", "crate_entity",
                            f"{BASE}liftsFrom"),
        "build_to_test": ("samples", "sample_id", "design_item_id",
                          f"{BASE}builtFrom"),
        # A Test result is identified by the sample it was read from, which
        # is also how it joins back to Build. Nothing here invents a new id.
        "test_to_learn": ("results", "sample_id", "design_item_id",
                          f"{BASE}measures"),
    }.get(name)
    if carried:
        rows, own, upstream, link = carried
        for row in (package.get(rows) or []):
            if not isinstance(row, dict) or not row.get(own):
                continue
            node = f"<{BASE}run/{run}/item/{_slug(row[own])}>"
            triples.append((subject, f"{BASE}carries", node))
            triples.append((node, f"{BASE}identifier", f'"{_escape(row[own])}"'))
            if row.get(upstream):
                target = row[upstream]
                triples.append((node, link,
                                f"<{iri(target)}>" if str(target).startswith("#")
                                else f"<{BASE}run/{run}/item/{_slug(target)}>"))

    for rec in (package.get("recommendations") or []):
        if not isinstance(rec, dict) or not rec.get("recommendation_id"):
            continue
        node = f"<{BASE}run/{run}/item/{_slug(rec['recommendation_id'])}>"
        triples.append((subject, f"{BASE}carries", node))
        triples.append((node, f"{BASE}identifier",
                        f'"{_escape(rec["recommendation_id"])}"'))
        # The evidence is the whole point of Handover 4: a recommendation
        # pointing at the measurements it rests on, in the graph.
        for cited in (rec.get("evidence") or []):
            triples.append((node, f"{BASE}restsOn",
                            f"<{BASE}run/{run}/item/{_slug(cited)}>"))
    return triples


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in str(text))


# --------------------------------------------------------------------------- #
# 3. asking the graph something
# --------------------------------------------------------------------------- #

# Both real crates in this project say "this came from that" in schema.org
# terms as well as in PROV, so the default follows both. A caller that wants
# only one dialect passes its own list.
FOLLOW = ("prov:wasDerivedFrom", "prov:wasGeneratedBy", "prov:used",
          "isBasedOn", "isPartOf")


def provenance_of(crate: dict, entity: str, follow=FOLLOW) -> list[dict]:
    """The chain behind one sequence, nearest first.

    This is the answer to the only question that matters in six months: where did
    this come from? With the graph it is a traversal. Without it, it is an email
    to whoever ran the pipeline, if they still work here.
    """
    index = {n["@id"]: n for n in crate.get("@graph", [])
             if isinstance(n, dict) and "@id" in n}

    # RO-Crate has no property pointing from a thing to the action that made
    # it, so a Process Run Crate is walked backwards: find the action whose
    # `result` contains the entity, then take that action's `object`. The
    # validator has done this since it first met somebody else's crate; this
    # helper had not, so the demos could check a crate they could not walk.
    produced_by: dict[str, list[str]] = {}
    for node in index.values():
        if "CreateAction" not in _type_list(node):
            continue
        for made in _id_list(node.get("result")):
            produced_by.setdefault(made, []).append(node["@id"])

    chain, seen, queue = [], {entity}, [entity]
    while queue:
        node = index.get(queue.pop(0))
        if node is None:
            continue
        types = node.get("@type")
        chain.append({"id": node["@id"], "name": node.get("name", ""),
                      "type": types if isinstance(types, str) else "/".join(types or [])})

        nxt = [t for prop in follow for t in _id_list(node.get(prop))]
        nxt += produced_by.get(node["@id"], [])
        if "CreateAction" in _type_list(node):
            nxt += _id_list(node.get("object"))
        for tid in nxt:
            if tid and tid not in seen:
                seen.add(tid)
                queue.append(tid)
    return chain


def _type_list(node: dict) -> list[str]:
    value = node.get("@type")
    return value if isinstance(value, list) else [value] if value else []


def _id_list(value) -> list[str]:
    if isinstance(value, dict):
        return [value["@id"]] if "@id" in value else []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_id_list(item))
        return out
    return [value] if isinstance(value, str) else []


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
