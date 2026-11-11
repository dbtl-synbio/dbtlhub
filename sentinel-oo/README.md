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
| `ACCEPTED_WITH_FLAGS` | Nothing stops the handover, but something was recorded for somebody to read. A value a model recovered from the crate's own text always lands here |
| `REFUSED` | At least one requirement failed. The next phase must not proceed |

A refusal still returns the crate, with the findings written inside it. A
refusal that exists only as a message in somebody's terminal is not a
record.

## What it is not

It is not a validator. A third party tool, `rocrate-validator`, already
checks that an RO-Crate is well formed, and this does not repeat that work.

The difference between the two is the point of the whole thing. Measured on
11 November 2026 with `rocrate-validator` 0.13.1, against the six crates of
the worked example, with no model running:

| Crate | `rocrate-validator` | `sentinel-oo` |
|---|---|---|
| The worked example | valid, 0 issues | ACCEPTED |
| Profile declaration removed | valid, 0 issues | REFUSED |
| A gene calling setting removed | valid, 0 issues | REFUSED |
| A reference to a file it never describes | valid, 0 issues | REFUSED |
| The setting present, but only as a flag in a command line | valid, 0 issues | REFUSED |
| The setting present, written out in a sentence | valid, 0 issues | REFUSED |

The last row is the one worth understanding. Nothing is missing from that
crate. The value is there, inside the text of a command line, where a person
can read it and no rule can. So a crate can satisfy every rule a standard
has and still be useless to the phase receiving it.

## Try it in two minutes

### What you need

| For | What |
|---|---|
| The commands in this section | Python 3.11 or later. On a Mac that is usually `python3`, not `python` |
| Deploying, further down | Docker, running. On a Mac that means Docker Desktop |
| A model, which is optional | Nothing extra: `deploy.py` starts one for you |

**About the model**, so there are no surprises. It runs under
[Ollama](https://ollama.com) in its own container. The default,
`qwen2.5:14b`, is about 9 gigabytes to download. Running it took 15,267
mebibytes, which is about 15 gigabytes, of graphics card memory when
measured on 11 November 2026 on an NVIDIA card: 8 gigabytes for the model
itself and 6 gigabytes of working memory, because Ollama gives the model
room for 32,768 tokens of text by default. A card with 16 gigabytes is
therefore tight, and one with 24 gigabytes is comfortable.

On that card the first answer took 39.6 seconds, of which about 19 seconds
was loading the model onto the card, and later answers took well under a
second. On a processor alone, including every Mac, because Docker cannot
reach a Mac's graphics hardware, expect tens of seconds for every answer. A
smaller model such as `qwen2.5:7b` is about 5 gigabytes and much faster,
and was not measured on the one job this service gives a model.

Everything below runs from this folder. Install it first, into a virtual
environment so nothing else on your machine is touched:

```
python3 -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -e .
```

That installs PyYAML, which the service needs, and puts `sentinel_oo` on the
path so the commands below work without setting `PYTHONPATH`.

```
export SENTINEL_CONTRACTS=examples/contracts
export SENTINEL_MODEL_URL=            # no model for these two minutes

python -m sentinel_oo examples/plate-test/valid --contract design_to_build
```

Without that second line the service tries to reach a model, finds none on
a machine that has not deployed one, and says so. It does not wait, and no
verdict changes.

That accepts. Now one that does not:

```
python -m sentinel_oo examples/plate-test/invalid/missing-conformsto \
    --contract design_to_build
```

```
  verdict    REFUSED

  REFUSE  The crate does not say which profile it follows, so nothing can be
          agreed about what its contents mean.
         at ./
```

That sentence came from a contract file, not from the code.

To see what is in a crate, which is the list a contract has to match:

```
python -m sentinel_oo --describe examples/plate-test/valid
```

To read a contract in plain words, which is what you send to the team that
produces the handover:

```
python -m sentinel_oo --show-contract design_to_build
```

**The worked example is a handover from Design to Build in a bioprospecting
cycle**: a panel of candidate proteins, the constructs made from them, and
the plate layout they are going onto, with a record of every step that
produced them. Bioprospecting means searching genomes and metagenomes for
enzymes that might be useful industrially.

**Nothing in the service knows what a protein or a plate is.** Every type
and value name in that example comes from the contract file and the crate,
and the same image checks a coating line, a chemical plant or anything else
whose handover can be written as a contract. The sequences in the example
are simulated and each one says so in its own line. See
[examples/README.md](examples/README.md).

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
| `examples/` | The worked example: 2 contracts and 7 crates |
| `docs/` | The manuals, as Markdown and as PDFs |
| `tests/` | 200 tests, which run inside the image at build time |
| `vocabulary/` | Empty. Taken from the `sentinel` framework at a later step |

## Running the tests

```
pip install -e ".[test]"
python -m pytest
```

214 tests. Three of them skip unless the third party RO-Crate validator is
installed, and those three matter most, because they ask a program that
knows nothing about this service whether the crate we returned is still
valid. The command above installs it along with pytest. **Its package is
called `roc-validator` and its command is `rocrate-validator`**, which
nobody would guess. In the container it is always installed, so there the
three always run.

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
| `SENTINEL_MODEL_FIRST_TIMEOUT` | Seconds to wait for the first answer, which includes loading the model | `180` |
| `SENTINEL_MODEL_TIMEOUT` | Seconds to wait for every answer after that | `60` |

```
docker compose up                                      model beside it
SENTINEL_MODEL_URL=http://gpu-box.lan:11434 ...        model elsewhere
SENTINEL_MODEL_URL= ...                                no model at all
```

`GET /health` says which of three states it is in: no model configured, a
model configured and answering, or a model configured and not answering.
Before 11 November 2026 all three looked identical, which is how an instance
can appear to be working while doing none of what it was deployed to do.

**What it can and cannot do, measured.** Both of these are crates in the
worked example, and you can run them.

Given `examples/plate-test/invalid/edge-handling-in-prose`, where the gene
calling step's description says in words that "contig edges were treated as
closed, so no partial genes were kept", a model of 14 billion parameters
recovered the value `closed`, the contract's own requirement confirmed it,
and the handover was accepted with a flag. Given
`examples/plate-test/invalid/missing-gene-calling-mode`, where the value is
not in the crate at all, the model wrote nothing and the handover was
refused.

Given the harder crate, `examples/plate-test/invalid/mode-in-prose`, the
same setting is recorded only as the flag `-c` inside a command line.
Recovering it means knowing what that program's flags mean. Two models of
the same size failed on 10 November 2026 and both stated a wrong meaning
without hedging. Every one of those outcomes was a refusal with nothing
written, because the contract's own requirements check whatever the model
proposes before it is kept.

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
