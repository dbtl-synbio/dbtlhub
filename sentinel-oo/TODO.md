# Version 1.1

What is known to be missing, and what to do about it. Each entry says how it
was found, so nobody has to rediscover why it matters.

**Two things found this.** Building it, and a deployment trial on
11 November 2026 in which somebody tried to deploy `sentinel-oo` using only
the Markdown documents in this repository, as a newcomer would, without
reading the source to fill gaps. The trial reproduced every result the
tutorial shows, so the documents are accurate about what they say; its 26
findings are about what they leave out. Entries below carry their finding
numbers.

Section 13 of [the system manual](docs/SYSTEM_MANUAL.md) lists the same
limitations from a reader's side. This file is the work.

---

## The order

Ordered by what blocks somebody first, not by how hard it is.

| | What | Why it is here |
|---|---|---|
| 1 | The record must say when the model was not reached | A record that misstates what happened is worse than a missing feature |
| 2 | `deploy.py` creates the model container | The model is on by default and the one deployment command does not start one |
| 3 | The front page's first command works on a clean Python | It fails in under a second on a machine without PyYAML |
| 4 | Not reachable from the whole network by default | It listens on every interface with no password |
| 5 | A command to describe a crate | The second thing a newcomer does, and there is no tool for it |
| 6 | Check the data, not only the description file | A crate whose data files are empty or missing passes today |
| 7 | The worked example leaves the coating laboratory | DONE. It was outside the application domain |
| 8 | The compose route | Four faults, including an unstated download of about 9 gigabytes |
| 9 | The documentation gaps | DONE. Eight small ones a newcomer hits in order |
| 10 | Everything else | Found while building, and nothing blocks a newcomer on it |
| 11 | Deploy to a remote machine | Asked for by Neil on 11 November 2026. The machine with the graphics hardware is usually not the machine you are sitting at |

---

## 1. The record must say when the model was not reached

**Findings 11, 13, 17 and 26. The most serious thing in the trial.**

**DONE, 11 November 2026.** The record and the command line now say which
of four things happened: no model configured; reachable and asked, with how
many times and how many changes were kept; reachable and not asked because
no failing requirement was marked repairable; or configured and NOT
REACHED, with the reason and the note that no value was recovered from free
text. Six tests, two of which were confirmed to fail with the fix disabled.
Verified against a real model rather than a stub, in all four states.

The rest of this entry is what was wrong, kept because the reasoning is
worth not losing.

A crate was refused on a requirement marked `repairable`, so the model
should have been asked. No model was reachable. The record written into the
returned crate says:

```
"name": "model engine", "value": "qwen2.5:14b at http://model:11434"
"description": "... Verdict: REFUSED. 1 finding(s), 0 change(s)."
```

**Anybody reading that later concludes a model with 14 billion parameters
looked for the value and found nothing.** No model was reached and the
sentence holding the value was never read. The record misstates what
happened, in the place the documents call durable and ask people to trust.

It is the same fault in kind as the one found on 10 November 2026, when a
refusal carried a value a model had invented. A wrong record is worse than
a missing feature.

**The command line is equally silent** (findings 11, 13, 17). It prints
`model engine: qwen2.5:14b at http://model:11434` whether or not anything
is there, with no wait, no error and no warning. A crate whose value is
written in a sentence was refused with exactly the same message as a crate
where the value is absent altogether.

**Only `deploy.py` warns**, once, at start-up, and that warning is in no
record.

**What to do.** The blessing already carries `engine_used`. It needs to
carry whether the model was reachable, and whether it was asked, and the
provenance writer needs to say so. `GET /health` already tells the three
states apart; the record and the command line must do the same.

---

## 2. `deploy.py` creates the model container

**Findings 1, 8 and 19.**

The model is on by default. The deployment guide labels
`python deploy.py <contracts>` as giving "a model beside it". It starts only
the sentinel container, and reports at its own stage 4:

```
model: configured but not answering  (qwen2.5:14b at http://model:11434)
WARNING: URLError: <urlopen error [Errno -2] Name or service not known>
```

A model container is created only by `compose.yaml`, a separate route the
guide describes as skipping `deploy.py`'s validation.

