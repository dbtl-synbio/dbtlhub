# sentinel-oo: user manual

How to put a checking service at one of your own handovers. You will write
contract files and run one command. You will not write any code.

**This manual is in three files.** This one is the front door and the
tutorial. The other two are reference:

| File | What it is for |
|---|---|
| This file | Start here. A tutorial that builds a contract from nothing |
| [WRITING_A_CONTRACT.md](WRITING_A_CONTRACT.md) | The contract language, field by field |
| [DEPLOYING.md](DEPLOYING.md) | The deployment program, option by option |

If you want to know how the system is built rather than how to use it, read
[the system manual](SYSTEM_MANUAL.md).

---

## What you will end up with

A service running in a container that you send a handover to and get a
verdict back from, plus the handover itself with a record of what was checked
written inside it.

A **handover** is the moment one phase of work passes its output to the next.
A **crate** is how that output travels: an RO-Crate, which is a folder of
data files with a JSON file alongside them describing what each file is and
how the things in it relate to one another.

### The three verdicts

| Verdict | What it means |
|---|---|
| `ACCEPTED` | Nothing was found |
| `ACCEPTED_WITH_FLAGS` | Nothing stops the handover, but something was recorded for somebody to look at. A value a model recovered from the crate's own text always lands here |
| `REFUSED` | At least one requirement with severity `refuse` was violated |

### What makes your instance yours

A folder of contract files, mounted into an image nobody modified. That is
the whole of the tailoring.

---

## Before you start

You need Docker, and a crate to try it on. If you have no crate of your own
yet, use the worked example that ships with the product, which is what this
tutorial does.

Everything below is run from the `sentinel-oo` folder.

---

# Part 1: a tutorial

**You can run every command here.** The tutorial builds a contract one
requirement at a time against the worked example that ships with the
product, and the output shown is the output you will get.

## The worked example

It is a handover from the Design phase to the Build phase of a
bioprospecting cycle. Bioprospecting means searching genomes and metagenomes
for enzymes that might be useful industrially.

The Design phase finishes with a panel of candidate proteins chosen from a
metagenome, a synthetic gene designed for each one, and a plate layout
saying which well each gene goes into. The Build phase orders those genes
from a synthesis company and spends money, so anything Build cannot judge
from the crate is a well that may be wasted.

**Nothing in the service knows what a protein or a plate is.** Every type
name and value name below comes out of the contract file and the crate. The
same image, unmodified, checks a coating line or a chemical plant.

All the sequence data in the example is simulated, and each sequence says so
in its own line.

## Step 1: look at what you have been given

```
python -m sentinel_oo --describe examples/plate-test/valid
```

It prints every entity type in the crate with a count, and the named values
hanging off each. **That is the list your contract has to match**, because a
requirement names a type and a value and both are compared as plain text.

That crate has 109 entities. The ones this tutorial uses are:

| Entity type | What it is | How many |
|---|---|---|
| `PlateWell` | One numbered position on the plate | 4 |
| `ExpressionConstruct` | A synthetic gene designed for one protein | 4 |
| `Protein` | A candidate enzyme found in the metagenome | 4 |
| `IntendedPlateLayout` | The plate itself | 1 |
| `GeneCallingStep` | The step that predicted genes in the assembled DNA | 1 |
| `File` | A file the crate names, carried or elsewhere | 11 |

## Step 2: ask the question, then write one requirement

**The question to ask about every requirement is: what does the receiving
phase do, and what goes wrong if this is missing?**

If a requirement has no answer to that, it is a preference rather than a
requirement. Preferences accumulate until a contract is too irritating to
use, and then people route around it, and then it protects nothing.

Here is one with an answer. If a well has no position, nobody can find it on
the physical plate.

Make a folder and put this in it as `my_handover.yaml`:

```yaml
contract: my_handover
version: 0.1.0

requires:
  - name: well_has_a_position
    applies_to: PlateWell
    property: name
    must: be recorded
    severity: refuse
    message: >-
      This well has no position, so nobody can find it on the physical plate.
```

Run it:

```
SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/plate-test/valid \
  --contract my_handover
```

```
  109 entities in, 122 out
  verdict                                ACCEPTED
```

