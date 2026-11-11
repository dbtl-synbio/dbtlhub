# Writing a contract

This is the whole of what you need in order to tailor `sentinel-oo` to your
own handover. You will not write any code.

Read [the worked example](../examples/README.md) alongside this. It is 2
contract files and 5 crates, and it is short on purpose.

## What a contract is

A handover is the moment one phase of work passes its output to the next. A
contract is a file saying what must be true of that output before the next
phase can act on it.

The service reads your contract, checks a crate against it, and returns one
of three verdicts: ACCEPTED, ACCEPTED_WITH_FLAGS, or REFUSED. The middle one
means nothing stopped the handover but something was recorded for a person or
a later step to look at. A crate here means an RO-Crate: a
folder of data files with a JSON file alongside them describing what each
file is and how the things in it relate to each other.

**What a contract is not.** It is not a schema, because it does not say what
shape the data must have. It is not a validator, because a third party
validator already checks that the packaging is well formed. It is not a set
of instructions to a model: there is no field for that, deliberately, and the
reader refuses a file that invents one.

## The one question to ask about every requirement

**What does the receiving phase do, and what goes wrong if this is missing?**

If a requirement has no answer to that, it is a preference rather than a
requirement. Preferences accumulate until a contract is too irritating to
use, and then people route around it, and then it protects nothing.

## The shape of the file

```yaml
contract: mixing_to_coating
version: 1.1.0

description: >
  What Mixing must hand to Coating, and why each item matters.

expects:
  - CoatingRecipe
  - RackSlot

requires:
  - name: declares_a_profile
    applies_to: root
    property: conformsTo
    must: be recorded
    severity: refuse
    message: >-
      The crate does not say which profile it follows, so nothing can be
      agreed about what its contents mean.
```

Five top level keys and nothing else: `contract`, `version`, `description`,
`expects`, `requires`. The name in `contract` is how callers ask for it, as
in `POST /check/mixing_to_coating`. The file name does not matter; this name
does.

## `expects`: what your contract is for

**Write this block. A contract without one accepts crates it has not
checked.**

`expects` lists the entity types your contract is written for. If any of
them is absent from the crate, the handover is refused before a single
requirement is applied, and the message names the type that is missing.

```yaml
expects:
  - CoatingRecipe
  - RackSlot
  - IntendedRackLayout
  - ThicknessReading
  - DryingStep
```

### Why it is not optional in practice

A requirement about a type says nothing about a crate containing none of
that type, and it should not, because presence and soundness are separate
things. Each requirement is behaving correctly. The problem is what happens
when you add them up.

This was measured on 11 November 2026. A crate from an unrelated domain was
posted to a contract of 18 requirements. The result was ACCEPTED with 0
findings:

| Of the 18 requirements | Count |
|---|---|
| Looked at something in that crate | 6 |
| Matched no entity at all, and passed | 12 |

The 12 were every requirement naming a type the crate did not contain. So
the service said ACCEPTED on a crate it had not meaningfully read.

**That is the worst thing this service can do.** Refusing something good is
visible and sends somebody to look. Blessing something unchecked is silent
and looks like success. A handover from the wrong phase, or a crate in which
one type name has been changed or misspelt, would come back accepted.

### Why you choose the list rather than the service inferring it

The service could gather every type your requirements mention and demand all
of them. It does not, because a contract may legitimately carry requirements
about entity types that are optional, and only you know which of yours must
be present. Inferring it would turn optional things into mandatory ones
without asking.

So list the types whose absence means this crate is not the handover your
contract is about.

## Every field of a requirement

| Field | Required? | What it does |
|---|---|---|
| `name` | Yes | How this requirement is referred to in a finding. Use words, not numbers |
| `applies_to` | Yes | Which entities it looks at |
| `property` | One of these two | A property written directly on the entity |
| `named_value` | One of these two | A value hanging off the entity as a separate entity |
| `must` | Yes | What it demands. One of exactly four things |
| `severity` | Yes | `refuse` or `flag` |
| `message` | Yes | The sentence a person reads when it is violated |
| `one_of` | No | The only values that mean anything |
| `of_type` | No | Narrows a reference to one kind of thing |
| `between` | Only with the range verb | Two numbers, lowest first |
| `repairable` | No | Whether a model may be asked to recover the value |

A requirement must say either `property` or `named_value`, never both and
never neither.

## `applies_to`: where it looks

Three possibilities.

**`root`** is the entity describing the crate as a whole. Use it for things
true of the package: its name, its licence, which profile it follows, the
list of files it claims to contain.

**`descriptor`** is the entity describing the metadata file itself. You will
rarely want it.

**Anything else is read as a type**, so `applies_to: CoatingRecipe` means
every entity in the crate that says it is a `CoatingRecipe`. You may write
`type:CoatingRecipe` if you want to be explicit.

A type here means either the entity's `@type` or its `additionalType`. The
second matters in practice: RO-Crate's vocabulary has no term for a coating
recipe, so the worked example types those entities as `CreativeWork` with
`additionalType: CoatingRecipe`, and a requirement can then name them.