**Neil's expectation: the one deployment command should create the model
container as well**, so a deployment gives a sentinel with a working model.

**What it needs.** A second container from the `ollama/ollama` image on its
own Docker network so the sentinel reaches it by name; the model pulled
before the first check so a handover does not wait on the download; both
skipped when `--model-url` points elsewhere, because then the model is
somebody else's to run; the download size stated before it starts; and
`--stop` removing both containers and the network.

**The documents contradict each other on this** and must be fixed with it:
the front page says one command does the whole deployment, the deployment
guide says `compose.yaml` starts the model, and its list of what
`deploy.py` does has four steps, none of which starts a model.

---

## 3. The front page's first command works on a clean Python

**Findings 6, 7, 9 and 10. DONE, 11 November 2026.**

The front page now says Python 3.11 or later, says `python3` rather than
`python` on a Mac, tells you to make a virtual environment and run
`pip install -e .`, and drops `PYTHONPATH=src` from every command because
installing makes it unnecessary. The test section says
`pip install -e ".[test]"` and names the package `roc-validator` against
the command `rocrate-validator`, which nobody would guess.

Checked in a virtual environment built from nothing: every command on the
front page runs, and all 214 tests pass with no skips, because the
validator is installed and on the path once the environment is activated.

The rest of this entry is what was wrong.

"Try it in two minutes" says it "needs only Python 3". Run exactly as
written on a clean Python, the first command stops in under one second:

```
ModuleNotFoundError: No module named 'yaml'
```

It needs PyYAML, which is named nowhere, with no install command. It worked
on the trial machine's other Python only because that one happened to have
PyYAML already, which is how this stayed hidden.

**Also:** every command says `python`, which often does not exist on a Mac;
no minimum Python version is given, though the code needs 3.11 or later; no
virtual environment is suggested; the tests need `pytest`, which is not
said; and the validator the page calls `rocrate-validator` installs under
the name `roc-validator`, which nobody would guess.

---

## 4. Not reachable from the whole network by default

**Finding 20. DONE, 11 November 2026.**

The port is published on the loopback interface, so only this machine can
reach the instance. `--reachable-from-network` opts out and warns in those
words when it starts. The deployment guide has a section saying which it is
and why, and `--stop` now removes the model container and the network too.

Verified: `docker port` shows `127.0.0.1:8080` by default and `0.0.0.0:8080`
with the flag, and it answers either way.

The rest of this entry is what was wrong.

`deploy.py` publishes port 8080 on every network interface, so on shared
wifi anyone on the same network can send the instance requests. There is no
password of any kind.

The printout says "answering on http://127.0.0.1:8080", which reads as
though it were local only. The API manual does warn, under its known
limitations, "There is no authentication of any kind. Deploy it where only
the things that should call it can reach it." `deploy.py` does the opposite
by default and neither it nor the deployment guide repeats the warning.

**What to do.** Publish on the loopback interface only unless asked
otherwise, and say plainly what asking otherwise means.

---

## 5. A command to describe a crate

**Finding 16, and found while building. DONE, 11 November 2026.**

```
python -m sentinel_oo --describe <a crate>
```

It prints every entity type with a count, and the named values hanging off
each, with a line saying the names are compared as plain text. On the
bioprospecting crate, 109 entities, it names every value a contract could
ask about in one screen.

The tutorial's step 1 now uses it, which is what finding 16 was: that step
read as though it provided this and did not.

Six tests. The rest of this entry is why it was needed.

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

## 6. Check the data, not only the description file

**Finding 25. DONE, 11 November 2026.**

A fifth verb, `hold data`: the file an entity stands for exists and is not
empty. It catches a step that ran, wrote a zero byte file and exited
successfully, which every other verb is blind to because they all read the
description.

**The web interface now carries a whole crate.** Neil's reason, which is
better than the one this entry started with: the crate has to be passed to
the next process in the workflow, so it must come out the other side
complete. `POST /check` takes a zipped crate and returns a zipped crate,
data and all, with the record written in. The verdict travels in headers so
a pipeline need not unpack anything. A bare `ro-crate-metadata.json` still
works and is refused by a contract that checks data, because a check that
could not run must not look like a check that passed.