Every well has a position, so it passes. The crate goes in with 109 entities
and comes out with 122, because the service wrote the record of this check
into it.

## Step 3: the trap, which you should walk into on purpose

Send it a crate from a completely different domain. One ships with the
product for exactly this purpose: a library catalogue, which has no wells,
no constructs and no gene calling step in it at all.

```
SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/from-another-phase \
  --contract my_handover
```

```
  9 entities in, 22 out
  verdict                                ACCEPTED
```

**It accepted a crate it knows nothing about.** Your requirement is about
`PlateWell`, that crate contains no `PlateWell`, so the requirement matched
nothing and passed.

The requirement is behaving correctly. A rule about a type should say
nothing about a crate with none of that type. The problem is the verdict
drawn from its silence.

**This is the worst thing the service can do**, and it is worth
understanding before you write anything else. Refusing something good is
visible and sends somebody to look. Blessing something unchecked is silent
and looks like success.

## Step 4: tell the contract what it is for

Add an `expects` block listing the entity types your contract is written
for:

```yaml
contract: my_handover
version: 0.2.0

expects:
  - PlateWell

requires:
  - name: well_has_a_position
    ...
```

Now run both crates again. These are the same two commands as in steps 2
and 3:

```
SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/plate-test/valid \
  --contract my_handover

SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/from-another-phase \
  --contract my_handover
```

```
  the plate crate       ACCEPTED
  the other domain      REFUSED
                        REFUSE  nothing of type PlateWell is in this crate,
                                and the contract my_handover is written for
                                crates that contain it
```

**Write this block in every contract you ever write.**

## Step 5: build up the requirements about your own entities

**Raise the version number each time you change the contract**, from `0.2.0`
to `0.3.0` here, and once more at each of steps 6, 7 and 8. That is what
makes the printout at step 9 read `version 0.6.0`. The service does not
force this on you: it reads whatever number is in the file. It matters
because the version is copied into the lasting record inside every crate the
service checks, so a crate checked last month says which wording of the
contract it was checked against.

Add the rest. Notice that references come in pairs: one requirement that the
reference is recorded at all, and a second that it lands on something real.
They are separate because one rule doing both would make one of them
impossible to say.

```yaml
expects:
  - PlateWell
  - ExpressionConstruct

requires:

  - name: well_has_a_position
    ...

  - name: one_well_per_position
    applies_to: PlateWell
    property: name
    must: be unique
    severity: refuse
    message: >-
      Two wells claim the same position on the plate, so what is physically
      in that position is undefined.

  - name: well_names_a_construct
    applies_to: PlateWell
    property: mainEntity
    must: be recorded
    severity: refuse
    message: >-
      This well does not say which construct is meant to go in it, so nothing
      measured from it later can be attributed to a sequence.

  - name: well_names_a_real_construct
    applies_to: PlateWell
    property: mainEntity
    must: point at something in the crate
    of_type: ExpressionConstruct
    severity: refuse
    message: >-
      This well names something that is not a construct in this crate, so
      whatever is in it cannot be identified.
```

Run the valid crate and two of the broken ones:

```
  valid                          ACCEPTED
  invalid/dangling-reference     ACCEPTED
  invalid/missing-conformsto     ACCEPTED
```

Two broken crates passed. Hold that thought until step 8.

## Step 6: a flag rather than a refusal

Not everything worth saying should stop a handover. `severity: flag` records
a finding and lets the crate through.

```yaml
  - name: construct_length_is_plausible
    applies_to: ExpressionConstruct
    named_value: coding sequence length
    must: be a number between
    between: [300, 3000]
    severity: flag
    message: >-
      This construct's coding sequence length, in base pairs, is outside the
      range a single bacterial enzyme usually falls in, which is 300 to 3000
      base pairs.
```

`named_value` rather than `property`. A property sits directly on an entity.
A named value is a separate entity carrying a name and a value, which the
first one points at. Crates following the Process Run Crate profile record
most numbers that way, and the four constructs here are 1053, 1080, 1101 and
1179 base pairs.

The valid crate still comes back `ACCEPTED`, because all four are in range.
A crate with one construct of 41000 base pairs comes back like this:

```
  verdict                                ACCEPTED_WITH_FLAGS

  FLAG  This construct's coding sequence length, in base pairs, is outside
        the range a single bacterial enzyme usually falls in, which is 300
        to 3000 base pairs.
```

The handover is not stopped. Somebody is told.

## Step 7: a value a model may be asked to recover

```yaml
expects:
  - PlateWell
  - ExpressionConstruct
  - GeneCallingStep

requires:
  ...

  - name: edge_handling_is_recorded
    applies_to: GeneCallingStep
    named_value: edge handling
    must: be recorded
    repairable: true
    severity: refuse
    message: >-
      The gene calling step does not say how it treated the edges of contigs,
      so nobody can tell whether any sequence in this panel may be a fragment.

  - name: edge_handling_is_closed
    applies_to: GeneCallingStep
    named_value: edge handling
    must: be recorded
    one_of: ["closed"]
    severity: refuse
    message: >-
      This contract is written for a panel called with closed ends. A panel
      called any other way may contain fragments, and needs a contract that
      says what to do about them.
```

**What edge handling is.** Gene calling means running a program over
assembled DNA to predict where the protein-coding genes are. When a
predicted gene runs off the end of a DNA fragment, the program either keeps
the partial gene or refuses to call it. `closed` means the second. It
matters to the Build phase because a partial gene ordered as a construct
makes a protein that is missing one end.

`repairable: true` means a model is asked one question when this fails: is
the value already written down somewhere in the record, including inside
free text? Everything it answers is checked by your rules before it counts,
which is what makes having it on safe. A model runs in its own container and
is called by default.

**With no model reachable**, which is what you get if you have not set one
up:

```
  valid                                ACCEPTED
  invalid/missing-gene-calling-mode    REFUSED
  invalid/edge-handling-in-prose       REFUSED
  invalid/mode-in-prose                REFUSED
```

**With a model reachable**, one of those three changes:

```
  invalid/edge-handling-in-prose       ACCEPTED_WITH_FLAGS

  FLAG  The edge handling was not recorded on this entity. The value
        'closed' was recovered from the text already in the crate by
        qwen2.5:14b, and confirmed by the requirement
        edge_handling_is_recorded.
```

In that crate the gene calling step's description says, in ordinary words,
"contig edges were treated as closed, so no partial genes were kept". The
model was asked one question, read that sentence, proposed `closed`, and
your own requirement checked the proposal before it was kept. On a laptop
that run took about 9 seconds.

**The other two do not change, and that is the point.**

In `missing-gene-calling-mode` the value is not in the crate at all, so
there is nothing to find and nothing is invented.

In `mode-in-prose` the value is in the crate, but only as the flag `-c`
inside the command line `prodigal -i contigs.fasta -a proteins.faa -p meta
-c -q`. Recovering it means knowing what that program's flags mean. Two
models of 14 billion parameters each were asked to do exactly that on
10 November 2026, and both stated a wrong meaning without hedging. Your
rules threw the answer out, the crate stayed refused, and nothing was
written.

So the model helps when the value is in the text in words, and fails safely
when it is not.

## Step 8: the second lesson

Two broken crates were accepted back at step 5. **A contract catches only
what it asks about**, and yours asks nothing about the packaging: whether
the crate says which profile it follows, whether it lists files it never
describes, or whether the files it carries hold anything.

Add those:

```yaml
  - name: declares_a_profile
    applies_to: root
    property: conformsTo
    must: be recorded
    severity: refuse
    message: >-
      The crate does not say which profile it follows, so nothing can be
      agreed about what its contents mean.

  - name: everything_the_crate_lists_is_present
    applies_to: root
    property: hasPart
    must: point at something in the crate
    severity: refuse
    message: >-
      The crate lists a file as part of itself that is described nowhere in
      it. Whoever receives this will look for it and not find it.

  - name: every_file_holds_data
    applies_to: File
    must: hold data
    severity: refuse
    message: >-
      This file is named in the crate and holds nothing, so the step that was
      meant to produce it produced no data.
```

`applies_to: root` means the entity describing the crate as a whole.

`hold data` opens the files themselves rather than reading the description.
A file named by a web address is left alone, because the crate does not
carry it.

With no model reachable, all six example crates now give this:

```
  valid                                ACCEPTED
  invalid/dangling-reference           REFUSED
  invalid/missing-conformsto           REFUSED
  invalid/missing-gene-calling-mode    REFUSED
  invalid/mode-in-prose                REFUSED
  invalid/edge-handling-in-prose       REFUSED
```

With a model reachable, `invalid/edge-handling-in-prose` is
`ACCEPTED_WITH_FLAGS` instead, for the reason given in step 7.

And a refusal reads like this:

```
  verdict                                REFUSED

  REFUSE  The crate lists a file as part of itself that is described
          nowhere in it. Whoever receives this will look for it and not
          find it.
         at ./
```

Every sentence in that came from your contract file, not from the code.

## Step 9: read your contract back in plain words

```
PYTHONPATH=src python -m sentinel_oo --show-contract my_handover
```

```
my_handover version 0.6.0

It is for crates containing all of: PlateWell, ExpressionConstruct,
GeneCallingStep
Each one that is missing is refused on its own, because a crate without it
cannot be checked by the requirements about it.

10 requirement(s):

  well_has_a_position
    PlateWell must record name
    failing it refuses the handover
    This well has no position, so nobody can find it on the physical plate.

  ...
```

**This is what you send to the team that produces the handover**, so they
can check themselves before they are checked. It ends with a short
explanation of each RO-Crate word it used, and it marks any requirement a
model may help with.

## Step 10: deploy it

```
python deploy.py <your folder of contracts>
```

That validates your contracts and refuses before building anything, builds
the generic image, starts an instance with your folder mounted read only,
and then confirms the running instance is serving exactly what it validated.

Then send it a crate. There are two ways, and they do different things.

**The whole crate, zipped. This is the one to use.** The service sends the
checked crate back, which is the copy carrying the record of the check and
the copy the next step in your workflow should receive. It is also the only
way a requirement using the `hold data` verb can be answered, because that
verb looks at the data files themselves.

```
cd <a crate> && zip -qr /tmp/crate.zip . && cd -

curl -s -D - -o /tmp/checked.zip \
  -X POST -H "Content-Type: application/zip" \
  --data-binary @/tmp/crate.zip \
  http://127.0.0.1:8080/check/my_handover
```

`-D -` prints the headers, which is where the verdict is, and `-o` saves the
returned crate rather than printing a zip file into your terminal:

```
HTTP/1.1 200 OK
Content-Type: application/zip
Content-Disposition: attachment; filename="checked-ac7326ea4fb4.zip"
X-Sentinel-Run: ac7326ea4fb4
X-Sentinel-Verdict: REFUSED
X-Sentinel-Findings: 2
```

`HTTP/1.1 200 OK` means the service answered, not that the crate was
accepted. The verdict is the `X-Sentinel-Verdict` line, and it is one of
`ACCEPTED`, `ACCEPTED_WITH_FLAGS` or `REFUSED`. The reasons are inside the
returned crate, in the record the service wrote into it.

**The description file on its own.** Quicker, and useful while you are
still writing the contract, but nothing comes back except a report, and any
requirement about the data files is refused because they were not sent.

```
curl -s -X POST --data-binary @<a crate>/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/my_handover
```

That reply is JSON, and it is long: about 18 kilobytes for the small
example crate, because it includes the whole checked description. Run as
written it fills your terminal. Pick the verdict out of it instead:

```
curl -s -X POST --data-binary @<a crate>/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/my_handover \
  | python -c "import json,sys
r = json.load(sys.stdin)
print(r['verdict'])
for f in r['findings']:
    print(' ', f['requirement'], '|', f['message'])"
```

For the `missing-gene-calling-mode` crate and the contract built in this
tutorial, that prints (each sentence is one long line in the terminal; they
are wrapped here to fit the page):

```
REFUSED
  edge_handling_is_recorded | The gene calling step does not say how it
      treated the edges of contigs, so nobody can tell whether any sequence
      in this panel may be a fragment.
  edge_handling_is_closed | This contract is written for a panel called
      with closed ends. A panel called any other way may contain fragments,
      and needs a contract that says what to do about them.
  every_file_holds_data | The data file 'panel.faa' was not sent, so
      whether it holds anything could not be checked, and a check that
      could not run is refused rather than passed. Send the whole crate as
      a zip rather than ro-crate-metadata.json on its own.
  every_file_holds_data | ... the same for constructs.json
  every_file_holds_data | ... and for plate-layout.csv
```

