# The demonstration

What is here, and what state each piece is in.

| File | What it is |
|---|---|
| `demo_part1.ipynb` | **Part one.** A Colab notebook that builds a working service on Google Cloud in front of an audience, sends packages to it, and draws the graph of a check |
| `build_demo_part1.py` | The script that writes that notebook. The notebook is generated, so change this and run it rather than editing the notebook by hand |
| `demo_part2.ipynb` | **Part two.** A Colab notebook each person in the room runs on their own Colab machine, with their own sentinel-oo, their own LLM and their own crates |
| `build_demo_part2.py` | The script that writes part two |
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

## Part two, in one paragraph

Each person runs this one on their own Colab machine. It installs sentinel-oo
as a Python package, installs Ollama and downloads an LLM, prints the same
`design_to_build` contract part one uses, starts their own instance, and
then hands them the example crate as a download so they have one of their
own. They send a crate by any of three routes, which are the example from
the repository, text pasted into a cell, or files uploaded from their own
computer. Then the broken crates, including the two where the LLM is asked
for help, the graph of their own check, and finally editing a requirement in
the contract and writing a contract of their own. It costs nothing: no
Google Cloud account, no billing account, and nothing installed on their own
computer.

**No Docker.** Colab does not allow a Docker daemon inside its machines, so
part two installs and runs the service directly. Part one is where the
Docker deployment is shown, which is the part only one person runs.

**Which LLM, and why it depends on the machine.** With a graphics card the
notebook uses `qwen2.5:14b`, which is the one measured recovering the value
from prose on 10 and 11 November 2026. Without a card it falls back to
`qwen2.5:7b`, because the larger one takes minutes per answer on a processor
alone. The smaller one has not been measured on that question, so the LLM
part of the notebook may come back refused rather than flagged. The notebook
says so on screen when it makes that choice.

### What has been tested in part two, and what has not

**Tested on a laptop on 12 November 2026**, by running every cell of the
notebook's own source against a real running service, with `qwen2.5:14b`
through Ollama:

- Installing the package into an empty environment and starting the service
  from it.
- The contract printed in plain words, and `--describe` on the crate.
- The compliant crate: `ACCEPTED`.
- The three singly broken crates: all `REFUSED`, each naming its own cause.
- The crate whose value is in prose: `ACCEPTED_WITH_FLAGS`, the value
  recovered and written in.
- The crate whose value is only a command line flag: `REFUSED`, nothing
  written.
- A Design to Build crate sent to the `build_to_test` contract: `REFUSED` by
  the `expects` block, naming the types that are missing.
- The graph: 127 nodes and 189 edges, drawn.
- Editing one number in the contract, restarting, and the same crate coming
  back `ACCEPTED_WITH_FLAGS` instead of `ACCEPTED`.
- Writing a new contract and having it served beside the other two.

**Not tested, because it needs Colab**: the clone and `pip install` from
GitHub, the Ollama install script on a Colab machine, the download of the
crate through the browser, the file picker in route C, and the `%%writefile`
cell. **Run the whole notebook once in Colab before anybody else does.**

### Three faults found by that testing, all fixed

**A service already on the port was treated as ours.** Starting the service
only checked that something was listening, so an instance left over from an
earlier run answered every request afterwards, from whichever contracts it
had been started with. The visible symptom was a compliant crate coming back
`REFUSED` against a contract that would have accepted it. The notebook now
refuses to start when the port is held by something it did not start, and
checks that what answers identifies itself as sentinel-oo.

**The graph came after the contract editing.** Editing a contract restarts
the service, and a restart empties the list of runs it holds, so the graph
request failed for a run made before it. The graph is now part 9 and the
editing is part 10.

**A message that contradicted its own rule.** Narrowing the length range
left the requirement's message still naming the old range, so the cell now
edits the message with the number, and says why.