A zip naming a path outside the folder it unpacks into is refused, which is
the one thing that matters when a service unpacks what it is sent.

Levels 3 and 4, whether the data matches what the crate says about it and
whether it is scientifically sound, are devolved to the architect. Not this
service's job.

Seven tests, four confirmed to fail with the verb disabled. Verified through
a running container: a crate with an empty data file is refused over HTTP,
where before it passed.

The rest of this entry is what was wrong.

`POST /check/{contract}` takes the contents of an `ro-crate-metadata.json`
and nothing else. The crate's data files never reach the service, and none
of the four verbs reads inside a file. Even `point at something in the
crate` checks that a listed file is described, not that it exists.

**So a crate whose description is correct, and whose data files are empty,
corrupt or missing, passes.** The manual and the deployment guide do not say
so, and a newcomer assumes their data is being checked.

**Neil's requirement: one of the basic things a sentinel should check is
that data has actually been produced by every step in the workflow.**

The contract language can already say that a step names an output which
is described in the crate. It cannot say that the file exists and holds
data. That needs the service to receive the data files, and a verb, or an
extension of one, that looks at them.

The agent interface takes a folder path, so it may already be able to
reach the data. The API manual does not say whether it reads them.

---

## 7. The worked example leaves the coating laboratory - DONE, 11 November 2026

**Neil, 11 November 2026:** "Our users have no idea about paint. Its outside
the aplpication domain." And: "we should use the enzyme plate example from
the bioprospecting use case as a demo. The team are familiar with it and it
doesnt make the system non-generic. Just easier to comprehend by our team."

**What the worked example is now.** The handover from Design to Build in a
bioprospecting cycle: a panel of candidate proteins pulled out of a
metagenome, a synthetic gene designed for each one, and the plate layout
saying which well each goes into. It is the bioprospecting use case's own
crates, copied into `examples/` so the product still stands alone.

**Where the coating laboratory went.** Into `tests/fixtures/`, unchanged.
The test suite uses it exactly as before. It is not a leftover: it is how
the suite holds in place that nothing in the service knows about any domain,
since the same code checks a coating line and a bioprospecting handover with
no difference but the contract file. The documents say so in four places and
a newcomer never meets it otherwise.

**What had to be built for it.** The plate example's repairable requirement
is the gene calling step's edge handling, and in the crate meant to hide a
value in prose the only trace is the flag `-c` in a command line. A model
cannot recover that without knowing the program's flags, and two models
failed at it on 10 November 2026. So the tutorial's model step had nothing
that works. One crate was added, `plate-test/invalid/edge-handling-in-prose`,
where the step says in words that "contig edges were treated as closed, so
no partial genes were kept". A model recovers `closed` from that in about 9
seconds on a laptop and the crate comes back ACCEPTED_WITH_FLAGS. The harder
crate stays in as the lesson about a wrong proposal being thrown out.

**Two requirements were added to the contract, in both copies**, because
your contract used only three of the five verbs and the tutorial teaches all
five. A construct's coding sequence length must be a number between 300 and
3000 base pairs, as a flag rather than a refusal. Every file the crate names
and carries must hold data.

**What was rewritten.** The front page's two-minute example, the whole
ten-step tutorial, the contract guide, the examples README, the deployment
guide's printout, two sentences in the system manual, one troubleshooting
example, and the library catalogue crate's own description, which described
itself against the coating laboratory and used addresses under
`example.org/coating-test`.

**Two faults found by doing it, both fixed.** When a crate arrived as its
description file alone, the new data requirement complained about every file
the crate names by web address, which it was never going to carry: the check
for "the data did not arrive" ran before the check for "this file lives
elsewhere". And four tests in the bioprospecting demonstration loaded only
the description file, so the same requirement refused them; they now load
the whole crate folder, which is what a real receiving step does.

**Checked rather than claimed.** Every command in the tutorial was run and
every printout in it is real. Every YAML block in the contract guide was fed
to the product's own contract reader. Every product path named in any of the
eight documents exists. The product was copied into an empty directory and
its tests pass there. And `rocrate-validator` 0.13.1 was installed to
measure all seven crates: every one is valid RO-Crate 1.3 with 0 issues,
which also unskipped the three tests that needed it. 263 tests pass with
nothing skipped.

