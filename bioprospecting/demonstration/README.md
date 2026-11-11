# The demonstration

What is here, and what state each piece is in.

| File | What it is |
|---|---|
| `demo_part1.ipynb` | **Part one.** A Colab notebook that builds a working service on Google Cloud in front of an audience, sends packages to it, and draws the graph of a check |
| `build_demo_part1.py` | The script that writes that notebook. The notebook is generated, so change this and run it rather than editing the notebook by hand |
| `WALKTHROUGH.md` | An earlier walkthrough, run from a terminal rather than a notebook |
| `simulate_downstream/` | A stand-in for the step that receives the handover, with its own tests |

## Part one, in one paragraph

The notebook starts with nothing. It makes a Google Cloud project, makes one
Linux machine in Madrid, puts the code on it, downloads the model onto it,
shows the contract in plain words, deploys the service, and then sends it
packages: one that is sound, three broken one way each, one where the value
the contract wants is buried in an English sentence, and one where it is
buried in a command line flag. It finishes by fetching the graph of a check
and drawing it, and then deletes the whole project.

**Audience**: people who have not seen any of this before. Every piece of
jargon is explained where it first appears.

## What it costs

One ordinary machine for about an hour, which is a few pence. The last cell
deletes the project, which stops every charge and leaves nothing behind.

## What has been tested, and what has not

**Tested on a laptop, against a real running service**, on 11 November 2026:

- Every package the notebook sends, sent the same way the notebook sends it,
  zipped, over the web interface. All six give the verdicts the notebook
  claims.
- The code that reads the record out of the returned package.
- The code that prints each finding.
- Fetching the graph and building the picture: 127 boxes, 142 lines once the
  packaging lines are left out.
- Installing the product the way the notebook installs it, into an empty
  environment, and using it to print the contract.
- The model recovering `closed` from an English sentence, which took 9
  seconds on a laptop with a graphics card.

**Not tested, because it needs Colab and a Google Cloud account**: signing
in, making the project, making the machine, putting the code on it, and the
tunnel. Those are ordinary `gcloud` commands, but they have not been run
from this notebook yet. **Run the whole notebook once, alone, before running
it in front of anybody.**

## Two things to know before running it live

**The model answers slowly on that machine.** A Google Cloud machine without
a graphics card takes tens of seconds for one answer, where a laptop with
one takes about nine. Only one cell waits on the model, and it is near the
end, so nobody is watching a blank screen in the middle. If a graphics card
is available, use one.

**The first deployment builds the image and runs the test suite inside the
build.** That is the point of it, and it takes about two minutes. Say what
it is doing while it runs.

## Part two, not written yet

A notebook each person in the room runs on their own Colab machine, with
their own copy of the service and their own graphics card, so nobody waits
for anybody else. Part one is the rehearsal for it.
