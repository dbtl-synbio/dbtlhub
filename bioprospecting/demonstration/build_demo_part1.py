"""Build part one of the demonstration notebook.

The notebook is generated from this script rather than edited by hand,
because a notebook file is JSON and hand-edited JSON breaks in ways that
are not visible until the file is opened.
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
# sentinel-oo, part one: deploying a service that checks a handover

**ELIXIR BioHackathon Europe 2026, Project 25.**

This notebook creates a machine in Google Cloud, deploys a service called
sentinel-oo onto it, and submits packages of laboratory results to that
service. For each package the service reads what is inside it, compares it
against a contract written by the team that will receive the work, and
returns a verdict saying whether the next phase can accept it.

## The problem

A Design, Build, Test, Learn cycle hands work from one phase to the next.
In the handover used throughout this notebook, the Design phase finishes
with a panel of candidate proteins, a synthetic gene designed for each one,
and a plate layout recording which gene goes in which well. The Build phase
then orders those genes from a synthesis company, at a real cost per well.

When something the Build phase requires is absent from what Design handed
over, the omission is found after the order has been placed.

Validators do not close this gap. Several good tools check that a package is
well formed, and a package can be well formed in every respect and still be
unusable by the phase receiving it.

## What sentinel-oo does

sentinel-oo stands at the handover. It reads the package, compares it
against a contract file written by the receiving team, and returns one of
three verdicts.

| Verdict | Meaning |
|---|---|
| `ACCEPTED` | Nothing was found. The handover proceeds |
| `ACCEPTED_WITH_FLAGS` | The handover proceeds, and a finding is recorded for somebody to read |
| `REFUSED` | At least one thing the receiving phase requires is absent or wrong |

The service holds no knowledge of the subject matter. It does not know what
a plate or a protein is. Everything it checks is read from the contract file
when it starts, so a different contract file makes the same service check a
different handover.

## Order of the notebook

1. Sign in to Google Cloud
2. Create a project
3. Create a machine
4. Put the code on the machine
5. Start the LLM
6. The contract
7. Deploy sentinel-oo
8. Query the deployment
9. Submit a compliant package
10. Submit packages with defects
11. A defect the LLM can repair
12. The graph of one check
13. Remove the project

## Cost

One `e2-standard-4` machine, which costs approximately 0.16 US dollars per
hour, running for about one hour. The total is well under 1 US dollar.
Section 13 deletes the project, which removes the machine and ends every
charge.
""")

# ------------------------------------------------------------------- settings

md("""
---

## Settings

The names, sizes and versions used by the rest of the notebook. This cell
contacts nothing and creates nothing, so it cannot fail.
""")

code("""
import datetime, json, os, subprocess, textwrap, time

# A project identifier has to be unique across the whole of Google Cloud,
# so it carries the date and time this notebook was started.
STAMP     = datetime.datetime.now().strftime("%Y%m%d-%H%M")
PROJECT   = f"dbtl-sentinel-{STAMP}"
ZONE      = "europe-southwest1-a"        # Madrid, the nearest to Barcelona
VM        = "sentinel-demo"
MACHINE   = "e2-standard-4"              # 4 processors, 16 gigabytes of memory
MODEL     = "qwen2.5:14b"                # 14 billion parameters, about 9 GB
DEPLOY    = "sentinel-demo"              # the name given to the deployment
REPO      = "https://github.com/dbtl-synbio/dbtlhub.git"


# Runs one gcloud command and returns its standard output, its standard
# error and its exit code.
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

Colab asks which Google account to use, and a window opens for that choice.

One further step is then needed, and it is not obvious. Signing in that way
gives credentials to Python's own Google libraries. It does not give them to
the `gcloud` command line tool, which is what the rest of this notebook
uses, and `gcloud` would report having no account at all. This cell
therefore takes the token Colab has just obtained and passes it to `gcloud`
through the environment variable `gcloud` reads for that purpose. There is
no second sign-in and nothing to paste.

The token is valid for approximately one hour. Calling `refresh()` obtains a
new one, which is the first thing to try if a later cell reports that you
are not signed in.

The cell then locates the billing account, since a machine cannot start
without one. The account number is looked up at run time rather than written
into this notebook, because the notebook is held in a public repository.
Only the account's display name is printed.

Nothing is created by this step and no charge arises from it.
""")