---

## 8. The compose route

**Findings 21, 22, 23 and 24. DONE, 11 November 2026.**

All four fixed and checked by running it. `SENTINEL_CONTRACTS` serves your
own folder, `SENTINEL_PORT` moves it off 8080 where it collided with
`deploy.py`, checked crates go to a named volume instead of writing an
`out` folder into the repository, and the header states the download as
about 2 GB for the model server and about 9 GB for the model, with the
Ollama image pinned to 0.5.7 rather than `latest`.

It also binds to `127.0.0.1` by default, matching `deploy.py`, which
finding 20 was about and this file would otherwise have undone.

The file now says plainly that `deploy.py` is the ordinary route and names
the three things Compose does not do: validate the contracts first, ask
before downloading, and confirm afterwards.

The rest of this entry is what was wrong.

| | |
|---|---|
| It cannot serve your own contracts | It always mounts the coating example's folder. Its header says a deployment mounts its own instead, and neither it nor the guide says how |
| It collides with `deploy.py` | Both publish port 8080, so one must be stopped or moved. Neither document says so |
| It writes into the repository | It mounts `./out:/out`, creating an `out` folder inside `sentinel-oo`. Nothing says so |
| The download size is not stated | It says "several gigabytes". The model is about 9 gigabytes, and the Ollama image is taken as `latest`, unpinned, while the model itself is described as pinned |

On a Mac the model runs on the processor only, because Docker cannot
reach the Mac's graphics hardware. The file says this "works and is slow",
with no figure.

---

## 9. The documentation gaps - DONE, 11 November 2026

**Findings 2, 3, 4, 12, 15 and 18, and the notes on tutorial steps.**

Each is small, and a newcomer hits them in this order. Finding 14, the
coating laboratory example, is item 7 and is not done.

**What changed.**

| Finding | What it says now |
|---|---|
| 2, 3, 4 | The front page has a "What you need" table (Python 3.11 or later, Docker running, Docker Desktop on a Mac) and an "About the model" paragraph naming Ollama, giving about 9 gigabytes to download and about 10 gigabytes of memory to run `qwen2.5:14b`, and saying Docker cannot reach a Mac's graphics hardware |
| 5 | The two-minute example sets `SENTINEL_MODEL_URL=` and says what that means |
| 12 | Without `--out` the printout says the crate was NOT saved and how to save it |
| 15 | The plain-words contract ends with the RO-Crate words it used, each explained in a sentence, and marks each requirement a model may help with |
| 18 | It now says each missing type is refused on its own, and why |
| steps 4, 7 | Both commands are written out, the five crates as a loop that was run as written |
| step 5 | It says to raise the version at each step, and why the version matters: it is copied into the record inside every checked crate |
| curl | Step 10 shows both routes with real replies: the whole crate zipped, which is the one to use because the checked crate comes back and `hold data` needs the data files, and the description file alone, with a command that picks the verdict out of the 18 kilobyte reply |

**Two faults found while writing it, both fixed.**

The documents said there were four verbs when the code has five, because
`hold data` was added earlier the same day. The error message a contract
author sees said "adding a fifth"; it now counts the verbs itself rather
than carrying a number that goes stale.

Posting a crate's description file on its own, with no data files, gave a
refusal carrying the contract author's sentence, "this file holds nothing,
so the step that was meant to produce it produced no data". The data had
never been sent. The reply now says the data file was not sent, that a
check which could not run is refused rather than passed, and that the whole
crate should be sent as a zip.

