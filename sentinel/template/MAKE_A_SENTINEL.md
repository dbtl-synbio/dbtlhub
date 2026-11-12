# How to prepare a sentinel

**A sentinel is a file.** Not a class, not a service, not a fork of this
repository. You write a contract, put it in `framework/contracts/`, and the one
sentinel guards it. If you ever have to edit Python to add a handover, that is
a bug in this framework and not something you should work around.

```python
from framework.agents.sentinel import Sentinel

Sentinel(profile="bioprospecting").check("your_handover", package)
```

That line works for a handover nobody has written any code for. There is a
worked example in `template/example/coat_to_cure.yaml` — a handover invented
only to prove this, which no part of this framework knows about.

---

## 1. Start the file

```bash
python3 scripts/new_handover.py coat_to_cure \
    --number 5 --label "coated panels" --from coat --to cure
```

Add `--dialect sentinel-oo` for the other language (see §3). Nothing else is
written: no agent, no registration, no import.

---

## 2. What a contract says

Two things, and they are different:

**A schema** — the shape the package must have. Required fields, types,
minimum lengths. This is ordinary JSON Schema, and it catches what is missing.

**Checks** (`x-dbtl-checks`) — what must be *true* across the package, which a
schema cannot say: that no two rows share an identifier, that every reference
resolves, that a quantity carries its unit, that a chain of provenance reaches
the ground.

```yaml
x-dbtl-checks:
  - kind: unique
    of: panels
    fields: [panel_id]
    code: duplicate_panel
    message: two panels carry the same identifier
    fix_hint: "not auto-fixable: somebody has to say which panel this is."
```

Every check needs a `code` (what a machine matches on), a `message` (the
sentence a person reads) and a `fix_hint` (what to do about it). Write the
message as the person who will have to fix it, not as the person who wrote the
rule.

**The kinds available:** `unique`, `cross_ref`, `accounted_for`,
`required_quantities`, `provenance_chain`, `required_provenance`,
`entity_value`, `derived`, `within_limits`, `empty`, `references_resolve`,
`root_declares`.

A kind this validator does not implement is reported as
`unknown_check_kind` rather than skipped, and a check whose own settings are
wrong is reported as `malformed_check`. **Neither is ever a silent pass.** A
contract asking for something nobody enforces is a contract nobody is
enforcing, and the whole point of this framework is that you find that out on
your own machine.

---

## 3. Two dialects, one sentinel

There are two contract languages in this project, and they look at different
objects. Pick the one that matches what you actually want to check.

| | `dbtl` (ours) | `sentinel-oo` (Anil Wipat's) |
|---|---|---|
| a check applies to | a **path in a package** — `order.items`, `bindings` | an **entity in a crate**, by type — `type:Protein`, `root` |
| the language | 12 check kinds | 5 demands |
| how a value is read | our own paths | a `property`, or a `named_value` hanging off the entity |
| guard against matching nothing | `matched_nothing` per check | `expects:` — the types the contract is for |
| written as | `<name>.yaml` + a `.schema.json` twin | `<name>.oo.yaml` |

**`sentinel-oo`'s five demands are the whole vocabulary**, deliberately:

```
be recorded                      optionally one_of: [...]
be unique
point at something in the crate  optionally of_type: SomeType
be a number between              needs between: [low, high]
hold data                        the file exists and is not empty
```

A language that can say anything can also say things nobody can check.

**One sentinel runs both.** Point it at a folder of `sentinel-oo` contracts and
a handover is held to both agreements at once:

```python
Sentinel(profile="bioprospecting",
         also="../dbtlhub/sentinel-oo/examples/contracts")
```

Every finding is stamped with whose contract it came from, and both ids are
recorded in the crate. A package that satisfies one and not the other is
refused, and the trace says which — which is the point: a disagreement between
two teams' contracts should be visible, not smoothed over.

---

## 4. What the sentinel does with it

The same thing for every contract, which is why you do not write it:

1. **Validates** the package. Three verdicts and only these:
   `accepted` · `accepted_with_flags` · `refused`.
2. **Writes its own act into the crate** — a `CreateAction` carrying the
   verdict, the contract id, the profile, and one `PropertyValue` per finding.
   So a crate nobody checked is visibly different from one that passed.
3. **Hands the crate on, richer.** It writes nothing about your science. It
   records its own act, which is a different thing and the only thing it is
   entitled to record.

It never repairs under the Architect: a repair is a change to the package, and
deciding to change something belongs to the Architect, which can ask you.

---

## 5. How it meets the Architect

You do not wire anything. The Architect takes two callables — a runner and a
checker — and `architect/wiring.py` already supplies both:

```
phase agent  produce()  ->  entities + the action that made them
             package()  ->  what the next phase is given
                  |
              sentinel  ->  accepted | accepted_with_flags | refused
                  |
             Architect  ->  GO_ON | GO_BACK | ASK | STOP
```

The verdict goes to the **Architect**, never straight to the next phase. That
is what lets it weigh the findings, decide to go back rather than ask, and
word a question about something it has actually seen. A phase agent that
consumed its own verdict would leave the Architect with a status and nothing
to reason about.

Your phase agent is the other half, and `template/phase_agent.py` is its
skeleton. It writes its part of the crate; the sentinel checks the handover;
neither does the other's job.

---

## 6. Before you hand it to anyone

- [ ] Every check has a `code`, a `message` and a `fix_hint`.
- [ ] A deliberately broken package is **refused**, and you have one to show.
- [ ] A correct package is **accepted**, and you have one to show.
- [ ] `expects` (or the equivalent) is set, so a crate from the wrong phase
      cannot pass by matching nothing. This is the failure that looks most
      like success.
- [ ] The contract carries a `$id` with a version, and you bump it when the
      meaning changes.
- [ ] Nothing in the contract is a prompt to a model. A contract says what
      must be true and stays true for years; a prompt says where to look and
      goes stale. `sentinel-oo` rejects a contract carrying one outright, and
      so should you.

Two example crates — one valid, one deliberately broken — are worth more than
a page of prose about your contract. `examples/design-to-build/` and
`dbtlhub/bioprospecting/exampleROcrates/` are both laid out that way.
