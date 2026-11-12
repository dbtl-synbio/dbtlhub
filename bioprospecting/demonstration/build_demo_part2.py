"""Build part two of the demonstration notebook.

Part one is the notebook one person runs on a Google Cloud machine while a
room watches. Part two is the notebook each person in that room runs on
their own Colab machine, with their own copy of sentinel-oo, their own LLM
and their own crates.

The notebook is generated from this script rather than edited by hand,
because a notebook file is JSON and hand-edited JSON breaks in ways that
are not visible until the file is opened.

One difference from part one shapes the whole of this notebook. Colab does
not allow a Docker daemon inside its machines, so sentinel-oo cannot be
deployed here the way part one deploys it. It is installed as a Python
package and started directly, and Ollama is installed into the machine
rather than run in a container.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "demo_part2.ipynb"

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


# ---------------------------------------------------------------- the opening

md("""
# sentinel-oo, part two: check a handover yourself

**ELIXIR BioHackathon Europe 2026, Project 25.**

Developed by Neil Wipat, Newcastle University, and Claude.

In part one of this demonstration, one instance of sentinel-oo was deployed
on a Google Cloud machine and watched from the room. In this notebook you
run your own instance, on the machine Google gives you for this notebook,
and check crates with it yourself. Nobody shares an instance, nobody waits
for anybody else, and nothing is installed on your own computer.

You need no Google Cloud account and no billing account. Everything here
runs on the temporary machine behind this notebook, and it costs nothing.

## The story this notebook tells

**One question runs through all ten steps: can the Build phase accept what
the Design phase has just handed over?**

You take the side that receives the work. Step 2 is what your side
requires, written in a file and nowhere else. Steps 4 to 7 are a handover
arriving and being checked against that file. Step 8 is the handovers that
cannot be accepted, including two where what you need is in the crate and no
rule can read it. Step 9 is what the check left behind. Step 10 is you
changing what your side requires, and the answer to the same question
changing with it.

## What you will do

| Step | What happens |
|---|---|
| 1 | Install sentinel-oo and an LLM on this machine |
| 2 | Read what the Build phase requires, in plain words. This is the contract, and it decides everything that follows |
| 3 | Start your own sentinel-oo and confirm it is answering |
| 4 | Look at what the crate from the Design phase actually records |
| 5 | Get a copy of that crate onto your own computer, to edit and send back |
| 6 | Send a crate to be checked, by one of three routes: the example crate, text you paste in, or a file you upload |
| 7 | Read the verdict, and the record sentinel-oo wrote inside the crate it returned |
| 8 | Send handovers that cannot be accepted, including two where an LLM is asked for help |
| 9 | Draw the check itself as a graph |
| 10 | Change what the Build phase requires, then write a contract of your own |

## Terms used throughout

**Handover**: the point where one phase of a Design, Build, Test, Learn
cycle passes its output to the next phase. This notebook works on one
handover, from Design to Build in a bioprospecting cycle.

**RO-Crate**: the packaging format the crates are in. A folder of data files
plus one metadata file, `ro-crate-metadata.json`, that says what each data
file is and how the things in the crate relate to each other.

**Contract**: a file, written by the team that receives the handover, listing
what that team requires. sentinel-oo knows nothing except what a contract
file tells it.

**LLM**: large language model. The one used here runs on this machine and
answers one narrow question, described in part 8.
""")

# ------------------------------------------------------------ before you start

md("""
---

# Before you start: ask Colab for a graphics card

Colab will give you one free of charge. With a card, part 8 uses the LLM
that has been measured doing the job and answers in about 1 second. Without
one, part 1 falls back to a smaller LLM that answers in tens of seconds and
has not been measured on that question, so part 8 may come back refused
rather than flagged. Nothing else in the notebook depends on it.

**Runtime, then Change runtime type, then T4 GPU, then Save.** Do it now,
because changing it later restarts the machine and loses everything the
notebook has installed.

If no card is available, carry on anyway. Every other part of the notebook
behaves identically.
""")

# ---------------------------------------------------------------- 1 install

md("""
---

# 1. Install sentinel-oo and an LLM on this machine

This step is plumbing. Nothing about handovers happens in it, and the
story starts in step 2. Four things happen in the cell below.

**The repository is cloned**, which brings the service, the contract files
and the example crates onto this machine.

**sentinel-oo is installed** as an ordinary Python package. In part one it
ran inside a Docker container, which is how it is deployed on a server.
Colab does not allow a Docker daemon inside its machines, so here it is
installed and run directly. It is the same code either way.

**Ollama is installed and started.** Ollama is a program that serves an LLM
over a plain web interface on this machine. Nothing leaves the machine: no
key, no account, and no request to anybody's service.

**An LLM is downloaded**, and which one depends on whether this machine was
given a graphics card.

| Card present | LLM used | Size of its file | Why |
|---|---|---|---|
| Yes | `qwen2.5:14b` | approximately 9 gigabytes | This is the one measured recovering the value in part 8, on 10 and 11 November 2026. It is the same LLM part one used |
| No | `qwen2.5:7b` | approximately 4.7 gigabytes | The larger one takes minutes per answer on a processor alone. The smaller one answers in tens of seconds, and it has not been measured on the question part 8 asks, so part 8 may be refused rather than flagged |

Both are Alibaba's Qwen 2.5, released under the Apache 2.0 licence, and the
number before the `b` is the number of parameters in billions.

Duration: approximately 3 minutes, most of it the download.
""")

code("""
import json, os, shutil, socket, subprocess, sys, textwrap, time
from pathlib import Path

REPO     = "https://github.com/dbtl-synbio/dbtlhub.git"
PORT     = 8099                       # the port your own sentinel-oo listens on
SERVICE  = f"http://127.0.0.1:{PORT}"
OLLAMA   = "http://127.0.0.1:11434"   # the address Ollama serves the LLM on