| | What is missing |
|---|---|
| 2 | Docker is never named as a requirement on the front page, nor which version, nor that a Mac needs Docker Desktop |
| 3 | The model server is not named. The default address is `http://model:11434` and nothing says that is Ollama, how to get the model, or how large it is |
| 4 | "A model worth using wants a GPU" gives no memory figure, and does not say whether a Mac without a separate graphics card will do |
| 12 | Without `--out`, the printout does not say where the checked crate went, or whether it was saved |
| 15 | The plain-words contract, which the front page says to send to the producing team, still needs RO-Crate terms to act on: `conformsTo`, `mainEntity`, `hasPart`, `isPartOf`. It also does not show which requirements a model may help with |
| 18 | It says "for crates containing all of" and then "a crate containing none of those is refused". A reader cannot tell what happens to a crate with some but not all. Each missing type is refused on its own, and nothing says so |
| 5 | The front page does not say what the two-minute example does when no model can be reached |
| steps 4, 7 | The tutorial says "run both crates again" and "run all five" without giving the commands |
| step 5 | It adds three requirements without saying what to change the version to, while step 9's printout implies one increase per step |
| curl | The manual does not show what the reply looks like, so `curl` prints 15 kilobytes of JSON in one block |

---

## 10. Everything else

Found while building. None of it blocks a newcomer.

### A second job: say which agreed term an unrecognised one means

**Agreed on 11 November 2026.**

When a crate uses a term no contract recognises, ask the model which agreed
term it means. **Record the suggestion and never apply it.** The handover
stays failed until a person confirms, and answering "no term fits" is useful
rather than a failure, because it tells somebody a new term has to be
agreed.

**Why it is the right second job.** It has the same shape as the first. The
model is asked one narrow question about something that has already failed,
it cannot decide anything, and what it offers is checked or confirmed before
it counts. A second job of that shape is worth having; a job of any other
shape is not.

**Why it matters.** Two sites doing the same work will not use the same
words for it. The rule that holds the vocabulary together is that **a site
may rename an agreed term but may not coin one**, and the thing that makes
that rule usable rather than irritating is something that suggests which
agreed term a local word probably means.

**What it needs.**

| | |
|---|---|
| The `vocabulary/` folder | Exists and is empty. It needs the agreed core terms, and one file per site mapping local names onto them |
| A way to record a suggestion | Written into the returned crate, clearly marked as unconfirmed, in the way a recovered value already is |
| A rule that it is never applied | The equivalent of the test that says a discarded proposal leaves no trace |
| A way for a person to confirm one | Which is a decision about process, not only about code |

**Where it comes from.** The `sentinel` framework already does this, and the
thinking behind it is the strongest part of that work. This would be
`sentinel-oo` catching up rather than inventing anything.

### A slow model delays a handover - DONE, 11 November 2026

**Was:** one timeout of 300 seconds for every call, so a model nobody could
see could block a handover for five minutes. A check is what a pipeline
waits for.

**Now:** two waits, both settable by a deployment without anything being
rebuilt. The first answer is allowed 180 seconds
(`SENTINEL_MODEL_FIRST_TIMEOUT`), because the model has to be loaded before
it can answer at all: about 19 seconds of a 39.6 second first answer when
measured on an NVIDIA card on 11 November 2026, and slower on a processor.
Every answer after that is allowed 60 seconds
(`SENTINEL_MODEL_TIMEOUT`), because the same question came back in 67
milliseconds once the model was loaded.

Only an answer shortens the wait. A call that fails proves nothing about
whether the model is loaded, so the call after it is still treated as a
first call.

**And the record gained a fifth state.** A model that did not answer in
time is now kept apart from one that was never reached and from one that
looked and found nothing, because a check that gave up waiting knows less
than either: whether the value was there is not known.

Nonsense in either environment variable falls back to the default rather
than stopping the service from starting. A mistyped number must not be the
reason handovers cannot be checked.

**Not done, and still worth considering:** moving the repair off the path
the caller waits on altogether. That is a change in shape rather than a
number.

### The network engine has not been tested against a slow or broken server - DONE, 11 November 2026

Eleven tests added. The engine is now given, in turn: a server that accepts
and never answers; one answering a proxy's error page rather than JSON; one
answering JSON that is not an object; one answering an object with no
answer in it; and one answering `null`, which Ollama does in some states
and which would otherwise have reached the rules as a value nobody wrote.

Every one of them produces an empty answer, no exception, and no change to
any verdict. The record says which happened.

No real socket is opened. The whole suite runs with sockets disabled, so
what the tests replace is urllib's own opener, which is where the waiting
happens.

---

### The contract language

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

