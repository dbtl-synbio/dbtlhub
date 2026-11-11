# How it was built, and what that found

This is the record of building `sentinel-oo` during the week of 9 to 13
November 2026. It is useful if you are changing the service. It is not
useful if you are only using it, and [the user
manual](USER_MANUAL.md) is the place to start instead.

It was moved out of the README on 11 November 2026, because the front page
was trying to be an introduction and a build journal at the same time and
was doing neither well.

---

## It was built in steps, each one runnable

Nothing was built that could not be run on the day it was written. That
turned out to matter more than anything else here: **every fault below was
found by running the thing, not by reading it.**

The order was: read a crate and write a record; apply checks written in
Python; move those checks into contract files so the code knows no handover;
write the real requirements for one handover; add the two interfaces; add
the model and the repair path.

Two later steps were planned and never started: advisory flags proposed by a
model, and an assistant that drafts a contract. The design is arranged so
that stopping where it stopped leaves a working service rather than a half
built one.

---

## Faults found by running it

Each of these passed review and failed use.

**Writing to a folder that did not exist produced a file with no
extension.** The check for a folder tested only whether one already existed.

**The service entity had no `url`.** RO-Crate 1.3 requires one on any
`SoftwareApplication`, and the third party validator refused the returned
crate until it was added. Our own tests had passed.

**Two exceptions escaped that should not have.** A string containing the
characters `@id` sitting in the graph produced a `TypeError`, because
testing `"@id" in entity` is true of any string containing them. Adding an
entity with no identifier produced a `KeyError`. The crate class promises
that nothing but `CrateMalformed` reaches a caller, and both broke that
promise. Found by feeding it deliberately awkward input.

**The first version of the profile check read the wrong entity.** It looked
at `conformsTo` on the metadata descriptor, which says which version of
RO-Crate the file is. The profile the contents follow is declared on the
root data entity instead. The check looked correct, passed its own tests,
and caught nothing. Running it against a crate built to be broken exposed
it.

**A repaired value could be written into a crate that was then refused.**
The repair path checked only the requirement being repaired. A model
answered with a phrase that was not one of the permitted values, which
satisfied "the setting must be recorded" and failed "the setting must be one
of these". The handover was correctly refused and the invented phrase was
written in anyway. A refusal carrying a fabrication is worse than a plain
refusal.

**A contract accepted a crate from an unrelated domain.** Found by deploying
two instances from one image and posting a crate to the wrong one. It came
back ACCEPTED with no findings, because 12 of that contract's 18
requirements named entity types the crate did not contain, so each matched
nothing and passed. Only 6 requirements looked at anything at all.

Each requirement was behaving correctly on its own. A rule about a type
should say nothing about a crate with none of that type. The failure was in
the sum, and the sum is the verdict. **Blessing a crate that was never
checked is worse than refusing a good one**, because a refusal is visible
and this was silent. A contract now declares what it is for, with `expects`.

**The agent interface died on a wrong argument name.** A tool call went
straight to the method, so a wrong keyword raised an error that propagated
out and killed the process. The agent got no answer at all, not even an
error. The caller is a model and models get argument names wrong.

**Three HTTP methods never reached the dispatcher.** `PUT`, `PATCH` and
`DELETE` were answered by Python's own handler with a page of HTML, from a
service that otherwise only returns JSON. The test for a wrong method called
the dispatcher directly, so it passed while the running server did something
else.

---

## Three decisions worth knowing if you change the code

**The crate is immutable.** Every method that changes anything returns a new
crate and leaves the original exactly as it was, down to nested values being
read only views. That is what lets the service show what it was sent at the
end of a run, and keeps the recorded checksum of the input correct without
anybody having to remember it separately.

**The checksum ignores formatting.** Entities are sorted by identifier and
keys sorted within them before hashing, so running a crate through a pretty
printer does not invalidate a record written about it. Changing any value
does change it.

**The writer alters exactly one thing it did not write.** It appends the new
action to the root entity's `mentions`. Without that the action sits in the
crate unreachable from the root, which was one of six faults found in an
example crate after it had already passed validation, and which no validator
catches. Everything else comes out byte for byte as it went in, and a test
says so.

---

## Where the line is between a file and the code

The code knows four kinds of check and nothing else: that a value is
recorded, that it is unique, that a reference lands on something really in
the crate, and that a number is within a range.

Which handover, which kind of entity, which property, which values, which
numbers, whether failing refuses or raises a flag, and the sentence a person
reads: all of those live in a file.

So "no two slots may claim the same position" is written entirely in a
contract. The code contributes the words `be unique`.

**A kind of check may go in the code only if it can be explained without
mentioning the domain.** "Values must not be shared" passes that test. "The
sequence must be valid DNA" does not, and the right form of it is a general
check that every character comes from a given set, with the set written in
the contract file.

A requirement that none of the five can express needs the vocabulary to
grow, which is a decision taken on purpose rather than a special case added
in a hurry. The error message a contract author sees says exactly that, and
says where in the code the next one would be added. The fifth verb,
`hold data`, was added on 11 November 2026 for exactly that reason: a
sentinel that reads only the description file cannot tell an empty result
from a real one.

**There is no field for instructing a model**, and a file carrying an
unknown field is refused rather than ignored, so a misspelled key cannot sit
in a file looking effective. The reason that matters most: this service
accepts a contract from whoever is sending the handover, so prompt text in a
contract would mean the sender writing the model's instructions.

Everything that can be wrong with a contract is found when it is read, with
the file named, rather than when somebody posts a crate.

---

## A known cost, written down so nobody is surprised

**Every change rewrites and re-hashes the whole graph.** At the size of the
worked example, 28 entities, that is immeasurable. It is recorded here so
nobody is surprised by it at a hundred times the size.

---

## What it still cannot do

Kept in one place rather than two: [TODO.md](../TODO.md), which lists what is
missing, how each was found, and what to do about it. Section 13 of [the
system manual](SYSTEM_MANUAL.md) says the same from a reader's side.
