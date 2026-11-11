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
requirement at a time against the worked example that ships with the product,
and the output shown is the output you will get.

The worked example is a coating laboratory. Recipes are blended, applied to
metal panels held in numbered slots on a rack, dried, and their film
thickness measured in micrometres. It is deliberately not biology, so that
nothing in the product looks as if it belongs to somebody's use case.

## Step 1: look at what you have been given

```
python -m sentinel_oo --describe examples/coating-test/valid
```

It prints every entity type in the crate with a count, and the named values
hanging off each. **That is the list your contract has to match**, because a
requirement names a type and a value and both are compared as plain text.

That crate has 28 entities. The ones that matter for this tutorial are:

| Entity type | What it is | How many |
|---|---|---|
| `CoatingRecipe` | A recipe to be applied | 3 |
| `RackSlot` | A numbered position on the rack | 3 |
| `IntendedRackLayout` | The rack itself | 1 |
| `ThicknessReading` | A measurement | 3 |
| `DryingStep` | The process step that dried the panels | 1 |

## Step 2: ask the question, then write one requirement

**The question to ask about every requirement is: what does the receiving
phase do, and what goes wrong if this is missing?**

If a requirement has no answer to that, it is a preference rather than a
requirement. Preferences accumulate until a contract is too irritating to
use, and then people route around it, and then it protects nothing.

Here is one with an answer. If a slot has no position, nobody can find it on
the physical rack.

Make a folder and put this in it as `my_handover.yaml`:

```yaml
contract: my_handover
version: 0.1.0

requires:
  - name: slot_has_a_position
    applies_to: RackSlot
    property: name
    must: be recorded
    severity: refuse
    message: >-
      This slot has no position, so nobody can find it on the physical rack.
```

Run it:

```
SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/coating-test/valid \
  --contract my_handover
```

```
  28 entities in, 41 out
  verdict                                ACCEPTED
```

Every slot has a position, so it passes.

## Step 3: the trap, which you should walk into on purpose

Send it a crate from a completely different domain. One ships with the
product for exactly this purpose: a library catalogue, which has no slots,
no recipes and no drying step in it at all.

```
SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/from-another-phase \
  --contract my_handover
```

```
  verdict                                ACCEPTED
```

**It accepted a crate it knows nothing about.** Your requirement is about
`RackSlot`, that crate contains no `RackSlot`, so the requirement matched
nothing and passed.

The requirement is behaving correctly. A rule about a type should say nothing
about a crate with none of that type. The problem is the verdict drawn from
its silence.

**This is the worst thing the service can do**, and it is worth
understanding before you write anything else. Refusing something good is
visible and sends somebody to look. Blessing something unchecked is silent
and looks like success.

## Step 4: tell the contract what it is for

Add an `expects` block listing the entity types your contract is written for:

```yaml
contract: my_handover
version: 0.2.0

expects:
  - RackSlot

requires:
  - name: slot_has_a_position
    ...
```

Now run both crates again. These are the same two commands as in steps 2
and 3:

```
SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/coating-test/valid \
  --contract my_handover

SENTINEL_CONTRACTS=<your folder> \
  PYTHONPATH=src python -m sentinel_oo examples/from-another-phase \
  --contract my_handover
```

```
  the coating crate     ACCEPTED
  the other domain      REFUSED
                        REFUSE  nothing of type RackSlot is in this crate,
                                and the contract my_handover is written for
                                crates that contain it
```

**Write this block in every contract you ever write.**

## Step 5: build up the requirements about your own entities

**Raise the version number each time you change the contract**, from
`0.2.0` to `0.3.0` here, and once more at each of steps 6, 7 and 8. That is
what makes the printout at step 9 read `version 0.8.0`. The service does not
force this on you: it reads whatever number is in the file. It matters
because the version is copied into the lasting record inside every crate the
service checks, so a crate checked last month says which wording of the
contract it was checked against. Two different contracts sharing one version
number make those records untrustworthy.

Add the rest. Notice that references come in pairs: one requirement that the
reference is recorded at all, and a second that it lands on something real.
They are separate because one rule doing both would make one of them
impossible to say.

```yaml
expects:
  - RackSlot
  - CoatingRecipe
  - DryingStep

requires:
  - name: slot_has_a_position
    applies_to: RackSlot
    property: name
    must: be recorded
    severity: refuse
    message: >-
      This slot has no position, so nobody can find it on the physical rack.

  - name: one_slot_per_position
    applies_to: RackSlot
    property: name
    must: be unique
    severity: refuse
    message: >-
      Two slots claim the same position, so what is in that position is
      undefined.

  - name: slot_names_a_recipe
    applies_to: RackSlot
    property: mainEntity
    must: be recorded
    severity: refuse
    message: >-
      This slot does not say which recipe goes on it.

  - name: slot_names_a_real_recipe
    applies_to: RackSlot
    property: mainEntity
    must: point at something in the crate
    of_type: CoatingRecipe
    severity: refuse
    message: >-
      This slot names something that is not a recipe in this crate.
```

## Step 6: a flag rather than a refusal

Not everything should stop a handover. The coating line cannot run below 5
micrometres or above 500 micrometres, where a micrometre is one thousandth of
a millimetre. But a recipe outside that range may be intended for a different
line, which is a judgment for a person rather than a reason to stop.