**A limitation worth knowing before you rely on it.** Types are compared as
plain text. Nothing in the service knows that schema.org considers a `Hotel`
to be a kind of `LodgingBusiness`, so a requirement asking for one will not
accept the other. If your crate uses a specific type and your contract names
a general one, the requirement will match nothing and pass silently.

## `property` or `named_value`: what it reads

**`property`** reads something written on the entity itself:

```yaml
    applies_to: RackSlot
    property: name
```

**`named_value`** reads a value hanging off the entity as a separate entity
of its own:

```yaml
    applies_to: CoatingRecipe
    named_value: film thickness
```

Both exist because crates following the Process Run Crate profile record most
numbers and strings the second way. The film thickness is not written on the
recipe. It is a separate entity carrying the name `film thickness` and the
value `42`, which the recipe points at.

**You do not have to say which property carries the reference.** Every
reference the entity makes is followed, and only entities of type
`PropertyValue` are read as values. So a step that points at a file, a tool
and a setting will give up only the setting, and a file that happens to have
a name is not mistaken for a value.

## `must`: the five verbs

This is the whole vocabulary. It is deliberately short, and it grows one
entry at a time, because a language that can say anything can also say things
nobody can check.

**You cannot add a verb by writing a contract.** If your requirement needs
one these five cannot express, you will get a message naming the five that
exist, and you are blocked until a sixth is added to the product. That means
editing `MUSTS` in `src/sentinel_oo/contract.py`, adding a branch to
`_apply` in `src/sentinel_oo/rules.py`, and writing tests for both. It is the
one case where tailoring is not enough, and it is a change somebody has to
agree to rather than something you can do in your own folder.

### `be recorded`

The value must be present and not empty.

```yaml
  - name: slot_has_a_position
    applies_to: RackSlot
    property: name
    must: be recorded
    severity: refuse
    message: >-
      This slot has no position, so nobody can find it on the physical rack.
```

**This is the only verb that fires when the value is absent.** The others
have nothing to say about something that is not there, because "it must be
present" and "it must be sound" are two separate requirements. A rule doing
both would make one of them impossible to say.

So presence and soundness come in pairs. Write both.

### `be unique`

No two entities of this type may share this value.

```yaml
  - name: one_slot_per_position
    applies_to: RackSlot
    property: name
    must: be unique
    severity: refuse
    message: >-
      Two slots claim the same position on the rack, so what is physically in
      that position is undefined.
```

**Think about whether duplication is actually wrong in your laboratory.** Two
slots holding the same recipe is a normal thing to do elsewhere: it is how a
replicate or a control is included. A check that fires on correct practice is
worse than no check. If replicates are normal for you, use `severity: flag`
or leave the requirement out.

### `point at something in the crate`

The reference must resolve to an entity the crate describes.

```yaml
  - name: slot_names_a_real_recipe
    applies_to: RackSlot
    property: mainEntity
    must: point at something in the crate
    of_type: CoatingRecipe
    severity: refuse
    message: >-
      This slot names something that is not a recipe in this crate, so
      whatever is on it cannot be identified.
```

With `of_type`, the thing it lands on must also be of that type. Without it,
anything in the crate will do.

A reference that points outside the crate, to a URL somewhere, counts as not
resolving. That is the point: a crate that refers to things it does not carry
or describe cannot be acted on by somebody who only has the crate.

### `be a number between`

The value must be a number, and within the range.

```yaml
  - name: recipe_thickness_is_in_range
    applies_to: CoatingRecipe
    named_value: film thickness
    must: be a number between
    between: [5, 500]
    severity: flag
    message: >-
      This recipe's specified film thickness, in micrometres, is outside what
      the coating line can run, which is 5 to 500 micrometres.
```

`between` takes two numbers, lowest first, and the range includes both ends.

**State the units in the message every time.** The contract has no field for
units, and a number with no unit in a finding is an invitation to compare a
thickness against a temperature.

### `hold data`

The file this entity stands for exists and is not empty.

```yaml
  - name: every_file_holds_data
    applies_to: File
    must: hold data
    severity: refuse
    message: >-
      This file is named in the crate and holds nothing, so the step that
      was meant to produce it produced no data.
```

**Every other verb reads the description.** A description can be perfectly
correct about a file that is empty, which is what happens when a step runs,
writes nothing and exits successfully. Nothing else here would notice.

It takes no `property` and no `named_value`, because it is about the file an
entity stands for rather than anything written on it.

**It says nothing about whether the data is right.** That is a different
question and not this service's to answer.

**The data has to be there.** A crate sent as a bare
`ro-crate-metadata.json` is its description with the data left behind, and
this refuses rather than passing in that case, because a check that could
not run must not look like a check that passed. Send a zipped crate, or
give the service a folder.

**A file identified by a URL is not looked at.** The crate does not carry
it, and fetching it is a different act with different consequences.