code("""
from google.colab import auth
import google.auth
import google.auth.transport.requests

auth.authenticate_user()


def refresh():
    \"\"\"Obtain a new access token from the sign-in above and pass it to
    gcloud.\"\"\"
    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())
    os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = credentials.token
    return credentials


credentials = refresh()
print("signed in, and gcloud has been given the same credentials")

# Locate the billing account. This call also confirms that gcloud holds the
# credentials, since listing billing accounts requires them.
listed = gcloud("billing", "accounts", "list",
                "--filter=open=true", "--format=json")
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

# Projects left behind by an earlier run of this notebook.
#
# A billing account permits a limited number of attached projects. A run
# that stops part way through leaves its project attached, and possibly a
# machine running and charging, so what remains is reported before another
# project is created.
leftovers = json.loads(gcloud(
    "projects", "list", "--filter=projectId:dbtl-sentinel-*",
    "--format=json").stdout or "[]")

if leftovers:
    print("\\nProjects left behind by earlier runs of this notebook:")
    for each in leftovers:
        print("   ", each["projectId"])
    print("\\nEach one holds a billing slot, and may still have a machine "
          "running\\nand charging. Delete them with:\\n")
    for each in leftovers:
        print(f"    !gcloud projects delete {each['projectId']} --quiet")
""")

# ------------------------------------------------------------- 2 the project

md("""
---

# 2. Create a project

A Google Cloud project is a container for resources: machines, networks and
the billing attached to them. An empty project costs nothing.

This step creates the project, attaches a billing account, since a machine
cannot start without one, and enables Compute Engine, which is the Google
Cloud service that runs machines.

Duration: approximately 30 seconds.
""")

code("""
# Every gcloud step from here on is checked. A step that fails prints what
# Google reported and stops the notebook, so that a later step does not run
# against a resource that was never created.
def must(what, *arguments):
    done = gcloud(*arguments)
    if done.returncode != 0:
        print(f"{what}: FAILED\\n")
        print(done.stderr or done.stdout)
        raise SystemExit(f"Stopped at: {what}")
    print(f"{what}: done")
    return done


must("make the project",
     "projects", "create", PROJECT,
     "--name=DBTL sentinel demonstration", "--quiet")

must("attach billing",
     "billing", "projects", "link", PROJECT,
     f"--billing-account={BILLING}", "--quiet")

must("switch on Compute Engine",
     "services", "enable", "compute.googleapis.com",
     f"--project={PROJECT}", "--quiet")

print(f"\\nproject {PROJECT} is ready")
""")

# ------------------------------------------------------------- 3 the machine

md("""
---

# 3. Create a machine

One Linux machine in the `europe-southwest1` region, which is Google's
Madrid data centre and the nearest one to Barcelona.

The machine installs Docker as it starts. Docker runs sentinel-oo and the
LLM alongside each other, each in its own container, which is what allows
the same image to run on any machine without software being installed into
the machine itself.

Duration: approximately 30 seconds for the machine to appear, and a further
60 seconds for Docker to finish installing. The cell waits for both.
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

must("make the machine",
     "compute", "instances", "create", VM,
     f"--project={PROJECT}", f"--zone={ZONE}",
     f"--machine-type={MACHINE}",
     "--image-family=ubuntu-2404-lts-amd64",
     "--image-project=ubuntu-os-cloud",
     "--boot-disk-size=100GB",
     "--metadata-from-file=startup-script=startup.sh",
     "--quiet")


def on_the_machine(command, quiet=False, must_work=True):
    # Runs one command on the machine over SSH. By default a non-zero exit
    # code stops the notebook, so that a step which failed is reported where
    # it happened rather than as a symptom in a later cell.
    done = subprocess.run(
        ["gcloud", "compute", "ssh", VM, "--zone", ZONE, "--project", PROJECT,
         "--quiet", "--command", command],
        capture_output=True, text=True)
    if not quiet:
        print(done.stdout or done.stderr)
    if must_work and done.returncode != 0:
        raise SystemExit(
            f"That command failed on {VM}, exit code {done.returncode}:\\n\\n"
            f"{(done.stderr or done.stdout)[-800:]}")
    return done


print("waiting for the machine to finish installing Docker ...")
for attempt in range(40):
    # must_work is disabled for this call. Until the machine accepts
    # connections SSH itself fails, and those failures are the expected
    # condition while waiting.
    ready = on_the_machine("test -f /var/tmp/ready && echo yes",
                           quiet=True, must_work=False)
    if ready.stdout.strip() == "yes":
        print("ready")
        break
    time.sleep(10)
else:
    raise SystemExit(
        f"{VM} did not finish installing Docker within about seven minutes. "
        "Run this cell again. If it keeps happening, look at the machine in "
        "the Google Cloud console.")
""")

