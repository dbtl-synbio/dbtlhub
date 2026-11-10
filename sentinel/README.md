# Sentinel agents

A sentinel agent stands at one phase transition of the DBTL cycle, reads what
the upstream phase produced, and decides whether the downstream phase can
accept it. It can refuse. That is the point of the name.

Use case independent: the framework here is shared, and what each use case
requires lives in a **profile**. `bioprospecting` and `directed_evolution`
can disagree about what a handover is incomplete without without forking
anything.

**Marco Anteghini, LifeGlimmer** — raised on Slack 10 November 2026.

## Start here

| | |
|---|---|
| **Taking a handover** | [`template/TAKE_A_HANDOVER.md`](template/TAKE_A_HANDOVER.md) — one page, and the thing to read first |
| Why the template exists | [`template/README.md`](template/README.md) |
| Handover 1 in detail | [`framework/DESIGN_TO_BUILD.md`](framework/DESIGN_TO_BUILD.md) |
| Slides | [`docs/sentinel_agents.pptx`](docs/sentinel_agents.pptx) |

```bash
python3 scripts/show_agents.py               # all four, as they are right now
python3 scripts/show_agents.py --handover 1  # one in full
python3 demo_d2b.py                          # H1: a clean crate, then a broken one
python3 demo_l2d.py                          # H4: the round that closes, then one that does not
```

`show_agents.py` reads the live classes and contract files, so it cannot drift
from the code. If it says a check exists, it exists.

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
- **No warning severity.** Checks pass or fail. Something like "gene calling
  mode is set to open ends" is not an error — it is a flag Build must act on —
  and there is currently nowhere to put it. This needs a third outcome.
- **Referential integrity is partial.** The validator checks the crate
  entities the order binds to. It does not yet check that *every* `@id` in
  `@graph` resolves, nor that every relative `@id` is a file that is present.
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
