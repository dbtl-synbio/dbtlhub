# Sentinel agents

A sentinel agent stands at one phase transition of the DBTL cycle, reads what
the upstream phase produced, and decides whether the downstream phase can
accept it. It can refuse. That is the point of the name.

Use case independent: the framework here is shared, and what each use case
requires lives in a **profile**. `bioprospecting` and `directed_evolution`
can disagree about what a handover is incomplete without without forking
anything.

**Marco Anteghini, LifeGlimmer** — raised on Slack 10 November 2026.

## The Architect

The centre of the agreed picture: the researcher talks to it, it holds what
was agreed and the crate that grows, and it decides what happens after every
verdict. Eight agents stand around it — four that do the work and may be
people rather than programs, four that check and may refuse.

It runs on your own machine, in a browser, out of a clone of this repository.
There is no install step: no pip, no virtualenv, no key, no network.

```bash
git clone https://github.com/dbtl-synbio/dbtlhub.git
cd dbtlhub/sentinel
python3 architect/web/server.py        # then open http://127.0.0.1:8765/
```

Pick **no model**, load the worked example, press Run: four accepted
handovers, with nothing sent anywhere.
**[`INSTALL.md`](INSTALL.md)** is the page to send a colleague — the three
clicks, where a run lands on disk, how to check it rather than trust it, and
what each failure message actually means.

The five parts also run on their own, without the browser:

```bash
python3 architect/architect.py
```

[`architect/README.md`](architect/README.md) says what each is for and what is
not done yet.

## Start here

| | |
|---|---|
| **Running it yourself** | [`INSTALL.md`](INSTALL.md) — clone, one command, a browser. Tested from an empty directory on Python 3.9 and 3.12 |
| **Taking a handover** | [`template/TAKE_A_HANDOVER.md`](template/TAKE_A_HANDOVER.md) — one page, and the thing to read first |
| Why the template exists | [`template/README.md`](template/README.md) |
| Handover 1 in detail | [`framework/DESIGN_TO_BUILD.md`](framework/DESIGN_TO_BUILD.md) |
| **Full report** | [`docs/REPORT.md`](docs/REPORT.md) — the complete record: every file, all three use cases, the three disagreements between them, every contract and check, how to reproduce each claim, what is verified and what is not, every defect found, and the open questions for the group |
| **Walkthrough** | [`docs/walkthrough.html`](docs/walkthrough.html) — one page, plain language: every step of the cycle, what each agent checks, where a model may act, and the diagram of the graph growing. Open it in a browser |
| Slides | [`docs/sentinel_agents.pptx`](docs/sentinel_agents.pptx) |

```bash
python3 tests/test_framework.py              # 15 tests, no dependencies
python3 scripts/show_agents.py               # all four, as they are right now
python3 scripts/show_agents.py --handover 1  # one in full
python3 demo_d2b.py                          # H1: a clean crate, then a broken one
python3 demo_l2d.py                          # H4: the round that closes, then one that does not
python3 scripts/check_crate.py --break-all   # H1 on this repo's own example crate
```

`show_agents.py` reads the live classes and contract files, so it cannot drift
from the code. If it says a check exists, it exists.

## It runs on this repository's own crate

```bash
python3 scripts/check_crate.py --break-all
```

Reads `bioprospecting/exampleROcrates/design-to-build-simple/`, the crate the
bioprospecting use case published, and then breaks it three ways on purpose:

| | | |
|---|---|---|
| the crate as published | **accepted, with one flag** | 105 entities → 570 triples, 0 unaligned keys, 4 constructs ordered — and `ENR-003` flagged, because the crate records it as a `right partial` |
| a file it promises, removed | refused | `missing_file` — a relative `@id` is a promise, and no profile validator checks it |
| the profile it claims, removed | refused | `too_few_items` — a crate that states no profile cannot be interpreted |
| the gene calling mode, removed | refused | `missing_provenance` — open ends permits a truncated gene, so Build cannot judge what it got |

Two of those three faults pass every RO-Crate validator there is. The third is
the argument for having a contract at all: conformance is not sufficiency.

The flag on the accepted crate is the other half of that argument. One of the
four proteins is recorded as a `right partial` — a gene called with open ends
that ran off the end of a contig, so the enzyme may be truncated. The crate
says so honestly. Refusing it would call an accurate crate invalid; saying
nothing would put a truncated gene in well A3 with nobody the wiser. So a
check can declare `"severity": "flag"`: the handover is accepted, the order
goes out, and well A3 is marked.

**Three faults, written out.** `--write-broken` puts them on disk as folders,
in `sentinel/examples/design-to-build/`, which is what
`exampleROcrates/README.md` asks for: one crate that satisfies the contract
and one that does not, per handover. Move them into `exampleROcrates/` if you
would rather they lived beside the good one.

**A second finding, smaller and more embarrassing.** A crate declares its
RO-Crate version on the metadata descriptor and its *profile* on the root
dataset. We were reading only the first, so a crate conforming to Process Run
Crate 0.6 came back as "ro/crate/1.3" and the statement that tells a reader
how to interpret it was lost. Both are read now.

**A finding, not a feature.** That crate expresses provenance through
`CreateAction` / `object` / `result`, walked backwards; the simulated crate in
`usecases/` follows PROV properties forwards. The metadata is in named
`PropertyValue` entries rather than flat keys, and three entities share the
type `Sample`, so the root is the one belonging to the study. All three
differences are declared in `profiles/bioprospecting.json`, which is why one
contract reads both — but **the group should pick one dialect.** Supporting two
is a tax that compounds with every handover.

