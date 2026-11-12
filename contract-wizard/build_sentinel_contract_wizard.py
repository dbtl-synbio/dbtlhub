"""Build the Sentinel Contract Wizard notebook.

The Sentinel Contract Wizard writes an interoperability contract for a handover
between two phases of a Design, Build, Test, Learn cycle. It takes two
things from the person using it: the handover itself, as an RO-Crate, and a
description of what their phase needs, written in ordinary English under six
headings. It gives back a contract, the questions it could not answer
itself, and three checks on what it drafted.

The notebook is generated from this script rather than edited by hand,
because a notebook file is JSON and hand-edited JSON breaks in ways that are
not visible until the file is opened.

What this notebook does, in one sentence: it reads a crate, reads a
statement of what the receiving phase needs written under six headings,
asks a language model for a contract, and then checks that contract three
ways before anybody relies on it.

Everything in it was measured on 12 November 2026 against
qwen2.5:14b running on a laptop. The measurements that shaped the design:

  - Asked for YAML in free text, the model invented a demand that does not
    exist in the language and put a field name into the severity field. A
    JSON schema with closed lists makes both impossible.
  - Asked for the whole contract in one request, it wrote 2 requirements
    from six headings. Asked heading by heading, it wrote 17. The notebook
    therefore asks heading by heading.
  - Asked which of three entities typed `Sample` a rule was meant for, it
    guessed, and refused a sound crate 4 times. Told in the crate
    description that one type covers several different things, it asked
    instead of guessing.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "sentinel_contract_wizard.ipynb"

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text, title=None):
    """One code cell. A cell given a title is shown collapsed.

    Colab collapses a cell whose first line is a `#@title` comment and whose
    metadata says `cellView: form`. It still runs in full, and a double
    click on the title bar opens it. This is used for the cells that are
    plumbing rather than content: nobody needs to read 195 lines of
    function definitions to use the tool, and scrolling past them is what
    makes a notebook feel like somebody else's code.
    """
    body = text.strip("\n")
    metadata = {}
    if title:
        body = f"#@title {title}\n{body}"
        metadata = {"cellView": "form"}
    cells.append({"cell_type": "code", "metadata": metadata,
                  "execution_count": None, "outputs": [],
                  "source": body.splitlines(keepends=True)})


# ---------------------------------------------------------------- the opening

md("""
# The Sentinel Contract Wizard

**Write an interoperability contract from a crate and a description of what
you need, without learning the contract language first.**

**ELIXIR BioHackathon Europe 2026, Project 25.**

Developed by Neil Wipat, Newcastle University, and Claude, with Prozomix
Ltd.

The bioprospecting handover this tool is built around comes from work with
Prozomix Ltd. The example crate holds simulated data only: no sequence in it
is real.

A contract is the file that says what one phase of a Design, Build, Test,
Learn cycle must hand to the next, and what the receiving phase will refuse.
It is checked by sentinel-oo, which reads the contract and the handover and
says whether the handover can be accepted.

Writing a contract by hand means learning its vocabulary first. This tool
does it the other way round. You describe what your side needs in ordinary
English, a language model turns that into a first draft, three checks say
which parts of the draft can be trusted, and you correct it.

## What this notebook asks you for, and what it gives back

**It asks for two things.** The first is an RO-Crate, which is a packaged
folder of data with a metadata file describing everything inside it. This is
the handover itself, as it would arrive from the phase before yours. The
second is a statement, in your own words, of what your phase needs in order
to accept that handover. You write it under six headings that the notebook
provides.

**It gives back three things.** A contract, as a file you can keep and use.
A list of questions the model wants answered, because a question costs you
10 seconds and a wrong rule costs you a handover refused for no reason. And
the result of three checks on the draft, so that you know which parts of it
can be trusted before anybody relies on it.

## The story this notebook tells

**The argument is that a contract is a file, and writing one should not
require a programmer.**

Step 1 installs the software. Steps 2 and 3 are the two things only you can
provide: a crate, and a statement of what your phase needs. Step 4 defines
the machinery and step 5 describes your crate back to you in the terms a
rule has to be written in. Step 6 drafts the contract and step 7 shows what
the model was unsure about. Step 8 checks the draft three ways. Step 9 is
you correcting it, which is the part that matters. Step 10 puts a real
handover through the contract you have just written, and step 11 hands you
the file.

## What this costs

Nothing. It runs on the temporary machine Google gives this notebook. There
is no Google Cloud account, no billing account, no API key and nothing
installed on your own computer.
""")

# ------------------------------------------------- 0 ask for a graphics card

md("""
---

# Before you start: ask Colab for a graphics card

This notebook runs a language model on the machine behind it. That machine
has no graphics card unless you ask for one, and without a card the model
takes minutes to answer each question rather than seconds.

**Do this now, before running any cell.** In the menu at the top: **Runtime**,
then **Change runtime type**, then choose **T4 GPU**, then **Save**. The
notebook restarts, which costs nothing because nothing has run yet.

A T4 is an NVIDIA graphics card with 16 gigabytes of video memory, offered
on the free Colab tier. The next cell reports which card you were given, or
says there is none, and chooses a model accordingly.
""")

# ------------------------------------------------------------------ 1 install

md("""
---

# 1. Install sentinel-oo and a language model on this machine

Three things are installed into the temporary machine behind this notebook:
sentinel-oo itself, which checks a crate against a contract; Ollama, which
runs a language model locally; and the model, which drafts the contract.

**Nothing here is installed on your own computer, and nothing leaves this
machine.** The model runs on the Colab machine, so the crate and the words
you write are not sent to any company's service.

**Which model, and why it depends on the machine.**

| Graphics card | Model | Download | Why |
|---|---|---|---|
| Yes | `qwen2.5:14b` | approximately 9 gigabytes | The model these steps were measured against on 12 November 2026 |
| No | `qwen2.5:7b` | approximately 4.7 gigabytes | The larger one takes minutes per answer on a processor alone |

Both are Alibaba's Qwen 2.5, released under the Apache 2.0 licence. The
number before the `b` is the number of parameters in billions, which is the
rough measure of a model's size.

