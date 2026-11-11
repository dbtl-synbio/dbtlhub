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

Everything the rest of the notebook uses. The project name has the date in
it so that running this twice does not collide.

**Your billing account is looked up when this runs**, not written into this
notebook. A machine cannot start without one, and the account belongs to
whoever is running this rather than to the notebook, which is in a public
repository.
""")

code("""
import datetime, json, subprocess, textwrap, time

# A project name nobody else in the world has used.
STAMP     = datetime.datetime.now().strftime("%Y%m%d-%H%M")
PROJECT   = f"dbtl-sentinel-{STAMP}"
ZONE      = "europe-southwest1-a"        # Madrid, the nearest to Barcelona
VM        = "sentinel-demo"
MACHINE   = "e2-standard-4"              # 4 processors, 16 gigabytes of memory
MODEL     = "qwen2.5:14b"                # 14 billion parameters, about 9 GB
DEPLOY    = "sentinel-demo"              # what the deployment is called
REPO      = "https://github.com/dbtl-synbio/dbtlhub.git"

# The billing account is looked up when this runs, rather than written
# down here. This notebook is in a public repository, and an account
# number belongs to whoever is running it, not to the notebook.
accounts = subprocess.run(
    ["gcloud", "billing", "accounts", "list",
     "--filter=open=true", "--format=value(name,displayName)"],
    capture_output=True, text=True).stdout.strip().splitlines()

if not accounts:
    raise SystemExit(
        "No open billing account on this login. A machine cannot start "
        "without one. Check you signed in as the right person.")
if len(accounts) > 1:
    print("More than one open billing account:")
    for line in accounts:
        print("   ", line.split("\t")[-1])
    print("Using the first. Set BILLING by hand if that is the wrong one.\n")

BILLING = accounts[0].split("\t")[0]
BILLING_NAME = accounts[0].split("\t")[-1]

print(f"project : {PROJECT}")
print(f"billing : {BILLING_NAME}")
print(f"machine : {VM} ({MACHINE}) in {ZONE}")
print(f"model   : {MODEL}")
""")

# ------------------------------------------------------------------- 1 sign in

md("""
---

# 1. Sign in to Google Cloud

Colab asks which Google account you are. A window opens, you choose the
account, and from then on this notebook may create things in your Google
Cloud account.

Nothing is created by this step and nothing is charged.
""")

code("""
from google.colab import auth
auth.authenticate_user()
print("signed in")
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

**What is about to run, said plainly.** A language model with 14 billion
parameters, downloaded onto your machine and running there. It is reachable
by nothing outside that machine: no key, no account, no request leaving to
anybody's service. It is about nine gigabytes, which on a Google Cloud
machine comes down in a couple of minutes.

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

# 6. The contract, in plain words

**This is the heart of it, so it is worth reading slowly.**

A contract is a file. It names the handover it is for, lists the kinds of
thing it expects to find in a package, and then lists requirements. Each
requirement says three things: what it looks at, what must be true of it,
and the sentence a person should read when it is not.

Nothing in the file is code. Adding a new handover means writing a file like
this and nothing else: no class, no registration, no entry in any table.

The cell below installs the service here in Colab, only so it can print the
contract. The real service runs on the Google Cloud machine.
""")

code("""
!git clone --depth 1 {REPO} local-copy --quiet
!pip install --quiet ./local-copy/sentinel-oo
%env SENTINEL_CONTRACTS=local-copy/bioprospecting/contracts
!python -m sentinel_oo --show-contract design_to_build
""")

md("""
**Three things to notice in what it just printed.**

Every sentence under a requirement was written by a person, in their own
words, about their own laboratory. None of it came from the service.

The block near the top saying what the contract is for. Without it, a
contract accepts packages it has never meaningfully looked at, because a
rule about a kind of thing says nothing at all about a package containing
none of that kind. That is the quietest way a check like this can fail.

The requirement marked as one a model may help with. That is the one the
model answers a question about, later in this notebook.
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

Then two questions, asked over that tunnel:

**Is it alive, and what is it?** Which image, which commit, and which model
it can see.

**What contracts is it serving?** With a checksum over all of them, which is
how the deployment proved that what is running is what it validated.
""")

code("""
tunnel = subprocess.Popen(
    ["gcloud", "compute", "ssh", VM, "--zone", ZONE, "--project", PROJECT,
     "--quiet", "--", "-N", "-L", "8080:127.0.0.1:8080"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(12)
SERVICE = "http://127.0.0.1:8080"
print("tunnel open\\n")

import requests
print("--- is it alive? ---")
print(json.dumps(requests.get(f"{SERVICE}/health").json(), indent=2))
print("\\n--- what does it hold? ---")
print(json.dumps(requests.get(f"{SERVICE}/contracts").json(), indent=2))
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
import io, shutil, zipfile
from pathlib import Path

CRATES = Path("local-copy/bioprospecting/exampleROcrates")

def send(folder):
    \"\"\"Zip a package, send it, and return the headers and the crate.\"\"\"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for item in Path(folder).rglob("*"):
            if item.is_file():
                bundle.write(item, item.relative_to(folder))
    answer = requests.post(f"{SERVICE}/check/design_to_build?by=the%20demonstration",
                           data=buffer.getvalue(),
                           headers={"Content-Type": "application/zip"})
    return answer

def verdict_of(answer):
    return answer.headers.get("X-Sentinel-Verdict", "no verdict")

def announce(answer, what):
    mark = {"ACCEPTED": "ACCEPTED",
            "ACCEPTED_WITH_FLAGS": "ACCEPTED, WITH A FLAG",
            "REFUSED": "REFUSED"}.get(verdict_of(answer), verdict_of(answer))
    line = "=" * 66
    print(line)
    print(f"  {what}")
    print(f"  {mark}")
    print(line)

answer = send(CRATES / "design-to-build" / "valid")
announce(answer, "the package the Design phase produced")
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
with zipfile.ZipFile(io.BytesIO(answer.content)) as bundle:
    bundle.extractall("checked")
    print("the package that came back holds:")
    for name in bundle.namelist():
        print("   ", name)

crate = json.load(open("checked/ro-crate-metadata.json"))
print("\\nwhat the record says about this check:\\n")
for thing in crate["@graph"]:
    if "/about/" in str(thing.get("@id")) or str(thing.get("@id", "")).endswith("/found/verdict"):
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

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(notebook, indent=1))
print(f"written: {OUT}")
print(f"{len(cells)} cells, "
      f"{sum(1 for c in cells if c['cell_type'] == 'code')} of them code")