### The service

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

### A crate checked from the command line does not say which code checked it - DONE, 11 November 2026

**Found by the RunPod session on 11 November 2026**, while testing the
model on a rented machine with graphics hardware. Running from the command
line rather than from the built image, the printout said:

```
  service image tag                      unset
  service commit                         unset
  rules checksum                         unset
```

Those three go into the crate's lasting record. A crate checked this way
therefore does not record which version of the service checked it, nor
which version of the rules. That may be intended, since the values are
stamped into the image when it is built, but it sits badly beside the rest
of the day's work, which was all about a record saying what actually
happened. At the least the printout and the record should say that the
service was run from source rather than leaving three fields reading
`unset`, which a reader cannot tell apart from a fault.

**What it says now.** Whatever is missing is worked out from the source
rather than written as `unset`:

```
  service image tag    none: run from source, not from a built image
  service commit       ab6c85d with uncommitted changes
  rules checksum       sha256:92c250be125f02d4 over the service's source files
```

"with uncommitted changes" matters: the commit on its own would be a claim
nobody could check, because the files at that commit are not the files that
ran. A source folder outside a git repository, and a machine with no `git`
program, each say which of those happened rather than going quiet. Ten
tests, including one that the facts reach the inside of the checked crate,
which is the only place that counts.

### The product itself

### A repository of its own

`sentinel-oo` identifies itself by the address of a bioprospecting
repository, because that is where the code currently sits. A wrong address
would be worse than an awkward one, so it stays until the product moves.
`SENTINEL_URL` overrides it in the meantime.

### The Build to Test contract is a stub with no `expects` - DONE, 11 November 2026

Every requirement in it applies to the root, so it checked packaging and
nothing else, and it would accept any crate at all.

**Fixed on 11 November 2026**, agreed with Anil Wipat. The types come from
the Build to Test row of the 14-step bioprospecting document, which says
the handover carries assembly outputs and quality control results: which
constructs passed, the product size in base pairs against the accepted
range, the concentration in nanograms per microlitre, and the build route
used.

```yaml
expects:
  - AssembledConstruct     # what came back from the build, one per well
  - PlateWell              # where each one sits
  - QualityControlResult   # the size and concentration measurements
  - AssemblyStep           # the process step that built them
```

`PlateWell` is spelled as the Design to Build contract spells it, because
the two handovers describe the same physical plate.

Checked: a crate from another phase is now refused four times, once per
missing type, where before it was accepted with no findings.

**Still a stub in what it checks.** Nothing yet requires a construct to say
whether it passed, a product size to fall in the accepted range, a
concentration to be recorded, or a build route to be named. Those are
written when the Test phase says what it needs. The file says so.

The file is at
`outputs/dbtl-bioprospecting-contracts/deployments/bioprospecting/contracts/build_to_test.yaml`,
which is the old private repository. **Where that deployment should live now
that the work is in `dbtlhub` is an open question for Neil.**

---

---

## 11. Deploy to a remote machine

**Asked for by Neil on 11 November 2026**, in these words: "when somebody
is deploying the sentinel we need to give them the option to deploy it
remotely on a server".

**Where it stands today.** `deploy.py` runs `docker` on the machine you run
it on, and only there. The one part that can already live elsewhere is the
model, through `--model-url`, added earlier the same week.

**What prompted it.** Trying to run the model on Neil's laptop failed
twice. Docker Desktop there is allocated 32768 MiB, which is 32 gigabytes
of the machine's 36 gigabytes, and loading a model needing about 10
gigabytes of memory inside that virtual machine brought the whole thing
down with an internal virtualization error. The work moved to a rented
machine with graphics hardware. That is the ordinary case, not the
exception: the machine with the graphics hardware is usually not the
machine the person deploying is sitting at.

### The shape agreed with Neil

One new option:

```
python deploy.py my-contracts --host ssh://neil@gpu-box.example
```

**Use Docker's own remote host support rather than inventing one.** The
`docker` command line already understands an `ssh://` address, so the image
is built on that machine, the containers run on that machine, and the
connection uses the person's existing SSH key with no password written to
any file. In practice that means setting `DOCKER_HOST` for every `docker`
call the program makes.

