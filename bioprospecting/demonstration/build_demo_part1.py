"""Build part one of the demonstration notebook.

Written as a script rather than by hand because a notebook is JSON, and JSON
written by hand acquires a missing comma at the worst moment.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "demo_part1.ipynb"

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


# ---------------------------------------------------------------- the opening

md("""
# sentinel-oo, part one: from nothing to a service that checks a handover

**ELIXIR BioHackathon Europe 2026, Project 25.**

This notebook builds a real thing while you watch. By the end of it there is
a machine in Google Cloud running a service that reads a package of
laboratory results, checks it against a contract somebody wrote, and says
whether the next phase of work can accept it.

## What the problem is

A Design, Build, Test, Learn cycle hands work from one phase to the next.
The Design phase finishes with a panel of candidate proteins, a synthetic
gene designed for each one, and a plate layout saying which gene goes in
which well. The Build phase then orders those genes from a synthesis
company, which costs real money.

If something the Build phase needs is missing from what Design handed over,
nobody finds out until the plate arrives and a well is wasted.

**A validator does not catch this.** There are good tools that check a
package is well formed. A package can be perfectly well formed and still be
useless to the phase receiving it.

## What this service does about it

It stands at the handover. It reads the package, checks it against a
contract written as a file by the people who know what the receiving phase
needs, and answers one of three things:

| Verdict | Meaning |
|---|---|
| `ACCEPTED` | Nothing was found. Carry on |
| `ACCEPTED_WITH_FLAGS` | Carry on, but somebody should look at something |
| `REFUSED` | At least one thing the next phase needs is missing or wrong |

**Everything it knows comes from the contract file.** The service has no
idea what a plate or a protein is. The same service, unmodified, checks a
coating line or a chemical plant.

## The order of this hour

1. Sign in to Google Cloud
2. Make a project
3. Make a machine
4. Put the code on it
5. Start the model
6. Read the contract, in plain words
7. Deploy the service
8. Ask it what it holds
9. Send it a good package
10. Send it packages that are broken
11. Fetch the graph of a check and draw it
12. Delete everything

## What it costs

A few pence. One ordinary machine, running for about an hour. Step 12
deletes the whole project, which stops every charge.
""")

# ------------------------------------------------------------------- settings

md("""
---

## Settings

Names and numbers the rest of the notebook uses. Nothing here talks to
Google Cloud, so this cell cannot fail.
""")

code("""
import datetime, json, os, subprocess, textwrap, time

# A project name nobody else in the world has used.
STAMP     = datetime.datetime.now().strftime("%Y%m%d-%H%M")
PROJECT   = f"dbtl-sentinel-{STAMP}"
ZONE      = "europe-southwest1-a"        # Madrid, the nearest to Barcelona
VM        = "sentinel-demo"
MACHINE   = "e2-standard-4"              # 4 processors, 16 gigabytes of memory
MODEL     = "qwen2.5:14b"                # 14 billion parameters, about 9 GB
DEPLOY    = "sentinel-demo"              # what the deployment is called
REPO      = "https://github.com/dbtl-synbio/dbtlhub.git"


# Runs one gcloud command and hands back everything it said, including
# what it complained about. An earlier version looked only at what gcloud
# printed and treated silence as an answer, so a command that failed for
# one reason was reported as a different thing entirely.
def gcloud(*arguments):
    return subprocess.run(["gcloud", *arguments], capture_output=True,
                          text=True)


print(f"project : {PROJECT}")
print(f"machine : {VM} ({MACHINE}) in {ZONE}")
print(f"model   : {MODEL}")
""")

# ------------------------------------------------------------------- 1 sign in

md("""
---

# 1. Sign in to Google Cloud

Colab asks which Google account you are. A window opens and you choose the
account.

