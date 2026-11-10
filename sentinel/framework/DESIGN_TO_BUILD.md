# Design → Build: the handover with two audiences

```bash
python3 demo_d2b.py     # no dependencies, no API key, no network
```

## The problem, stated precisely

The synthesis provider needs almost nothing: a list of sequences and the well
each one goes into. Everything that made those sequences — the station the
sediment core came from, the freezer it is in, the assembler version, the HMM
profile that scored the hit, the person who held the corer — is irrelevant to
them and essential to us.

So this handover is a **projection**, and projection is where traceability dies.
The order is what everyone needs tomorrow; the crate is what someone needs in two
years. Whoever is under time pressure sends the order and means to write the rest
up later.

The contract's job is to make the projection safe: **you may strip the metadata
for the provider only if what you stripped is still attached, aligned and
connected to what you sent.**

## What the agent is, and what it is not

An RO-Crate metadata descriptor is JSON-LD. **JSON-LD is RDF.** Turning a crate
into a knowledge graph is therefore one call:

```python
rdflib.Graph().parse("ro-crate-metadata.json", format="json-ld")
```

Writing an agent to do that would be writing an agent to call a parser. The
agent exists for the three things the parser cannot do:

| | what it does | deterministic? |
|---|---|---|
| **align** | the lab wrote `freezer_temp: -80`; no query can use that. Map every invented key onto a term that resolves | no — **this is the only place a model earns its keep** |
| **normalise** | fold a bare value + `unit` into the `quantity/value/unit/method` shape the other three contracts already use, so one query spans the whole cycle | yes |
| **verify** | walk the graph and prove every ordered sequence is connected to a physical sample | yes — it is a validator check, not an agent decision |

That middle column is the finding worth reporting. In the whole framework there
is exactly **one** task where an LLM is clearly better than a rule: mapping an
unknown key onto the right term out of ENVO, MIxS, OBI, EDAM, PROV-O and Darwin
Core. A rules engine can match `storage_temperature_c` to a key it already
knows; it cannot look at `box_temp_c`, work out that the box is a freezer rack,
and judge whether an existing term fits or one must be minted. The demo shows it
failing to, on purpose.

**But the mapping is never the agent's to make at run time.** A term chosen by a
model on each run is not reproducible, and two teams checking the same crate
would reach different verdicts. So the vocabulary is three layers, and only the
last one is a model:

| | | who decides |
|---|---|---|
| `vocabulary/core.json` | the terms this project agreed on | a pull request |
| `vocabulary/labs/<lab>.json` | how one site spells them | that site, in a file |
| `Engine.propose_terms()` | a key neither file covers | reported, **never applied** |

A lab file may only point at a term `core.json` already declares - `load_vocabulary`
raises if it does not. A site renames; it does not coin. Without that rule, three
labs means three vocabularies and the graphs stop merging.

And a proposed term is **never applied**. It goes into the result for review, the
key stays unaligned, and the handover still fails. That ordering is the whole
difference between a model helping and a model quietly inventing an ontology.

## The stack

Everything below is one `pip install` and runs on a laptop. Nothing needs a
server, which matters for a five-day week.