# Whether this machine has a graphics card decides which LLM is used, so it
# is established here rather than assumed.
#
# nvidia-smi is the program that reports NVIDIA cards. A machine with no
# card does not have the program either, so asking for it raises
# FileNotFoundError rather than returning a failure, and both outcomes mean
# the same thing here.
try:
    cards = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                           text=True)
    HAS_A_CARD = cards.returncode == 0 and "GPU" in cards.stdout
    what_it_said = cards.stdout.strip()
except FileNotFoundError:
    HAS_A_CARD, what_it_said = False, ""

print("graphics card:", what_it_said if HAS_A_CARD else "none")

if HAS_A_CARD:
    MODEL, MODEL_SIZE = "qwen2.5:14b", "9 gigabytes"
    print(f"LLM: {MODEL}, the one measured recovering the value in part 8")
else:
    MODEL, MODEL_SIZE = "qwen2.5:7b", "4.7 gigabytes"
    print(f"LLM: {MODEL}, because the larger one takes minutes per answer "
          f"on a processor alone.\\n     It has not been measured on the "
          f"question part 8 asks, so part 8 may be\\n     refused rather "
          f"than flagged. Everything else is unaffected.")

print("\\ncloning the repository ...")
# Removed first, so that running this cell a second time works rather than
# failing because the folder is already there.
!rm -rf dbtlhub && git clone --depth 1 {REPO} dbtlhub --quiet

if not Path("dbtlhub/sentinel-oo/pyproject.toml").exists():
    raise SystemExit(
        "The repository did not arrive. Check this machine has a network "
        "connection, then run this cell again.")

print("installing sentinel-oo ...")
!pip install --quiet ./dbtlhub/sentinel-oo

# Proved rather than assumed: everything after this cell runs the installed
# package, and a failed install otherwise shows up several cells later as
# something stranger.
installed = subprocess.run([sys.executable, "-m", "sentinel_oo", "--help"],
                           capture_output=True, text=True)
if installed.returncode != 0:
    print(installed.stderr[-800:])
    raise SystemExit("sentinel-oo did not install. The reason is above.")
print("sentinel-oo installed")

print("installing Ollama ...")

# Ollama's installer unpacks its download with zstd, and a Colab machine
# does not have zstd. Installing it first is quicker than working round it.
# Measured on 12 November 2026: without this the installer stops with
# "This version requires zstd for extraction".
!apt-get -qq install -y zstd > apt-zstd.log 2>&1 || (apt-get -qq update >> apt-zstd.log 2>&1 && apt-get -qq install -y zstd >> apt-zstd.log 2>&1)

if shutil.which("zstd") is None:
    print(open("apt-zstd.log").read()[-600:])
    print("zstd did not install, and Ollama's installer needs it. Trying "
          "anyway, in case this version of the installer does not.")

!curl -fsSL https://ollama.com/install.sh | sh > ollama-install.log 2>&1

if shutil.which("ollama") is None:
    print(open("ollama-install.log").read()[-1000:])
    raise SystemExit(
        "Ollama did not install. What its installer said is above. Without "
        "it everything in this notebook works except the one check in "
        "part 8 that asks an LLM.")

# Ollama is started as a background process rather than as a system service,
# because a Colab machine has no service manager. Its output goes to a file
# so that it can be read if the LLM turns out to be unreachable later.
ollama_said = open("ollama.log", "w", buffering=1)
ollama = subprocess.Popen(["ollama", "serve"],
                          stdout=ollama_said, stderr=ollama_said)


def waiting_for(address, seconds=60):
    # Waits for something to start listening on an address, by trying to
    # open a connection rather than by sleeping a fixed time.
    host, port = address.replace("http://", "").split(":")
    for attempt in range(seconds):
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex((host, int(port))) == 0:
                return True
        time.sleep(1)
    return False


if not waiting_for(OLLAMA):
    print(open("ollama.log").read()[-800:])
    raise SystemExit("Ollama did not start. What it said is printed above.")
print("Ollama is serving\\n")

print(f"downloading {MODEL}, approximately {MODEL_SIZE} ...")
# `ollama pull` writes a progress bar on every line, so only the last two
# lines of its output are kept.
pulled = subprocess.run(["ollama", "pull", MODEL],
                        capture_output=True, text=True)
print("\\n".join((pulled.stdout + pulled.stderr).strip().splitlines()[-2:]))
if pulled.returncode != 0:
    raise SystemExit(f"{MODEL} did not download. See the lines above.")

print(f"\\n{MODEL} is on this machine and ready")
""")

# --------------------------------------------------------------- 2 the contract

md("""
---

# 2. What the Build phase requires: the contract

**This is the centre of the demonstration.** The contract is the whole of
what sentinel-oo knows. Every verdict in the rest of this notebook comes out
of this one file, so the rest of the notebook is this file being enforced
and nothing more.

It is the same contract used in part one: `design_to_build`, for the
handover from the Design phase to the Build phase of a bioprospecting
cycle. Design finishes with a panel of candidate proteins drawn from a
metagenome, a synthetic gene designed for each one, and a plate layout
recording which gene goes in which well. Build orders those genes from a
synthesis company and pays for each gene synthesised.

The cell below copies the contract files out of the repository into a folder
called `my-contracts`, which is yours to change in part 10, and then asks
sentinel-oo to print the contract in plain words rather than as the file
itself. The printing is done by sentinel-oo, not by this notebook, and it is
the form you would send to the team that produces the handover so that they
can check their own work before it is checked for them.
""")

code("""
# The contracts are copied rather than read where they lie, so that part 10
# can change them without changing the clone of the repository.
shutil.rmtree("my-contracts", ignore_errors=True)
shutil.copytree("dbtlhub/bioprospecting/contracts", "my-contracts")
print("my-contracts holds:", ", ".join(sorted(
    p.name for p in Path("my-contracts").iterdir())))


