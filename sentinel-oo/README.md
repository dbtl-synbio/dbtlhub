# sentinel-oo

Decides whether one phase of a Design, Build, Test, Learn cycle can accept what
the previous phase produced.

A crate goes in and a crate comes out. The crate that comes out is the one that
went in, plus a record of what was checked, against which rules, by which build
of this service, with which model if any, and what was found.

The full design is in `outputs/sentinel_service_spec.md` in the working project.
This README covers only what exists today.

## Start here

| If you want to | Read |
|---|---|
| Use it: tailor it to your own handover | [docs/USER_MANUAL.md](docs/USER_MANUAL.md), which has a tutorial you can run |
| Look up the contract language | [docs/WRITING_A_CONTRACT.md](docs/WRITING_A_CONTRACT.md) |
| Get an instance running | [docs/DEPLOYING.md](docs/DEPLOYING.md) |
| Call it from a pipeline or an agent | [docs/API_MANUAL.md](docs/API_MANUAL.md) |
| Understand how it is built, with diagrams | [docs/SYSTEM_MANUAL.md](docs/SYSTEM_MANUAL.md) |
| See a complete small example | [examples/README.md](examples/README.md) |

All three are also built as PDFs in [docs/pdf/](docs/pdf/). Rebuild them with
`cd docs && ./make_pdfs.sh`.

**The product is generic and holds no deployable contracts.** You supply a
folder of them and they are mounted into an unmodified image. One command
does the whole deployment:

```
python deploy.py <your folder of contracts>
```

Built by Anil Wipat (Newcastle University and Prozomix Ltd) and
Marco Anteghini (LifeGlimmer).

sentinel-oo is a deployable version of sentinel. The generic system is
combined with a hand written contract file that tailors the sentinel to a
system and deploys it to a container. A REST API is provided, and Model
Context Protocol access for other agents.

What it takes from the sentinel framework is set out under Acknowledgements
in [docs/SYSTEM_MANUAL.md](docs/SYSTEM_MANUAL.md).

The rest of this file is the record of how it was built and what was found
while building it, which is useful if you are changing the service and not
if you are only using it.

## What works today: steps 1 to 6 of the build order

**A crate goes in. It is checked against a contract file. A crate comes out
carrying what was found.**

There is no check written in Python anywhere. Every requirement lives in a file
under `contracts/`, and the engine that applies them knows no handover by name.

**A handover is added by writing a file.** The product ships no deployable
contracts at all. A deployment supplies its own. The worked example in
`examples/contracts/` has two of them, and the second was added with no
class, no registration call and no entry in any table mapping a name to code.
The test that proves it greps the source and fails the day somebody adds one:

```
$ grep -ri "coating_to_inspection" src/ | wc -l
0
```

What is deliberately absent: no graph, no model, no web interface and no agent
interface. Each arrives with its own step.

### Run it

The product holds no contracts, so every run has to be told where a
deployment's contracts are. Either pass `--contracts`, or set it once:

```
export SENTINEL_CONTRACTS=examples/contracts

PYTHONPATH=src python -m sentinel_oo \
    examples/coating-test/valid --out out
```

It prints the record it wrote and leaves `out/ro-crate-metadata.json` behind.

```
python -m sentinel_oo <crate> --contract mixing_to_coating
python -m sentinel_oo --list-contracts
python -m sentinel_oo --show-contract mixing_to_coating
```

`--show-contract` prints the rules in plain words, which is what a producing
team reads to check themselves before they are checked.

Exit codes: 0 when the crate was not refused, 1 when it was, 2 when what it was
given is not a crate at all or the contract was not found.

A crate that fails the check:

```
PYTHONPATH=src python -m sentinel_oo \
    examples/coating-test/invalid/missing-conformsto
```

```
  verdict    REFUSED

  REFUSE  The crate does not say which profile it follows, so nothing can be
          agreed about what its contents mean.
         at ./
```

**That crate passes `rocrate-validator` and fails this check.** It is a valid
RO-Crate 1.3 that does not say which profile it follows, which is the whole
argument for a checking service in one example: conformance is not sufficiency.

### Run it in Docker

The build context is the repository root, not this folder, because the tests
read the example crates next door.

```
docker compose -f sentinel-oo/compose.yaml up --build
```

The image runs the test suite at build time, so an image whose tests fail is
never built.

### Run the tests

```
python -m pytest
```

113 tests. Three of them skip unless `rocrate-validator` is installed, and those
three are the ones that matter most, because they ask a third party program
whether the crate we returned is still valid. In the container it is installed,
so there they always run.

