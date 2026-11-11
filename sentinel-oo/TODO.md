# Version 1.1

What is known to be missing, and what to do about it. Everything here was
found by using the thing rather than by reviewing it, and each entry says
how it was found so that nobody has to rediscover why it matters.

Section 13 of [the system manual](docs/SYSTEM_MANUAL.md) lists the same
limitations from the reader's side. This file is the work.

---

## Blocking somebody's first hour

### A command to describe a crate

```
python -m sentinel_oo --describe <a crate>
```

printing the entity types with counts, and the named values hanging off
them.

**Why.** That list is exactly what somebody needs in order to write their
first contract, because a requirement names an entity type and the names
have to match. Today there is no way to get it: the service can check a
crate, list its contracts and print a contract in plain words, but it
cannot say what is in a crate. Their only options are to read the raw JSON
or write a throwaway script, and a real crate has a hundred or more
entities.

**It also catches the commonest mistake before it is made.** Types are
compared as plain text, so a crate saying `CoatingRecipe` against a contract
saying `Recipe` means every requirement matches nothing and passes in
silence.

**Found** on 11 November 2026, walking through what a new user actually has
to do, step by step. It is the second thing they do and there is no tool
for it.

**Size:** about 30 minutes.

---

## The contract language

These three are the limits people will hit. Each needs a new verb or a new
shape, which is a change to the product rather than to anybody's contract
file, and the error message now tells an author exactly that.

### Compare one value against another

Nothing can say that one recorded value must be consistent with another.

**Why it matters.** The check that would catch a real fault in the
bioprospecting handover is exactly this: a construct about three times the
length of its protein is right, and half or double that means a truncation,
a duplication, or a wrong sequence pasted in. It cannot be written.

### Conditional requirements

Nothing can say that if one setting had a particular value, then another
thing must also be recorded.

**Why it matters.** The gene calling requirements in the bioprospecting
contract are written for a pipeline that always runs one way, because there
is no way to say "if it ran the other way, then this as well".

### "If present, must be one of these"

`one_of` hangs off `be recorded`, so a missing value fires both
requirements and the report says two things where one would do. Two true
statements rather than one wrong one, but it is noise in a report somebody
has to read.

---

## The service

### The run graph

`GET /graph/{run}` returns 501 and says it is not built. The graph store was
designed and never written, which is also why the Monday class diagram named
components that do not exist.

### Test the agent interface against a real client

It is tested against the Model Context Protocol as written down, and by
hand against the running container. It has never been driven by a real
client, so the first team to try it will find whatever is wrong.

### An action does not name who ran it

Process Run Crate says an action should name the person or organisation
responsible. The service is not told, so it writes nothing rather than
inventing a name. It should become something a caller can supply.

### `--list-contracts` with nothing mounted

It prints an empty list followed by a checksum, and that checksum is the
SHA-256 of nothing at all. It should say it holds no contracts.

### A crate with no `@context` is read without complaint

It is interpretable, so the reader accepts it. This is now expressible as a
contract requirement, so it is a line somebody should write rather than a
change to the code.

---

## The product itself

### A repository of its own

`sentinel-oo` identifies itself by the address of a bioprospecting
repository, because that is where the code currently sits. A wrong address
would be worse than an awkward one, so it stays until the product moves.
`SENTINEL_URL` overrides it in the meantime.

### The Build to Test contract is a stub with no `expects`

Every requirement in it applies to the root, so it checks packaging and
nothing else, and it would accept any crate at all. The warning is at the
top of the file. The types belong to whoever specifies what that handover
carries.

---

## Deliberately not here

**Advisory flags proposed by a model**, and **a contract authoring
assistant**. Both were planned as later steps of the original build order
and neither was started. The design is arranged so that stopping where it
stopped leaves a working service rather than a half-built one.

**Act 2 of the demonstration**, where somebody from another use case writes
their own contract and deploys it. That is theirs to do, not ours. If we
write their contract, nothing has been tested.