def sentinel_oo(*arguments):
    # Runs the sentinel-oo command line program and prints what it printed.
    # Every call in this notebook that is not an HTTP request goes through
    # this, so the arguments used are visible in the output.
    #
    # It returns nothing on purpose. A notebook prints the value of a cell's
    # last line, so returning the finished process here would print the
    # whole of its output a second time, as one long line with the line
    # breaks written out as \\n.
    print(f"\\n$ sentinel-oo {' '.join(arguments)}\\n")
    done = subprocess.run([sys.executable, "-m", "sentinel_oo", *arguments],
                          capture_output=True, text=True)
    print(done.stdout or done.stderr)


sentinel_oo("--contracts", "my-contracts", "--list-contracts")
sentinel_oo("--contracts", "my-contracts", "--show-contract", "design_to_build")
""")

md("""
**Five things to notice in what was just printed.**

**The handover's name is `design_to_build`.** That name, not the file name,
is how anything asks for this check.

**The `expects` block names the kinds of thing the contract is written
for**: plate wells, the plate layout, expression constructs, proteins and
the gene calling step. Without that block a contract accepts crates it has
never meaningfully examined, because a requirement about plate wells says
nothing about a crate containing no plate wells. Every requirement behaves
correctly, nothing fails, and a clean verdict is returned on a crate the
contract never looked at. Part 8 shows that happening on purpose.

**Each requirement demands one of five conditions**: that something be
recorded, that it be unique, that it point at something else in the crate,
that it be a number within a range, or that a file hold data. Those five are
the whole language. Anything a contract asks for is one of them.

**Presence and soundness are separate requirements.** One requirement says a
reference is recorded at all; another says it lands on something that exists
in the crate. They are two because one requirement doing both could not
report which of the two failed.

**Every message was written by a person**, about their own laboratory, in
their own words. When you see a refusal later in this notebook you are
reading somebody's sentence out of this file.
""")

# -------------------------------------------------------- 3 start the service

md("""
---

# 3. Start your own sentinel-oo

You have read what the Build phase requires. This step puts a service
in front of it, so that crates can be sent to it and answered.

The cell below starts the service on this machine, listening on port 8099 of
the machine's own loopback address, which nothing outside this notebook can
reach. It then asks it two questions.

`GET /health` asks what it is: which version of the code, which contracts it
can see, and whether it can reach the LLM. An instance that cannot reach its
LLM says so here rather than carrying on silently.

`GET /contracts` asks which contracts it is serving, with a SHA-256 checksum
over all of them.

The cell also defines `start_sentinel()` and `stop_sentinel()`, which part 10
uses to restart the service after you have changed a contract.
""")

code("""
import requests

# The service reads these when it starts. Pointing it at the Ollama on this
# machine is the whole of the LLM configuration.
os.environ["SENTINEL_MODEL_URL"] = OLLAMA
os.environ["SENTINEL_MODEL"] = MODEL

# The first question to an LLM includes loading it into memory, which takes
# longer than the questions after it. 300 seconds is generous enough for a
# machine with no graphics card.
os.environ["SENTINEL_MODEL_FIRST_TIMEOUT"] = "300"

service = None


def anything_on_the_port():
    # Whether something is listening on the port, whoever it is.
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def stop_sentinel():
    # Stops the instance this notebook started, if it is running, and waits
    # for the port to be released. Called before starting another, so that
    # two instances never hold the same port.
    global service
    if service is not None and service.poll() is None:
        service.terminate()
        try:
            service.wait(timeout=20)
        except subprocess.TimeoutExpired:
            service.kill()
    service = None
    for attempt in range(20):
        if not anything_on_the_port():
            return
        time.sleep(0.5)


def start_sentinel(contracts="my-contracts"):
    # Starts sentinel-oo as a background process and waits for it to answer.
    # Its output goes to a file, which is printed if it does not start.
    global service
    stop_sentinel()

    # An instance left behind by an earlier run of this notebook, or
    # anything else that happens to hold this port, would take the requests
    # that follow. It would answer them, and it would answer them from
    # whichever contracts it was started with, which is how a cell further
    # down comes to report a verdict that does not match the contract on
    # screen. So the port has to be free before anything is started.
    if anything_on_the_port():
        raise SystemExit(
            f"Something is already listening on port {PORT}, and this cell "
            f"did not start it. If an earlier instance of sentinel-oo is "
            f"still running, stop it by running  !pkill -f sentinel_oo  in a "
            f"cell. Otherwise change PORT in part 1 to another number, run "
            f"that cell, and run this one again.")

    said = open("sentinel.log", "w", buffering=1)
    service = subprocess.Popen(
        [sys.executable, "-m", "sentinel_oo", "--serve",
         "--contracts", contracts, "--host", "127.0.0.1", "--port", str(PORT)],
        stdout=said, stderr=said)

    if not waiting_for(SERVICE) or service.poll() is not None:
        print(open("sentinel.log").read()[-1500:])
        raise SystemExit(
            "sentinel-oo did not start. What it said is printed above. The "
            "usual cause is a contract file it refuses to load, which it "
            "names.")

    # And whatever is answering has to be the thing just started, not
    # something else that took the port in between.
    alive = ask("/health")
    if alive.get("service") != "sentinel-oo":
        raise SystemExit(
            f"Something answered on port {PORT} and it is not sentinel-oo. "
            f"It said:\\n\\n{json.dumps(alive, indent=2)[:400]}")
    return service