```yaml
  - name: recipe_thickness_is_in_range
    applies_to: CoatingRecipe
    named_value: film thickness
    must: be a number between
    between: [5, 500]
    severity: flag
    message: >-
      This recipe's film thickness, in micrometres, is outside what the
      coating line can run, which is 5 to 500 micrometres.
```

`severity: refuse` stops the handover. `severity: flag` records the finding
and lets it through. There is nothing in between, on purpose: a severity
nobody can act on is a severity nobody reads.

**State the units in every message.** The contract has no field for them, and
a number with no unit in a finding is an invitation to compare a thickness
against a temperature.

## Step 7: a value a model may be asked to recover

```yaml
  - name: drying_atmosphere_is_recorded
    applies_to: DryingStep
    named_value: drying atmosphere
    must: be recorded
    repairable: true
    severity: refuse
    message: >-
      The drying step does not say what atmosphere it ran in, so these
      thickness readings cannot be compared with each other.
```

`repairable: true` means a model is asked one question when this fails: is
the value already written down somewhere in the record, including inside
free text? Everything it answers is checked by your rules before it counts,
which is what makes having it on safe. A model runs in its own container
and is called by default.

Now run all five example crates. Each is a separate command, the same shape
as before, with the crate folder changed:

```
for crate in coating-test/valid \
             coating-test/invalid/missing-conformsto \
             coating-test/invalid/dangling-reference \
             coating-test/invalid/missing-atmosphere \
             coating-test/invalid/atmosphere-in-prose
do
  SENTINEL_CONTRACTS=<your folder> \
    PYTHONPATH=src python -m sentinel_oo examples/$crate \
    --contract my_handover
done
```

**With no model reachable**, which is what you get if you have not set one
up, all five come back like this:

```
  valid                          ACCEPTED
  invalid/missing-conformsto     ACCEPTED
  invalid/dangling-reference     ACCEPTED
  invalid/missing-atmosphere     REFUSED
  invalid/atmosphere-in-prose    REFUSED
```

**With a model reachable**, the last line changes, and that change is the
whole point of this step:

```
  invalid/atmosphere-in-prose    ACCEPTED_WITH_FLAGS

  FLAG  The drying atmosphere was not recorded on this entity. The value
        'dry' was recovered from the text already in the crate by
        qwen2.5:14b, and confirmed by the requirement
        drying_atmosphere_is_recorded. A value somebody wrote down and a
        value something read out of prose are not equally trustworthy, so
        somebody should check it and ask the producing step to record it
        properly.
         at #act-drying
```

That crate does not record the drying atmosphere as a value, but the word
is sitting in the text of a command inside it, written as
`dryer --panels rack-A1 --atmosphere dry --hold 20 -q`. The model was asked
one question, found `dry`, proposed it, and your own requirement checked the
proposal before it was kept.

`invalid/missing-atmosphere` stays `REFUSED` with a model, because in that
crate the atmosphere is not written anywhere at all. Nothing is invented.

**The verdict is `ACCEPTED_WITH_FLAGS` rather than `ACCEPTED` on purpose.**
The handover goes through. The flag is there because the crate itself
records that this value was read out of prose rather than stated outright,
and because the team producing the handover should know their step is
leaving out something a model had to go and find.

## Step 8: the second lesson

Two broken crates were accepted. **A contract catches only what it asks
about**, and yours asks nothing about the packaging: whether the crate says
which profile it follows, or whether it lists files it never describes.

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
```

`applies_to: root` means the entity describing the crate as a whole.

With no model reachable:

```
  valid                          ACCEPTED
  invalid/missing-conformsto     REFUSED
  invalid/dangling-reference     REFUSED
  invalid/missing-atmosphere     REFUSED
  invalid/atmosphere-in-prose    REFUSED
```

With a model reachable, `invalid/atmosphere-in-prose` is
`ACCEPTED_WITH_FLAGS` instead, for the reason given in step 7. The other
four are unchanged: a model is only ever asked about a requirement marked
`repairable: true`, and only the drying atmosphere is marked that way.

And a refusal reads like this:

```
  verdict                                REFUSED

  REFUSE  The crate lists a file as part of itself that is described
          nowhere in it. Whoever receives this will look for it and not
          find it.
         at ./
```

The sentence is yours. Write the message you would want to receive at four
o'clock on a Friday.

## Step 9: read your contract back in plain words

```
PYTHONPATH=src python -m sentinel_oo --show-contract my_handover
```

```
my_handover version 0.8.0

It is for crates containing all of: RackSlot, CoatingRecipe, DryingStep
A crate containing none of those is refused rather than accepted without
being checked.

8 requirement(s):

  declares_a_profile
    root must record conformsTo
    failing it refuses the handover
    The crate does not say which profile it follows, so nothing can be
    agreed about what its contents mean.
  ...
```

**This is what you send to the team that produces the handover**, so they
can check themselves before they are checked. It is not YAML and they do not
need to read YAML.

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

For the `missing-atmosphere` crate and the contract built in this tutorial,
that prints (the sentence is one long line in the terminal; it is wrapped
here to fit the page):

```
REFUSED
  drying_atmosphere_is_recorded | The drying step does not say what
      atmosphere it ran in, so nobody can tell whether these thickness
      readings are comparable with each other.
```

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
crate says `CoatingRecipe` and your contract says `Recipe`, the requirement
matches nothing and passes.

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
