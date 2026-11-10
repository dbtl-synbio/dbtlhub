# The handover agent template

```bash
python3 scripts/new_handover.py test_to_learn \
    --number 3 --label "screening results" --from test --to learn
```

Two files appear, both full of TODOs and neither guessing at your use case.

## Why a template at all

Four handovers, four people, one week. The risk is not that anyone writes a bad
agent — it is that four correct agents disagree about small things: what the
envelope is called, whether a number carries its unit, what a failed check does
to the route. By Thursday the coordinator is special-casing each of them and
nothing composes.

So the shared part is **written once** and nobody reimplements it:

| | |
|---|---|
| `framework/agents/sentinel_base.py` | translate → validate → repair → escalate |
| `framework/validator.py` | the only authority on whether a package is valid |
| the envelope | `contract`, `contract_version`, `profile`, `run_id`, `produced_by`, `produced_at`, and a mandatory backlink |
| the measurement shape | `quantity + value + unit + method`, in every contract |

## What you actually write

An agent is a declaration. This is the Build → Test one, complete:

```python
class BuildToTestAgent(SentinelAgent):
    name          = "sentinel_b2t"
    contract_name = "build_to_test"
    never_autofix = {"double_booked_location", "unknown_design_item",
                     "duplicate_sample_id"}
```

Four lines, no logic. That is the normal case. `sentinel_d2b.py` is longer only
because the Design handover has to project an order out of a crate and keep the
two joined — real work, and the exception rather than the shape to copy.

### The four decisions

1. **The contract** — what this handover carries, in `framework/contracts/`.
2. **The profile entries** — `required_quantities.<your_handover>` in **both**
   `bioprospecting.json` and `biomanufacturing.json`, plus any identifier
   patterns the contract refers to with `x-pattern`. If the two use cases need
   different things here, that is correct: it is what the profile is for.
3. **`never_autofix`** — the errors a patch must never touch. The test is not
   "is it hard to fix" but *"would fixing it invent something nobody recorded"*.
   A guessed well, a guessed derivation step, a renamed duplicate: each writes a
   lab record that was never observed, which is worse than a failed handover.
4. **`translate()`** — only if the upstream phase does not already emit a
   package in the contract's shape. Delete it otherwise.

You can also mark an error blocking from inside the contract: any check whose
`fix_hint` starts with `"not auto-fixable"` is never patched. Prefer that when
the reason is worth reading — the decision then sits in the contract, in prose a
reviewer sees, instead of in a Python set only its author knows about.

## The checks a JSON Schema cannot express

Contracts carry an `x-dbtl-checks` section. Kinds available today:

| kind | catches |
|---|---|
| `unique` | two samples claiming one well |
| `cross_ref` | an item the previous phase never committed to |
| `required_quantities` | a measurement the profile says this handover needs |
| `provenance_chain` | a sequence with no path back to a physical sample |
| `required_provenance` | context that cannot be recovered later |
| `empty` | a list that must be empty, e.g. unmapped vocabulary keys |
| `derived` | a field that must equal a value computable from the data, e.g. a checksum |
| `entity_value` | a referenced entity says something the next phase must act on |

Adding a kind is one function in `validator.py` plus one line in its `CHECKS`
table. Delete the examples you do not use: an unused check is worse than no
check, because people stop reading them.

## Last step, and do not skip it

Write a **deliberately broken package** and a test that it fails for the reason
you expect. A check nobody has seen fail is a check nobody trusts — and the use
case's own `exampleROcrates/README.md` asks for exactly this: one package that
satisfies the contract, one that does not.

## The worked example: Handover 1

`framework/agents/sentinel_d2b.py` is the one to show people. It is the *un*typical
case on purpose — it is the only handover whose `translate()` does real work,
because Design has to project an order for the synthesis vendor out of the crate
and keep the two joined. Everything else about it is template.

Compare it with `sentinel_b2t.py` and `sentinel_t2l.py`, which are four-line
declarations with no logic at all. That contrast is the argument: the template
holds, and a handover only costs more when it genuinely is more.

```bash
python3 demo_d2b.py                        # Handover 1, clean run and broken run
python3 demo_l2d.py                        # Handover 4, the round that closes
python3 scripts/check_crate.py --break-all # Handover 1 on the use case's own crate
python3 scripts/show_agents.py             # all four, as they are right now
python3 scripts/show_agents.py --handover 1
```

## Status

| | handover | contract | agent | |
|---|---|---|---|---|
| 1 | construct specification | working | working | custom `translate()` — the worked example |
| 2 | assembly outputs and QC results | working | working | four lines, no logic |
| 3 | screening results | working | working | four lines, no logic |
| 4 | model predictions and recommendations | working | working | three lines, no logic |

Read it from the code rather than from this table, which will go stale:

```bash
python3 scripts/show_agents.py
```