def ask(path, tries=20):
    # Sends one GET request to your own sentinel-oo and returns the reply as
    # data. A reply that is not JSON is reported with what it actually said,
    # which is more use than a parsing error.
    for attempt in range(tries):
        try:
            answer = requests.get(f"{SERVICE}{path}", timeout=10)
        except requests.exceptions.RequestException:
            time.sleep(1)
            continue
        try:
            return answer.json()
        except ValueError:
            raise SystemExit(
                f"{path} answered with status {answer.status_code} and this, "
                f"which is not JSON:\\n\\n{answer.text[:400] or '(nothing)'}")
    raise SystemExit("Your sentinel-oo stopped answering. Run this cell again.")


start_sentinel()
print("your sentinel-oo is answering\\n")

print("--- identity and health ---")
print(json.dumps(ask("/health"), indent=2))

print("\\n--- the contracts it is serving ---")
print(json.dumps(ask("/contracts"), indent=2))
""")

# ----------------------------------------------------------- 4 look at a crate

md("""
---

# 4. What the crate from the Design phase records

A handover has arrived. Before sending it to be checked, look at what it
actually records, because a contract can only require what is there.

A contract can only require things that are actually recorded in a crate, so
the first thing to do with a crate is to find out what it records.

`--describe` prints exactly that: every kind of entity in the crate with a
count, and the named values hanging off each kind. That list is what a
contract has to match. If a contract names a kind of thing that does not
appear in this list, no requirement about it can ever be answered.

The crate described below is the compliant example from the repository: four
candidate proteins drawn from a metagenome, a synthetic gene designed for
each one, the plate layout recording which well each gene occupies, and a
record of every step that produced them, back to the environmental sample.
Every sequence in it is simulated, and each one is labelled as such.
""")

code("""
CRATES = Path("dbtlhub/bioprospecting/exampleROcrates")
EXAMPLE = CRATES / "design-to-build" / "valid"

print("the files in this crate:")
for item in sorted(EXAMPLE.iterdir()):
    print(f"   {item.name:28} {item.stat().st_size:,} bytes")

sentinel_oo("--describe", str(EXAMPLE))
""")

# --------------------------------------------------------------- 5 send a crate

md("""
---

# 5. Get a copy of the crate onto your own computer

Routes B and C below send a crate that you supply, which means you need the
crate as a file on your own computer. The cell below gives it to you: it
zips the example crate you have just looked at and downloads it through your
browser.

Open it, change something in `ro-crate-metadata.json`, and send it back in
by route C. Deleting a value, renaming a well so that two wells share a
position, or pointing a well at a construct that is not in the crate are all
changes this contract has something to say about.

Two other ways to the same files, if the download is awkward:

**The file browser.** The folder icon on the left of this notebook shows
every file on this machine. The crate is at
`dbtlhub/bioprospecting/exampleROcrates/design-to-build/valid`. Double
clicking `ro-crate-metadata.json` opens it in an editor here, where it can
be read and copied for route B, and the three dots beside a file download it.

**Your own copy, edited here.** Route A copies the crate to a folder called
`my-crate`, and you can edit the files in `my-crate` in that same file
browser and send it again without downloading anything at all.
""")

code("""
# Zipped and handed back through the browser, so that there is a real crate
# on the participant's own computer for routes B and C to use.
archive = shutil.make_archive("design-to-build-valid", "zip", EXAMPLE)
print(f"{Path(archive).name}: {Path(archive).stat().st_size:,} bytes")

from google.colab import files
files.download(archive)
""")

md("""
---

# 6. Send the crate to be checked

**You choose which crate to send.** Three routes are offered, and the cells
below define all three. Run whichever you want; each one sets `CRATE` to the
folder that will be sent, and running another one afterwards simply replaces
it.

| Route | What it does | When to use it |
|---|---|---|
| A | Uses the example crate from the repository | Quickest. Start here if you have no crate of your own |
| B | Takes `ro-crate-metadata.json` as text you paste into the cell | A crate you have in a text editor, or one you want to alter by hand before sending |
| C | Takes files you upload with Colab's file picker | A crate on your own computer |

**On route C and folders.** Colab's file picker accepts files, not folders.
A crate folder therefore arrives either as a zip archive of the folder,
which is one file and the quickest way, or as a multiple selection of the
files inside it, which the cell reassembles into a folder. Either works. A
crate large enough to be awkward either way can also be read from Google
Drive, which the cell explains.

**What is sent and what comes back.** The crate is zipped and posted to
`POST /check/design_to_build`. What comes back is the whole crate, not a
report about it: the same files, with the record of the check written inside
the metadata file, ready to pass on to whoever runs the Build phase. The
verdict also comes back on its own in the `X-Sentinel-Verdict` response
header, so a program can act on it without opening the archive.
""")

code("""
import io, zipfile

MINE = Path("my-crate")


def as_the_crate_to_send(folder):
    # Puts the chosen crate in one known place, so the cells after this do
    # not care which route it arrived by.
    shutil.rmtree(MINE, ignore_errors=True)
    shutil.copytree(folder, MINE)
    held = sorted(p.name for p in MINE.rglob("*") if p.is_file())
    print(f"the crate to send is now {MINE}, holding {len(held)} files:")
    for name in held:
        print("   ", name)
    if not (MINE / "ro-crate-metadata.json").exists():
        print("\\n  WARNING: there is no ro-crate-metadata.json in it, and "
              "sentinel-oo will refuse it for that reason alone.")
    return MINE


def send(folder=None, contract="design_to_build", by="a workshop participant"):
    # Zips the crate and posts it. The crate travels as a zip so that the
    # data files go with the metadata that describes them. Posting the
    # metadata file alone is also accepted, and then no requirement about
    # the contents of a data file can be answered.
    #
    # `by=` states who is asking. sentinel-oo writes it into the record as
    # the caller's own claim about itself. It authenticates nobody.
    folder = Path(folder or MINE)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for item in folder.rglob("*"):
            if item.is_file():
                bundle.write(item, item.relative_to(folder))
    answer = requests.post(
        f"{SERVICE}/check/{contract}",
        params={"by": by},
        data=buffer.getvalue(),
        headers={"Content-Type": "application/zip"})
    if answer.headers.get("Content-Type") != "application/zip":
        raise SystemExit(
            f"sentinel-oo answered with status {answer.status_code} and "
            f"{answer.headers.get('Content-Type')}, not a crate:\\n\\n"
            f"{answer.text[:400]}")
    return answer


