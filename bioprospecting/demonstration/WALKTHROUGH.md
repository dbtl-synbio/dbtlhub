# The demonstrator: a walkthrough

A running deployment doing one job from the bioprospecting cycle end to end,
in front of people, in about 15 minutes.

**Every command here has been run and every output shown is real**, captured
on 11 November 2026. Nothing below is a mock-up.

---

## What it proves, and what it does not

| It shows | It does not show |
|---|---|
| A generic service tailored by a contract file, with no code written | Somebody else's use case. That is theirs to write |
| A valid crate being refused, and why that matters | A model recovering a value. No local model could do it |
| Money not spent, because a handover was refused | A real vendor. The ordering step is simulated |
| One image serving two different cycles at once | A real adapter between the crate and a vendor system |

**Say the simulation out loud early.** The program that writes the order is a
stand-in for a gene synthesis vendor's ordering system, which exists already
and is not ours. Somebody in the room will spot it, and it is better said
than caught.

---

## Before the room

Run these once, well before you start. The first build takes about a minute.

```
cd dbtlhub/sentinel-oo
python deploy.py ../bioprospecting/contracts \
    --crates ../bioprospecting/exampleROcrates
```

Check it is answering:

```
curl -s http://127.0.0.1:8080/health
```

Have two terminal windows open, both in
`dbtlhub`, and a browser tab on
`http://127.0.0.1:8080/contracts`.

**If the room has no network, everything still works.** Nothing here reaches
outside the machine.

---

## Act 1: what is deployed, and what was not written

**About 2 minutes.**

Start by killing the instance and bringing it back up in front of them, so
nobody thinks there is a trick.

```
python deploy.py ../bioprospecting/contracts --stop
python deploy.py ../bioprospecting/contracts \
    --crates ../bioprospecting/exampleROcrates --no-build
```

```
1. Reading contracts from ../bioprospecting/contracts
   build_to_test                0.2.0      2 requirements
   design_to_build              0.10.0    18 requirements
   checksum over all of them: sha256:a23c50aa...

2. Building the generic image
   using the existing sentinel-oo:dev

3. Starting the instance
   container sentinel-bioprospecting started from sentinel-oo:dev
   contracts mounted read only from ../bioprospecting/contracts

4. Checking the instance serves what was validated
   answering on http://127.0.0.1:8080
   2 contract(s) served, checksum matches what was validated
```

**What to say.** The image is generic and holds no contracts at all. What
makes this instance a bioprospecting instance is one folder of YAML files
mounted into it. Nobody wrote code to deploy this, and nobody edited the
image.

Then show the folder, which is the shortest part of the demonstration:

```
ls ../bioprospecting/contracts/
```

```
build_to_test.yaml    design_to_build.yaml
```

**Worth pausing on.** Those two files are the entire difference between this
instance and one for anybody else's cycle.

---

## Act 2: a good handover becomes an order

**About 3 minutes.**

This is the job somebody does by hand today: the end of Design is a file you
upload to a gene synthesis vendor, and money is spent.

```
curl -s -X POST --data-binary \
  @bioprospecting/exampleROcrates/design-to-build-simple/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/design_to_build > /tmp/demo/reply.json

python -c "
import json; d=json.load(open('/tmp/demo/reply.json'))
print('verdict:', d['verdict'], ' run:', d['run'])
json.dump(d['crate'], open('/tmp/demo/ro-crate-metadata.json','w'), indent=2)
"
```

```
verdict: ACCEPTED  run: d71ef1345972
```

Then the simulated downstream process:

```
cd bioprospecting/demonstration/simulate_downstream
python make_order.py /tmp/demo --out /tmp/demo/order
```

```
4 well(s) to order    -> /tmp/demo/order/vendor_upload.csv
0 well(s) held back   -> /tmp/demo/order/held_back.csv
```

```
cat /tmp/demo/order/vendor_upload.csv
```

```
plate,well,name,sequence
PLATE-AB-12-01,A1,CON-001,AGGGTTTCCAGGACAAAACGATTGCCGC...
PLATE-AB-12-01,A2,CON-002,ACACCCAGAGGACCTTTCCGTGTTCCTA...
PLATE-AB-12-01,A3,CON-003,CGTCGACCATATGCTGTCTGATTCGCGA...
PLATE-AB-12-01,A4,CON-004,CGGCTCATTATAGAGAATCTCAAGAGTA...
```

**What to say.** That file is the point. Not the verdict. The service decides
and something else acts on the decision, and the thing that acts knows
nothing about contracts.