# ---------------------------------------------------------------- 4 the code

md("""
---

# 4. Put the code on the machine

Clones the project's repository onto the machine. The repository holds the
service, the contract files and the example packages.

Duration: a few seconds.
""")

code("""
on_the_machine(f"rm -rf dbtlhub && git clone --depth 1 {REPO} && "
               f"echo '--- the repository on the machine ---' && ls dbtlhub")
""")

# --------------------------------------------------------------- 4.5 the LLM

md("""
---

# 5. Start the LLM

LLM stands for large language model.

**Which LLM, and where it runs.** The LLM is `qwen2.5:14b`, which is
Alibaba's Qwen 2.5 at 14 billion parameters, released under the Apache 2.0
licence. It is downloaded onto the machine created in section 3 and runs
there under Ollama, which is a program that serves a local LLM over an
ordinary web interface.

Nothing outside that machine can reach it. There is no key, no account, and
no request leaving for anybody's service. The LLM's file is approximately
9 gigabytes, which takes a few minutes to download onto a Google Cloud
machine.

The name and version are pinned in the deployment rather than resolved to
whatever is newest, so that a check performed today and the same check
performed next year are performed by the same LLM. The record written inside
every checked package names it.

**The task the LLM performs here.** One requirement in the contract is
marked as a requirement an LLM may assist with. When that requirement fails,
the LLM is asked a single question: is this value already recorded somewhere
in this package, including inside prose that no rule can read? It answers
from the package's own text. Whatever it proposes is then put back through
the contract's rules, and is kept only if every requirement concerning that
value passes.

**The narrow task is a deliberate choice and not the limit of the LLM.** The
task is kept narrow here so that every answer can be verified by a mechanism
that cannot be persuaded. The same LLM could do considerably more: explain a
refusal in the vocabulary of the team that caused it, draft a contract from a
package that already exists, propose the vocabulary two groups should agree
on, or sit above the whole cycle and decide which handover to check next. The
architecture permits all of these. What changes as the LLM is given more
latitude is how much of the result remains provable afterwards, and
sentinel-oo was built to keep it provable.

This cell downloads the LLM now, so that the deployment in section 7 is
quick.
""")

code("""
print(f"downloading {MODEL}, which takes a few minutes.\\n")

# Every docker command runs under sudo. The startup script adds the login
# user to the group permitted to use Docker, but group membership only takes
# effect at the next login, so sudo is used throughout. The deployment in
# section 7 runs under sudo for the same reason.
#
# The LLM is downloaded into a named Docker volume. The deployment mounts
# that same volume, so it finds the LLM already present rather than
# downloading 9 gigabytes a second time.
#
# `ollama pull` writes a progress bar on every line, so only the last two
# lines of its output are kept.
on_the_machine(
    f"set -o pipefail; "
    f"sudo docker volume create {DEPLOY}-model-store >/dev/null && "
    f"sudo docker rm -f warming >/dev/null 2>&1; "
    f"sudo docker run -d --name warming "
    f"-v {DEPLOY}-model-store:/root/.ollama ollama/ollama:0.5.7 >/dev/null && "
    f"until sudo docker exec warming ollama list >/dev/null 2>&1; do sleep 2; done && "
    f"sudo docker exec warming ollama pull {MODEL} 2>&1 | tail -2 && "
    f"echo '--- what is in the store now ---' && "
    f"sudo docker exec warming ollama list && "
    f"sudo docker rm -f warming >/dev/null")

print(f"\\n{MODEL} is on {VM}, ready for sentinel-oo to use")
""")