```
pip install -e ".[test]"
```

## What is in here

| File | What it is |
|---|---|
| `src/sentinel_oo/crate.py` | The crate, held immutably. Reading, checksums, writing |
| `src/sentinel_oo/identity.py` | What built this service and what it is carrying |
| `src/sentinel_oo/blessing.py` | The record, as pure data |
| `src/sentinel_oo/provenance.py` | Writing that record into a crate |
| `src/sentinel_oo/contract.py` | Reading contract files. Executes nothing |
| `src/sentinel_oo/rules.py` | Applying a contract. The only component that may decide |
| `src/sentinel_oo/sentinel.py` | The orchestrator. Holds no rule of its own |
| `src/sentinel_oo/__main__.py` | The command line, which is the whole surface until step 5 |
| `tests/test_invariants.py` | The tests that protect design decisions rather than code |
| `contracts/` | One file per handover. This is where a handover is added |
| `vocabulary/` | Empty. Taken from the `sentinel` framework at a later step |

## Three things worth knowing

**The crate is immutable.** Every method that changes anything returns a new
crate and leaves the original exactly as it was, down to nested values being
read-only views. That is what lets the service show what it was sent at the end
of a run, and what keeps the recorded checksum of the input correct without
anybody having to remember it separately.

**The checksum ignores formatting.** Entities are sorted by identifier and keys
sorted within them before hashing, so running a crate through a pretty printer
does not invalidate a record written about it. Changing any value does change
it.

**The writer alters exactly one thing it did not write.** It appends the new
action to the root entity's `mentions`. Without that the action sits in the
crate unreachable from the root, which was one of the six faults found in the
published example crate after it had already passed validation, and which no
validator catches. Everything else comes out byte for byte as it went in, and
there is a test that says so.

## What a local model could and could not do, measured on 10 November 2026

The one job a model has here is to read a value out of free text when no rule
can. The test case is a crate whose gene calling step records no setting but
whose description says it ran as `prodigal -i contigs.fasta -a proteins.faa
-p meta -c -q`. The answer, "closed", is in that command line.

Two models already on the machine were asked, both running locally through
Ollama, which is a program that runs a model on your own machine.

| Model | Answer | Outcome |
|---|---|---|
| `qwen2.5:14b` | nothing found | Handover refused, nothing written |
| `qwen2.5-coder:14b` | nothing found | Handover refused, nothing written |

Neither recovered it. Asked directly what Prodigal's `-c` flag does, both gave
a confident and wrong answer: one said it excludes proteins with internal stop
codons, the other that it is a mode for complete circular chromosomes. The
documentation says "Closed ends. Do not allow partial genes at edges of
sequence."

Told the meaning explicitly and asked only to apply it, `qwen2.5-coder:14b`
answered "closed", which is right, and `qwen2.5:14b` answered "open", which is
the opposite of right.

**Three things follow.**

A model of this size cannot be relied on to know what a bioinformatics tool's
flag means, and will state a wrong meaning without hedging.

Supplying the domain knowledge in the prompt would fix the mapping, and that
knowledge would have to live somewhere. It must not live in the contract: a
contract says what must be true and carries no instruction to a model, for the
reasons in section 10 of the specification.

**Nothing bad happened in any case.** Every outcome above was a refusal with
nothing written. A stub model answering "open" was discarded by the rules, and
so was one answering the raw flag `-c`. The system is built so that a model
being wrong, slow, absent or confidently mistaken changes no verdict and
writes nothing into the record, and that is what was observed.

## Known gaps

Recorded rather than left to be discovered.

**The action does not name an agent.** Process Run Crate says an action should
say who or what ran it, meaning the person or organisation, not the software.
The service is not told, so it writes nothing rather than inventing a name. It
should become something a caller can supply.

**A crate with no `@context` is read without complaint.** It is interpretable,
so the reader accepts it, and nothing checks for it yet. It is now expressible
as a contract requirement, so it is a line somebody should write rather than a
gap in the code.

**A rule cannot compare one value against another.** A construct's length
should be consistent with the length of the protein it was designed from,
and a construct half or double the expected size means a truncation, a
duplication or a wrong sequence pasted in. There is no way to say that: a
requirement reads one thing and judges it on its own. The first requirement
met that is out of reach rather than merely unwritten.

**A rule cannot depend on another value.** The general form of the gene
calling rule is conditional: if the edges were open, then completeness
matters. Every requirement stands on its own, so a contract has to be
written for a pipeline that always does one thing.