## One base class, four handovers

`framework/agents/sentinel_base.py` holds the loop, written once:

    translate -> validate -> repair (bounded) -> escalate

The four handover agents are **subclasses** of it, not four programs.
`sentinel_b2t.py` and `sentinel_t2l.py` are four lines each and contain no
logic at all — that is the normal case. So a rule added to the base class
holds in all four the same day, and nobody can omit it in their own file,
because nobody has a copy.

The rule that matters: a repair patch is applied only if the validator
reported that exact path as fixable, and the package is re-validated
afterwards. Without it a model could "fix" two samples claiming one well by
renaming one of them — re-validation would pass, and a lab record that never
happened would have been written.

| | handover | contract | agent | |
|---|---|---|---|---|
| 1 | construct specification | working | working | the worked example; the only one with a `translate()` |
| 2 | assembly outputs and QC results | working | working | four lines, no logic |
| 3 | screening results | working | working | four lines, no logic |
| 4 | model predictions and recommendations | working | working | three lines, no logic |

## Vocabulary: the agent never decides a term

A term chosen by a model on each run is not reproducible, and two teams
checking the same crate would reach different verdicts. So, in
`framework/vocabulary/`:

1. `core.json` — the shared terms, changed by pull request.
2. `labs/<lab>.json` — local spellings. `freezer_temp` at Newcastle and
   `tempC` at LifeGlimmer both resolve to `dbtl:storageTemperature`.
3. A model may **draft** a line for a key nobody has mapped. It is reported,
   never applied.

A lab file may only alias to a term `core.json` already declares. Anything
else raises `VocabularyError`: a lab may rename a term, not coin one.

## Models and API keys

**Nothing here reads an API key, and the default path never calls a model.**
The demo runs offline. The default engine is deterministic: it restores a unit
the profile already states and recomputes a checksum, both derivable.

If you want one, three routes, all one argument (`framework/engines.py`):

```python
CommandEngine("claude")   # the Claude Code CLI, using the login you already have
CommandEngine("codex")    # the OpenAI Codex CLI, same
CommandEngine("ollama")   # a model on your own machine: no key, no network
```

Whatever engine is passed: blocking errors never reach it; a patch is applied
only where the validator pointed; the package is re-validated afterwards;
vocabulary suggestions are reported, never applied, and a term `core.json`
does not declare is rejected; and the ledger records which engine ran.

```bash
python3 scripts/prove_engine.py --engine claude   # or codex, or ollama, or none
```

Measured, same code, same broken crate, one key nobody had mapped
(`box_temp_c`):

| engine | proposed | what happened |
|---|---|---|
| no model | nothing | left for a human |
| `claude -p` | `dbtl:storageTemperature` | reported, not applied |
| `codex exec` | `dbtl:storageTemperature` | reported, not applied |
| `ollama`, 3B, local | `envo:temperature` | **rejected — a model may rename, not coin** |

In all four runs the handover still failed. Full statement in
[`template/TAKE_A_HANDOVER.md`](template/TAKE_A_HANDOVER.md).

## Known gaps, stated rather than discovered later

- **`dbtl:` is not minted.** The namespace `https://w3id.org/dbtlhub/` needs a
  w3id pull request. Until then the IRIs do not resolve.
- **The SHACL shapes are written but never executed.**
  `framework/contracts/shapes/` holds the equivalents of the graph checks;
  nothing runs `pyshacl` against them yet.
- **Referential integrity is partial.** For a crate read from disk, every
  relative `@id` typed `File` is checked against the folder, and a file the
  crate promises and does not deliver is a `missing_file` violation. What is
  still missing is the general case: that *every* `@id` referenced anywhere in
  `@graph` resolves to an entry in it.
- **H2 and H3 packages are JSON, not RO-Crates.** The slides for the use case
  imply every handover is packaged as an RO-Crate. Worth settling as a group:
  the contracts do not care, but the example packages should be consistent.
- **H2 and H3 packages are JSON, not RO-Crates.** The slides for the use case
  imply every handover is packaged as an RO-Crate. Worth settling as a group:
  the contracts do not care, but the example packages should be consistent.
- **Nobody has run this on a real crate.** Everything here is checked against
  simulated packages generated in `usecases/`. Anil's own Design → Build
  example crates use Process Run Crate's `CreateAction` / `object` / `result`
  rather than PROV properties, so the provenance traversal does not yet walk
  them: the mechanism is hardcoded where it should be declared in the profile.
  That is the next thing worth fixing, and it is what would make Handover 1
  run on somebody else's data rather than only on mine.

## Layout

```
framework/
  agents/sentinel_base.py     the loop, once, for all four handovers
  agents/sentinel_{d2b,b2t,t2l,l2d}.py
  contracts/*.schema.json     what crosses, plus x-dbtl-checks
  contracts/profiles/*.json   what each use case requires
  contracts/shapes/           SHACL equivalents (not yet executed)
  validator.py                the only authority on whether a package is valid
  vocab.py, vocabulary/       three layers, anti-drift rule enforced
  kg.py                       crate -> aligned crate + N-Triples
  llm.py                      where a model may act, and what constrains it
template/                     copy-me agent and contract, plus the one-pager
scripts/new_handover.py       scaffolds both files with the envelope correct
scripts/show_agents.py        read the four from the code, not from a diagram
usecases/bioprospecting/      simulated crates, including deliberately broken ones
```
