# The Architect, in a container

Two files and one engine. The container is the easy part; the key is not, so
read [What you are trusting](#what-you-are-trusting-when-you-paste-a-key-in-here)
before you export anything.

```bash
# from the repository root
docker build -f architect/deploy/Dockerfile -t dbtl-architect:dev .
docker run --rm dbtl-architect:dev                      # the health check
docker run --rm -v runs:/app/runs dbtl-architect:dev architect/wiring.py
```

or with Compose, from this directory:

```bash
docker compose up architect          # the real agents, no key, offline
docker compose run --rm check        # the health check, and read it
docker compose run --rm with-model   # with your key, if you have one
```

Any file in the image is runnable, because the entrypoint is `python3` and
nothing else:

| | |
|---|---|
| `tests/test_framework.py` | 16 checks over the whole framework. The default. |
| `architect/wiring.py` | the four real phase agents and the four real sentinels, under the Architect |
| `architect/architect.py` | the loop with the verdicts scripted, so the policy is visible |
| `framework/engines_api.py` | what happens to an API key, asserted |
| `scripts/show_agents.py` | what agents are in here |

## What is in the image, and what is not

146 MB: `python:3.13-slim` pinned by digest, plus 1.1 MB of Python.

**Nothing is installed.** There is no `pip install` line in the Dockerfile.
That is not a size optimisation - it is how `requirements.txt` stays honest.
That file promises every demo and every script runs on the Python standard
library alone; an image that quietly installed a dependency would make the
promise untestable, and the test suite that runs at build time is the test.
So: no compiler in any layer, no headers, no wheel cache, nothing to strip out
of a final stage. PyYAML is still optional and still absent, and
`load_contract()` reads the `*.schema.json` form of each contract.

**No key, and nowhere to put one.** The image contains no key, no key file, no
placeholder and no `--build-arg` for one. A build argument would be visible in
`docker history` for the life of the image, which is why the key is not one.

**Nothing listens.** No `EXPOSE`, no port, no bind address, and no `ports:`
section in `compose.yaml`, because nothing in this framework opens a socket.
The commented block in `compose.yaml` is the shape to use if that ever changes,
and it binds `127.0.0.1` unless the operator deliberately names something else.

**The literature scripts are not in it.** Six of the eighteen files in
`scripts/` are copied - the six that import nothing but the standard library
and this framework. The rest belong to the citation survey and need matplotlib,
pandas and the network; including them would mean either a broken script in
the image or a toolchain that exists only for them.

## The health check proves the framework works

```bash
docker compose run --rm check          # or: docker run --rm dbtl-architect:dev
```

The check is the test suite, not a liveness ping. It runs four demonstrations
as subprocesses and asserts the verdicts they report, checks that a profile's
predicted and measured quantities share a unit, that a graph query reaches a
physical sample *on disk* rather than in memory, and that a patch naming a path
the validator did not report is refused. A container that answers it is a
container in which the framework demonstrably works.

The same command is the image's `HEALTHCHECK`, so a container kept running
reports `healthy` on its own. Two consequences worth knowing:

- **It writes.** A real run leaves real run directories in `/app/runs`. That is
  the price of a check that is a run; a check that wrote nothing would be
  proving less. If you keep a container up with the health check firing, expect
  its runs beside yours.
- **One test skips.** `test_handover_one_accepts_the_published_crate` needs a
  crate from the `dbtlhub/bioprospecting` repository, which is deliberately not
  in the image. `OK (skipped=1)` is the expected result, not a partial pass.

The check is also a build gate. The `test` stage runs it and the engine's key
checks, then touches a marker file; the final stage copies that marker in. The
marker cannot exist unless both passed, so an image whose tests fail is never
produced.

## `runs/` is a volume, so a run outlives the container

Every ledger, every crate that grew, every graph and every handover package is
written under `/app/runs`. `compose.yaml` mounts a named volume there:

```bash
docker compose cp architect:/app/runs ./runs     # copy a run out
docker volume rm dbtl-architect_runs             # throw them all away
```

A named volume rather than a bind mount into the working tree, for two reasons:
the container runs as uid 10001, not as you, so a bind mount on Linux would be
unwritable or would leave files you do not own in your checkout; and `runs/` is
in `.gitignore` precisely because nobody wants a demo's output in a commit. To
use a directory of your own anyway, bind-mount it and pass
`user: "${UID}:${GID}"` - the comment in `compose.yaml` has the lines.

The volume is deliberately not declared with `VOLUME` in the Dockerfile. A
declared volume makes a plain `docker run` create an anonymous one that nobody
cleans up, and hides whether the operator mounted anything at all. Mount it, or
accept that the run dies with the container.

## The model is optional, and the default has none

The framework's default engine is `RulesEngine`: deterministic, offline, no
key, no network. It repairs only what can be repaired without inventing data -
a unit the profile states, a checksum computable from the crate - and leaves
everything else for a person, on purpose. `docker compose up architect` runs
that way, and with a key exported in your shell it *still* runs that way: the
`architect` service passes no environment variable in at all, which you can
check yourself:

```bash
ANTHROPIC_API_KEY=whatever docker compose run --rm --entrypoint env architect | grep ANTHROPIC
# (prints nothing)
```

`framework/engines_api.py` adds `ApiEngine`, which calls the Anthropic Messages
API over `urllib.request` - one POST, standard library, no `anthropic` package
and no `requests`, for the same reason the image installs nothing.

```python
from framework.engines_api import ApiEngine
agent = DesignToBuildAgent(profile="bioprospecting", engine=ApiEngine())
```

The default model is the constant `DEFAULT_MODEL = "claude-opus-5"` in that
file, and the comment above it says what it is: a choice, not a requirement.
The request body carries only a model id, a token ceiling and one message, so
`ApiEngine(model=...)` is the whole of what it takes to point this at something
else.

## What you are trusting when you paste a key in here

Plainly, because this is the part that cannot be undone by deleting a container.

**You are trusting this framework's prompts with your account.** Set the
variable and `propose_patches` and `propose_terms` will spend your tokens
against your rate limit, charged to whoever owns the key. Nothing here caps
that. An agent in a loop is a bill.

**You are sending laboratory data to a third party.** The prompts in
`framework/engines.py` are not abstract. `_patch_prompt` sends the contract id,
the use case profile, the failing paths, and *the object each failing path sits
in* - up to 12 000 characters of the package, which is to say your samples,
your locations, your measurements. `_term_prompt` sends the local key names a
laboratory invented and an example value for each. If that data is under an
agreement that says where it may go, read the agreement before you read this
sentence twice. `RulesEngine` sends nothing anywhere, and the framework is
fully usable with it.

**You are trusting a container with a secret in its environment.** The key is
in `/proc/<pid>/environ` for the life of the process, so anyone who can
`docker exec` into that container, or who can read the daemon's socket, can
read it. That is true of every container that holds a credential; it is listed
here because it is the thing a container does not protect you from.

**You are trusting compose not to print it.** This file and `compose.yaml`
never contain a key - `with-model` lists `ANTHROPIC_API_KEY` with no value, so
Compose takes it from your shell. But `docker compose config` *interpolates*
and will print the resolved value. Do not paste the output of that command into
an issue.

**A `.env` file is the usual way a key escapes.** Compose will read one sitting
beside `compose.yaml`. If you put a key there, add `.env` to the repository's
`.gitignore` first: as of today it is not listed. The container is rarely the
leak. The commit is.

### What the code does to keep its end of it

- The key is read from `os.environ["ANTHROPIC_API_KEY"]` at the moment of the
  call, and from nowhere else: not a file, not an argument, not a constructor
  parameter. `ApiEngine` has no `api_key` field, deliberately - a key that is
  never an attribute cannot be printed by a dataclass `repr`, serialised into a
  crate, or dumped by anything that walks an object.
- It travels in the `x-api-key` header. Never in the prompt, never in the URL -
  a URL ends up in proxy logs and in every exception that mentions it.
- Only the engine's `name` is ever recorded: `api:claude-opus-5`. That is
  exactly enough to tell a run that used a model apart from one that did not,
  which is the comparison this framework exists to make, and it is all that
  reaches the ledger, the crate, a package or a handover.
- Everything `ApiEngine` raises goes through `redact()` first, in two passes:
  the exact key, and anything key-shaped. The second pass is the one that
  matters - a gateway, a proxy or an authentication error that echoes the
  credential it rejected will put a key in a body you did not expect to hold
  one, and you cannot redact a secret you do not know you have.
- Errors are raised with `from None`, so Python does not print the original
  exception - which still holds the response - under "During handling of the
  above exception".
- A missing key is a normal state. `available()` returns `False`, the message
  says so in those words and names `RulesEngine` as what runs instead.

Six checks assert all of that, and they run offline, at image build time, and
on demand:

```bash
docker compose run --rm with-model      # or: python3 framework/engines_api.py
```

| check | what would otherwise be possible |
|---|---|
| `check_no_key_is_a_normal_state` | a missing key reported as a failure |
| `check_the_name_carries_the_model_and_not_the_key` | a key in the ledger via `repr` |
| `check_the_key_is_only_a_header` | a key in the prompt, the body or the URL |
| `check_an_error_cannot_leak_the_key` | a 401 that quotes your key, raised and printed |
| `check_redaction_also_catches_a_key_this_process_never_had` | somebody else's key passing through |
| `check_a_truncated_answer_is_not_a_partial_answer` | half a patch list treated as a patch list |

With no key the sixth section says so and sends nothing anywhere. With a key it
makes one real call and prints the term the model suggested - as a suggestion,
recorded and never applied, like every other engine's output here.

What `ApiEngine` does **not** change: the five guarantees in
`framework/engines.py` hold whatever engine you pass, because they are enforced
in the agents and the validator rather than by the engine's good behaviour. The
engine is asked only about non-blocking errors; a patch is applied only if the
validator reported that exact path as fixable; the package is re-validated
afterwards; `propose_terms` output is reported, never applied; the ledger
records which engine ran. `ApiEngine` borrows both of those methods from
`CommandEngine` verbatim rather than reimplementing them, so the rule that a
model may rename but never coin a term cannot drift between the two.

## What has actually been verified, and what has not

Verified on an arm64 Mac with Docker Desktop 25.0.3, on 11 November 2026:

- the image builds; the test stage ran the suite (`Ran 16 tests ... OK
  (skipped=1)`) and the engine's six key checks (`0 failure(s)`), so the marker
  exists and the image is the one the gate allowed;
- the health check answers: a kept-alive container reports `healthy`, exit code
  0, last line `OK (skipped=1)`;
- `architect/wiring.py` runs inside the container: four phases accepted, then
  the same agents with three faults injected and refused, 55 entities in one
  crate;
- the run survived the container in the named volume, owned by uid 10001;
- the `architect` service receives no `ANTHROPIC_*` variable even with one
  exported on the host; `with-model` receives exactly one;
- with a deliberately invalid key, the container reached the real API over
  HTTPS and reported `the API answered 401: invalid x-api-key` - a real error
  path, with no key in the message.

Not verified, and not claimed:

- **a successful real call.** No valid `ANTHROPIC_API_KEY` was available, so
  `ApiEngine` has been exercised against the real endpoint only as far as a
  401. The success path - the request shape, the reply parsing, the thinking
  blocks being skipped - is covered by the offline checks against a stubbed
  `urlopen`, which is not the same thing as the live API agreeing.
- **amd64.** The digest pinned in the Dockerfile is the multi-architecture
  index, so an amd64 build should work, but only arm64 was built here.
- **a bind-mounted `runs/` on Linux.** The uid advice above is reasoning about
  how bind mounts behave, not an observation.
- **the skipped test.** Worth saying out loud: on the machine this was built
  on, where `dbtlhub/bioprospecting` *is* checked out next door, that test
  currently **fails** - the published crate is refused on three checks the
  contracts have since grown. The container skips it because the crate is not
  in the image, so `OK (skipped=1)` is a real pass of fifteen things and
  silence about a sixteenth. The health check cannot see that regression. Fix
  it in the repository, not here.