def announce(answer, what):
    # The verdict, printed as a banner, because it is the thing being
    # looked for. It returns nothing, for the reason given above.
    verdict = answer.headers.get("X-Sentinel-Verdict", "no verdict")
    rule = "=" * 66
    print(rule)
    print(f"  {what}")
    print(f"  {verdict}")
    print(rule)
    print(f"  run       {answer.headers.get('X-Sentinel-Run')}")
    print(f"  findings  {answer.headers.get('X-Sentinel-Findings')}")


def crate_in(answer):
    # The metadata file out of the crate that came back, as data. This is
    # the one helper that returns something, so a cell ending with it
    # should assign it to a name rather than leave it as its last line.
    return json.loads(zipfile.ZipFile(io.BytesIO(answer.content))
                      .read("ro-crate-metadata.json"))


def findings_in(answer):
    # Prints the findings out of the crate that came back. sentinel-oo adds
    # entities whose identifiers say what they are: `/found/` for what was
    # found, `/about/` for what was checked.
    for thing in crate_in(answer)["@graph"]:
        identifier = str(thing.get("@id", ""))
        if "/found/" in identifier and "verdict" not in identifier:
            print(f"\\n  {thing.get('name')}")
            print(textwrap.fill(str(thing.get("value")), 64,
                                initial_indent="      ",
                                subsequent_indent="      "))


# Nothing has been chosen yet. The three routes below each set this, and
# the cell that sends says so plainly if none of them has been run.
CRATE = None

print("three routes are now available: route A, route B and route C below")
""")

md("""
### Route A: use the example crate
""")

code("""
CRATE = as_the_crate_to_send(EXAMPLE)
""")

md("""
### Route B: paste a crate in as text

Replace the text between the three quotation marks with the contents of your
own `ro-crate-metadata.json`, then run the cell. Leaving it as it is skips
the route and changes nothing, so running every cell in order is safe.

A crate sent this way is its metadata file and nothing else, so any
requirement about the contents of a data file cannot be answered. In this
contract that is `every_file_holds_data`.
""")

code("""
PASTED = r'''
paste the contents of ro-crate-metadata.json here
'''

if "paste the contents" in PASTED:
    print("Route B skipped: nothing was pasted in.")
else:
    try:
        parsed = json.loads(PASTED)
    except json.JSONDecodeError as wrong:
        raise SystemExit(
            f"That is not valid JSON: {wrong}. Line {wrong.lineno}, column "
            f"{wrong.colno}. Paste the whole file, from its first {{ to its "
            f"last }}.")
    if "@graph" not in parsed:
        raise SystemExit(
            "That JSON has no @graph, so it is not an RO-Crate metadata "
            "file. What was pasted begins: " + PASTED.strip()[:120])
    shutil.rmtree("pasted-crate", ignore_errors=True)
    Path("pasted-crate").mkdir()
    (Path("pasted-crate") / "ro-crate-metadata.json").write_text(
        json.dumps(parsed, indent=1))
    print(f"the pasted crate describes {len(parsed['@graph'])} entities")
    CRATE = as_the_crate_to_send("pasted-crate")
""")

md("""
### Route C: upload a crate from your computer

Running this cell opens a file picker. Choose either a zip archive of your
crate folder, or all the files inside the folder at once. Choosing nothing
skips the route and changes nothing.

If your crate is too large to upload comfortably, put it in your Google
Drive instead, then run `from google.colab import drive;
drive.mount('/content/drive')` in a cell of your own and call
`as_the_crate_to_send('/content/drive/MyDrive/your-crate-folder')`.
""")

code("""
from google.colab import files

print("choose a zip of your crate folder, or the files inside it")
uploaded = files.upload()

if not uploaded:
    print("Route C skipped: nothing was uploaded.")
else:
    shutil.rmtree("uploaded-crate", ignore_errors=True)
    Path("uploaded-crate").mkdir()
    zips = [name for name in uploaded if name.lower().endswith(".zip")]
    if zips:
        # A zip of a folder usually holds that folder as its top level, so
        # the crate is looked for rather than assumed to be at the root.
        with zipfile.ZipFile(io.BytesIO(uploaded[zips[0]])) as bundle:
            bundle.extractall("uploaded-crate")
        print(f"unpacked {zips[0]}")
        found = list(Path("uploaded-crate").rglob("ro-crate-metadata.json"))
        root = found[0].parent if found else Path("uploaded-crate")
    else:
        for name, content in uploaded.items():
            (Path("uploaded-crate") / Path(name).name).write_bytes(content)
        print(f"wrote {len(uploaded)} uploaded files")
        root = Path("uploaded-crate")
    CRATE = as_the_crate_to_send(root)
""")

md("""
### Send the crate you chose
""")

code("""
if CRATE is None:
    raise SystemExit(
        "No crate has been chosen yet. Run route A, B or C above, then run "
        "this cell.")

answer = send(CRATE)
announce(answer, f"{CRATE}, checked against design_to_build")
""")

# --------------------------------------------------------- 6 read what came back

md("""
---

# 7. What came back, and the record inside it

The handover was accepted. What matters now is what that acceptance
leaves behind for whoever receives the crate next.

sentinel-oo wrote a record into the crate itself. That record is the part
that lasts: it travels with the crate, so whoever receives the crate in a
year's time can see what was checked, which version of sentinel-oo checked
it, which version of the contract was applied, and what was found, without
asking anybody.