**Then one extra step, which is not obvious.** Signing in that way gives
your credentials to Python's own Google libraries. It does not give them to
the `gcloud` command line tool, which is what the rest of this notebook
uses, and `gcloud` will say it has no account at all. So this cell takes
the token Colab just got for you and hands it to `gcloud` through the
setting it reads for exactly that. No second sign-in and nothing to paste.

That token lasts about an hour. `refresh()` gets a new one, and is worth
running if a later cell suddenly says you are not signed in.

Finally it finds your billing account. A machine cannot start without one.
**The number is looked up here rather than written into this notebook**,
which is in a public repository, and only its name is printed.

Nothing is created by this step and nothing is charged.
""")

code("""
from google.colab import auth
import google.auth
import google.auth.transport.requests

auth.authenticate_user()


def refresh():
    \"\"\"Hand gcloud a fresh token from the sign-in above.\"\"\"
    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())
    os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = credentials.token
    return credentials


credentials = refresh()
print("signed in, and gcloud has been given the same credentials")

# Proof rather than assumption: ask gcloud to do something that needs them.
listed = gcloud("billing", "accounts", "list",
                "--filter=open=true", "--format=json")
# Read as structured data rather than as columns of text. An earlier
# version split the answer on a tab, and the tab did not survive being
# written into this notebook, so the number and the name came back joined
# together and would have been passed to --billing-account as one string.
accounts = json.loads(listed.stdout or "[]")

if not accounts:
    print("\\nNo open billing account came back.")
    print("What gcloud said:\\n", listed.stderr or "(nothing)")
    raise SystemExit(
        "A machine cannot start without a billing account. Either the "
        "account you chose in the sign-in window is not the one that has "
        "the billing, or the credentials did not reach gcloud. The lines "
        "above say which.")

if len(accounts) > 1:
    print("\\nMore than one open billing account:")
    for account in accounts:
        print("   ", account["displayName"])
    print("Using the first. Set BILLING by hand if that is the wrong one.")

BILLING = accounts[0]["name"].split("/")[-1]
BILLING_NAME = accounts[0]["displayName"]
print(f"billing : {BILLING_NAME}")
""")

# ------------------------------------------------------------- 2 the project

md("""
---

# 2. Make a project

A Google Cloud project is a box to keep things in: machines, networks,
billing. It is empty until something is put in it, and an empty project
costs nothing.

This step also attaches a billing account, because a machine cannot start
without one, and turns on Compute Engine, which is the part of Google Cloud
that runs machines.

Takes about half a minute.
""")

code("""
!gcloud projects create {PROJECT} --name="DBTL sentinel demonstration" --quiet
!gcloud billing projects link {PROJECT} --billing-account={BILLING} --quiet
!gcloud services enable compute.googleapis.com --project={PROJECT} --quiet
print(f"\\nproject {PROJECT} is ready")
""")

# ------------------------------------------------------------- 3 the machine

md("""
---

# 3. Make a machine

One ordinary Linux machine in Madrid, which is the Google data centre
nearest to this room.

It installs Docker as it starts. Docker is the thing that runs the service
and the model side by side, each in its own container, which is what lets
the same image run on anybody's machine without installing anything into it.

The machine takes about half a minute to appear, and about another minute
to finish installing Docker. The cell waits for both.
""")

code("""
startup = '''#!/bin/bash
apt-get update -y
apt-get install -y docker.io git python3 python3-pip python3-yaml
systemctl enable --now docker
usermod -aG docker $(ls /home | head -1)
touch /var/tmp/ready
'''
open("startup.sh", "w").write(startup)

!gcloud compute instances create {VM} \\
    --project={PROJECT} --zone={ZONE} \\
    --machine-type={MACHINE} \\
    --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \\
    --boot-disk-size=100GB \\
    --metadata-from-file=startup-script=startup.sh \\
    --quiet

def on_the_machine(command, quiet=False):
    \"\"\"Run one command on that machine and return what it printed.\"\"\"
    done = subprocess.run(
        ["gcloud", "compute", "ssh", VM, "--zone", ZONE, "--project", PROJECT,
         "--quiet", "--command", command],
        capture_output=True, text=True)
    if not quiet:
        print(done.stdout or done.stderr)
    return done