# ------------------------------------------------------------- 5 the contract

md("""
---

# 6. The contract

Everything sentinel-oo does in the rest of this notebook is determined by
this one file, so the file is set out here before the service is deployed.

A contract is a file written by the team that receives the handover. It
records which handover it governs, which kinds of thing it expects to find
in a package, and then a list of requirements. Each requirement states three
things: what to examine, what must be true of it, and the sentence a person
should read when it is not true.

The file contains no code. Adding a handover means writing a file of this
kind and nothing else. No class is written, no name is registered anywhere,
and no table maps a handover onto any part of sentinel-oo.

The cell below clones the repository into this notebook as well, so that the
notebook has packages to submit in later sections, and prints the opening of
the contract file.
""")

code("""
# The repository is cloned into this notebook as well as onto the machine.
# The copy here is used only for the packages submitted in later sections
# and for printing the contract file. The service itself runs on the Google
# Cloud machine, and nothing is installed in this notebook.
!git clone --depth 1 {REPO} local-copy --quiet

CONTRACT = "local-copy/bioprospecting/contracts/design_to_build.yaml"
text = open(CONTRACT).read()
lines = text.splitlines()


def requirement_called(name):
    # Extracts one requirement from the file by name. A requirement begins
    # at a "- name:" line and ends where the next one begins, so the lines
    # between the two are collected.
    out, inside = [], False
    for line in lines:
        if line.strip().startswith("- name:"):
            if inside:
                break
            inside = line.strip().endswith(name)
        if inside:
            out.append(line)
    return "\\n".join(out)


# The head of the file, which states what the contract is and what it is
# for. Its end is located by searching for the line on which the
# requirements begin, rather than by a fixed line count, so this prints
# correctly if the contract changes length.
head = lines[:next(n for n, line in enumerate(lines)
                   if line.startswith("requires:"))]
print("\\n".join(head))
print("\\n          . . .\\n")

# One requirement in full, to show the shape a requirement takes.
print(requirement_called("well_has_a_position"))
print("\\n          . . .\\n")

# The one requirement in the file that an LLM is permitted to assist with.
print(requirement_called("edge_handling_is_recorded"))
print(f"\\n{len(lines)} lines in all, holding 20 requirements")
""")

md("""
**The parts of the file.**

`contract: design_to_build` is the name of the handover. That name is how a
caller asks for this check, and it is the only name by which sentinel-oo
knows this contract. The file itself may be called anything.

`version: 0.11.0` is written into the record inside every package this
contract checks. A package checked last month therefore carries the version
of the contract it was checked against, which matters when the contract
changes and somebody asks why an older package passed.

`expects:` lists the kinds of thing the contract is written for: plate
wells, expression constructs, proteins, the plate layout, and the step that
predicted the genes. Without this block, a contract accepts packages it has
not meaningfully examined, because a requirement about plate wells says
nothing about a package that contains no plate wells. Every requirement
behaves correctly, nothing fails, and a clean verdict is returned on a
package the contract never looked at.

Then the requirements. Each one carries:

- `name`, by which a finding is cited afterwards
- `applies_to`, the kind of thing the requirement examines
- `property` or `named_value`, the part of that thing it reads
- `must`, one of the five conditions a requirement may demand
- `severity`, either `refuse`, which stops the handover, or `flag`, which
  allows it through and records a finding
- `message`, the sentence a person reads

Every sentence in those messages was written by a person, about their own
laboratory, in their own words. None of it originates in sentinel-oo. A
refusal shown later in this notebook is that person's sentence, read back
out of this file.

One requirement further down the file carries `repairable: true`. That is
the requirement the LLM may answer a question about, and it is the only
point in the system at which an LLM may propose anything.
""")

# ----------------------------------------------------------------- 6 deploy

md("""
---

# 7. Deploy sentinel-oo

One command, run on the machine. It performs five steps and stops at the
first one that fails.

1. Reads every contract file and refuses to build anything if one of them
   does not make sense
2. Builds the container image
3. Runs sentinel-oo's own test suite inside the build, so that an image
   whose tests fail is never produced
4. Starts sentinel-oo, with the contracts mounted read only, alongside the
   LLM downloaded in section 5
5. Confirms by checksum that the running instance is serving exactly the
   contracts read in step 1

No package has been submitted at this point. This is sentinel-oo standing
ready.

Duration: approximately 2 minutes, nearly all of it the image build.
""")