The cell below unpacks the reply and prints that record.
""")

code("""
shutil.rmtree("checked", ignore_errors=True)
with zipfile.ZipFile(io.BytesIO(answer.content)) as bundle:
    bundle.extractall("checked")
    print("the crate that came back holds:")
    for name in bundle.namelist():
        print("   ", name)

crate = json.load(open("checked/ro-crate-metadata.json"))
print("\\nthe record of this check:\\n")
for thing in crate["@graph"]:
    identifier = str(thing.get("@id", ""))
    if "/about/" in identifier or identifier.endswith("/found/verdict"):
        print(f"  {str(thing.get('name')):34} {str(thing.get('value'))[:70]}")

findings_in(answer)
""")

# ------------------------------------------------------------- 7 break it

md("""
---

# 8. Handovers that cannot be accepted

Everything so far has gone well. This step is the handovers that have
not, which is the case sentinel-oo exists for.

Five crates from the repository, each broken in one way, plus one deliberate
mistake of a different kind. Every one of them passes a standard RO-Crate
validator with no issues reported, measured with `rocrate-validator` version
0.13.1 on 11 November 2026. They are well formed. They are also unusable by
the Build phase, and that gap is what sentinel-oo exists to close.

| Crate | What was changed |
|---|---|
| `missing-conformsto` | The `conformsTo` statement is deleted, so the crate no longer states which profile it follows |
| `dangling-reference` | A file named `sequencing-report.pdf` is listed as part of the crate, and nothing in the crate describes it |
| `missing-gene-calling-mode` | The gene calling step's recorded `edge handling` value, which was `closed`, is deleted |
| `edge-handling-in-prose` | The same value is absent as a value, but a sentence in the gene calling step's description says the edges were treated as closed |
| `mode-in-prose` | The same value is absent again, and the only trace of it is the flag `-c` inside a recorded command line |
""")

code("""
BROKEN = CRATES / "design-to-build" / "invalid"

for folder in ["missing-conformsto", "dangling-reference",
               "missing-gene-calling-mode"]:
    answer = send(BROKEN / folder)
    announce(answer, folder)
    findings_in(answer)
    print()
""")

md("""
## When the value is there, but written in a sentence

**The setting is called `edge handling`.** A metagenome is assembled into
contigs, which are stretches of reconstructed sequence with two ends. A gene
predicted at an end may run off it, in which case the gene is a fragment
rather than a whole one. `edge handling` records what the gene caller did
about that, and the value `closed` means it discarded any gene running off a
contig end, so every protein in the panel is a complete gene with a start
codon and a stop codon.

Build requires this because it pays for each gene synthesised. If the panel
keeps fragments, some of those orders are for partial sequences, and a
partial sequence makes a protein that does not fold or does not function.

**The problem.** In `edge-handling-in-prose` the value is not recorded as a
value. It sits in an ordinary English sentence in the description of the gene
calling step: "Contig edges were treated as closed, so no partial genes were
kept". The information is in the crate, and no rule can read it, because a
rule reads a value recorded as a value.

Refusing the crate would be wrong in substance, since the crate does contain
what Build needs. Accepting the sentence would also be wrong, since Build is
a program ordering genes and a program cannot read a sentence.

**What happens instead.** The contract marks that one requirement as a
requirement an LLM may assist with. The LLM is asked a single question: is
this value recorded anywhere in this crate, including inside prose? It
answers from the crate's own text and proposes a value. The proposal is
written down as a properly recorded value and put back through the
contract's own rules, and it is kept only if every requirement about that
value then passes. The requirement itself is never relaxed.

The verdict is therefore `ACCEPTED_WITH_FLAGS`, not `ACCEPTED`, and the flag
says which value was recovered, by which LLM, and which requirement
confirmed it.

This cell is the only one that waits on the LLM. With a graphics card it
takes about 1 second and without one it takes tens of seconds.
""")

code("""
started = time.time()
answer = send(BROKEN / "edge-handling-in-prose")
waited = round(time.time() - started)
announce(answer, "edge-handling-in-prose: the value is in a sentence")
print(f"\\n  the check took about {waited} "
      f"{'second' if waited == 1 else 'seconds'}, nearly all of it the LLM")

findings_in(answer)

for thing in crate_in(answer)["@graph"]:
    identifier = str(thing.get("@id", ""))
    if "/changed/" in identifier or "/recovered/" in identifier:
        print(f"\\n  written into the crate: {thing.get('name')} = "
              f"{thing.get('value')}")

FLAGGED_RUN = answer.headers.get("X-Sentinel-Run")
""")

md("""
## When the value is there, but only as a command line flag

In `mode-in-prose` the same value is absent and the only trace of it is `-c`
inside a command line recorded in the description: "Ran as: prodigal -i
contigs.fasta -a proteins.faa -p meta -c -q". Recovering the value from that
would require knowing what that program's flags mean, rather than reading
what the record states.

Two LLMs were asked to do exactly that on 10 November 2026, `qwen2.5:14b`
and `qwen2.5-coder:14b`, each with 14 billion parameters. Neither recovered
anything from the crate, and when asked directly what `-c` means, both
stated a wrong meaning without qualification.

The contract's rules reject any proposed answer that fails them, nothing is
written into the crate, and the verdict stays `REFUSED`. **The LLM is never
the component that decides.**
""")

code("""
answer = send(BROKEN / "mode-in-prose")
announce(answer, "mode-in-prose: the value is only a flag in a command line")

# What the LLM did is read out of the record rather than asserted here. The
# record states whether an LLM was reachable, how many times it was asked,
# and how many of its answers survived the contract's rules.
crate = json.loads(zipfile.ZipFile(io.BytesIO(answer.content))
                   .read("ro-crate-metadata.json"))