print("waiting for the machine to finish installing Docker ...")
for attempt in range(40):
    if on_the_machine("test -f /var/tmp/ready && echo yes", quiet=True).stdout.strip() == "yes":
        print("ready")
        break
    time.sleep(10)
else:
    print("it is taking longer than expected. Run this cell again.")
""")

# ---------------------------------------------------------------- 4 the code

md("""
---

# 4. Put the code on the machine

Clones the project's repository onto it. The service, the contracts and the
example packages are all in there.

Takes a few seconds.
""")

code("""
on_the_machine(f"rm -rf dbtlhub && git clone --depth 1 {REPO} && "
               f"echo '--- what came down ---' && ls dbtlhub")
""")

# --------------------------------------------------------------- 4.5 the model

md("""
---

# 5. Start the model

**Which model, and where it runs.** `qwen2.5:14b`. That is Alibaba's Qwen
2.5, the version with 14 billion parameters, released under the Apache 2.0
licence. It is downloaded onto your own machine and runs there, under
Ollama, which is a program that serves a model over a plain web interface.

It is reachable by nothing outside that machine: no key, no account, and no
request leaving to anybody's service. The model file is about nine
gigabytes, which on a Google Cloud machine comes down in a couple of
minutes.

The name and version are pinned in the deployment rather than left to
whatever is newest, so that a check done today and the same check done next
year were done by the same model. The record inside every checked package
names it.

**What it is here to do.** One requirement in the contract is marked as one
a model may help with. When that requirement fails, the model is asked a
single question: is this value already written down somewhere in this
package, including inside ordinary prose that no rule can read? It answers
out of the package's own text. Whatever it proposes is then put back through
the contract's rules and kept only if every requirement about that value now
passes.

**That one job is a deliberate choice, not the limit of the model.** It is
given a narrow job here so that every answer can be checked by something
that cannot be talked round. The same model could do considerably more:
explain a refusal in the words of the team that caused it, draft a contract
from a package somebody already has, propose the vocabulary two groups
should agree on, or sit above the whole cycle deciding which handover to
check next. The architecture allows all of that. What changes when you do it
is how much you can still prove afterwards, and this service was built to
keep that provable.

This cell downloads the model now so that the deployment in the next step is
quick.
""")

code("""
print("pulling the model server, then the model itself. A few minutes.\\n")
# sudo on every docker command: on a machine this new, your login user is
# not in the docker group yet. The deployment in the next step runs under
# sudo for the same reason.
on_the_machine(
    f"sudo docker volume create {DEPLOY}-model-store >/dev/null && "
    f"sudo docker rm -f warming >/dev/null 2>&1; "
    f"sudo docker run -d --name warming -v {DEPLOY}-model-store:/root/.ollama ollama/ollama:0.5.7 && "
    f"until sudo docker exec warming ollama list >/dev/null 2>&1; do sleep 2; done && "
    f"sudo docker exec warming ollama pull {MODEL} && "
    f"sudo docker exec warming ollama list && "
    f"sudo docker rm -f warming >/dev/null")
print("\\nthe model is on the machine and ready for the service to use")
""")

# ------------------------------------------------------------- 5 the contract

md("""
---

# 6. The contract itself

**This is the heart of it, so it is worth reading slowly.** Everything the
service will do in the rest of this notebook comes out of this one file.

A contract is a file somebody writes. It says which handover it is for,
which kinds of thing it expects to find, and then lists requirements. Each
requirement says three things: what to look at, what must be true of it, and
the sentence a person should read when it is not true.

Nothing in the file is code. Adding a new handover means writing a file like
this and nothing else. No class is written, no name is registered anywhere,
and no table maps a handover to any piece of the service.