code("""
# `tail` keeps the last 40 lines, which carry the summary of what was
# deployed. The full output includes the image build and runs to several
# hundred lines.
#
# `pipefail` is required here. Without it the exit code would be tail's,
# which always succeeds, so a failed deployment would be reported as a
# successful one and would appear two cells later as a service that does
# not answer.
on_the_machine(
    f"set -o pipefail; cd dbtlhub/sentinel-oo && "
    f"sudo python3 deploy.py ../bioprospecting/contracts "
    f"--name {DEPLOY} --yes 2>&1 | tail -40")
""")

# --------------------------------------------------------------- 7 what it holds

md("""
---

# 8. Query the deployment

sentinel-oo listens on its machine's loopback address only, so nothing on
the internet can reach it. The cell below forwards a port from this notebook
to the machine over SSH, which is how any machine of your own is reached.

Three queries are then sent over that connection.

**Identity and health.** Which image the instance was built from, which
commit of the code it holds, and which LLM it can see. An instance given an
LLM it cannot reach reports that here rather than continuing silently.

**The contracts it is serving**, with a checksum over all of them. The
deployment compared that checksum against the contracts it read in step 1 of
section 7, which is how it established that the running instance holds
exactly what was validated, and not some other file that happened to be on
the machine.

**The contract in plain words, reported by the running service** rather than
read from the file. This is the form sent to the team that produces the
handover, so that they can check their own work before it is checked for
them.
""")

code("""
import requests, socket

# A free port on this notebook's own machine. Colab runs services of its
# own on the conventional ports, so the operating system is asked for an
# unused port rather than one being chosen here.
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    HERE_PORT = probe.getsockname()[1]

SERVICE = f"http://127.0.0.1:{HERE_PORT}"

# sentinel-oo listens on the machine's own loopback address, which nothing
# outside that machine can reach. This forwards the free port chosen above
# to port 8080 on that machine over an SSH connection, so the requests
# below do not travel over the open internet.
#
# ssh's own output is kept rather than discarded, because a forward that
# cannot be established reports the reason there. The file is line
# buffered, so that ssh's output is present by the time anything reads it.
tunnel_said = open("tunnel.log", "w", buffering=1)

# A forward left behind by an earlier run of this cell would still hold its
# port and its connection, so it is closed first.
if "tunnel" in dir():
    tunnel.terminate()

tunnel = subprocess.Popen(
    ["gcloud", "compute", "ssh", VM, "--zone", ZONE, "--project", PROJECT,
     "--quiet", "--", "-N", "-L", f"{HERE_PORT}:127.0.0.1:8080"],
    stdout=tunnel_said, stderr=tunnel_said)
print(f"forwarding port {HERE_PORT} here to port 8080 on {VM}")


def ask(path, tries=30):
    # Sends one request to sentinel-oo, retrying for up to 60 seconds. The
    # forwarded port takes a few seconds to open, and on the first run of a
    # notebook gcloud also generates an SSH key, which takes longer.
    for attempt in range(tries):
        if tunnel.poll() is not None:
            raise SystemExit(
                "The tunnel closed. Run the cell again; if it keeps closing, "
                "the machine is not reachable over SSH.")
        try:
            answer = requests.get(f"{SERVICE}{path}", timeout=5)
        except requests.exceptions.RequestException:
            time.sleep(2)
            continue
        try:
            return answer.json()
        except ValueError:
            raise SystemExit(
                f"{path} answered with status {answer.status_code} and this, "
                f"which is not JSON:\\n\\n{answer.text[:400] or '(nothing)'}"
                f"\\n\\nWhat ssh said about the forward:\\n"
                f"{open('tunnel.log').read()[-400:] or '(nothing)'}")
    raise SystemExit(
        "The service did not answer within a minute. Check the cell above "
        "finished, then run: on_the_machine('sudo docker ps')\\n\\n"
        f"What ssh said about the forward:\\n"
        f"{open('tunnel.log').read()[-400:] or '(nothing)'}")


alive = ask("/health")

# Whatever answered is identified before anything is concluded from it. If
# the forward failed to take the port, these requests reach whatever else is
# listening on it, and a plausible reply from the wrong service is harder to
# notice than no reply at all.
if alive.get("service") != "sentinel-oo":
    raise SystemExit(
        f"Something answered on port {HERE_PORT}, and it is not sentinel-oo. "
        f"It said:\\n\\n{json.dumps(alive, indent=2)[:400]}")

print("sentinel-oo is answering\\n")
print("--- identity and health ---")
print(json.dumps(alive, indent=2))

print("\\n--- the contracts it is serving ---")
print(json.dumps(ask("/contracts"), indent=2))
""")

