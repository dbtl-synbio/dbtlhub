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
| 7 | The worked example leaves the coating laboratory | It is outside the application domain |
| 8 | The compose route | Four faults, including an unstated download of about 9 gigabytes |
| 9 | The documentation gaps | Eight small ones a newcomer hits in order |
| 10 | Everything else | Found while building, and nothing blocks a newcomer on it |

---

## 1. The record must say when the model was not reached

**Findings 11, 13, 17 and 26. The most serious thing in the trial.**

**DONE, 12 November 2026.** The record and the command line now say which
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

**Findings 6, 7, 9 and 10. DONE, 12 November 2026.**

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

**Finding 20. DONE, 12 November 2026.**

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

**Finding 16, and found while building. DONE, 12 November 2026.**

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

**Finding 25. DONE, 12 November 2026.**

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

## 7. The worked example leaves the coating laboratory

**Decided by Neil Wipat on 11 November 2026.** There is no harm in using a
synthetic biology exemplar in the tutorial and the documents. The system is
still generic.

**Why it is a coating laboratory today.** It was made neutral on 11 November
2026 so that nothing in the product would look as though it belonged to one
use case, at a point when the product and one deployment were still
entangled and the separation was being argued about.

**Why that reasoning no longer holds.** Genericity is a property of the
code, not of the example, and the code's genericity is now held in place by
tests rather than by the choice of nouns:

| Test | Fails if |
|---|---|
| `test_no_handover_name_in_source` | Any handover's name appears in the service source |
| `test_source_imports_no_use_case` | Any service file imports from a deployment |
| `test_fixtures_stay_inside_the_product` | Any test holds a path resolving outside the product |

**The example is outside the application domain.** That is the objection,
and it is one of kind rather than of taste. The application domain is
synthetic biology and the DBTL cycle. An example from outside it is not a
neutral choice, it is the wrong sort of thing to be explaining with.

**The users have no idea about paint**, which is what that costs in
practice. The tutorial asks a synthetic biologist to understand rack slots,
film thickness in micrometres and drying atmospheres, none of which they
will meet again, before they can reach a lesson about handovers.

An exemplar from their own field costs them nothing to read, and every noun
in it is one they already know.

**What it touches**, which is why it is a version and not an afternoon:

| | Mentions |
|---|---|
| `examples/`, the generator, 2 contracts and 6 crates | about 60 |
| `docs/USER_MANUAL.md`, the tutorial, step by step | 22 |
| `docs/WRITING_A_CONTRACT.md`, every worked example in it | 21 |
| The test suite, which reads the example as its fixtures | about 80 |
| `README.md`, `DEPLOYING.md`, `SYSTEM_MANUAL.md` and the diagrams | 10 |

**One thing that must survive the change.** The tutorial's step 3 sends a
crate from a completely different domain and watches a contract without an
`expects` block wrongly accept it. That needs a crate that shares nothing
with the main example. `examples/from-another-phase/` is a library
catalogue, which stays usable whatever the main example becomes.

**About half a day**, and the risk is in the test fixtures rather than in
the prose.

---

## 8. The compose route

**Findings 21, 22, 23 and 24.**

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

## 9. The documentation gaps

**Findings 2, 3, 4, 12, 14, 15 and 18, and two notes on tutorial steps.**

Each is small, and a newcomer hits them in this order.

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

### A slow model delays a handover

The model is called during a check, and a check is what a pipeline waits
for. The timeout is 300 seconds, which is long enough for a cold model on
another machine to load, and that is 300 seconds a pipeline can block for.

**Why it has not bitten yet.** A warm model answers in about half a second,
and only requirements marked `repairable` are ever asked about, which is
typically one in a contract of nineteen.

**What it needs.** Either a shorter timeout with the long one only on the
first call, or the repair moved off the path the caller waits on. Both are
a change in shape rather than a tweak, which is why neither is done.

**Found** on 11 November 2026, when the model became the default.

### The network engine has not been tested against a slow or broken server

It is tested against a server that is not there, and by hand against a real
one. It has never been given a server that accepts a connection and then
never answers, or that returns something that is not JSON. Both are things
a real model host does.

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

### The product itself

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

---

## Deliberately not here

**Advisory flags proposed by a model**, and **a contract authoring
assistant**. Both were planned as later steps of the original build order
and neither was started. The design is arranged so that stopping where it
stopped leaves a working service rather than a half-built one.

**Act 2 of the demonstration**, where somebody from another use case writes
their own contract and deploys it. That is theirs to do, not ours. If we
write their contract, nothing has been tested.