The cell below fetches the repository here, so this notebook has the
packages to send later, and prints the beginning of the contract file.
""")

code("""
# The repository is cloned here as well as on the machine. Here it is only
# for the packages this notebook sends later and for showing the contract
# file. The service itself runs on the Google Cloud machine and nothing is
# installed in this notebook.
!git clone --depth 1 {REPO} local-copy --quiet

CONTRACT = "local-copy/bioprospecting/contracts/design_to_build.yaml"
text = open(CONTRACT).read()
lines = text.splitlines()


def requirement_called(name):
    # Pulls one requirement out of the file by its name. A requirement
    # starts at "- name:" and ends where the next one starts, so this
    # collects lines from the one to the other.
    out, inside = [], False
    for line in lines:
        if line.strip().startswith("- name:"):
            if inside:
                break
            inside = line.strip().endswith(name)
        if inside:
            out.append(line)
    return "\\n".join(out)


# The head of the file: what this contract is, and what it is for.
head = lines[:lines.index("expects:") + 7]
print("\\n".join(head))
print("\\n          . . .\\n")

# Then one requirement in full, so the shape of a requirement is visible.
print(requirement_called("well_has_a_position"))
print("\\n          . . .\\n")

# And the only one in the file a model is allowed to help with.
print(requirement_called("edge_handling_is_recorded"))
print(f"\\n{len(lines)} lines in all, holding 20 requirements")
""")

md("""
**What you are looking at, part by part.**

`contract: design_to_build` is the handover's name. That name is how
anything asks for this check later, and it is the only name the service
knows this contract by. The file could be called anything.

`version: 0.11.0` is written into the record inside every package this
contract checks. A package checked last month therefore says which wording
of the contract it was checked against, which matters when the contract
changes and somebody asks why an old package passed.

`expects:` lists the kinds of thing this contract is written for: plate
wells, expression constructs, proteins, the plate layout, and the step that
predicted the genes. **Without this block a contract quietly accepts
packages it has never meaningfully looked at**, because a requirement about
plate wells says nothing at all about a package containing no plate wells.
Every requirement behaves correctly, nothing fails, and the verdict comes
back clean. That is the quietest way a check like this can fail, and it was
measured happening on 11 November 2026.

Then the requirements. Each one has:

- `name`, which is how a finding is cited afterwards
- `applies_to`, the kind of thing it looks at
- `property` or `named_value`, which part of that thing it reads
- `must`, one of five things a requirement is allowed to demand
- `severity`, either `refuse`, which stops the handover, or `flag`, which
  lets it through and tells somebody
- `message`, the sentence a person reads

**Every sentence in those messages was written by a person**, about their
own laboratory, in their own words. None of it came from the service. When
you see a refusal later in this notebook, you are reading somebody's
sentence out of this file.

One requirement further down the file carries `repairable: true`. That is
the one the model is allowed to answer a question about, and it is the only
place in the whole system where a model may suggest anything.
""")

# ----------------------------------------------------------------- 6 deploy

md("""
---

# 7. Deploy the service

One command, on the machine. It does five things, and it stops at the first
one that fails:

1. Reads every contract and refuses before building anything if one of them
   does not make sense
2. Builds the image
3. Runs the service's own test suite inside the build, so an image whose
   tests fail is never produced
4. Starts the service, with the contracts mounted read only, beside the
   model that is already downloaded
5. Checks that the service now running is serving exactly the contracts it
   validated in step 1, by checksum

**No package has been sent yet.** This is only the service, standing ready.

About two minutes, nearly all of it the build.
""")

code("""
on_the_machine(
    f"cd dbtlhub/sentinel-oo && "
    f"sudo python3 deploy.py ../bioprospecting/contracts "
    f"--name {DEPLOY} --yes 2>&1 | tail -40")
""")

# --------------------------------------------------------------- 7 what it holds

md("""
---

# 8. Ask it what it holds

The service listens only on its own machine, so nothing on the internet can
reach it. The cell below opens a private tunnel from this notebook to it, in
the same way you would reach any machine you own.