md("""
The contract as the running service reports it, in plain words.
""")

code("""
# The contract is requested from sentinel-oo rather than read from the file
# a second time. The reply carries it in two forms: `summary` is the
# contract written out as sentences, which is the form sent to a producing
# team, and `requirements` is the same content as data, for a program that
# acts on it rather than a person who reads it.
held = ask("/contracts/design_to_build")
print(held["summary"])
""")

# ------------------------------------------------------------ 8 a good crate

md("""
---

# 9. Submit a compliant package

The package is an RO-Crate: a folder of data files together with one
metadata file that describes what each data file is and how the things
described relate to each other.

This package is a Design to Build handover: four candidate proteins drawn
from a metagenome, a synthetic gene designed for each one, the plate layout
recording which well each gene occupies, and a record of every step that
produced them, back to the environmental sample. Every sequence in it is
simulated, and each one is labelled as such.

It is submitted as a zip archive, so that the data files travel with the
metadata describing them. What comes back is the whole package rather than a
report about it: the same crate, with the record of the check written inside
it, ready to pass to whoever runs the Build phase.
""")

code("""
import io, zipfile
from pathlib import Path

# The example packages come from the copy of the repository cloned into
# this notebook in section 6. The machine holds its own copy, but the
# package has to be sent from here for the submission to be a real one.
CRATES = Path("local-copy/bioprospecting/exampleROcrates")


def send(folder):
    # A package is a folder: one metadata file and the data files it
    # describes. It is zipped and posted whole, so that the data travels
    # with the metadata. Posting the metadata file on its own is also
    # accepted, and in that case no requirement about the contents of a
    # data file can be answered.
    #
    # `by=` states who is asking. sentinel-oo writes that into the record
    # as the caller's own claim about itself. It authenticates nobody.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for item in Path(folder).rglob("*"):
            if item.is_file():
                bundle.write(item, item.relative_to(folder))
    answer = requests.post(
        f"{SERVICE}/check/design_to_build?by=the%20demonstration",
        data=buffer.getvalue(),
        headers={"Content-Type": "application/zip"})

    # The expected reply is the package itself. Any other content type
    # means sentinel-oo declined to perform the check, which is a different
    # condition from refusing the package, and reporting it here is clearer
    # than a failure to unpack the reply two lines later.
    if answer.headers.get("Content-Type") != "application/zip":
        raise SystemExit(
            f"The service answered with status {answer.status_code} and "
            f"{answer.headers.get('Content-Type')}, not a package:\\n\\n"
            f"{answer.text[:400]}")
    return answer


def verdict_of(answer):
    # The verdict is carried in a response header, so that a pipeline can
    # act on it without unpacking the reply.
    return answer.headers.get("X-Sentinel-Verdict", "no verdict")


def announce(answer, what):
    # The verdict is printed in a banner, because it is the part of the
    # output an audience is looking for.
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

# The run identifier names this particular check. Section 12 uses an
# identifier of this kind to request the graph of a check.
print(f"\\n  run            {answer.headers.get('X-Sentinel-Run')}")
print(f"  findings       {answer.headers.get('X-Sentinel-Findings')}")
print(f"  returned       {len(answer.content):,} bytes")
GOOD_RUN = answer.headers.get("X-Sentinel-Run")
""")

md("""
The record inside the returned package is shown next. sentinel-oo wrote that
record into the package itself, and it is the part that persists: it travels
with the package, so that whoever receives the package a year later can see
what was checked, by which version of which service, and what was found,
without asking anybody.
""")

