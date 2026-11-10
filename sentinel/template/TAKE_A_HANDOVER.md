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
python3 scripts/new_handover.py learn_to_design \
    --number 4 --label "model predictions" --from learn --to design
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

**Nothing here needs an API key, and the default path never calls a model.**
Run `demo_d2b.py` on a laptop with no network and it works.

The one place a model may act is an **engine**, `framework/llm.py`:

```python
class Engine:
    name = "none"
    def propose_patches(self, package, report, contract) -> list[Patch]: ...
    def propose_terms(self, keys, crate, vocab=None) -> dict: ...
```

The default is `RulesEngine`: deterministic, offline, and it does two things —
restore a unit the profile already states, and recompute a checksum. Both are
*derivable*. Nothing is guessed.

If your lab wants a model instead, you write your own subclass of `Engine`,
with your own provider and **your own key, read from your own environment
variable**. Nobody else's key is involved, nothing is hardcoded, and the key
never enters a contract, a crate or the ledger:

```python
agent = DesignToBuildAgent(profile="bioprospecting", engine=MyModelEngine())
```

What the framework guarantees, whatever engine you pass:

1. The engine is **only asked** about errors that are not blocking. Blocking
   errors never reach it.
2. A patch is applied **only if the validator reported that exact path** as
   fixable. Anything else is refused and recorded as refused in the trace.
3. The package is **re-validated** afterwards. The engine is never its own
   authority.
4. `propose_terms` output is **reported, never applied**. A model may draft a
   vocabulary line for a human to accept; it cannot mint a term.
5. Every step records which engine ran, in an append-only ledger, so a run
   with a model and a run without are told apart afterwards.

So "does this use an LLM?" has a precise answer: not by default; optionally,
behind those five constraints; and the handover can always be checked with no
model at all.