for thing in crate["@graph"]:
    if thing.get("name") == "model":
        print("\\n  the record of what the LLM did:\\n")
        print(textwrap.fill(str(thing.get("value")), 66,
                            initial_indent="    ", subsequent_indent="    "))

print("\\n  Nothing was written into the crate, and the handover is refused.")
""")

md("""
## A crate sent to a contract written for a different handover

The crate you have been sending is a Design to Build handover. The cell
below sends it to a different contract, `build_to_test`, which governs the
next handover in the cycle and expects assembled constructs, quality control
results and an assembly step. The crate contains none of those.

Without its `expects` block that contract would examine the crate, find that
no requirement of its own applies to anything in it, and return a clean
verdict on a crate it never looked at. With the block it refuses before a
single requirement is applied, and says which kinds of thing are missing.

**That is worth more attention than a refusal.** A refusal is visible. A
clean verdict on a crate that was never examined is not, and it would travel
on inside the crate as a record saying the handover was checked.
""")

code("""
answer = send(CRATE, contract="build_to_test")
announce(answer, "a Design to Build crate sent to the build_to_test contract")
findings_in(answer)
""")

# ------------------------------------------------------------------ 9 the graph

md("""
---

# 9. The check itself, drawn as a graph

The check in step 8 left a record inside the crate. This step draws that
record, together with the handover it is about.

A crate is a set of things that refer to each other. A plate well refers to
the gene it holds; that gene refers to the protein it was designed from; a
processing step refers to the files it read and the files it produced.

The request is `GET /graph/<run identifier>`, where the run identifier is the
one sentinel-oo returned in the `X-Sentinel-Run` header when it checked the
crate. The reply carries the nodes and the edges, with the check itself, each
finding, and any value the LLM recovered marked so that they stand apart from
the handover they describe.

The graph drawn below is of the check in part 8 where the LLM recovered a
value, because that one holds something nothing else does.

**Two things worth knowing about this request.** sentinel-oo keeps only its
most recent runs, and restarting it forgets all of them, so a run can be
asked for and be gone. When that happens it says so and lists the runs it
still holds. The durable copy of a check is not held by the service at all:
it is the record inside the crate that came back, and
`sentinel_oo.graph.of(crate)` builds this same answer out of that crate with
no service running anywhere.
""")

code("""
if "FLAGGED_RUN" not in globals():
    raise SystemExit(
        "There is no run to draw yet. Run the cell in part 8 that sends "
        "edge-handling-in-prose, then run this one.")

graph = ask(f"/graph/{FLAGGED_RUN}")

# A run the service no longer holds is answered with an explanation rather
# than a graph, and reading it is more use than a missing key further down.
if "error" in graph:
    print(json.dumps(graph, indent=2))
    raise SystemExit(
        "sentinel-oo does not hold that run any more, which happens if it "
        "has been restarted since part 8. Run the cell in part 8 that sends "
        "edge-handling-in-prose again, then run this one.")
print(f"verdict : {graph['verdict']}")
print(f"nodes   : {graph['counts']['nodes']}")
print(f"edges   : {graph['counts']['edges']}")
print()
for role, count in sorted(graph["counts"]["by_role"].items(),
                          key=lambda pair: -pair[1]):
    print(f"  {role:28} {count}")
""")

code("""
# One colour for each role sentinel-oo gives a node. The roles come from the
# service rather than from this notebook, so a role added later appears in
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
    # Draws the graph with the vis-network library. Nodes belonging to the
    # check, rather than to the handover being checked, are drawn larger so
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
**What the picture shows.**

The orange node is the check itself. The red nodes attached to it are its
findings. The purple node is the value the LLM recovered, which is the only
value in this crate that no person recorded.

The blue nodes are the handover: the wells, the genes, the proteins and the
steps that produced them.

The picture shows fewer lines than the edge count printed above it, because
the drawing leaves out the references that hold an RO-Crate together, such as
every file being a part of the crate. Those connect almost everything to one
node and hide the structure of the handover.

Dragging a node separates the picture. Holding the pointer over a node shows
its role, its type and its identifier.

To draw a different check, put another run identifier in place of
`FLAGGED_RUN`. Every `announce(...)` in this notebook printed one.
""")

# ---------------------------------------------------- 8 edit or write a contract

md("""
---

# 10. Change what the Build phase requires

Every verdict so far came from a contract somebody else wrote. This step
is you changing it, and then writing one of your own.

This is the argument of the whole demonstration: tailoring sentinel-oo to a
different laboratory, a different handover or a different cycle means writing
a file. No Python is written, no class is added, and nothing is registered
anywhere.

Two things to try. The first changes the contract you have been using. The
second writes a new contract of your own and checks the same crate against
it.

Both restart your sentinel-oo, because it reads its contracts when it starts.
A restart also empties the list of runs it holds, so the graph in part 9
should be drawn before you work through this part.
""")

md("""
### Change one requirement, and send the same crate again

In the contract, `construct_length_is_plausible` requires that a construct's
coding sequence length, measured in base pairs, lies between 300 and 3000
base pairs. Its severity is `flag`, which lets the handover through and
records a finding for somebody to read.

The cell below narrows that range to between 300 and 900 base pairs, which
is narrower than the constructs in the crate. Then it restarts your
sentinel-oo and sends the same compliant crate again. The crate has not
changed. The verdict changes from `ACCEPTED` to `ACCEPTED_WITH_FLAGS`,
because the contract changed.

Three things to try next, in increasing order of effect:

**Edit the two numbers** in the cell below and run it again.

**Change `severity: flag` to `severity: refuse`** on that requirement. The
contract file is at `my-contracts/design_to_build.yaml` and the file browser
on the left opens it for editing. Then run `start_sentinel()` and send the
crate again: the same crate is now refused outright. If you do that, change
the requirement's message too, because the message as written says that a
flag rather than a refusal is why somebody looks at it, and a message that
contradicts its own verdict is worse than no message.