**The complication, which is real and must not be hidden.** Contracts are a
folder on the deploying person's own machine, and today that folder is
mounted into the container. A mount on a remote Docker host names a path on
*that* machine, not on this one, so a remote deployment that simply passed
the same path would mount whatever happened to be at that path on the
server, or nothing.

The answer: after validating the contracts and before starting anything,
copy them into a named volume on the remote machine and mount that volume
read only. Contracts are a few kilobytes, so copying them with `docker cp`
is safe. **That is the one case where `docker cp` is fine. Never use it for
anything of gigabyte size: on 11 November 2026 copying an 8.99 gigabyte
model with it brought Docker Desktop down on Neil's laptop.**

### What must not change

- It still reads and checks every contract before building anything, and
  refuses on the first one that does not make sense.
- It still confirms afterwards that the running instance is serving exactly
  the contracts it validated, by checksum.
- It still publishes the port on `127.0.0.1` of the machine it runs on
  rather than on every network interface. On a remote machine that means
  reaching the service through an SSH tunnel rather than through a port
  open to whatever network that machine is on. The service asks for no
  password of any kind, so this matters more remotely, not less.

### Three routes, not one. Worked out with Neil on 11 November 2026

A deployment goes to one of three kinds of place, and the person deploying
picks by what their machine allows.

| Where | How | State |
|---|---|---|
| Their own machine | `python deploy.py my-contracts` | Works today |
| A machine they reach over SSH that runs Docker: their own server, an AWS EC2 instance, a Google Compute Engine virtual machine | `python deploy.py my-contracts --host ssh://them@that-machine` | Built on 11 November 2026, not yet tested against a real second machine |
| A service that runs an image for them rather than giving them a machine: RunPod, Google Cloud Run, AWS Fargate, a Kubernetes cluster | They point the service at our published image and hand it their contracts the way that service does files | Not built. Needs the image published |

**The image is published once per version, by us, not by each user.** This
matters and was nearly got wrong: an image is the generic product, which
does not change when somebody writes a contract. Tailoring is the contracts
and nothing else. So nobody building a deployment builds or pushes an
image.

**The remote route should pull the published image rather than build it on
the far machine.** It builds today, which is slower and needs a build
toolchain on somebody else's server for no reason. Building should happen
only when asked for.

### Docker cannot run inside a RunPod Pod, measured

Worth writing down, because it was argued about and it decides the third
route. A RunPod Pod is itself a container. On `sentinel-oo-gpu`, Pod id
`5r236t84yew8ph`, on 11 November 2026, over SSH and changing nothing:

```
docker                  not installed, no binary anywhere
CapEff                  00000000a80425fb, which lacks the privilege a
                        Docker daemon needs to create mount namespaces
/dev/fuse               missing
unshare --user          "Operation not permitted", so rootless Docker
                        cannot start either
```

The earlier model test on RunPod, which succeeded, used no Docker: Ollama
was installed directly into the Pod. RunPod's own Docker runs the Pod, on
RunPod's machine. That is why a Pod feels like a container and still cannot
host one.

The route that does work on RunPod is the third one above: start the Pod
from our published image, with the contracts on a RunPod network volume
mounted at `/contracts`.

### Still to decide

- Whether `--host` should also move the model container to the remote
  machine by default, or whether the model stays wherever `--model-url`
  says. The likely answer: if the person gives `--host` and no
  `--model-url`, the model container goes on the same remote machine, since
  the reason for deploying there is usually that it has the graphics
  hardware.
- What `--stop` does with a remote deployment. It should stop the remote
  containers, and it should refuse to stop containers on a machine the
  person did not name.
- Whether the documents need a short section on SSH tunnelling, written for
  somebody who has not done it.

---

## Deliberately not here

**Advisory flags proposed by a model**, and **a contract authoring
assistant**. Both were planned as later steps of the original build order
and neither was started. The design is arranged so that stopping where it
stopped leaves a working service rather than a half-built one.

**Act 2 of the demonstration**, where somebody from another use case writes
their own contract and deploys it. That is theirs to do, not ours. If we
write their contract, nothing has been tested.