**There is no way to say "must be a number" or "if present, must be one
of".** Both can be forced with `be a number between` over an absurd range,
or `one_of` attached to `be recorded`, and both read oddly in a file people
are meant to understand. The vocabulary should grow a plain way to say
them rather than leaving the contortion in the contract.

**Types are compared as plain text.** Nothing knows that schema.org considers a `Protein` to be a kind of `BioChemEntity`, so a requirement asking for one will not accept the other. A rule can therefore look stricter than it is, or refuse something it should allow. Teaching it the hierarchy means giving it the whole of schema.org.

**Rewriting the whole crate on every change.** Each write rebuilds and re-hashes
the entire graph. At 105 entities that is immeasurable. It is written down here
so nobody is surprised by it at a hundred times the size.

## Four faults found by running it

Recorded because both were found by use rather than by review, which is the
argument for having something runnable from step 1.

**Writing to a folder that did not exist yet produced a file with no
extension.** The check for a folder tested only whether one already existed.

**The service entity had no `url`.** RO-Crate 1.3 requires one on any
`SoftwareApplication`, and the third party validator refused the returned crate
until it was added. Our own tests had passed.

**Two exceptions escaped that should not have.** A string containing the
characters `@id` sitting in the graph produced a `TypeError`, because testing
`"@id" in entity` is true of any string containing them. Adding an entity with
no identifier produced a `KeyError`. The crate class promises that nothing but
`CrateMalformed` reaches a caller, and in both cases it broke that promise.
Found by feeding it deliberately awkward input rather than by reading it.

**The first version of the profile check looked at the wrong entity.** It read
`conformsTo` on the metadata descriptor, which says which version of RO-Crate
the file is. The profile the contents follow is declared on the root data
entity instead. The check looked correct, passed its own tests, and caught
nothing. Running it against a crate built to be broken is what exposed it.

## What a contract looks like

```yaml
contract: mixing_to_coating
version: 1.0.0

requires:
  - name: declares_a_profile
    applies_to: root
    property: conformsTo
    must: be recorded
    severity: refuse
    message: >-
      The crate does not say which profile it follows, so nothing can be
      agreed about what its contents mean.
```

Five things per requirement: what it applies to, which property, what must be
true of it, whether failing refuses the handover or raises a flag, and the
sentence a person reads.

There are four kinds of demand, and that is the whole vocabulary:

| `must` | Means |
|---|---|
| `be recorded` | The property is present. With `one_of`, its value is one of a list |
| `be unique` | No other entity records the same value. Both ends of a clash are reported |
| `point at something in the crate` | The reference lands on an entity that is really there. With `of_type`, of the right kind |
| `be a number between` | With `between: [low, high]`, inclusive at both ends |

Only `be recorded` has anything to say about a property that is absent. "It
must be present" and "it must be sound" are two requirements, and a rule doing
both would make one of them impossible to say.

### Where the line is between a file and the code

The code knows the four kinds of check above. It knows nothing else.

Which handover, which kind of entity, which property, which values, which
numbers, whether failing refuses or flags, and the sentence a person reads: all
of those live in a file.

So "no two constructs may claim the same well" is written entirely in a
contract. The code contributes the words `be unique`.

**A kind of check may go in the code only if it can be explained without
mentioning biology.** "Values must not be shared" passes that test. "The
sequence must be valid DNA" does not, and the right form of it is a general
check that every character comes from a given set, with `ACGT` written in the
contract file.

A requirement that none of the four can express needs the vocabulary to grow,
which is a decision taken on purpose rather than a special case added in a
hurry.

**There is no field for instructing a model**, and a file carrying an unknown
field is refused rather than ignored, so a misspelled key cannot sit in a file
looking effective. The reasons are in section 10 of the specification. The one
that matters most: this service accepts a contract from the sender, so prompt
text in a contract would mean the sender writing the model's instructions.

Everything that can be wrong with a contract is found when it is read, with the
file named, rather than when somebody posts a crate.

## Next

Step 4 of the build order, which is in two halves.

**The vocabulary half is done.** Writing out what the Design to Build handover
actually needs showed that most of it could not be said at all, so uniqueness,
following a reference, and numeric ranges were added.

**The biology half is not started**, because it is a question about the
laboratory rather than about the code. What must Design give Build, and what
goes wrong without each thing? The three requirements in the shipped contract
today are checks on the packaging: a crate could satisfy all three and hold an
empty folder.
