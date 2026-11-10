# Taking a handover — one page

You are writing a **checking agent** for one phase transition. You are not
writing a pipeline, and you are not writing the four steps every agent does:
those live once, in `framework/agents/sentinel_base.py`, in the class
`SentinelAgent`:

    translate -> validate -> repair (bounded) -> escalate

Your agent is a **subclass** of it. It inherits that loop. `sentinel_b2t.py` and
`sentinel_t2l.py` are four lines each and contain no logic at all — that is the
normal case, not a cut-down one.

## 0. Scaffold it

```bash
python3 scripts/new_handover.py <name> \
    --number N --label "what the use case calls it" --from <phase> --to <phase>
```

Two files appear, both marked TODO. **Do not copy an existing file by hand.**
The envelope is identical in every contract, and identical by construction
beats identical by discipline: three people copying a file produce three
slightly different envelopes within a week.

## 1. The contract — `framework/contracts/<name>.schema.json`

What crosses the handover. JSON Schema, plus a section `x-dbtl-checks` for the
things a schema cannot state:

| kind | catches |
|---|---|
| `unique` | two samples claiming one well |
| `cross_ref` | an item the previous phase never committed to |
| `required_quantities` | a measurement the profile says this handover needs |
| `provenance_chain` | a sequence with no path back to a physical sample |
| `required_provenance` | context that cannot be recovered later |
| `empty` | a list that must be empty, e.g. unmapped vocabulary keys |
| `derived` | a field that must equal a value computable from the data, e.g. a checksum |

Keep the envelope and the measurement shape (`quantity + value + unit +
method`) exactly as scaffolded. Delete the example checks you do not use — an
unused check is worse than no check, because people stop reading them.

## 2. The profile entries — `framework/contracts/profiles/*.json`, **both**

`required_quantities.<your_handover>`, plus any identifier patterns your
contract refers to with `x-pattern`. If `bioprospecting` and
`biomanufacturing` need different things here, that is correct — it is exactly
what the profile is for. Do not fork the contract to say it.

## 3. `never_autofix` — one line in your agent

The errors a patch must never touch. The test is **not** "is this hard to fix"
but:

> would fixing it invent something nobody recorded?

A guessed well, a guessed derivation step, a renamed duplicate: each writes a
lab record that was never observed, which is worse than a failed handover.

You can mark an error blocking from inside the contract instead: any check
whose `fix_hint` starts with `"not auto-fixable"` is never patched. Prefer
that when the reason is worth reading — the decision then sits in prose a
reviewer sees, not in a Python set only its author knows about.

## 4. `translate()` — delete it

Keep it only if your upstream phase does not already emit a package in the
contract's shape. Handover 1 is the one exception: Design has to project an
order for the synthesis vendor out of the crate and keep the two joined.

## 5. The step everyone skips

A **deliberately broken package**, and a test that it fails *for the reason you
expect*. A check nobody has seen fail is a check nobody trusts, and
`exampleROcrates/` asks for exactly this: one package that satisfies the
contract, one that does not.

## Looking at it

```bash
python3 scripts/show_agents.py               # all four, side by side
python3 scripts/show_agents.py --handover 1  # one in full
python3 demo_d2b.py                          # H1: clean run, then broken run
python3 demo_l2d.py                          # H4: the round that closes, then one that does not
```

`show_agents.py` reads the live classes and contract files, so it cannot drift
from the code. If it says a check exists, it exists.

## What you must not do

- **Do not re-implement the loop.** A rule added to the base class reaches all
  four handovers the same day. A copy does not.
- **Do not let the agent decide a vocabulary term.** Terms are looked up in
  `framework/vocabulary/`: a shared `core.json` changed by pull request, a file
  per lab for local spellings. A model may *draft* a line for a key nobody has
  mapped — reported, never applied. A term chosen per run is not reproducible,
  and two teams checking the same crate would reach different verdicts.
- **Do not let the agent be its own authority.** The validator decides. After
  any repair the package is re-validated; a patch is applied only if the
  validator reported that exact path as fixable.

## Models and API keys

**Nothing here reads an API key, and the default path never calls a model.**
Run `demo_d2b.py` on a laptop with no network and it works.

If you do want a model, there are three routes and all three are one argument:

```python
from framework.engines import CommandEngine

CommandEngine("claude")   # the Claude Code CLI, using the login you already have
CommandEngine("codex")    # the OpenAI Codex CLI, same
CommandEngine("ollama")   # a model on your own machine: no key, no network

CommandEngine(argv=["my-tool", "--flag"])        # anything that reads stdin

agent = DesignToBuildAgent(profile="bioprospecting",
                           engine=CommandEngine("ollama"))
```

No key is read by this repository, nothing is hardcoded, and the key never
enters a contract, a crate, a package or the ledger — only the engine's `name`
does, so a run with a model and a run without can be told apart afterwards.

### What the framework guarantees, whatever engine you pass

1. The engine is **only asked** about errors that are not blocking. Blocking
   errors never reach it.
2. A patch is applied **only if the validator reported that exact path** as
   fixable. Anything else is refused, and the refusal is in the trace.
3. The package is **re-validated** afterwards. The engine is never its own
   authority — and `derived` checks mean a fabricated value fails even when
   the field it fills was genuinely missing.
4. `propose_terms` output is **reported, never applied**, and a term the
   shared `core.json` does not declare is rejected outright. A model may
   rename; it may not coin.
5. Every step records which engine ran, in an append-only ledger.

### See it for yourself

```bash
python3 scripts/prove_engine.py                  # no model at all
python3 scripts/prove_engine.py --engine claude  # or codex, or ollama
```

Measured on the same broken crate, one key nobody had mapped (`box_temp_c`):

| engine | proposed | what happened |
|---|---|---|
| no model | nothing — a rule cannot reason about a new word | left for a human |
| `claude -p` | `dbtl:storageTemperature` | reported, not applied |
| `codex exec` | `dbtl:storageTemperature` | reported, not applied |
| `ollama`, 3B, local | `envo:temperature` — nobody agreed it | **rejected** |

In all four runs the handover still failed. A model may draft. It may not
decide.

Part 3 of that script needs no model and is the one that matters: a
deliberately hostile engine proposes a renamed well, an invented coordinate
and a fabricated checksum. Two never reach the package. The third does, and
the re-validation catches it.
