# sentinel-oo

**A service that stands at one handover of a DBTL cycle and decides whether
the next phase can accept what the previous phase produced. It can refuse.**

DBTL stands for Design, Build, Test, Learn, the engineering cycle used in
synthetic biology. A **handover** is the moment one phase passes its output
to the next, and there are four of them in a cycle.

`sentinel-oo` is a deployable version of [`sentinel`](../sentinel/), which
sits beside it in this repository. The generic service is combined with a
hand written contract file that tailors it to one system, and deployed to a
container. A web interface is provided, and Model Context Protocol access
for other agents.

## What it actually does

A **crate** goes in and a crate comes out. A crate here means an RO-Crate: a
folder of data files with a JSON file alongside them describing what each
file is and how the things in it relate to one another. It is how a handover
travels.

The crate that comes out is the one that went in, plus a record of what was
checked, against which rules, by which build of the service, with which
model if any, and what was found.

There are three answers:

| Verdict | What it means |
|---|---|
| `ACCEPTED` | Nothing was found. The next phase proceeds |
| `ACCEPTED_WITH_FLAGS` | Nothing stops the handover, but something was recorded for somebody to read |
| `REFUSED` | At least one requirement failed. The next phase must not proceed |

A refusal still returns the crate, with the findings written inside it. A
refusal that exists only as a message in somebody's terminal is not a
record.

## What it is not

It is not a validator. A third party tool, `rocrate-validator`, already
checks that an RO-Crate is well formed, and this does not repeat that work.

The difference between the two is the point of the whole thing. Measured
against five crates on 10 November 2026:

| Crate | `rocrate-validator` | `sentinel-oo` |
|---|---|---|
| The worked example | valid | ACCEPTED |
| Profile declaration removed | valid | REFUSED |
| A required setting removed | valid | REFUSED |
| A reference to a file it never describes | valid | REFUSED |
| The setting present, but only in prose | valid | REFUSED |

The last row is the one worth understanding. Nothing is missing from that
crate. The value is there, inside the text of a command line, where a person
can read it and no rule can. So a crate can satisfy every rule a standard
has and still be useless to the phase receiving it.

## Try it in two minutes

Everything below runs from this folder and needs only Python 3.

```
export SENTINEL_CONTRACTS=examples/contracts

PYTHONPATH=src python -m sentinel_oo examples/coating-test/valid \
    --contract mixing_to_coating
```

That accepts. Now one that does not:

```
PYTHONPATH=src python -m sentinel_oo \
    examples/coating-test/invalid/missing-conformsto \
    --contract mixing_to_coating
```

```
  verdict    REFUSED

  REFUSE  The crate does not say which profile it follows, so nothing can be
          agreed about what its contents mean.
         at ./
```

That sentence came from a contract file, not from the code.

To read a contract in plain words, which is what you send to the team that
produces the handover:

```
PYTHONPATH=src python -m sentinel_oo --show-contract mixing_to_coating
```

The worked example is a coating laboratory, deliberately not a DBTL cycle,
so that nothing in the product looks as though it belongs to one use case.
See [examples/README.md](examples/README.md).

## Deploy your own

**The service holds no contracts and knows no handover by name.** You supply
a folder of contract files and they are mounted into an unmodified image.
One command does the whole deployment:

```
python deploy.py <your folder of contracts>
```

It validates every contract and refuses before building anything, builds the
image with the test suite running inside the build as a gate, starts the
instance with your contracts mounted read only, then checks the running
instance is serving exactly what it validated.

**You will not write any code.** [docs/USER_MANUAL.md](docs/USER_MANUAL.md)
has a tutorial that builds a contract from nothing, one requirement at a
time, and every command in it can be run.

## Where to read more

| If you want to | Read |
|---|---|
| Tailor it to your own handover | [docs/USER_MANUAL.md](docs/USER_MANUAL.md) |
| Look up the contract language | [docs/WRITING_A_CONTRACT.md](docs/WRITING_A_CONTRACT.md) |
| Get an instance running | [docs/DEPLOYING.md](docs/DEPLOYING.md) |
| Call it from a pipeline or an agent | [docs/API_MANUAL.md](docs/API_MANUAL.md) |
| Understand how it is built | [docs/SYSTEM_MANUAL.md](docs/SYSTEM_MANUAL.md), with diagrams |
| See a complete small example | [examples/README.md](examples/README.md) |
| Know what it cannot do | [TODO.md](TODO.md) |
| Read how it was built, and the faults that found | [docs/BUILD_NOTES.md](docs/BUILD_NOTES.md) |