**A newer model is available and is not the default.** `qwen3.5:9b` is two
generations newer and smaller, at approximately 6.6 gigabytes. It has not
been measured on the task in this notebook, so it is not the default, but
one line in the next cell switches to it and the line says where.

Duration: approximately 3 minutes, most of it the download.
""")

code("""
import json, os, re, shutil, socket, subprocess, sys, textwrap, time
from collections import Counter
from pathlib import Path

REPO   = "https://github.com/dbtl-synbio/dbtlhub.git"
OLLAMA = "http://127.0.0.1:11434"    # the address Ollama serves the model on

# Whether this machine has a graphics card decides which model is used, so
# it is established here rather than assumed.
#
# nvidia-smi is the program that reports NVIDIA cards. A machine with no
# card does not have the program either, so asking for it raises
# FileNotFoundError rather than returning a failure, and both outcomes mean
# the same thing here.
try:
    cards = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
    HAS_A_CARD = cards.returncode == 0 and "GPU" in cards.stdout
    what_it_said = cards.stdout.strip()
except FileNotFoundError:
    HAS_A_CARD, what_it_said = False, ""

print("graphics card:", what_it_said if HAS_A_CARD else "none")

if HAS_A_CARD:
    MODEL, MODEL_SIZE = "qwen2.5:14b", "9 gigabytes"
else:
    MODEL, MODEL_SIZE = "qwen2.5:7b", "4.7 gigabytes"

# To use the newer model instead, remove the # from the start of the next
# line. It is approximately 6.6 gigabytes and has not been measured on the
# drafting task, so the drafts it writes may be better or worse.
# MODEL, MODEL_SIZE = "qwen3.5:9b", "6.6 gigabytes"

print(f"model: {MODEL}")

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

# Proved rather than assumed: everything after this cell uses the installed
# package, and a failed install otherwise appears several cells later as
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

!curl -fsSL https://ollama.com/install.sh | sh > ollama-install.log 2>&1

if shutil.which("ollama") is None:
    print(open("ollama-install.log").read()[-1000:])
    raise SystemExit(
        "Ollama did not install. What its installer said is above. Without "
        "a model this notebook cannot draft a contract, although every "
        "check in step 8 would still work on a contract written by hand.")

# Ollama is started as a background process rather than as a system service,
# because a Colab machine has no service manager. Its output goes to a file
# so that it can be read if the model turns out to be unreachable later.
ollama_said = open("ollama.log", "w", buffering=1)
ollama = subprocess.Popen(["ollama", "serve"],
                          stdout=ollama_said, stderr=ollama_said)


def waiting_for(address, seconds=60):
    # Waits for something to start listening on an address by trying to open
    # a connection, rather than by sleeping for a fixed time.
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
pulled = subprocess.run(["ollama", "pull", MODEL], capture_output=True, text=True)
print("\\n".join((pulled.stdout + pulled.stderr).strip().splitlines()[-2:]))
if pulled.returncode != 0:
    raise SystemExit(f"{MODEL} did not download. See the lines above.")

print(f"\\n{MODEL} is on this machine and ready")
""", title="Install sentinel-oo, Ollama and the model. Takes about 3 minutes. Double click to read the code")

# ------------------------------------------------------------- 2 the machinery

md("""
---

# 2. The crate the contract will be written against

A contract is written against a particular shape of handover. It names
types and values that have to exist in the crate, so the crate has to be in
front of you before the first rule can be written.

**Three ways to provide one.** Run the cell for whichever route suits you
and leave the other two alone.

- **Route A** uses an example from the repository, which is a bioprospecting
  Design to Build handover: a panel of candidate enzymes drawn from a
  metagenome, with a synthetic gene designed for each one. Use this if you
  have no crate of your own to hand.
- **Route B** uses a crate you upload from your own computer, as a folder or
  as a zip file.
- **Route C** uses a metadata file you paste in as text, which is enough on
  its own because a contract only ever reads the metadata.
""")

md("""
### Route A: the example from the repository
""")

code("""
CRATE = "dbtlhub/bioprospecting/exampleROcrates/design-to-build/valid"
print(f"using the example crate at {CRATE}")
""")

md("""
### Route B: upload a crate from your own computer

Running this cell opens a file chooser. Select the files of one crate,
including its `ro-crate-metadata.json`, or select a single zip file of the
whole crate.
""")

code("""
from google.colab import files

shutil.rmtree("my-crate", ignore_errors=True)
Path("my-crate").mkdir()

sent = files.upload()
for filename, content in sent.items():
    Path("my-crate", filename).write_bytes(content)
    if filename.endswith(".zip"):
        shutil.unpack_archive(f"my-crate/{filename}", "my-crate")

# A zip of a crate usually holds one folder with everything inside it, so
# the metadata file is found rather than assumed to be at the top.
found = list(Path("my-crate").rglob("ro-crate-metadata.json"))
if not found:
    raise SystemExit(
        "No ro-crate-metadata.json among those files. That file is what "
        "makes a folder a crate, so the crate cannot be read without it.")

CRATE = str(found[0].parent)
print(f"using your crate at {CRATE}")
""")

md("""
### Route C: paste a metadata file in as text