The last three are there because only the description file was posted. The
three files the crate carries never arrived, so the requirement that they
hold data could not be answered, and a check that could not run is refused
rather than passed. Send the whole crate as a zip and those three go away.
The eight files the crate names by web address are not mentioned at all,
because the crate was never carrying them.

The reply has four fields: `run`, a twelve character identifier for this
check; `verdict`; `findings`, one entry per requirement that failed, each
naming the requirement, which entity failed it, and the contract author's
sentence; and `crate`, the whole checked description.

Full details in [DEPLOYING.md](DEPLOYING.md) and
[API_MANUAL.md](API_MANUAL.md).

---

# Part 2: the contract language

Every field, all five verbs, and the three things the language cannot say
yet: [WRITING_A_CONTRACT.md](WRITING_A_CONTRACT.md).

The five verbs are the whole vocabulary:

| Verb | What it demands |
|---|---|
| `be recorded` | The value is present and not empty |
| `be unique` | No two entities of this type share it |
| `point at something in the crate` | The reference resolves to something described here |
| `be a number between` | It is a number, within a range |
| `hold data` | The file this entity describes is really in the crate and is not empty |

**You cannot add a sixth by writing a contract.** If you need one, you will
get a message naming the five that exist and saying where a sixth would be
added, and you are blocked until somebody adds it to the product.

---

# Part 3: deploying

[DEPLOYING.md](DEPLOYING.md) covers the deployment program, its options,
running more than one instance, and the interface for a coordinating agent.

---

# Part 4: when something goes wrong

| What you see | What it means |
|---|---|
| `does not understand ['propery']` | A misspelt field. The message lists every field a requirement may have |
| `says 'be greater than', which is not something a requirement can demand` | A verb that does not exist. The message lists the four that do |
| `has no message` | Every requirement needs a sentence a person can read |
| `has severity 'warn'` | It is `refuse` or `flag`, and nothing else |
| `says 'be a number between' but does not say between` | That verb needs a `between: [low, high]` |
| `must say either property, for something written on the entity itself, or named_value` | A requirement reads one or the other, never both and never neither |
| `two files define the contract 'x'` | Two files in your folder declare the same contract name. The name inside the file is what matters, not the file name |
| `no contract called 'x'. This service knows: none at all.` | Nothing was mounted at `/contracts`, or the wrong folder was |
| `the running instance is not serving the contracts that were validated` | Usually the wrong folder being mounted. The message names what it expected and what it found |

**Everything is refused loudly rather than ignored.** A contract containing
something the reader does not understand is rejected whole, because a
silently ignored requirement is a requirement you believe is protecting you.

### It accepted something I expected it to refuse

Three usual causes:

**Your contract does not ask about it.** A contract catches only what it
asks about. Step 8 of the tutorial is this mistake.

**The type name does not match.** Types are compared as plain text, and
nothing knows that schema.org considers one type a kind of another. If your
crate says `ExpressionConstruct` and your contract says `Construct`, the
requirement matches nothing and passes.

**You have no `expects` block.** Run `--show-contract`. If it warns that the
contract does not say what it is for, that is the cause.

---

# Part 5: before you rely on it

A checklist. Each line is a mistake somebody has actually made.

- [ ] Every contract has an `expects` block listing the types it is for
- [ ] Every reference has a pair: one requirement that it is recorded, one that it lands on something real
- [ ] Every message is a sentence you would want to receive, and states units for every number
- [ ] Every requirement answers "what does the next phase do, and what goes wrong if this is missing?"
- [ ] You have run it against a crate you know is good **and** a copy you have deliberately broken
- [ ] `--show-contract` reads correctly to somebody who has never seen YAML
- [ ] You have sent that plain-words version to the team producing the handover
- [ ] `be unique` is only used where duplication really is wrong in your laboratory, not where it is how a replicate or a control is included

**A contract that accepts everything is the same as no contract.** The only
way to know yours is doing something is to watch it refuse something.