| layer | use | why this one |
|---|---|---|
| **crate** | [`ro-crate-py`](https://github.com/ResearchObject/ro-crate-py) | writes and reads crates with the community's own library; do not hand-roll the descriptor |
| **crate profile** | [Process Run Crate](https://w3id.org/ro/wfrun/process/0.5) | *made* for "this entity was produced by this action with these parameters" — exactly our chain. Declaring a profile is what makes a crate interpretable by someone else's code |
| **graph** | `rdflib` | parses JSON-LD directly; pure Python |
| **store + query** | [`pyoxigraph`](https://github.com/oxigraph/oxigraph) | embedded, single file, full SPARQL 1.1. Neo4j needs a server and speaks Cypher, which nobody else in the project will be able to re-run |
| **validation** | `pyshacl` | SHACL is to graphs what JSON Schema is to documents. See `contracts/shapes/design_to_build.shacl.ttl` |
| **identifiers** | `identifiers.org` / ROR / ORCID, and a **minted `w3id.org` namespace** | until `dbtl:` resolves, every id we create is local and two teams' graphs cannot be merged |
| **vocabularies** | PROV-O · schema.org · Bioschemas · Darwin Core · MIxS · ENVO · OBI · EDAM · QUDT | see the table below |

### Which vocabulary for what

Resist the urge to invent. One term per job, and only mint a `dbtl:` term when a
real search has failed — `vocabulary/core.json` records which ones those are and
why, so the list is reviewable rather than accidental.

| what you are describing | use |
|---|---|
| X was derived from Y, this activity used/generated that | **PROV-O** |
| files, datasets, people, software, instruments | **schema.org** (RO-Crate's own base) |
| samples, proteins, workflows as first-class types | **Bioschemas** |
| where and when something was collected, by whom | **Darwin Core** (`dwc:`) |
| sample checklist fields: depth, env_medium, host | **MIxS** |
| biome, environmental material | **ENVO** |
| assays, specimens, the act of measuring | **OBI** |
| what a tool does, what format its data is in | **EDAM** — and this is the join to the `dbtlhub` bio.tools classification |
| units, quantity kinds | **QUDT** (or UO) |
| storage temperature, rack position, sequence checksum | **minted `dbtl:`** — no suitable term found; flagged `proposed` in `vocab.py` |

> The minted namespace is a **deliverable, not a detail**. `w3id.org` is a pull
> request to a public repository. Open it in the first session, not on Friday.

## Where it sits in the framework

```
framework/
  vocab.py                    loads the vocabulary; enforces the anti-drift rule
  vocabulary/core.json        the agreed terms - the shared deliverable
  vocabulary/labs/*.json      each site's own spellings, pointing at core terms
  kg.py                       align -> normalise -> lift to triples; the SPARQL questions
  agents/
    sentinel_base.py             translate -> validate -> repair -> escalate, once, for all handovers
    phase_design.py           runs the (simulated) selection pipeline, emits crate + items
    crate_to_graph.py         THE AGENT: the vocabulary gate
    sentinel_d2b.py              the handover: projects the order, keeps the crate, binds the two
  contracts/
    design_to_build.schema.json      the order, the crate_ref, the bindings
    shapes/design_to_build.shacl.ttl the same graph rules as SHACL
usecases/bioprospecting/sampling.py  the chain: site -> sample -> DNA -> reads -> ... -> FASTA
```

`SentinelAgent` is the part to copy. Every handover does the same four things in
the same order and only `translate` differs, so a new sentinel agent is a
subclass with one method — which is what makes four contracts a week's work for
two pairs rather than four codebases.

## The three checks a JSON Schema cannot express

| check | catches |
|---|---|
| `provenance_chain` | a FASTA whose derivation stops in mid-air. **The one that matters.** |
| `required_provenance` | the context that cannot be recovered later: coordinates, collection date, storage temperature. The metadata counterpart of `required_quantities` — same mechanism, same profile file |
| `empty` on `alignment.unaligned` | a key nobody mapped, i.e. metadata that is really just a note |

An error is never auto-fixed when the contract's own `fix_hint` begins with
*"not auto-fixable"*. The decision lives in the contract, in prose a reviewer
reads, not in a Python set only the author knows about.

In the demo's broken run, **zero** of the failures are repairable. The one repair
this handover allows is the crate checksum, because a checksum is derivable and a
provenance step is not. That ratio is the honest result: this handover is not a
place where agents fix things, it is a place where they refuse to ship.

## Same contract, other use case

The profile carries the difference, not the code. In biomanufacturing the chain
roots in a **registered part and a chassis strain** rather than a field site:
`root_type` becomes `bioschemas:BioChemEntity`, the required properties become a
registry accession and a strain collection id. The traversal, the shapes and the
agent are untouched.

## Open, in priority order

1. **Mint the `w3id.org` namespace.** Blocks graph merging between teams.
2. Review the `proposed` terms in `vocabulary/core.json` with someone who knows ENVO and OBI.
   Six terms, one hour, and they stop being ours alone.
3. Swap `lift()` for rdflib and run `pyshacl` against the shapes — they are
   written but have not been executed.
4. Ingest a **real** crate. The chain here is simulated; the shape of the
   failures is not.
5. A model engine for `propose_terms`, and the measurement: how often does it
   propose a term a human accepts unchanged? The ledger records `engine` on every
   step, so this is a query over `runs/*/ledger.jsonl`, not a separate experiment.
6. Decide what the provider sends **back**, and check it: a returned sequence that
   does not hash to its order line is not the thing we ordered. Today the contract
   can detect this and nothing acts on it.