**Say the simulation here if you have not already.** A real vendor system
would not read an RO-Crate, so in reality an adapter would sit between these
two. This program collapses the adapter and the vendor into one, because
there is no live vendor account in the room.

---

## Act 3: a broken handover, and the money not spent

**About 3 minutes.**

Send the crate that lists a file it never describes:

```
curl -s -X POST --data-binary \
  @bioprospecting/exampleROcrates/design-to-build/invalid/dangling-reference/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/design_to_build \
  | python -c "
import json,sys; d=json.load(sys.stdin)
print(d['verdict'])
for f in d['findings']: print(' ', f['requirement'], '\n   ', f['message'])
"
```

```
REFUSED
  everything_the_crate_lists_is_present
    The crate lists a file as part of itself that is described nowhere in
    it. Whoever receives this will look for it and not find it.
```

Now give that refused crate to the ordering step:

```
python make_order.py /tmp/demo/refused --out /tmp/demo/refused/order
echo "exit code: $?"
```

```
no order written: the service refused this handover, so no order is
written. Fix what it reported and check the crate again.
exit code: 1
```

Nothing was written. No folder was even created.

### The third case, which is the one people do not expect

Give it a crate the service has never seen:

```
python make_order.py ../../exampleROcrates/design-to-build-simple \
    --out /tmp/demo/bypass
echo "exit code: $?"
```

```
no order written: this crate carries no record from the checking service,
so nothing has confirmed it is fit to order from
exit code: 2
```

**What to say.** Exit code 1 and exit code 2 are deliberately different. A
refused handover is a laboratory problem and somebody goes and fixes the
record. An unchecked crate is a process problem: somebody has bypassed the
service entirely, and that is worse, because nothing has looked at it at
all.

---

## Act 4: valid, and still refused

**About 4 minutes. This is the act that makes the argument.**

```
curl -s -X POST --data-binary \
  @bioprospecting/exampleROcrates/design-to-build/invalid/mode-in-prose/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/design_to_build \
  | python -c "
import json,sys; d=json.load(sys.stdin); print(d['verdict'])
for f in d['findings']: print(' ', f['requirement'])
"
```

```
REFUSED
  edge_handling_is_recorded
  edge_handling_is_closed
```

Now show what is actually in that crate:

```
python -c "
import json
d = json.load(open('bioprospecting/exampleROcrates/design-to-build/invalid/mode-in-prose/ro-crate-metadata.json'))
for e in d['@graph']:
    if e.get('additionalType') == 'GeneCallingStep':
        print(e['description'])
"
```

```
Ran as: prodigal -i contigs.fasta -a proteins.faa -p meta -c -q. The
settings are in that command line and nowhere else in this crate, which is
how most real records look before anybody tidies them up.
```

**What to say.** Nothing is missing from that crate. The setting is there,
in a sentence, where a person can read it and no rule can. Prodigal's `-c`
means closed ends, so no partial gene at the edge of a contig was reported.
That one setting decides whether a whole class of question needs asking
about every protein in the panel.

And the third party validator calls that crate valid. All five of these
crates are valid RO-Crate 1.3 with 0 issues each.

| Crate | `rocrate-validator` | `sentinel-oo` |
|---|---|---|
| The published one | valid | ACCEPTED |
| Profile declaration removed | valid | REFUSED |
| Gene calling setting removed | valid | REFUSED |
| A dangling reference | valid | REFUSED |
| Setting only in the command line | valid | REFUSED |

**The sentence to land.** Conformance is not sufficiency. A crate can satisfy
every rule a standard has and still be useless to the phase receiving it.

### If somebody asks whether a model could fix it

Answer with the measurement rather than an opinion. Two models running
locally, each with 14 billion parameters, were asked to recover that setting
from that command line on 10 November 2026. Neither could. Asked directly
what `-c` means, both answered confidently and wrongly; told the meaning and
asked only to apply it, one got it right and one said the exact opposite.

Every one of those outcomes was a refusal with nothing written, because
whatever a model proposes is checked by the rules before it counts. That is
the part worth saying: the system is built so that a model being wrong
changes no verdict.

---

## Act 5: one image, two cycles

**About 2 minutes. This is the one that answers "could we use it?"**

```
cd ../../../sentinel-oo
python deploy.py examples/contracts --no-build --port 8081 --name sentinel-example
```