## `severity`: how hard it bites

Two values and nothing in between.

**`refuse`** stops the handover. The verdict becomes REFUSED and whatever
comes next should not run.

**`flag`** records the finding and lets the handover through. The verdict
stays ACCEPTED and the finding is written into the returned crate, where
something downstream can act on it or a person can read it.

There is no middle value on purpose. A severity nobody can act on is a
severity nobody reads.

**Use `flag` when the answer is a judgment for a person**, and `refuse` when
proceeding would waste money or produce a record that is wrong.

## `one_of`: the only values that mean anything

```yaml
  - name: drying_atmosphere_is_dry
    applies_to: DryingStep
    named_value: drying atmosphere
    must: be recorded
    one_of: ["dry"]
    severity: refuse
    message: >-
      This contract is written for panels dried in a dry atmosphere. Panels
      dried any other way cure differently, and need a contract that says
      what to do about them.
```

**A known awkwardness, stated so it does not surprise you.** `one_of` hangs
off `be recorded`, so when the value is absent both the presence requirement
and this one fire, and the report says two things rather than one. Both are
true, but it is noise. There is no way to say "if present, must be one of
these" yet.

## `repairable`: letting a model help

```yaml
    repairable: true
```

Marking a requirement repairable means a model may be asked one question when
that requirement fails: **is this value already written down somewhere in the
record, including inside free text?**

That is the whole of what a model does here. It is the one job rules cannot
do, because a rule can only read a value recorded as a value, and a value
sitting inside a sentence is invisible to it.

Everything a model proposes is then checked by your rules before it counts,
and it is kept only if every requirement reading that value now passes and
nothing new is broken anywhere. The returned crate records that the value was
recovered from text rather than stated, and which engine proposed it.

**A value a model recovers raises a flag**, naming the value, the model that
proposed it and the requirement that confirmed it. So a crate rescued this
way comes back as `ACCEPTED_WITH_FLAGS` rather than `ACCEPTED`. The handover
is not blocked and nobody has to act. The flag is there because the crate
itself already says a value read out of prose is less trustworthy than one
somebody wrote down, and the verdict should say the same thing rather than
contradict it. The person worth telling is the team producing the handover:
a step that relies on a model to recover what it should be recording is a
fault further up the workflow.

**Repairable is not the same as guessable.** Nothing may be invented. The
value either is in the record or it is not, and answering that it is not
there is a correct and expected answer.

**What this was measured to do.** On 10 November 2026 two models running
locally, each with 14 billion parameters, were asked to do exactly this job
on a real crate. Neither could. Every outcome was a refusal with nothing
written, which is the system behaving correctly. A model being wrong, slow,
absent or confidently mistaken changes no verdict. Mark a requirement
repairable because it would be useful if it worked, not because you are
relying on it.

**A model is called by default**, so `repairable: true` takes effect as soon
as a contract is deployed. A deployment turns it off by setting the model
address to nothing, or a caller by passing a repair budget of 0.

## What happens when you get it wrong

The reader refuses the whole contract and names the fault. It does not ignore
what it does not understand, because a silently ignored requirement is a
requirement you believe is protecting you.

```
trial.yaml: requirement 1 (r) says 'be greater than', which is not something
a requirement can demand. It may say: ['be a number between', 'be recorded',
'be unique', 'hold data', 'point at something in the crate'].

trial.yaml: requirement 1 does not understand ['propery']. A requirement may
say ['applies_to', 'between', 'message', 'must', 'name', 'named_value',
'of_type', 'one_of', 'property', 'repairable', 'severity'] and nothing else.
In particular there is no field for instructing a model.

trial.yaml: requirement 1 (r) has no message. A violation nobody can read is
not worth raising.

trial.yaml: requirement 1 (r) has severity 'warn'. It is ['flag', 'refuse']:
either the handover stops or it is mentioned, and there is nothing in between
that anybody can act on.
```

## What the language cannot say yet

Three gaps, recorded rather than worked around. If you need one of these, you
are blocked until a verb is added to the product, and that is a change to the
code rather than to your file.

**It cannot compare one value against another.** You cannot say that a
recipe's thickness must be about three times its primer's thickness, or that
one length must be consistent with another. Every requirement reads one value
and judges it on its own.

**There are no conditional requirements.** You cannot say that if the drying
atmosphere was humid then a correction factor must also be recorded. Each
requirement fires or does not fire regardless of anything else in the crate.

**There is no way to say "if present, must be one of these".** `one_of` hangs
off `be recorded`, so a missing value triggers both requirements.

## Checking your contract before you deploy

The service prints a contract back in plain words, which is what a producing
team reads to check themselves before they are checked:

```
python -m sentinel_oo --show-contract mixing_to_coating
```

Then run it against a crate you know is good, and against a copy you have
deliberately broken. A contract that accepts everything is the same as no
contract, and the only way to know yours is doing something is to watch it
refuse something.

See [DEPLOYING.md](DEPLOYING.md) for getting it running.
