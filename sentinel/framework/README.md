# The framework, in one page

```bash
python3 demo.py     # no dependencies, no API key, no network
```

## The idea in five lines

1. A **contract** says what one phase must hand to the next.
2. A **package** is the handover itself — a JSON file on disk, not an object in memory.
3. The **validator** decides whether a package satisfies its contract. It is deterministic and it is the only authority: an agent never declares its own output valid.
4. **Agents** do the parts that need judgement — reshaping one tool's output into the next tool's input, and repairing what the validator flagged.
5. The **ledger** records every step, including which model ran it.

The contracts are the deliverable. The agents are how the contracts get enforced.

## The common ground between the two use cases

One contract, two profiles. The contract holds what bioprospecting and
biomanufacturing genuinely share:

- every sample traces to a **Design item** and to a **physical location**;
- every number is a **measurement**: `quantity + value + unit + method` travel together — a bare number is not a measurement;
- the **target list** is inherited from Design, with InChIKey;
- the chain back to the previous package is **mandatory**, so a result can always be traced to what was built.

The profile holds only what differs: identifier patterns, the container
vocabulary (`PLATE-1/A4` vs `REACTOR-1/R1`), and which measurements a handover is
incomplete without.

| | bioprospecting | biomanufacturing |
|---|---|---|
| B→T requires | `fragment_size` (bp), `dna_concentration` (ng/uL) | `sequence_verified`, `biomass` (gDW/L) |
| T→L requires | `blank_corrected_absorbance` (AU) | `titre` (mg/gDW) |

That last row is "peak area is not flux", made machine-checkable. Biomanufacturing
demands biomass at B→T precisely because T→L cannot produce a titre per gDW without it.

Section 3 of the demo proves the claim: the same contract passes a biomanufacturing
package, and the identical package fails under the bioprospecting profile with eight
specific errors.

## Map

```
framework/
  contracts/
    build_to_test.schema.json      generic; x-pattern fields are bound by the profile
    test_to_learn.schema.json      generic
    profiles/bioprospecting.json   patterns + required measurements
    profiles/biomanufacturing.json
  validator.py     JSON Schema subset + the two checks a schema cannot express
  llm.py           the decision layer, swappable. RulesEngine = no key, no network
  ledger.py        append-only run record
  agents/
    base.py            capabilities() / handle(task) - the whole interface
    phase_build.py     runs OT-2 + TapeStation, emits a b2t package
    phase_test.py      consumes b2t, runs CLARIOstar, emits t2l
    sentinel_b2t.py       validate -> repair (bounded) -> escalate
    coordinator.py     routes, records, stops on escalation
usecases/bioprospecting/instruments.py   the three simulated devices
runs/<run_id>/                           packages + ledger.jsonl
```

## The two checks a schema cannot express

Plain JSON Schema validates a document in isolation. The real handover bugs are
relational, so the contracts carry an `x-dbtl-checks` section:

- **`unique`** — two samples cannot claim one well.
- **`cross_ref`** — every sample must trace to an item Design actually committed to.
- **`required_quantities`** — profile-driven: which measurements must be present, in which unit.

This is worth reporting from the week: a schema alone is not enough for a handover
contract.

## Why repair is deliberately weak

`RulesEngine` fixes only what can be fixed without inventing data — a unit the
instrument export dropped, because the profile already declares what unit that
quantity must be in.

A double-booked well and an unlabelled candidate are **never** auto-fixed. Guessing
which sample sat in which well would fabricate a lab record, which is worse than a
failed handover. Both escalate, and the route stops rather than handing Test a
package the validator rejected.

So the result to report is not "the agents fix everything" but **three real errors
caught, one safely repairable, two needing a decision** — with the ledger as proof.

## What is stubbed, and what Tuesday needs

| | state |
|---|---|
| B→T contract + validator + repair + escalation | working |
| **D→B contract + crate→graph agent + graph checks** | **working** — `python3 demo_d2b.py`, see [DESIGN_TO_BUILD.md](DESIGN_TO_BUILD.md) |
| `SentinelAgent` base: translate → validate → repair → escalate | working; B→T and D→B are both subclasses, one with no code at all |
| SHACL shapes for D→B | written, **never executed** (needs `pyshacl`) |
| T→L contract | working, validated directly — **no sentinel agent yet** |
| L→D contract + iteration record | **not written** — the coordinator is to own the loop closure |
| Learn phase agent | **not written** |
| Model engine | interface ready (`propose_patches`, `propose_terms`), only `RulesEngine` implemented |
| Biomanufacturing tool adapters | **not written** — only the profile exists |
| `w3id.org` namespace for `dbtl:` | **not minted** — blocks merging two teams' graphs |

Suggested order: mint the namespace (it is a pull request, and it blocks others),
one more sentinel agent (T→L) to confirm the pattern repeats a third time, then
L→D and the coordinator's loop closure. Not all eight agents in parallel.

## The Design → Build handover is a graph, not a document

The other three handovers are documents: a list of samples, a list of results.
D→B is not. The order that goes to the synthesis provider is document-shaped —
and trivial — but what has to survive is the chain behind each sequence, back to
a vial in a freezer. So that contract carries **three checks a JSON Schema
cannot express at all**, the important one being `provenance_chain`: can this
FASTA be traced, link by link, to a physical sample?

This is the concrete evidence for the claim already made above — that a schema
alone is not enough for a handover contract. For D→B a schema is not even the
right *shape* of tool, and `contracts/shapes/` carries the same rules as SHACL
for when the graph goes into a real store.

## Swapping in a model

Implement `propose_patches` on an `Engine` subclass in `llm.py` and pass it to the
sentinel agent. Every ledger entry already records `engine`, so comparing a large
model against a small open one is a query over `runs/*/ledger.jsonl` rather than a
separate experiment — the honest version of the cheap-decision-layer argument.