code("""
# The reply is a zip archive of the whole package: the same data files that
# were submitted, and a metadata file with the record of this check added
# to it.
with zipfile.ZipFile(io.BytesIO(answer.content)) as bundle:
    bundle.extractall("checked")
    print("the returned package contains:")
    for name in bundle.namelist():
        print("   ", name)

# The metadata file is a list of entities, each with an identifier. The
# entities sentinel-oo added for this check carry identifiers that state
# what they are: `/about/` for what was checked, and `/found/` for what was
# found.
crate = json.load(open("checked/ro-crate-metadata.json"))
print("\\nthe record of this check:\\n")
for thing in crate["@graph"]:
    identifier = str(thing.get("@id", ""))
    if "/about/" in identifier or identifier.endswith("/found/verdict"):
        print(f"  {thing.get('name'):34} {str(thing.get('value'))[:70]}")
""")

# ------------------------------------------------------------ 9 broken crates

md("""
---

# 10. Submit packages with defects

Three packages, each with exactly one defect, so that every refusal can be
traced to a single cause.

Each of these packages passes a standard RO-Crate validator with no issues
reported. That was measured with `rocrate-validator` version 0.13.1 on
11 November 2026. The packages are well formed, and they are also unusable
by the Build phase. That gap is what sentinel-oo exists to close.
""")

