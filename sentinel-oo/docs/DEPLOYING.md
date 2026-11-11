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
   image dev, commit c0525b0, model engine none
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
| `--stop` | Stop and remove the instance |

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

## A model is optional

With no model configured the service refuses and accepts exactly as it does
with one, except that it cannot recover a value that is present in a crate
only inside free text. The repair budget defaults to 0, so by default no
model is called at all.

Two local models with 14 billion parameters each were measured on this on
10 November 2026 and neither could do the job. That measurement is in the
product README. A model being wrong, slow, absent or confidently mistaken
changes no verdict and writes nothing into any record.

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
file at all. A hand written Compose file can do the same thing, but without
the validation in steps 1 and 4, so a broken contract will not be caught
until first use.

## Stopping

```
python deploy.py <your folder of contracts> --stop
```