Then three questions, asked over that tunnel.

**Is it alive, and what is it?** Which image it was built from, which commit
of the code, and which model it can see. If it had been given a model it
could not reach, this is where it would say so rather than carrying on
quietly.

**What contracts is it serving?** With a checksum over all of them. The
deployment compared that checksum against the contracts it read in step one,
which is how it proved that the service now running holds exactly what was
validated and not something else that happened to be on the machine.

**And the contract itself, from the service rather than from a file.** The
same contract you read a moment ago, handed back by the thing that will
enforce it, in plain words. This is what you send to the team that produces
the handover, so they can check themselves before they are checked.
""")

code("""
# The service listens on the machine's own loopback address, which nothing
# outside that machine can reach. This forwards port 8080 of this notebook
# to port 8080 of the machine, down the same SSH connection used above, so
# the requests below go nowhere near the open internet.
tunnel = subprocess.Popen(
    ["gcloud", "compute", "ssh", VM, "--zone", ZONE, "--project", PROJECT,
     "--quiet", "--", "-N", "-L", "8080:127.0.0.1:8080"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(12)
SERVICE = "http://127.0.0.1:8080"
print("tunnel open\\n")

import requests
print("--- is it alive, and what is it? ---")
print(json.dumps(requests.get(f"{SERVICE}/health").json(), indent=2))

print("\\n--- what contracts does it hold? ---")
print(json.dumps(requests.get(f"{SERVICE}/contracts").json(), indent=2))
""")

md("""
Now the contract, from the running service, in plain words.
""")

code("""
# Asking the service for the contract rather than reading the file again.
# What comes back carries the contract both ways: `summary` is it written
# out as sentences, which is the form a producing team is sent, and
# `requirements` is the same thing as data, for something that has to act
# on it rather than read it.
held = requests.get(f"{SERVICE}/contracts/design_to_build").json()
print(held["summary"])
""")

# ------------------------------------------------------------ 8 a good crate

md("""
---

# 9. Send it a good package

The package is an RO-Crate: a folder of data files with one file beside them
describing what each one is and how the things in it relate.

This one is a real Design to Build handover: four candidate proteins pulled
out of a metagenome, a synthetic gene designed for each, the plate layout
saying which well each goes in, and a record of every step that produced
them, back to the environmental sample. All the sequences in it are
simulated, and each one says so.

It is sent zipped, so the data files travel with the description. **What
comes back is the whole package**, not a report about it: the same crate,
with the record of the check written inside it, ready to hand to whoever
runs the Build phase.
""")

code("""
import io, zipfile
from pathlib import Path

# The packages live in the copy of the repository cloned into this notebook
# earlier. The service has its own copy on the machine, but what is sent
# has to come from here, because sending it is the point.
CRATES = Path("local-copy/bioprospecting/exampleROcrates")


def send(folder):
    # A package is a folder: a description file and the data files it
    # describes. It is zipped and posted whole, so the data goes with the
    # description. Sending the description on its own would also work, and
    # then any requirement about the data files could not be answered.
    #
    # `by=` says who is asking. The service writes that into the record as
    # the caller's claim about itself: it authenticates nobody.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for item in Path(folder).rglob("*"):
            if item.is_file():
                bundle.write(item, item.relative_to(folder))
    return requests.post(
        f"{SERVICE}/check/design_to_build?by=the%20demonstration",
        data=buffer.getvalue(),
        headers={"Content-Type": "application/zip"})


def verdict_of(answer):
    # The verdict travels in a header, so a pipeline can act on it without
    # unpacking anything that came back.
    return answer.headers.get("X-Sentinel-Verdict", "no verdict")


def announce(answer, what):
    # Large and unmissable, because in a room the verdict is the thing
    # everybody is looking for.
    said = {"ACCEPTED": "ACCEPTED",
            "ACCEPTED_WITH_FLAGS": "ACCEPTED, WITH A FLAG",
            "REFUSED": "REFUSED"}.get(verdict_of(answer), verdict_of(answer))
    rule = "=" * 66
    print(rule)
    print(f"  {what}")
    print(f"  {said}")
    print(rule)


answer = send(CRATES / "design-to-build" / "valid")
announce(answer, "the package the Design phase produced")

# The run identifier names this one check. It is how the graph of it is
# asked for at the end of this notebook.
print(f"\\n  run            {answer.headers.get('X-Sentinel-Run')}")
print(f"  findings       {answer.headers.get('X-Sentinel-Findings')}")
print(f"  came back      {len(answer.content):,} bytes of package")
GOOD_RUN = answer.headers.get("X-Sentinel-Run")
""")

md("""
**Now look at what is inside what came back.** The service wrote a record
into the package itself. That record is the thing that lasts: it travels
with the package, so whoever receives it a year later can see what was
checked, by what, and what was found, without asking anybody.
""")

code("""
# What came back is a zip of the whole package: the same data files that
# were sent, and a description file with the record of this check added to
# it.
with zipfile.ZipFile(io.BytesIO(answer.content)) as bundle:
    bundle.extractall("checked")
    print("the package that came back holds:")
    for name in bundle.namelist():
        print("   ", name)

# The description file is a list of things, each with an identifier. The
# ones the service added for this check have identifiers that say what they
# are: `/about/` for what was checked, `/found/` for what was found.
crate = json.load(open("checked/ro-crate-metadata.json"))
print("\\nwhat the record says about this check:\\n")
for thing in crate["@graph"]:
    identifier = str(thing.get("@id", ""))
    if "/about/" in identifier or identifier.endswith("/found/verdict"):
        print(f"  {thing.get('name'):34} {str(thing.get('value'))[:70]}")
""")

# ------------------------------------------------------------ 9 broken crates

md("""
---

# 10. Send it packages that are broken

Four packages, each broken in exactly one way, so that every refusal can be
read back to a single cause.

**Every one of these passes a standard RO-Crate validator with no issues at
all.** That was measured, with `rocrate-validator` version 0.13.1, on
11 November 2026. They are well formed. They are also useless to the Build
phase, and that gap is the whole reason this service exists.
""")

code("""
# Each of these is a copy of the sound package with exactly one thing
# changed, so every refusal can be read back to one cause rather than to a
# pile of them.
broken = [
    ("missing-conformsto",        "does not say which standard it follows"),
    ("dangling-reference",        "lists a file it never describes"),
    ("missing-gene-calling-mode", "a setting the Build phase needs is absent"),
]

for folder, what in broken:
    answer = send(CRATES / "design-to-build" / "invalid" / folder)
    announce(answer, f"{folder}: {what}")
    crate = json.loads(zipfile.ZipFile(io.BytesIO(answer.content))
                       .read("ro-crate-metadata.json"))
    for thing in crate["@graph"]:
        if "/found/" in str(thing.get("@id")) and "verdict" not in str(thing.get("@id")):
            print(f"    {thing.get('name')}")
            print(textwrap.fill(str(thing.get('value')), 64,
                                initial_indent="      ",
                                subsequent_indent="      "))
    print()
""")

# -------------------------------------------------------- 9b the model's turn

md("""
---

# 11. The one the model can rescue

This package is broken in a subtler way. The setting the Build phase needs
is not recorded as a value. It is sitting in an ordinary English sentence in
the description of the step that produced the data: "contig edges were
treated as closed, so no partial genes were kept".

No rule can read that. A rule reads a value recorded as a value.

So the contract marks that requirement as one a model may help with, and the
model is asked its single question. It reads the sentence, proposes
`closed`, and the contract's own rules check the proposal before it is
kept.

**The verdict that comes back is not `ACCEPTED`.** It is `ACCEPTED_WITH_FLAGS`,
and the flag says what happened: which value, found by which model,
confirmed by which requirement. The handover goes through, and whoever
produced it is told that a machine had to go and find something they should
have recorded.

This machine has no graphics card, so the model takes tens of seconds to
answer rather than about one second. On a machine with one, this is quick.
""")

code("""
started = time.time()
answer = send(CRATES / "design-to-build" / "invalid" / "edge-handling-in-prose")
announce(answer, "the setting is there, written in a sentence")
print(f"\\n  the model took about {time.time() - started:.0f} seconds\\n")

crate = json.loads(zipfile.ZipFile(io.BytesIO(answer.content))
                   .read("ro-crate-metadata.json"))
for thing in crate["@graph"]:
    identifier = str(thing.get("@id"))
    if "/found/" in identifier and "verdict" not in identifier:
        print(textwrap.fill(str(thing.get("value")), 68,
                            initial_indent="  ", subsequent_indent="  "))
    if "/changed/" in identifier or "/recovered/" in identifier:
        print(f"\\n  written into the package: {thing.get('name')} = {thing.get('value')}")
FLAGGED_RUN = answer.headers.get("X-Sentinel-Run")
""")

md("""
**And the one it cannot rescue**, which matters just as much.

In the next package the same setting is recorded only as `-c`, a flag inside
a command line. Recovering it would mean knowing what that program's flags
mean, rather than reading what the record says. Two models of this size were
asked to do exactly that on 10 November 2026, and both stated a wrong
meaning without hedging.

The contract's rules reject the answer, nothing is written, and the package
stays refused. **The model is never the thing that decides.**
""")

code("""
answer = send(CRATES / "design-to-build" / "invalid" / "mode-in-prose")
announce(answer, "the setting is there, but only as a flag in a command line")
print("\\n  the model proposed something. The rules threw it out, nothing was")
print("  written into the package, and the handover is refused.")
""")

# ------------------------------------------------------------------ 10 graph

md("""
---

# 12. The graph of a check, drawn

A package is a set of things that point at each other. A plate well points
at the gene that goes in it; that gene points at the protein it was designed
from; a step points at the files it read and the files it produced.

Ask the service for the graph of one check and it hands back the boxes and
the lines, with the check itself, each finding, and anything the model
recovered marked so they stand out from the handover they are about.
""")

code("""
graph = requests.get(f"{SERVICE}/graph/{FLAGGED_RUN}").json()
print(f"verdict : {graph['verdict']}")
print(f"boxes   : {graph['counts']['nodes']}")
print(f"lines   : {graph['counts']['edges']}")
print()
for role, count in sorted(graph["counts"]["by_role"].items(),
                          key=lambda pair: -pair[1]):
    print(f"  {role:28} {count}")
""")

code("""
COLOURS = {
    "the handover": "#8fb8de", "a recorded value": "#cfd8e3",
    "a file": "#b7d7b0", "the check": "#f2b134", "the verdict": "#e8743b",
    "a finding": "#d9534f", "a change made": "#9b59b6",
    "a value a model recovered": "#9b59b6", "who asked": "#7f8c8d",
    "the service": "#f2b134", "what was checked": "#f7d8a0",
    "missing": "#000000", "elsewhere": "#dddddd",
}

def draw(graph, leave_out_packaging=True, height=640):
    nodes, edges = [], []
    for node in graph["nodes"]:
        important = node["role"] not in ("the handover", "a recorded value",
                                         "a file", "elsewhere")
        nodes.append({
            "id": node["id"],
            "label": node["name"][:28],
            "title": f"{node['role']}\\n{node['type']}\\n{node['id']}",
            "color": COLOURS.get(node["role"], "#cccccc"),
            "size": 26 if important else 14,
        })
    for edge in graph["edges"]:
        if leave_out_packaging and edge["packaging"]:
            continue
        edges.append({"from": edge["from"], "to": edge["to"],
                      "label": edge["property"], "font": {"size": 9}})
    html = f'''
    <html><head>
      <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/dist/vis-network.min.js"></script>
      <style>#net {{ width: 100%; height: {height}px; background: #fbfbfb; }}</style>
    </head><body><div id="net"></div><script>
      new vis.Network(document.getElementById("net"),
        {{nodes: new vis.DataSet({json.dumps(nodes)}),
          edges: new vis.DataSet({json.dumps(edges)})}},
        {{physics: {{stabilization: true, barnesHut: {{springLength: 150}}}},
          nodes: {{shape: "dot", font: {{size: 11}}}},
          edges: {{arrows: "to", color: {{color: "#aaaaaa"}}, smooth: false}}}});
    </script></body></html>'''
    from IPython.display import HTML
    return HTML(html)

draw(graph)
""")

md("""
**What to look for in the picture.**

The orange box is the check itself. The red boxes hanging off it are what it
found. The purple box is the value the model recovered, which is the one
thing in this package that nobody wrote down by hand.

Everything in blue is the handover: the wells, the genes, the proteins, the
steps that produced them.

Drag a box to pull the picture apart. Hover over one to see what it is.
""")

# -------------------------------------------------------------- 11 shut down

md("""
---

# 13. Delete everything

Deletes the whole project, which deletes the machine with it and stops every
charge. There is nothing left to forget about afterwards.
""")

code("""
tunnel.terminate()
!gcloud projects delete {PROJECT} --quiet
print(f"\\n{PROJECT} is gone, and so is everything that was in it")
""")

md("""
---

## What was shown

A service that stands at a handover, deployed in about five minutes onto a
machine that did not exist when this notebook started.

**Everything it checks came from a file.** Not one line of code was written
to teach it about plates, genes or proteins. A different laboratory writes a
different file and the same service checks a different handover.

**A package that passes a standards validator can still be refused**, and
should be, when what the next phase needs is not there.

**The model helps where rules cannot reach**, reading values out of ordinary
prose, and it is never allowed to decide. Every answer it gives is checked
by the contract before it counts.

**What comes back is the handover itself**, with the record of the check
written inside it, so that whoever receives it can see what was checked
without asking anybody.
""")

notebook = {
    "cells": cells,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

def every_code_cell_compiles(cells) -> int:
    """Refuse to write a notebook whose Python will not run.

    Every code cell here is written inside a triple-quoted string, so a
    backslash has to survive one more round of reading than it looks like
    it does. On 12 November 2026 a `\\n` and a `\\t` became a real newline
    and a real tab, which broke the first cell of the notebook: an
    unterminated string. Nothing in the notebook itself would have shown
    that until somebody ran it in front of an audience.
    """
    broken = 0
    for number, cell in enumerate([c for c in cells
                                   if c["cell_type"] == "code"], 1):
        text = "".join(cell["source"])
        # Colab's shell and magic lines are not Python. A shell line can be
        # continued with a backslash, so its continuation goes with it.
        out, skipping = [], False
        for line in text.splitlines():
            if skipping:
                out.append("pass")
                skipping = line.rstrip().endswith("\\")
            elif line.lstrip().startswith(("!", "%")):
                out.append("pass")
                skipping = line.rstrip().endswith("\\")
            else:
                out.append(line)
        try:
            compile("\n".join(out), f"cell {number}", "exec")
        except SyntaxError as exc:
            broken += 1
            print(f"  cell {number}: {exc.msg}, line {exc.lineno}")
            for line in "\n".join(out).splitlines()[max(0, exc.lineno - 2):
                                                    exc.lineno + 1]:
                print(f"      {line}")
    return broken


broken = every_code_cell_compiles(cells)
if broken:
    raise SystemExit(f"\n{broken} cell(s) will not run. Nothing was written.")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(notebook, indent=1))
print(f"written: {OUT}")
print(f"{len(cells)} cells, "
      f"{sum(1 for c in cells if c['cell_type'] == 'code')} of them code")
