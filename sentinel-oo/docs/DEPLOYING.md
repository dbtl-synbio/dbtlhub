# Deploying your own instance

You need a folder of contract files. That is the whole of what makes an
instance yours, and you will not write any code.

See [WRITING_A_CONTRACT.md](WRITING_A_CONTRACT.md) for the contract language.

## One command

```
python deploy.py <your folder of contracts>
```

For example, using the worked example that ships with the product:

```
python deploy.py examples/contracts
```

The deployment is a program rather than a page of instructions on purpose.
Nothing is tailored by hand and no person follows steps.

## What it does, in order

It stops at the first thing that fails, and the exit code is 1 when it stops.

**1. It reads every contract in your folder** and refuses the deployment if
any of them is malformed, naming the file, the requirement and what a
requirement may say.

This happens before anything is built or started. A deployment that starts
with a broken contract discovers the problem at first use, which means
discovering it in front of whoever sent the handover. Finding out here costs
nobody anything.

It also refuses a folder that holds no contract files at all, because an
instance with none would refuse every handover it was given.

**2. It builds the generic image** from the product folder. The product's own
test suite, 200 tests, runs inside that build, and the image cannot be
produced if any of them fails.

Pass `--no-build` to use an image that already exists.

**3. It starts an instance** with your contracts folder mounted read only at
`/contracts`. The image is not modified and holds no contracts of its own.

Read only is deliberate: a service that checks handovers has no business
editing the contract it checks against.

**4. It checks the running instance is serving what was validated**, comparing
the contract names, their versions, and a checksum over the files.

That catches two things. The wrong folder being mounted, which is the common
mistake. And a contract edited between step 1 and step 3, which is a real
window because the build takes about a minute.

## What you see when it works

```
sentinel-oo: deploying a tailored instance

1. Reading contracts from examples/contracts
   coating_to_inspection        0.2.0      2 requirements
   mixing_to_coating            1.1.0     19 requirements
   checksum over all of them: sha256:dd5dd91a...

2. Building the generic image
   sentinel-oo:dev built
   the product's test suite ran inside the build and passed

3. Starting the instance
   container sentinel-examples started from sentinel-oo:dev
   contracts mounted read only from examples/contracts

4. Checking the instance serves what was validated
   answering on http://127.0.0.1:8080
   image dev, commit c0525b0
   model: reachable  (qwen2.5:14b at http://model:11434)
   2 contract(s) served, checksum matches what was validated

Deployed.
```

## The options

| Option | What it does |
|---|---|
| `--check-only` | Validate the contracts and stop. Nothing is built or started |
| `--no-build` | Use the existing image instead of building |
| `--crates <folder>` | Mount a folder of crates read only at `/crates`, for trying it |
| `--port <n>` | Which port to serve on. The default is 8080 |
| `--name <n>` | The container name. The default is `sentinel-<your folder's parent>` |
| `--image <n>` | The image to build and run. The default is `sentinel-oo:dev` |
| `--model-url <url>` | Where the model is. An empty value means no model |
| `--model <name>` | Which model to use, pinned by name |
| `--reachable-from-network` | Let other machines reach it. Off by default |
| `--yes` | Agree in advance to downloading the model |
| `--stop` | Stop and remove the instance, the model beside it, and the network between them |

## Using it once it is running

```
curl -s http://127.0.0.1:8080/contracts

curl -s -X POST --data-binary @<a crate>/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/<your contract name>
```

The reply carries the verdict, the findings, and the crate with the service's
record of what it checked written inside it.

| Method and path | What it does |
|---|---|
| `POST /check/{contract}` | The whole job. A crate in, a checked crate out |
| `GET /contracts` | Which contracts this instance holds, with versions and a checksum |
| `GET /contracts/{name}` | One contract written out in plain words |
| `GET /runs` | The runs this instance is still holding |
| `GET /health` | The build it is running and which model, if any |
| `GET /openapi.json` | A description of the service, generated from its route table |

## Two instances at once

The image is generic, so one image serves any number of deployments. Give
each one its own port and name:

```
python deploy.py <your own contracts> --port 8080
python deploy.py examples/contracts --port 8081 --name sentinel-example
```

That was run on 11 November 2026 and both instances served at the same time
from one unmodified image, each holding only its own contracts and each
refusing a contract name the other one knew.

## For a coordinator agent rather than a pipeline

The same image speaks the Model Context Protocol on standard input and
output instead of HTTP. An agent starts it when it wants it:

```
docker run -i --rm \
  -v "$PWD/<your contracts>:/contracts:ro" \
  sentinel-oo:dev --agent-interface
```

It offers four tools: `check_handover`, `list_handovers`, `read_contract` and
`get_run_graph`. It never returns the crate, only the verdict, the findings
and the path the crate was written to, because a crate is thousands of lines
of JSON and putting that in an agent's context costs money on every call and
invites the agent to start editing laboratory records.

A test fails if the two interfaces ever give different verdicts.

**Not yet tested against a real Model Context Protocol client.** It is tested
against the protocol as written down.

## The model, and where it runs

**A model is called by default.** A sentinel at a handover without one is
not what this project is about.

**It runs in its own container, which does not have to be on this machine.**
A model worth using wants a GPU, and the machine with the GPU is usually not
the machine running the service.

| Option | Environment variable | What it is |
|---|---|---|
| `--model-url` | `SENTINEL_MODEL_URL` | Where the model is. Default `http://model:11434` |
| `--model` | `SENTINEL_MODEL` | Which model, pinned by name. Default `qwen2.5:14b` |

```
python deploy.py <contracts>                                 a model beside it
python deploy.py <contracts> --model-url http://gpu:11434    a model elsewhere
python deploy.py <contracts> --model-url ""                  no model at all
```

`compose.yaml` starts a model container alongside the service, using the
`ollama/ollama` image, with a volume so the model is not downloaded again on
every start. On a machine with an NVIDIA GPU, uncomment the `deploy` block
in that file to hand the GPU to the model container.

### Knowing whether it is actually there

`deploy.py` says so at step 4, and `GET /health` reports one of three
states:

| State | Meaning |
|---|---|
| `none configured` | No model was asked for. Deliberate |
| `reachable` | A model is configured and answering |
| `configured but not answering` | A model was wanted and cannot be reached |

The third carries the error and says what follows from it: checks run
normally, no verdict changes, and a value recorded only in free text cannot
be recovered. Before 11 November 2026 all three looked identical, which is
how an instance can appear to be working while doing none of what it was
deployed to do.

### Why having it on is safe

Not because models are reliable. Because of where it sits.

It is asked one question, about a check that has already failed, at a place
the rules named. Whatever it answers is written to a copy and the whole
contract is run again, and the change is kept only if every requirement
reading that value now passes and nothing new broke anywhere.

Measured on 11 November 2026 against a running instance: given a crate whose
value sits inside a command line, a 14 billion parameter model recovered it
and the handover was accepted in about half a second. Given a crate where
the value is not present at all, it wrote nothing and the handover was
refused.

## Who can reach it

**By default, only this machine.** The port is published on the loopback
interface, so other machines on your network cannot send it requests.

**The service asks for no password of any kind.** That is why the default is
what it is. Before 11 November 2026 it published on every interface, which
on shared wifi at a conference means anyone on that network could use it.

To let other machines reach it:

```
python deploy.py <contracts> --reachable-from-network
```

It says so when it starts, in those words, because somebody doing it by
accident should find out immediately. Put it behind something that
authenticates before you use it anywhere you do not control.

## What your deployment folder needs

Only the contracts. Everything else is optional:

```
your-deployment/
  contracts/
    your_handover.yaml        the whole of the tailoring
  crates/                     optional, for trying it
  README.md                   optional, what this deployment is for
```

There is a worked one in `examples/`.

## If you prefer Docker Compose

`deploy.py` uses `docker run` directly, so a deployment needs no compose
file at all. `compose.yaml` in this folder does the same thing for somebody
who would rather use Compose:

```
SENTINEL_CONTRACTS=../my-deployment/contracts docker compose up
```

| Setting | What it does | Default |
|---|---|---|
| `SENTINEL_CONTRACTS` | Your folder of contracts | The worked example |
| `SENTINEL_PORT` | Which port | 8080, which collides with `deploy.py` |
| `SENTINEL_BIND` | Which interface | `127.0.0.1`, this machine only |
| `SENTINEL_MODEL_URL` | Where the model is | A container beside it |

**Three things it does not do**, which is why `deploy.py` is the ordinary
route: it does not check your contracts before starting, it does not tell
you that it is about to download about 11 gigabytes and wait for a yes, and
it does not confirm afterwards that the running instance serves what you
meant.

Checked crates go into a named volume rather than a folder, so nothing is
written into the repository. Copy them out with
`docker compose cp sentinel:/out ./out`.

## Stopping

```
python deploy.py <your folder of contracts> --stop
```