Three of those are also built as PDFs in [docs/pdf/](docs/pdf/): the user
manual, which absorbs the contract language and the deployment guide into
one document, the API manual, and the system manual. Rebuild them with
`cd docs && ./make_pdfs.sh`, which needs pandoc and XeLaTeX.

## What is in here

| Path | What it is |
|---|---|
| `src/sentinel_oo/sentinel.py` | The orchestrator. Holds no rule of its own |
| `src/sentinel_oo/crate.py` | The crate, held immutably. Reading, checksums, writing |
| `src/sentinel_oo/contract.py` | Reading contract files. Executes nothing |
| `src/sentinel_oo/rules.py` | Applying a contract. The only component that may decide |
| `src/sentinel_oo/engines.py` | The model adapter. On by default, over the network |
| `src/sentinel_oo/repair.py` | Writing a proposed value, then handing it back to the rules |
| `src/sentinel_oo/provenance.py` | Writing the record into a crate |
| `src/sentinel_oo/blessing.py` | That record, as pure data |
| `src/sentinel_oo/identity.py` | Which image, commit and contracts ran |
| `src/sentinel_oo/api.py` | The web interface |
| `src/sentinel_oo/agent_interface.py` | Model Context Protocol, for a coordinating agent |
| `src/sentinel_oo/runs.py` | The last few runs, held in memory |
| `src/sentinel_oo/__main__.py` | The command line |
| `src/sentinel_oo/__init__.py` | What the package offers, and how to build one |
| `deploy.py` | The deployment program |
| `examples/` | The worked example: 2 contracts and 6 crates |
| `docs/` | The manuals, as Markdown and as PDFs |
| `tests/` | 200 tests, which run inside the image at build time |
| `vocabulary/` | Empty. Taken from the `sentinel` framework at a later step |

## Running the tests

```
python -m pytest
```

200 tests. Three of them skip unless `rocrate-validator` is installed, and
those three matter most, because they ask a third party program whether the
crate we returned is still a valid RO-Crate. In the container it is
installed, so there they always run.

```
docker build -t sentinel-oo:dev .
```

The image runs the test suite at build time and cannot be produced if it
fails.

## The model, which is on by default and in its own container

A sentinel at a handover without a model is not what this project is about,
so one is called unless a deployment says otherwise.

**It has exactly one job.** When a check fails, it is asked whether the
value is already written down somewhere in the record, including inside free
text. A rule can only read a value recorded as a value; a fact sitting in a
sentence is invisible to it.

**Whatever it answers goes back through the rules before it counts.** That is
what makes turning it on safe, and it is a property of where the model sits
rather than of models being reliable. A proposal is kept only if every
requirement reading that value now passes and nothing new broke. Measured
over two days, every wrong answer was discarded and nothing was written.

**The model runs in its own container**, and that container does not have to
be on this machine. A model worth using wants a GPU, and the machine with
the GPU is usually not the machine running the service. Two settings, both
environment variables:

| Setting | What it is | Default |
|---|---|---|
| `SENTINEL_MODEL_URL` | Where the model is | `http://model:11434` |
| `SENTINEL_MODEL` | Which model, pinned by name | `qwen2.5:14b` |

```
docker compose up                                      model beside it
SENTINEL_MODEL_URL=http://gpu-box.lan:11434 ...        model elsewhere
SENTINEL_MODEL_URL= ...                                no model at all
```

`GET /health` says which of three states it is in: no model configured, a
model configured and answering, or a model configured and not answering.
Before 11 November 2026 all three looked identical, which is how an instance
can appear to be working while doing none of what it was deployed to do.

**What it can and cannot do, measured.** Given a crate whose drying
atmosphere is recorded only inside the command line `dryer --atmosphere dry`,
a 14 billion parameter model running locally recovered it and the handover
was accepted. Given a crate where the value is not present at all, it wrote
nothing and the handover was refused.

Given a harder case, a gene calling setting recorded only as the flag `-c`,
where recovering the value means knowing what the flag means, two models of
the same size failed on 10 November 2026 and both stated a wrong meaning
without hedging. Every one of those outcomes was a refusal with nothing
written.

So it helps when the value is in the text and fails safely when it is not.
Section 7 of [docs/SYSTEM_MANUAL.md](docs/SYSTEM_MANUAL.md) has the full
measurement.

## Authors

Built by Anil Wipat (Newcastle University and Prozomix Ltd) and
Marco Anteghini (LifeGlimmer), for Project 25 at ELIXIR BioHackathon Europe
2026.

What `sentinel-oo` takes from the [`sentinel`](../sentinel/) framework is
set out under Acknowledgements in
[docs/SYSTEM_MANUAL.md](docs/SYSTEM_MANUAL.md).