A contract reads only the metadata file, never the data files, so pasting
that one file is enough to draft and check a contract. Replace the text
between the triple quotes with your own.
""")

code('''
PASTED = r"""
{"@context": "https://w3id.org/ro/crate/1.3/context",
 "@graph": [
   {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
    "about": {"@id": "./"},
    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.3"}},
   {"@id": "./", "@type": "Dataset", "name": "Paste your own crate here"}
 ]}
"""

shutil.rmtree("pasted-crate", ignore_errors=True)
Path("pasted-crate").mkdir()
Path("pasted-crate/ro-crate-metadata.json").write_text(PASTED.strip())

CRATE = "pasted-crate"
print(f"using the crate you pasted, at {CRATE}")
''')

# ------------------------------------------------------------- 4 describe it

md("""
---

# 3. Say what your phase needs, in your own words

This is the part only you can do. Everything else in this notebook is
mechanical.

**Write under the six headings below and change nothing else.** The headings
are not decoration: each one supplies a different part of a requirement.

| Heading | What it decides |
|---|---|
| 1. Which handover is this? | The contract's name and description |
| 2. What does the receiving phase do with it? | Whether each rule is justifiable. A rule with no answer to "what goes wrong without it" is a preference rather than a requirement |
| 3. What must be present? | Which rules say `be recorded` |
| 4. What must be true of the values? | Which rules use a range, a list of permitted values or uniqueness |
| 5. What is worth a warning but not a refusal? | Which rules are `flag` rather than `refuse` |
| 6. What could be recovered rather than refused? | Which rules a language model may later be permitted to help with |

**Headings 1 and 2 are context rather than rules.** They are sent with every
request so that each rule can be written knowing what the handover is for,
but no requirement is drawn from them directly.

The text below is filled in for the example crate. Replace it with your own.
""")

code('''
NEEDS = r"""
# 1. Which handover is this?

The Design phase hands a panel of candidate enzymes to the Build phase,
which orders the genes from a synthesis company and has them expressed.

# 2. What does the receiving phase do with it?

Build pays a synthesis company for each gene in the panel, and then puts one
gene in each well of a plate. Anything Build cannot read out of the crate is
a well that may be wasted, and a wasted well is not discovered until the
plate comes back several weeks later.

# 3. What must be present, or the handover is useless?

Every candidate protein must carry its amino acid sequence, because that is
what is ordered, and the contig it was predicted from, because that is the
only route back from the enzyme to the material it was found in.

Every expression construct must carry the codon optimised coding sequence
that will actually be synthesised, and the host it was optimised for, since
a sequence optimised for the wrong host expresses poorly.

The intended plate layout must record which plate format it assumes.

# 4. What must be true of the values?

Protein identifiers must not repeat, because a repeated identifier means two
different genes ordered under one name.

A coding sequence must be between 300 and 3000 nucleotides. Below 300 it is
too short to be a whole enzyme, and above 3000 the synthesis company charges
a surcharge nobody has agreed to.

# 5. What is worth a warning but not a refusal?

The depth the environmental sample came from, and the time the sampling step
finished. Both matter for publishing the panel afterwards, and neither stops
a gene being ordered.

# 6. What could be recovered rather than refused?

How the gene caller treated contig edges is often written into the gene
calling step's description as a sentence rather than recorded as a value,
because the person running it writes prose. That one is worth trying to
recover before refusing anything.
"""

print(f"{len(NEEDS.split())} words, under "
      f"{len([l for l in NEEDS.splitlines() if l.startswith('# ')])} headings")
''')

# ------------------------------------------------------------- 6 the drafting

md("""
---

# 4. The machinery, defined once

This cell defines the six operations the rest of the notebook uses. It
prints nothing and changes nothing. Read it if you want to know how the
drafting works, and skip it if you do not: every function is used in a
later step, where what it does is explained again in context.

**The six operations.**

| Operation | What it does |
|---|---|
| `describe(crate)` | Turns a crate into a description a model can read: which types are in it, what each one carries, and which types cover more than one kind of thing |
| `schema_for(crate)` | Builds the rules the model's answer must obey, using the type names from your crate |
| `ask(prompt, schema)` | Sends one question to the model and returns its answer as data |
| `draft(crate, needs)` | Asks for requirements one heading at a time and merges the answers into one contract |
| `check(contract, crate)` | The three checks of step 8 |
| `run(contract, crate)` | Puts a crate through a contract and reports the verdict |

**Why the model's answer is constrained rather than trusted.** Ollama
accepts a schema and holds the model to it while it generates, so a word
outside the permitted lists cannot be produced at all. Measured on 12
November 2026 without this: the model invented a sixth demand called `exist`
when the language has five, and wrote the word `repairable` into the
severity field, which accepts two values. Neither is now possible.

**Why the permitted words are imported rather than typed out here.** They
come from `sentinel_oo.contract`, which is the code that decides whether a
contract is valid. A copy would disagree with it the day somebody adds a
sixth demand, and nothing would notice.
""")

code('''
import urllib.request
import yaml
from sentinel_oo.contract import MUSTS, SEVERITIES, parse, ContractError
from sentinel_oo.crate import Crate
from sentinel_oo.rules import types_of

# Ollama reads only the first 2,048 tokens of what it is sent unless this is
# raised, and a crate description alone is longer than that. Left at the
# default, the model would never see what you wrote at all.
WINDOW = 16384

# Above this many entities of one type, they are counted rather than listed.
# A panel of 96 wells listed one per line would bury everything else.
LIST_THEM_UP_TO = 6


def describe(folder):
    """Describe a crate in the terms a contract is written in."""
    crate = Crate.from_path(folder)
    lines, counts, members = [], Counter(), {}
    properties, values, carried_by = {}, {}, {}

    for entity in crate:
        for kind in types_of(entity):
            counts[kind] += 1
            members.setdefault(kind, []).append(entity)
            properties.setdefault(kind, Counter())
            values.setdefault(kind, Counter())
            for key in entity:
                if not key.startswith("@"):
                    properties[kind][key] += 1
            carries = set()
            for held in entity.get("additionalProperty", []) or []:
                named = crate.get(held.get("@id")) if hasattr(held, "get") else None
                if named and named.get("name"):
                    values[kind][named["name"]] += 1
                    carries.add(named["name"])
            carried_by.setdefault(kind, {})[entity["@id"]] = carries

    lines.append(f"{sum(1 for _ in crate)} entities in this crate.\\n")
    lines.append("Each heading below is a type, and a type is what a rule names")
    lines.append("in `applies_to`. Under it are the properties written on that")
    lines.append("type and the named values hanging off it.\\n")

    for kind, count in counts.most_common():
        lines.append(f"{kind}  ({count} of them)")
        for key, seen in properties[kind].most_common():
            lines.append(f"    property     {key:<20} on {seen:>3} of them")
        for name, seen in sorted(values[kind].items()):
            lines.append(f"    named_value  {name!r} on {seen} of them")
        if count <= LIST_THEM_UP_TO:
            lines.append(f"    the {count} of them, one by one:")
            for entity in members[kind]:
                label = (entity.get("name") or entity.get("identifier")
                         or entity["@id"])
                lines.append(f"      - {label}")
        lines.append("")

    # One type, several different things.
    #
    # A rule applies to every entity of the type it names, with no exceptions
    # available. Measured on 12 November 2026: a crate typed the sediment,
    # the DNA extracted from it and the sequencing library all as `Sample`.
    # A rule meant for the sediment caught all three, and the two that were
    # never collected from anywhere were refused for not recording where
    # they were collected. The crate was sound and the contract was wrong.
    #
    # So wherever entities of one type carry different values, it is said
    # here, before any rule is written.
    mixed = [kind for kind, carried in carried_by.items()
             if len(carried) > 1
             and len({frozenset(v) for v in carried.values()}) > 1
             and any(carried.values())]

    if mixed:
        lines.append("=" * 66)
        lines.append("WARNING: these types cover more than one kind of thing")
        lines.append("=" * 66)
        lines.append("")
        lines.append("A rule applies to every entity of the type it names.")
        lines.append("There is no way to write a rule for some of them. So")
        lines.append("where entities of one type carry different values they")
        lines.append("are probably different things, and a rule meant for one")
        lines.append("will be applied to all of them. Ask which is meant.")
        lines.append("")
        # Fewest entities first: a type covering 3 things is a sharper
        # warning than one covering 14.
        for kind in sorted(mixed, key=lambda k: (counts[k], k)):
            lines.append(f"  {kind}, {counts[kind]} of them:")
            for entity in members[kind][:6]:
                label = (entity.get("name") or entity.get("identifier")
                         or entity["@id"])
                holds = sorted(carried_by[kind][entity["@id"]])
                lines.append(f"    - {label}")
                lines.append(f"        carries: "
                             f"{', '.join(holds) if holds else 'no named values'}")
            if counts[kind] > 6:
                lines.append(f"    and {counts[kind] - 6} more of them")
            lines.append("")

    return "\\n".join(lines)


def names_in(folder):
    """Every type name, value name and property name this crate contains."""
    crate = Crate.from_path(folder)
    kinds, values, properties = set(), set(), set()
    for entity in crate:
        kinds.update(types_of(entity))
        properties.update(k for k in entity if not k.startswith("@"))
        for held in entity.get("additionalProperty", []) or []:
            named = crate.get(held.get("@id")) if hasattr(held, "get") else None
            if named and named.get("name"):
                values.add(named["name"])
    return sorted(kinds), sorted(values), sorted(properties)


def schema_for(folder):
    """What the model's answer must look like, in this crate's own words.

    This is not the contract format. A contract says either `property` or
    `named_value`, never both and never neither, which a schema cannot
    require of two separate optional fields. Left optional, the model
    omitted both from all 10 of its requirements. So the model answers two
    compulsory fields and `as_a_contract` below assembles them into the one
    field a contract wants.
    """
    kinds, values, properties = names_in(folder)
    return {
        "type": "object",
        "required": ["contract", "description", "requires", "questions"],
        "properties": {
            "contract": {"type": "string"},
            "description": {"type": "string"},
            "requires": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "applies_to", "looks_at_kind",
                                 "looks_at_name", "must", "between",
                                 "severity", "message"],
                    "properties": {
                        "name": {"type": "string"},
                        # Only what this crate holds, plus the two entities
                        # every crate has. A rule naming a type that is not
                        # in the crate matches nothing and passes in
                        # silence, and silence reads as approval.
                        "applies_to": {"type": "string",
                                       "enum": kinds + ["root", "descriptor"]},
                        "looks_at_kind": {"type": "string",
                                          "enum": ["property", "named_value",
                                                   "the file itself"]},
                        "looks_at_name": {"type": "string",
                                          "enum": values + properties
                                          + ["the file"]},
                        "must": {"type": "string", "enum": sorted(MUSTS)},
                        # Compulsory here and thrown away below unless the
                        # demand uses it. A schema cannot say "required only
                        # when another field holds a particular value", and
                        # left optional the model omitted it from the one
                        # rule that needed it.
                        "between": {"type": "array",
                                    "items": {"type": "number"},
                                    "minItems": 2, "maxItems": 2},
                        "of_type": {"type": "string"},
                        "severity": {"type": "string",
                                     "enum": sorted(SEVERITIES)},
                        "message": {"type": "string"},
                    },
                },
            },
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["about", "question"],
                    "properties": {"about": {"type": "string"},
                                   "question": {"type": "string"}},
                },
            },
        },
    }


# What to say when the model is not there. It is said in full rather than
# as a traceback, because sixteen frames of urllib tells a person nothing
# about what to do next.
NOT_RUNNING = """
Nothing is answering where the language model should be.

The model runs as a background program on this machine, started by step 1.
It dies whenever the Python kernel restarts, which Colab does when the
runtime type is changed and sometimes on its own. The step 1 cell still
shows as having run, because it did, on a machine that no longer exists.

WHAT TO DO: run the step 1 cell again. It is the collapsed one titled
"Install sentinel-oo, Ollama and the model". It is quicker the second time,
because the model is usually still on this machine's disk.
"""


def the_model_is_there():
    """True when something is listening where the model should be."""
    host, port = OLLAMA.replace("http://", "").split(":")
    with socket.socket() as probe:
        probe.settimeout(2)
        return probe.connect_ex((host, int(port))) == 0


def ask(prompt, schema):
    """One question to the model, with its answer held to the schema."""
    if not the_model_is_there():
        raise SystemExit(NOT_RUNNING)

    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "format": schema,
                       "options": {"num_ctx": WINDOW, "temperature": 0}}).encode()
    started = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"{OLLAMA}/api/generate", data=body,
                headers={"Content-Type": "application/json"}), timeout=3600) as reply:
            answer = json.load(reply)
    except urllib.error.URLError as unreachable:
        # It was listening a moment ago and is not now, or it refused the
        # request. Either way the person needs the same instruction.
        raise SystemExit(f"{NOT_RUNNING}\\nWhat the request said: {unreachable}")
    return json.loads(answer["response"]), time.time() - started
''', title="Define how a crate is described and how the model is constrained. Prints nothing. Double click to read the code")

code('''
THE_LANGUAGE = """
Every requirement says what it looks at, in two fields.

  looks_at_kind   `property` for something written on the entity itself,
                  such as name or identifier or isPartOf.
                  `named_value` for a value hanging off the entity, which is
                  how a crate records a measurement such as a pH or a
                  collection date.
                  `the file itself` only with the demand `hold data`.
  looks_at_name   the exact name of that property or value. Write `the file`
                  when the kind is `the file itself`.
  between         the lowest and highest permitted number, used only by the
                  demand `be a number between`. Write [0, 0] for every other
                  demand, where it is ignored.

The five demands are the whole vocabulary:

  be recorded                      the property or named value is present
  be unique                        no two entities share this value
  point at something in the crate  the reference lands on an entity here.
                                   Only for a property holding a reference.
                                   A property holding text is not one.
  be a number between              the value is a number inside `between`
  hold data                        the file this entity stands for has
                                   content

Only `be recorded` fires when something is absent. The others say nothing
about a property that is not there, so "it must be present" and "it must be
sound" are two separate requirements.

`severity` is `refuse` when the receiving phase cannot proceed, and `flag`
when it can proceed but somebody should know.

A rule applies to every entity of the type it names, with no exceptions
available. Where the crate description warns that one type covers more than
one kind of thing, do not write a rule that would catch the wrong ones. Ask
a question instead.

Ask a question whenever the words could mean more than one thing in this
crate. A question costs the person 10 seconds. A wrong rule costs them a
handover refused for no reason, which they then have to debug.
"""

# Words that show the model has answered with the names of the fields it was
# given rather than with a name for the handover. Measured on 12 November
# 2026: asked for a name, it answered
# `applies_to_sample_requirements_demand_be_recorded_looks_at_k`.
LANGUAGE_WORDS = ("applies_to", "looks_at", "named_value", "be_recorded",
                  "severity", "requirement", "demand")


def a_name(text):
    """Lower case with underscores, which is what a name has to be."""
    kept = [c.lower() if c.isalnum() else "_" for c in str(text).strip()]
    return "_".join(part for part in "".join(kept).split("_") if part)[:60]


def as_a_contract(answer):
    """Turn the model's answer into the contract format itself."""
    name = a_name(answer.get("contract") or "")
    if not name or len(name) > 40 or any(w in name for w in LANGUAGE_WORDS):
        name = "drafted_contract"

    out = {"contract": name, "version": "0.1.0",
           "description": answer.get("description", ""),
           # Worked out from the rules rather than asked for. `root` and
           # `descriptor` are the two entities every crate has rather than
           # types, so naming one here would refuse every crate ever sent.
           "expects": sorted({r.get("applies_to") for r in answer.get("requires", [])
                              if r.get("applies_to") not in
                              ("root", "descriptor", None, "")}),
           "requires": []}

    for raw in answer.get("requires", []):
        kind = raw.get("looks_at_kind")
        rule = {"name": a_name(raw.get("name", "")),
                "applies_to": raw.get("applies_to", "")}
        # `hold data` is about the file an entity stands for, so it takes
        # neither a property nor a named value.
        if raw.get("must") != "hold data" and kind != "the file itself":
            rule["property" if kind == "property" else "named_value"] = \\
                raw.get("looks_at_name", "")
        rule["must"] = raw.get("must")
        if raw.get("must") == "be a number between":
            rule["between"] = raw.get("between") or [0, 0]
        if raw.get("of_type"):
            rule["of_type"] = raw["of_type"]
        rule["severity"] = raw.get("severity")
        rule["message"] = str(raw.get("message", "")).strip()
        # `repairable`, which permits a model to propose a value where none
        # is recorded, is deliberately never set here. It is a decision for
        # the person reading the draft. Asked for it, the model set it true
        # on all 7 of its rules, including on identifiers, which would
        # license it to invent one.
        out["requires"].append(rule)

    # Two requirements under one name is refused by the parser, and a model
    # repeating itself is not a fault worth showing anybody.
    seen = set()
    for position, rule in enumerate(out["requires"], start=1):
        if not rule["name"] or rule["name"] in seen:
            rule["name"] = f"{rule['name'] or 'requirement'}_{position}"
        seen.add(rule["name"])
    return out


def draft(folder, needs):
    """Draft a contract, asking for one heading at a time.

    Asked for the whole contract in one request, qwen2.5:14b wrote 2
    requirements from six headings of free text. Asked heading by heading it
    wrote 17, measured on 12 November 2026 on the same crate and the same
    words. Each request is a smaller job, and the answers are merged here.

    The first two headings are not asked about. They say which handover this
    is and what the receiving phase does with it, which is context for every
    other heading rather than a source of rules of their own.
    """
    schema = schema_for(folder)
    description = describe(folder)
    # Empty pieces are dropped before anything is counted. Splitting text
    # that begins with a newline puts an empty string first and shifts
    # every heading by one, which sent heading 2 to the model as though it
    # asked for rules. What is first in the list must not decide anything.
    sections = [part for part in needs.split("\\n# ") if part.strip()]
    context = "\\n# ".join(section.strip() for section in sections[:2])
    merged = {"contract": "", "description": "", "requires": [], "questions": []}
    spent = 0.0

    # The first two headings say which handover this is and what the
    # receiving phase does with it. They are context for every other
    # heading rather than a source of rules of their own, so they are sent
    # with each request and never asked about directly.
    for section in sections[2:]:
        heading = section.strip().splitlines()[0]
        prompt = f"""You are drafting an interoperability contract for a
handover between two phases of a Design, Build, Test, Learn cycle. It is
checked by a program against an RO-Crate, which is a packaged folder of data
with a metadata file describing everything in it.
{THE_LANGUAGE}

Here is a description of the crate the contract is checked against.

=== THE CRATE ===
{description}
=== END OF THE CRATE ===

Here is what the person receiving the handover needs. This is one heading
out of several. Write every requirement this heading calls for and no
others.

=== WHAT THEY NEED ===
# {section.strip()}
=== END OF WHAT THEY NEED ===

Here is the context for it, which is the handover this is and what the
receiving phase does with it:

# {context}

Write the requirements, and any questions you need answered before they can
be trusted."""

        answer, took = ask(prompt, schema)
        spent += took
        print(f"  {heading[:50]:<52} {len(answer.get('requires', [])):>2} rules,"
              f" {took:>4.0f} s")
        merged["contract"] = merged["contract"] or answer.get("contract", "")
        merged["description"] = merged["description"] or answer.get("description", "")
        merged["requires"].extend(answer.get("requires", []))
        merged["questions"].extend(answer.get("questions", []))

    print(f"\\n  {len(merged['requires'])} requirements and "
          f"{len(merged['questions'])} question(s) in {spent:.0f} seconds")
    return as_a_contract(merged), merged.get("questions", [])
''', title="Define the contract language given to the model, and how its answer becomes a contract. Prints nothing. Double click to read the code")

# --------------------------------------------------------------- 3 the crate

md("""
---

# 5. What is in your crate, in the terms a rule is written in

A rule can only name something the crate actually contains. The names are
compared as plain text, so a rule saying `Well` against a crate saying
`PlateWell` matches nothing, raises nothing and passes in silence.

This cell describes the crate back to you: every type in it, the properties
written on each type, and the named values hanging off each type. A **named
value** is how a crate records a measurement, as a small entity holding a
name and a value rather than as a property on the thing being measured, so
a pH is recorded this way and a name is not.

**Read the warning at the end, if there is one.** It appears where several
entities share a type but carry different values, which usually means the
type covers more than one kind of thing. A rule applies to every entity of
the type it names, so this is where a rule meant for one thing silently
becomes a rule about three.
""")

code("""
description = describe(CRATE)
print(description)
""")

# ---------------------------------------------------------- 5 what you need

md("""
---

# 6. Draft the contract

The model is now asked for the contract, **one heading at a time** rather
than all at once.

**Why one at a time.** Asked for the whole contract in a single request on
12 November 2026, the model wrote 2 requirements from six headings of this
same text. Asked heading by heading, from the same crate and the same words,
it wrote 17. Each request is a smaller job: the model sees one heading, the
crate, and nothing else to balance against it.

**What the model is not allowed to do.** Its answer is held to a schema
while it generates. It cannot use a word outside the 5 permitted demands or
the 2 permitted severities, and it cannot name a type or a value that is not
in your crate, because those lists were read out of the crate in step 5.

Duration: approximately 40 seconds per heading with a graphics card, so
between 2 and 4 minutes in total. Four headings are asked about.
""")

code("""
contract, questions = draft(CRATE, NEEDS)

Path("my-contracts").mkdir(exist_ok=True)
DRAFT = Path("my-contracts/drafted.yaml")
DRAFT.write_text(yaml.safe_dump(contract, sort_keys=False, width=74,
                                default_flow_style=False, allow_unicode=True))

print(f"\\nwritten to {DRAFT}")
""")

md("""
### The draft, as a file

This is the contract itself. It is ordinary YAML, and in step 9 you edit it.
""")

code("""
print(DRAFT.read_text())
""")

# ------------------------------------------------------------- 7 the questions

md("""
---

# 7. What the model was unsure about

A model asked to turn English into rules has to resolve the places where the
English could mean more than one thing. Guessing produces a rule that looks
reasonable and refuses sound handovers. Asking takes you a few seconds.

**These questions are not answered automatically.** Read them, decide, and
make the change yourself in step 9. The most common one is the one the
warning in step 5 predicts: you wrote about one kind of thing, and the crate
gives that type to several different kinds of thing.
""")

code("""
if not questions:
    print("The model asked nothing. Read the draft anyway: no questions "
          "means it was confident, not that it was right.")
else:
    for number, question in enumerate(questions, start=1):
        print(f"{number}. about {question.get('about', 'the draft')}")
        print(textwrap.fill(question.get("question", ""), 72,
                            initial_indent="   ", subsequent_indent="   "))
        print()
""")

# ---------------------------------------------------------------- 8 the checks

md("""
---

# 8. Three checks on the draft

A drafted contract can be wrong in three ways, and they are not equally
visible. These checks make all three visible.

| Check | The question it answers | Why it matters |
|---|---|---|
| 1 | Does it parse? | A contract that does not parse cannot be used at all. The parser names the one fault it found |
| 2 | Can every rule ever fire? | A rule naming something the crate does not contain matches nothing and passes in silence. Silence reads as approval |
| 3 | Does it refuse the crate it was drafted from? | That crate is the one you supplied as an example of a sound handover. A contract that refuses it is too strict |

**Check 2 is the one nobody would think to do.** A contract made entirely of
rules that match nothing reports `ACCEPTED` on every crate forever, and
looks like a working contract while doing so. That is worse than having no
contract, because somebody is now relying on it.

**Check 3 does not prove the contract is right.** It proves it is not
obviously too strict. A contract with 1 rule in it passes all three checks
and is close to useless, which is why step 9 exists.
""")

code('''
def check(contract_file, folder):
    """The three checks, in order. Returns True if all three pass."""
    crate = Crate.from_path(folder)

    print("=" * 68)
    print("CHECK 1: does the contract parse")
    print("=" * 68)
    try:
        contract = parse(Path(contract_file).read_text(), Path(contract_file).name)
    except ContractError as fault:
        print(f"\\n  NO. It cannot be used as it stands.\\n\\n  {fault}\\n")
        print("  Fix that one fault in step 9 and run this again.")
        return False
    print(f"\\n  YES. {len(contract.requirements)} requirements, named "
          f"{contract.name} version {contract.version}.")

    print("\\n" + "=" * 68)
    print("CHECK 2: can every rule ever fire")
    print("=" * 68)

    def entities_of(kind):
        if kind == "root":
            return [crate.root]
        if kind == "descriptor":
            return [crate.descriptor]
        wanted = kind.split(":", 1)[1] if kind.startswith("type:") else kind
        return [e for e in crate if wanted in types_of(e)]

    def carries(entity, requirement):
        # The crate hands back mappingproxy objects rather than plain
        # dicts, and a mappingproxy is not an instance of dict, so testing
        # with isinstance(x, dict) here finds nothing at all.
        if requirement.property:
            return requirement.property in entity
        if requirement.named_value:
            for held in entity.get("additionalProperty", []) or []:
                named = crate.get(held.get("@id")) if hasattr(held, "get") else None
                if named and named.get("name") == requirement.named_value:
                    return True
            return False
        return True

    silent = []
    for requirement in contract.requirements:
        found = entities_of(requirement.applies_to)
        if not found:
            silent.append((requirement.name,
                           f"no entity of type {requirement.applies_to}"))
        elif requirement.must != "be recorded" and not any(
                carries(e, requirement) for e in found):
            # Only `be recorded` fires when the thing is absent. For the
            # other demands, an entity that does not carry it is simply not
            # checked, so the rule never has anything to say.
            looks_for = (requirement.property
                         or f"the value {requirement.named_value!r}")
            silent.append((requirement.name,
                           f"no {requirement.applies_to} carries {looks_for}"))

    if not silent:
        print(f"\\n  YES. All {len(contract.requirements)} rules look at "
              f"something in this crate.")
    else:
        print(f"\\n  NO. {len(silent)} of {len(contract.requirements)} rules "
              f"can never fire against this crate.\\n  They pass in silence, "
              f"which reads as approval:\\n")
        for name, why in silent:
            print(f"    {name}\\n        {why}")

    print("\\n" + "=" * 68)
    print("CHECK 3: does it refuse the crate it was drafted from")
    print("=" * 68)
    verdict, refusals, flags = run(contract_file, folder, quiet=True)
    print(f"\\n  verdict: {verdict}")
    print(f"  {len(refusals)} refusal(s), {len(flags)} flag(s)")

    if refusals:
        print("\\n  NO. This draft refuses the crate it was written for. Each "
              "refusal is\\n  either a rule that is wrong or a crate worse "
              "than it was assumed to be:\\n")
        for message, times in Counter(refusals).most_common(10):
            print(f"    {message[:78]}{f'  ({times} times)' if times > 1 else ''}")
    elif flags:
        print("\\n  YES, it accepts it, raising these flags:\\n")
        for message, times in Counter(flags).most_common(10):
            print(f"    {message[:78]}{f'  ({times} times)' if times > 1 else ''}")
        print("\\n  A flag raised dozens of times is usually one rule aimed "
              "at the wrong\\n  type rather than a crate with dozens of faults.")
    else:
        print("\\n  YES, it accepts it with nothing to report.")

    return not silent and not refusals


def run(contract_file, folder, quiet=False):
    """Put a crate through a contract, the way the rest of the world would.

    sentinel-oo is run as a program rather than called into, so what this
    prints is what anybody running the contract outside this notebook sees.
    """
    holding = Path("running"); shutil.rmtree(holding, ignore_errors=True)
    holding.mkdir()
    shutil.copy(contract_file, holding / Path(contract_file).name)
    name = parse(Path(contract_file).read_text()).name

    done = subprocess.run(
        [sys.executable, "-m", "sentinel_oo", folder, "--contracts", str(holding),
         "--contract", name, "--out", "checked", "--by", "the contract wizard"],
        capture_output=True, text=True)
    said = done.stdout + done.stderr
    if not quiet:
        print(said)

    found = re.search(r"verdict\\s+(\\w+)", said)
    return (found.group(1) if found else "could not be read",
            re.findall(r"^\\s*REFUSE\\s+(.*)$", said, re.M),
            re.findall(r"^\\s*FLAG\\s+(.*)$", said, re.M))
''', title="Define the three checks and how a crate is run through a contract. Prints nothing. Double click to read the code")

code("""
all_three_passed = check(DRAFT, CRATE)
""")

# ------------------------------------------------------------------- 9 edit it

md("""
---

# 9. Correct the draft

**This step is the point of the notebook.** The model wrote a first pass.
You decide what the contract says.

Four things are worth looking for, in this order.

1. **Anything check 2 named.** A rule that can never fire is doing nothing
   while appearing to do something. Either correct the name it uses or
   delete the rule.
2. **Anything check 3 refused.** The crate you supplied is a sound handover,
   so a refusal means the rule is too strict, usually because it names a
   type that covers more kinds of thing than you meant.
3. **The questions from step 7.** They are the places the model guessed.
4. **What is missing.** The model writes what the headings say and no more.
   A contract of 10 rules from six headings has almost certainly left
   something out.

**How to edit it.** The cell below puts the drafted contract into an editing
box, already filled in. Change what you want in the box, press **Save and
check**, and the three checks run again on what you saved. Press it as often
as you like: each press overwrites your copy of the contract and rechecks
it, and the original draft is left untouched in `my-contracts/drafted.yaml`.

**If no box appears**, which happens occasionally in Colab, use the file
browser instead. The folder icon on the left of the window opens it. Open
`my-contracts`, double click `drafted.yaml`, edit it in the pane that
appears, save it with Control and S, and then run the cell after the box.

**The whole vocabulary**, which is 5 demands and 2 severities and nothing
else:

| Field | What it may say |
|---|---|
| `applies_to` | a type name from step 5, or `root` for the crate itself |
| `property` or `named_value` | one or the other, never both |
| `must` | `be recorded`, `be unique`, `point at something in the crate`, `be a number between`, `hold data` |
| `severity` | `refuse` or `flag` |
| `message` | what a person reads when it fails |
| `repairable` | `true` permits a language model to propose a value when none is recorded |
""")

code('''
MINE = Path("my-contracts/mine.yaml")

# The box is filled with the draft rather than with a blank or a skeleton.
# Copying 60 lines of YAML out of printed output and pasting it into a cell
# is where indentation is lost and where people give up. The draft and the
# thing being edited should be the same object.
if not MINE.exists():
    shutil.copy(DRAFT, MINE)


def save_and_check(_=None):
    """Write what is in the box, then run the three checks on it."""
    said.clear_output()
    MINE.write_text(box.value)
    with said:
        print(f"saved to {MINE}, {len(box.value.splitlines())} lines\\n")
        check(MINE, CRATE)


# ipywidgets is what draws the box. Colab has it. Another machine may not,
# and a box that cannot be drawn should say so rather than stopping the
# notebook, because the file browser route works either way.
try:
    import ipywidgets as widgets
    from IPython.display import display
except ImportError:
    print("This machine has no ipywidgets, so there is no editing box here.")
    print(f"Edit {DRAFT} in the file browser instead, then run the next cell.")
else:
    box = widgets.Textarea(value=MINE.read_text(),
                           layout=widgets.Layout(width="100%", height="560px"))
    box.add_class("contract-editor")
    saving = widgets.Button(description="Save and check",
                            button_style="primary",
                            layout=widgets.Layout(width="180px"))
    said = widgets.Output()
    saving.on_click(save_and_check)

    display(widgets.HTML(
        "<style>.contract-editor textarea "
        "{font-family: monospace; font-size: 13px; line-height: 1.35;}</style>"))
    display(box, saving, said)
''', title="Build the editing box. Double click to read the code")

md("""
### If the editing box did not appear

Run this cell after editing `my-contracts/drafted.yaml` in the file browser.
It copies what you saved into your own contract and runs the three checks on
it. If the box above did work, this cell changes nothing and simply reports
the state of your contract.
""")

code('''
MINE = Path("my-contracts/mine.yaml")

# The file browser edits the draft itself, so what is in the draft is taken
# as the edited version unless the box above has already saved something
# newer.
if not MINE.exists() or DRAFT.stat().st_mtime > MINE.stat().st_mtime:
    shutil.copy(DRAFT, MINE)
    print(f"took {DRAFT} as your contract\\n")

check(MINE, CRATE)
''')


# --------------------------------------------------------- 10 use the contract

md("""
---

# 10. Put a handover through the contract you wrote

The checks in step 8 are about the contract. This step is the contract doing
its job: a crate arrives, and the contract says whether the receiving phase
can accept it.

This is the contract you have just written being used for what contracts
are for, rather than being inspected. Nobody opened a Python file to get
here.

The verdict is one of three words.

| Verdict | What it means |
|---|---|
| `ACCEPTED` | Every requirement passed. The receiving phase can proceed |
| `ACCEPTED_WITH_FLAGS` | Nothing that refuses failed, but something worth knowing was recorded. The receiving phase can proceed |
| `REFUSED` | At least one requirement with severity `refuse` failed. The handover stops here |

Whatever the verdict, the crate is given back with the check written inside
it, so the record travels with the data rather than living in a log file
somebody has to be told about.
""")

code("""
# The contract you edited in step 9, or the draft if you changed nothing.
FINAL = MINE if MINE.exists() else DRAFT
print(f"using {FINAL}\\n")

verdict, refusals, flags = run(FINAL, CRATE)
""")

md("""
### The same contract against a handover that is broken

A contract that accepts everything is indistinguishable from no contract at
all, so it is worth seeing one refuse.

This cell takes the crate you used, removes the name from every entity in
it, and sends it through the same contract.

**Removing names breaks more than it looks.** A named value is a small
entity holding a name and a value, and a rule finds it by that name. So
taking the names away does not only leave entities unnamed, it makes every
recorded measurement unfindable, which is what most rules are about. If the
contract has rules about named values, this is where they fire.

If the crate comes back accepted, that tells you something about the
contract rather than about the crate.
""")

code('''
BROKEN = Path("broken-crate")
shutil.rmtree(BROKEN, ignore_errors=True)
shutil.copytree(CRATE, BROKEN)

# One property is removed from every entity that has it: the name. Almost
# every contract has something to say about a thing with no name, and it is
# removable from any crate whatever the domain, which a named value is not.
metadata = json.loads((BROKEN / "ro-crate-metadata.json").read_text())
removed = 0
for entity in metadata["@graph"]:
    if entity.get("@id") not in ("./", "ro-crate-metadata.json") and "name" in entity:
        del entity["name"]
        removed += 1
(BROKEN / "ro-crate-metadata.json").write_text(json.dumps(metadata, indent=2))

print(f"removed the name from {removed} entities, then sent it through "
      f"the same contract\\n")
verdict, refusals, flags = run(DRAFT, BROKEN)
''')

# ------------------------------------------------------------- 11 take it away

md("""
---

# 11. Take the contract with you

A contract written in a notebook that disappears when the notebook closes is
of no use to anybody. This cell downloads it to your own computer.

The file downloaded is the one you edited in step 9, not the model's
original draft.

**What to do with it afterwards.** It is a plain text file of about 2
kilobytes. Put it in the repository that holds the handover it describes,
beside the code, under version control, so that a change to what a phase
requires is a change somebody can see and argue with. That is the argument
this tool rests on: a contract is a file, and nothing about adding a
handover requires writing Python.
""")

code("""
from google.colab import files

files.download(str(FINAL))
print(f"downloaded {FINAL.name}")
""")

# ------------------------------------------------------------------ afterwards

md("""
---

# Afterwards: nothing is left running

Everything in this notebook ran on the temporary machine Google gave it.
When you close the notebook, or when Colab reclaims the machine, all of it
goes: sentinel-oo, Ollama, the model, the crate and the contract. Nothing
was installed on your own computer and no account was charged.

The only thing that survives is the file you downloaded in step 11.

## What you have just done

**You wrote a contract without knowing the contract language.** The six
headings of step 3 were the only part that required any knowledge of the
handover, and they are written in ordinary English.

**The model never decided anything.** It proposed rules. Every rule was
checked three ways, every ambiguity it found came back as a question for a
person, and the one field that would let a model invent a value is never set
by the model.

**Where the draft was wrong, it was visible.** The checks exist because a
contract that quietly checks nothing is worse than no contract at all, and
it looks exactly like one that works.
""")


# ------------------------------------------------------------------- write it

notebook = {
    "cells": cells,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
        "accelerator": "GPU",
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

OUT.write_text(json.dumps(notebook, indent=1))
print(f"written: {OUT}")
print(f"{len(cells)} cells, {sum(1 for c in cells if c['cell_type'] == 'code')} "
      f"of them code")
