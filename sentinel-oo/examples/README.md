# The product's worked example

**Read this first if you are about to write a contract.** It is the shortest
complete thing in the repository: two contract files and seven crates, and
the whole of it is meant to be read rather than skimmed.

## What it is about

A handover from the Design phase to the Build phase of a bioprospecting
cycle. Bioprospecting means searching genomes and metagenomes for enzymes
that might be useful industrially.

The Design phase finishes with a panel of candidate proteins pulled out of a
metagenome, a synthetic gene designed for each one, and a plate layout saying
which well each gene goes into. The Build phase orders those genes from a
synthesis company and spends money, so anything Build cannot judge from the
crate is a well that may be wasted.

**Nothing in the service knows what a protein or a plate is.** Every type
name and value name here comes out of the contract file and the crate. The
same image, unmodified, checks a coating line or a chemical plant. The test
suite proves it rather than claiming it: its fixtures, in
`tests/fixtures/`, are a coating laboratory, and the same code checks those
with no change but the contract file.

**All the sequence data here is simulated.** Every sequence says so in its own
description line, the accessions are placeholders under `example.org` and
resolve to nothing, and the quantities are invented.

## What is in here

| Path | What it is |
|---|---|
| `contracts/design_to_build.yaml` | The worked contract, 20 requirements, version 0.11.0 |
| `contracts/build_to_test.yaml` | The next handover, 2 requirements, version 0.3.0, a stub |
| `plate-test/valid/` | A crate that satisfies the contract, 109 entities |
| `plate-test/invalid/` | Five copies, each broken in exactly one way |
| `from-another-phase/` | A crate from an unrelated domain, a library catalogue |

The second contract exists to demonstrate one thing: adding a handover means
writing a file like that and nothing else. No class was written for it, no
name was registered anywhere, and no table maps its name to any code. A test
in the product's own suite greps the service source for every handover name
it knows and fails the day one appears in the code.

## What the contract covers

All five verbs the language has, both severities, and every extra field:

| Verb | Where it is used in the example |
|---|---|
| `be recorded` | The crate's profile, name and licence; a well's position; a construct's length |
| `be unique` | Two wells may not claim the same position on the plate |
| `point at something in the crate` | A well's construct; a step's inputs and outputs; the crate's own file list |
| `be a number between` | A construct's coding sequence length, which must be 300 to 3000 base pairs |
| `hold data` | Every file the crate names and carries must hold something |

Both contracts also carry an `expects` block, which lists the entity types
the contract is written for. Each one that is missing is refused on its own,
before a single requirement about it is applied. Write one: a contract
without it accepts crates it has never meaningfully checked, which was
measured on 11 November 2026 and is explained in
[WRITING_A_CONTRACT.md](../docs/WRITING_A_CONTRACT.md).

`severity: refuse` stops the handover. `severity: flag` records a finding and
lets it through. `of_type` narrows a reference to one kind of thing. `one_of`
lists the only values that mean anything. `repairable: true` allows a model
to be asked whether a value is already written down somewhere in the record,
and whatever it answers is then checked by these same rules.

## What the crates do

Measured on 11 November 2026, with no model running.

| Crate | Verdict | Why |
|---|---|---|
| `plate-test/valid` | ACCEPTED, 0 findings | |
| `plate-test/invalid/missing-conformsto` | REFUSED | The root does not say which profile it follows |
| `plate-test/invalid/dangling-reference` | REFUSED | It lists a file it then never describes |
| `plate-test/invalid/missing-gene-calling-mode` | REFUSED | The gene calling step's settings are nowhere in the crate |
| `plate-test/invalid/mode-in-prose` | REFUSED | The setting is in the crate, as a flag inside a command line |
| `plate-test/invalid/edge-handling-in-prose` | REFUSED | The setting is in the crate, written out in a sentence |
| `from-another-phase` | REFUSED | It contains nothing the contract is written for |

**The two prose crates are the ones worth understanding**, and they are
worth understanding together.

Nothing is missing from either. In both, the setting the contract asks for
is in the crate, written where no rule can read it. So a crate that
satisfies every rule a standard has can still be refused, and refused for
being unreadable rather than for being incomplete. That is the whole
argument for a contract sitting on top of a validator, in one example.

They differ in what a model can do about them. **With a model running**,
`edge-handling-in-prose` comes back `ACCEPTED_WITH_FLAGS`: its gene calling
step says in ordinary words that "contig edges were treated as closed, so no
partial genes were kept", so the model only has to read. `mode-in-prose`
stays refused: there the only trace is the flag `-c` in the command line
`prodigal -i contigs.fasta -a proteins.faa -p meta -c -q`, and recovering it
means knowing what that program's flags mean. Two models of 14 billion
parameters each were asked to do exactly that on 10 November 2026 and both
stated a wrong meaning without hedging. The rules threw the answer out and
nothing was written.

So the model helps when the value is in the text in words, and fails safely
when it is not.

## Running it

```
cd sentinel-oo
export SENTINEL_CONTRACTS=examples/contracts

PYTHONPATH=src python -m sentinel_oo examples/plate-test/valid \
    --contract design_to_build

PYTHONPATH=src python -m sentinel_oo \
    examples/plate-test/invalid/edge-handling-in-prose \
    --contract design_to_build
```

To see what is in a crate, which is the list a contract has to match:

```
PYTHONPATH=src python -m sentinel_oo --describe examples/plate-test/valid
```

To read the contract in plain words rather than as YAML:

```
PYTHONPATH=src python -m sentinel_oo --show-contract design_to_build
```

That is what a producing team reads to check themselves before they are
checked.

## Where these crates come from

They are the bioprospecting use case's own crates, which live in
`bioprospecting/exampleROcrates/` in this repository, copied in here so that
`sentinel-oo/` can be checked out on its own and still build, test and run
with nothing beside it.

One crate here has no copy there: `edge-handling-in-prose` was made on
11 November 2026 for the tutorial, so that the step about the model has a
case the model can actually solve.

`from-another-phase` is a library catalogue, chosen because nobody could
mistake it for a bioprospecting handover or for anybody's DBTL cycle, where
DBTL stands for Design, Build, Test, Learn. It is there so the tutorial's
most important lesson can be run rather than described: a contract with no
`expects` block accepts it, and one with such a block refuses it and names
every type it was looking for.

It is regenerated, along with the test suite's own fixtures, by:

```
cd tests/fixtures && python make_example.py
```