```
1. Reading contracts from examples/contracts
   coating_to_inspection        0.2.0      2 requirements
   mixing_to_coating            1.1.0     19 requirements

4. Checking the instance serves what was validated
   answering on http://127.0.0.1:8081
   2 contract(s) served, checksum matches what was validated
```

```
docker ps --format '{{.Names}}  {{.Image}}  {{.Ports}}' | grep sentinel
```

```
sentinel-example         sentinel-oo:dev  0.0.0.0:8081->8081/tcp
sentinel-bioprospecting  sentinel-oo:dev  0.0.0.0:8080->8080/tcp
```

Then show that each knows only its own:

```
curl -s -X POST --data-binary @examples/coating-test/valid/ro-crate-metadata.json \
  http://127.0.0.1:8081/check/design_to_build \
  | python -c "import json,sys; print(json.load(sys.stdin)['detail'])"
```

```
no contract called 'design_to_build'. This service knows:
coating_to_inspection, mixing_to_coating.
```

**What to say.** Same image, same commit, nothing rebuilt. The second one is
about a coating laboratory and has nothing to do with biology. The only
difference between them is which folder of YAML was mounted.

### And the one that would have been missed

Send the coating crate to the bioprospecting instance:

```
curl -s -X POST --data-binary @examples/coating-test/valid/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/design_to_build \
  | python -c "
import json,sys; d=json.load(sys.stdin); print(d['verdict'], len(d['findings']), 'findings')
for f in d['findings'][:3]: print(' ', f['requirement'])
"
```

```
REFUSED 5 findings
  crate_contains_PlateWell
  crate_contains_IntendedPlateLayout
  crate_contains_ExpressionConstruct
```

**Worth telling them this was a bug found yesterday.** Before 11 November
2026 that came back ACCEPTED with 0 findings, because 12 of the 18
requirements named entity types the crate did not contain, so each matched
nothing and passed. A contract now declares what it is for.

It is the failure mode worth naming to that room: not refusing something
good, which is visible, but blessing something unchecked, which is silent
and looks like success.

---

## The invitation

**Do not end on your own use case.** End by asking somebody from the other
team to write a contract for one of their handovers.

What they need:

| | |
|---|---|
| To read | `sentinel-oo/docs/USER_MANUAL.md`, which has a tutorial you can run |
| To write | One YAML file |
| To run | `python deploy.py <their folder>` |
| Code to write | None |

The tutorial in that manual builds a contract from nothing against the
worked example, and the second step walks the reader into the exact trap
that was found yesterday, on purpose.

**That is the part of the demonstration that has not been done**, and it is
the part that decides whether anybody uses this after Friday.

---

## What can go wrong on the day

| Symptom | Cause and fix |
|---|---|
| `no contract called 'design_to_build'` | Nothing is mounted at `/contracts`, or the wrong folder. Re-run `deploy.py` |
| Nothing answers on port 8080 | `docker ps` to see if the container is up; `docker logs sentinel-bioprospecting` |
| The deployment stops at step 1 | A contract file is malformed. It names the file and the requirement |
| `make_order.py` says no module named `sentinel_oo` | You are running an old copy. This was fixed on 11 November 2026 |
| The build takes a minute | It is running the product's 200 tests inside the build. Use `--no-build` |

**Have `/tmp/demo` already created** and the first reply already saved, so
Act 2 cannot fail on a missing folder in front of people.

---

## Limitations to state rather than hide

Each of these is something somebody in that room may well spot.

**The ordering step is simulated**, and it reads the crate directly, whereas
a real vendor system would need an adapter between the two.

**No well is held back in this demonstration.** The ordering step can hold
wells back, and it is tested, but the shipped contract flags nothing that
names a well. That is deliberate: the obvious candidate was a vendor's
length limit, and that was kept out of the contract because it is a fact
about a supplier rather than about the handover, it goes stale when the
supplier changes, and a refusal for a reason that has nothing to do with the
science is how a contract earns a reputation for being in the way.

**No model recovered anything.** The repair path works and is tested, but
with stub models. No real model has completed the job.

**The agent interface has not been tested against a real Model Context
Protocol client**, only against the protocol as written down.

**The contract language cannot compare one value against another.** The
check that would catch a real fault here is exactly that: a construct about
three times the length of its protein is right, and half or double that
means a truncation or a duplication. It cannot be written today.

---

## Stopping afterwards

```
cd sentinel-oo
python deploy.py ../bioprospecting/contracts --stop
python deploy.py examples/contracts --stop --name sentinel-example
```