**Put the contract back as it was** by running the cell in part 2 that
copies the contracts out of the repository, then `start_sentinel()`.
""")

code("""
CONTRACT = Path("my-contracts/design_to_build.yaml")
original = CONTRACT.read_text()

# One number changed in one line of one file. That is the whole of what
# tailoring this service to a different laboratory amounts to.
changed = original.replace("between: [300, 3000]", "between: [300, 900]")

# The message names the range in words, so it goes stale the moment the
# range changes. A message that contradicts the rule it belongs to is worse
# than no message, so it is edited here too.
changed = changed.replace(
    "which is 300 to 3000\\n      base pairs",
    "which is 300 to 900\\n      base pairs")

if changed == original:
    raise SystemExit(
        "Nothing was changed, so the contract no longer contains the text "
        "this cell looks for. Run the cell in part 2 that copies the "
        "contracts out of the repository and try again.")

CONTRACT.write_text(changed)
print("the requirement now reads:\\n")
inside = False
for line in changed.splitlines():
    if line.strip().startswith("- name: construct_length_is_plausible"):
        inside = True
    elif inside and line.strip().startswith("- name:"):
        break
    if inside:
        print("   ", line)

# The service reads its contracts when it starts, so a changed contract
# takes effect at the next start and not before.
start_sentinel()
print("\\nsentinel-oo restarted with the changed contract\\n")

answer = send(CRATE)
announce(answer, "the same crate, against the changed contract")
findings_in(answer)
""")

md("""
### Write a contract of your own

The cell below writes a complete contract in six lines of requirements. It
is deliberately short, so that every part of it is visible at once, and it
is a real contract: sentinel-oo will serve it beside the other two.

Edit it. Change what it expects, add a requirement, change a message to
something your own laboratory would say, then run the cell and the one after
it. The one after it restarts sentinel-oo and shows your contract being
served alongside `design_to_build` and `build_to_test`.

Everything a requirement may say is in part 2 above: `applies_to`, then
`property` or `named_value`, then `must`, which is one of the five
conditions, then `severity`, which is `refuse` or `flag`, then `message`.
""")

code("""
%%writefile my-contracts/my_handover.yaml
contract: my_handover
version: 0.1.0

description: >
  A contract written during the workshop. Replace this with what your own
  receiving phase requires.

# Every type named here must be in the crate, or the handover is refused
# before a single requirement below is applied.
expects:
  - Protein
  - PlateWell

requires:
  - name: the_crate_says_what_it_is
    applies_to: root
    property: name
    must: be recorded
    severity: refuse
    message: >-
      This crate has no name, so nobody receiving it can tell what it is.

  - name: every_well_has_a_position
    applies_to: PlateWell
    property: name
    must: be recorded
    severity: refuse
    message: >-
      This well has no position, so nobody can find it on the physical
      plate.

  - name: no_two_wells_share_a_position
    applies_to: PlateWell
    property: name
    must: be unique
    severity: refuse
    message: >-
      Two wells claim the same position on the plate.

  - name: every_protein_says_if_it_is_partial
    applies_to: Protein
    named_value: partial
    must: be recorded
    severity: flag
    message: >-
      This protein does not say whether its start and stop codons were both
      present.
""")

code("""
# The new contract is picked up when the service starts, like any other.
start_sentinel()
sentinel_oo("--contracts", "my-contracts", "--list-contracts")
sentinel_oo("--contracts", "my-contracts", "--show-contract", "my_handover")

answer = send(CRATE, contract="my_handover")
announce(answer, "your crate, against the contract you just wrote")
findings_in(answer)
""")

# ------------------------------------------------------------------ afterwards

md("""
---

# Afterwards: nothing is left running

**Nothing is left running and nothing is charged.** This machine belongs to
Colab, not to you, and it is taken away when you close the notebook or leave
it idle. Nothing was installed on your own computer, and no account of yours
was used except your Google sign-in to Colab.

**What you can take away.** The contracts in `my-contracts`, including any
you wrote, and any crate that came back checked. Download them from the file
browser on the left, or with `files.download('my-contracts/my_handover.yaml')`
in a cell of your own.

## What this showed

A service that stands at a handover, running on a machine that did not exist
when you opened this notebook.

Everything it checks was read from a contract file. You changed a
requirement, restarted, and the verdict on an unchanged crate changed with
it. You wrote a contract of your own and it was served beside the others. No
Python was written in either case.

A crate that passes an RO-Crate validator with no issues can still be
refused, and should be, when what the receiving phase requires is absent.
A crate sent to a contract written for a different handover is refused
before any requirement is applied, rather than being quietly accepted.

The LLM is used where rules cannot reach, recovering a value recorded only in
prose, and it is never permitted to decide. Every answer it proposed was
checked against the contract before it counted, and the one it got wrong was
thrown away.

What sentinel-oo returns is the handover itself, with the record of the check
written inside it, so whoever receives the crate can see what was checked
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

    Every code cell is written here inside a triple-quoted string, so a
    backslash in a cell's source has to survive one more round of reading
    than it appears to. A backslash that does not survive produces a cell
    which only fails when somebody runs it, and in this notebook's case
    that is in a room full of people. Compiling every cell before the
    notebook is written catches it at build time instead.
    """
    broken = 0
    for number, cell in enumerate([c for c in cells
                                   if c["cell_type"] == "code"], 1):
        text = "".join(cell["source"])
        # A cell whose first line is a Colab cell magic, such as
        # `%%writefile`, is not Python at all: its body is the file being
        # written. Compiling it would be compiling YAML.
        if text.lstrip().startswith("%%"):
            continue
        # Colab's shell and line magic lines are not Python either. A shell
        # line can be continued with a backslash, so its continuation goes
        # with it.
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
