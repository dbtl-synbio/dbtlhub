# The product's worked example

**Read this first if you are about to write a contract.** It is the shortest
complete thing in the repository: 2 contract files and 6 crates, and the
whole of it is meant to be read rather than skimmed.

## Why it is about paint

It is deliberately not a DBTL cycle, where DBTL stands for Design, Build,
Test, Learn. The domain is a coating laboratory: recipes are blended, applied
to metal panels held in numbered slots on a rack, dried, and their film
thickness measured.

Nothing here is biology, so nobody reading the product can mistake its
example for somebody's use case. The product is generic and this example
proves it rather than claiming it.

## What is in here

| Path | What it is |
|---|---|
| `make_example.py` | Generates all 5 crates. Run it with no arguments |
| `contracts/mixing_to_coating.yaml` | The worked contract, 19 requirements, version 1.1.0 |
| `contracts/coating_to_inspection.yaml` | A second handover, 2 requirements, version 0.2.0, a stub |
| `coating-test/valid/` | A crate that satisfies the contract, 28 entities |
| `coating-test/invalid/` | 4 copies, each broken in exactly one way |
| `from-another-phase/` | A crate from an unrelated domain, a library catalogue |

The second contract exists to demonstrate one thing: adding a handover means
writing a file like that and nothing else. No class was written for it, no
name was registered anywhere, and no table maps its name to any code. A test
in the product's own suite greps the service source for every handover name
it knows and fails the day one appears in the code.

## What the contract covers

All 4 verbs the language has, both severities, and every extra field:

| Verb | Where it is used in the example |
|---|---|
| `be recorded` | The crate's profile, name and licence; a slot's position; a recipe's thickness |
| `be unique` | Two slots may not claim the same position on the rack |
| `point at something in the crate` | A slot's recipe; a step's inputs and outputs; the crate's own file list |
| `be a number between` | A recipe's film thickness, which must be 5 to 500 micrometres |

Both contracts also carry an `expects` block, which lists the entity types
the contract is written for. A crate containing none of them is refused
before a single requirement is applied. Write one: a contract without it
accepts crates it has never meaningfully checked, which was measured on
11 November 2026 and is explained in
[WRITING_A_CONTRACT.md](../docs/WRITING_A_CONTRACT.md).

`severity: refuse` stops the handover. `severity: flag` records a finding and
lets it through. `of_type` narrows a reference to one kind of thing.
`one_of` lists the only values that mean anything. `repairable: true` allows
a model to be asked whether a value is already written down somewhere in the
record, and whatever it answers is then checked by these same rules.

## What the five crates do

Measured on 11 November 2026. The third party tool `rocrate-validator` calls
all 6 of them valid RO-Crate 1.3 with 0 issues each.

| Crate | Verdict | Why |
|---|---|---|
| `valid` | ACCEPTED, 0 findings | |
| `invalid/missing-conformsto` | REFUSED | The root does not say which profile it follows |
| `invalid/dangling-reference` | REFUSED | It lists a file it then never describes |
| `invalid/missing-atmosphere` | REFUSED | The drying step's atmosphere is nowhere in the crate |
| `invalid/atmosphere-in-prose` | REFUSED | The atmosphere is in the crate, inside a sentence |
| `from-another-phase` | REFUSED | It contains nothing the contract is written for |

**The last one is the case worth understanding.** Nothing is missing from
that crate. The drying atmosphere is recorded, in the text of a command line,
where no rule can read it. So a crate that satisfies every rule a standard has
can still be refused, and refused for being unreadable rather than for being
incomplete. That is the whole argument for a contract sitting on top of a
validator, in one example.

It is also the only one of the four that a model could do anything about, by
reading the setting out of the command line. Two local models with 14 billion
parameters each were asked to do exactly that job on a real deployment's crate
on 10 November 2026, and neither could. That measurement is recorded in the
product README.

## Running it

```
cd sentinel-oo
export SENTINEL_CONTRACTS=examples/contracts

PYTHONPATH=src python -m sentinel_oo examples/coating-test/valid \
    --contract mixing_to_coating

PYTHONPATH=src python -m sentinel_oo \
    examples/coating-test/invalid/atmosphere-in-prose \
    --contract mixing_to_coating
```

To see the contract in plain words rather than as YAML:

```
PYTHONPATH=src python -m sentinel_oo --show-contract mixing_to_coating
```

That is what a producing team reads to check themselves before they are
checked.

## Regenerating the crates

```
cd examples && python make_example.py
```

It rewrites all 6 crates, and the 5 coating ones come from one function, so
each broken copy differs from the valid one in exactly one way and a refusal
can always be read back to a single cause.

`from-another-phase` is a library catalogue, chosen because nobody could
mistake it for a coating laboratory or for anybody's DBTL cycle. It is there
so the tutorial's most important lesson can be run rather than described: a
contract with no `expects` block accepts it, and one with such a block
refuses it and names every type it was looking for.

**ALL DATA HERE IS INVENTED.** The thicknesses, the recipe codes and the
identifiers under example.org are made up and resolve to nothing.