code("""
# Each of these is a copy of the compliant package with exactly one change,
# so that each refusal can be traced to one cause rather than to several at
# once.
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

# ---------------------------------------------------------- 9b the LLM's turn

md("""
---

# 11. A defect the LLM can repair

This package carries a subtler defect. The setting the Build phase requires
is not recorded as a value. It appears inside an ordinary English sentence
in the description of the step that produced the data: "contig edges were
treated as closed, so no partial genes were kept".

No rule can read that sentence. A rule reads a value recorded as a value.

The contract marks this requirement as one an LLM may assist with, so the
LLM is asked its single question. It reads the sentence, proposes the value
`closed`, and the contract's own rules then check the proposal before it is
kept.

The verdict is `ACCEPTED_WITH_FLAGS` rather than `ACCEPTED`, and the flag
records what happened: which value was recovered, by which LLM, and which
requirement confirmed it. The handover proceeds, and the team that produced
it is told that a machine had to recover something they should have
recorded.

The machine created in section 3 has no graphics card, so the LLM takes tens
of seconds to answer rather than about 1 second. On a machine with a
graphics card this step is quick.
""")

code("""
started = time.time()
answer = send(CRATES / "design-to-build" / "invalid" / "edge-handling-in-prose")
announce(answer, "the setting is there, written in a sentence")
waited = round(time.time() - started)
print(f"\\n  the whole check took about {waited} "
      f"{'second' if waited == 1 else 'seconds'}, nearly all of it the "
      f"LLM\\n")

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
The next package shows the opposite case, which matters equally.

In it the same setting appears only as `-c`, a flag within a recorded
command line. Recovering the value would require knowing what that
program's flags mean, rather than reading what the record states. Two LLMs
of this size were asked to do exactly that on 10 November 2026, and both
stated a wrong meaning without qualification.

The contract's rules reject the proposed answer, nothing is written into the
package, and the verdict remains `REFUSED`. The LLM is never the component
that decides.
""")

code("""
answer = send(CRATES / "design-to-build" / "invalid" / "mode-in-prose")
announce(answer, "the setting is there, but only as a flag in a command line")

# What the LLM did is read out of the record rather than asserted here. The
# record states whether an LLM was reachable, how many times it was asked,
# and how many of its answers survived the contract's own rules.
crate = json.loads(zipfile.ZipFile(io.BytesIO(answer.content))
                   .read("ro-crate-metadata.json"))
for thing in crate["@graph"]:
    if thing.get("name") == "model":
        print(f"\\n  the record of what the LLM did:\\n")
        print(textwrap.fill(str(thing.get("value")), 66,
                            initial_indent="    ", subsequent_indent="    "))

print("\\n  Nothing was written into the package, and the handover is refused.")
""")

# ------------------------------------------------------------------ 10 graph

md("""
---

# 12. The graph of one check

A package is a set of things that refer to each other. A plate well refers
to the gene it holds; that gene refers to the protein it was designed from;
a processing step refers to the files it read and the files it produced.

Requesting the graph of one check returns the nodes and the edges of that
structure, with the check itself, each finding, and any value the LLM
recovered marked so that they are distinguishable from the handover they
describe.
""")

code("""
# The graph of one check: every entity in the package, every reference
# between them, and the check itself.
graph = ask(f"/graph/{FLAGGED_RUN}")
print(f"verdict : {graph['verdict']}")
print(f"nodes   : {graph['counts']['nodes']}")
print(f"edges   : {graph['counts']['edges']}")
print()
for role, count in sorted(graph["counts"]["by_role"].items(),
                          key=lambda pair: -pair[1]):
    print(f"  {role:28} {count}")
""")

code("""
# One colour for each role sentinel-oo assigns to a node. The roles come
# from the service, not from this notebook, so a role added later appears in
# grey rather than breaking the drawing.
COLOURS = {
    "the handover": "#8fb8de", "a recorded value": "#cfd8e3",
    "a file": "#b7d7b0", "the check": "#f2b134", "the verdict": "#e8743b",
    "a finding": "#d9534f", "a change made": "#9b59b6",
    "a value a model recovered": "#9b59b6", "who asked": "#7f8c8d",
    "the service": "#f2b134", "what was checked": "#f7d8a0",
    "missing": "#000000", "elsewhere": "#dddddd",
}

def draw(graph, leave_out_packaging=True, height=640):
    # Draws the graph with the vis-network library. Nodes that belong to the
    # check, rather than to the handover being checked, are drawn larger, so
    # that the findings are visible among several dozen other nodes.
    #
    # Packaging edges are left out by default. Those are the references that
    # hold an RO-Crate together, such as every file being a part of the
    # crate, and they connect almost everything to one node, which hides the
    # structure of the handover itself.
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
**Reading the picture.**

The orange node is the check itself. The red nodes attached to it are its
findings. The purple node is the value the LLM recovered, which is the only
value in this package that no person recorded.

The blue nodes are the handover: the wells, the genes, the proteins and the
steps that produced them.

Dragging a node separates the picture. Holding the pointer over a node shows
its role, its type and its identifier.
""")

# -------------------------------------------------------------- 11 shut down

md("""
---

# 13. Remove the project

Deletes the project, which deletes the machine with it and ends every
charge. Nothing is left running afterwards.
""")

code("""
tunnel.terminate()

gone = gcloud("projects", "delete", PROJECT, "--quiet")
if gone.returncode != 0:
    print("The project was not deleted. What Google said:\\n")
    print(gone.stderr or gone.stdout)
    raise SystemExit(
        "Delete it by hand, or it keeps a billing slot and anything still "
        "running in it keeps charging:\\n\\n"
        f"    !gcloud projects delete {PROJECT} --quiet")

state = gcloud("projects", "describe", PROJECT,
               "--format=value(lifecycleState)").stdout.strip()
print(f"{PROJECT}: {state or 'gone'}")
print("\\nThe machine went with it, so nothing is charging any more.")
""")

md("""
---

## Summary

A service that stands at a handover, deployed in approximately 5 minutes
onto a machine that did not exist when this notebook started.

Everything it checks was read from a contract file. No code was written to
teach it about plates, genes or proteins, and a different laboratory writes
a different file for the same service to enforce.

A package that passes a standards validator can still be refused, and
should be, when what the receiving phase requires is absent.

The LLM is used where rules cannot reach, recovering values recorded only in
prose, and it is never permitted to decide. Every answer it proposes is
checked against the contract before it counts.

What the service returns is the handover itself, with the record of the
check written inside it, so that whoever receives the package can see what
was checked without asking anybody.
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

    Every code cell is written here inside a triple-quoted string, so a
    backslash in a cell's source has to survive one more round of reading
    than it appears to. A backslash that does not survive produces a cell
    which only fails when somebody runs it, and in this notebook's case
    that is in front of an audience. Compiling every cell before the
    notebook is written catches it at build time instead.
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
