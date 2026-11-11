# A simulation of the first process downstream

This folder is neither the product nor a deployment. It stands in for the
first thing that happens after a handover is accepted, so that the
demonstration has somewhere to hand a checked crate off to.

## What it is standing in for

In the bioprospecting Design to Build handover, the next thing that happens in
real life is that somebody uploads a file to a gene synthesis vendor and
spends money. That ordering system exists already. We do not build it, we do
not change it, and we do not deploy it.

**The boundaries either side of the point where the sentinel is inserted are
fixed in reality, and altering them is not this project's job.** So this
program is scaffolding for a demonstration, not a deliverable, and there is no
live vendor account in the room to use instead.

## What it does

It reads a crate the service has returned and writes two files:

| File | What is in it |
|---|---|
| `vendor_upload.csv` | One row per well being ordered: plate, well position, construct name, DNA sequence |
| `held_back.csv` | One row per well not being ordered, with the reason |

```
python make_order.py <a crate the service returned> --out orders/
```

Exit codes, where a code is the number a program returns to whatever started
it and zero conventionally means success:

| Exit code | Situation |
|---|---|
| 0 | An order was written |
| 1 | The service checked this crate and refused it, so no order |
| 2 | The crate carries no record of ever being checked, or the input is not a crate |

Codes 1 and 2 are deliberately different. A refused handover is a laboratory
problem and somebody has to go and fix the record. An unchecked crate is a
process problem, because somebody has bypassed the service entirely, and that
is worse, since nothing has looked at it at all.

## A simplification, stated rather than hidden

This simulator reads the RO-Crate directly. A real vendor ordering system
would not: it would accept a comma-separated file or a web form, and something
would have to convert the crate into that shape first.

That something is an adapter. An adapter is tailored to one cycle and belongs
to a deployment, alongside the contract. This demonstration leaves that slot
empty by collapsing the adapter and the downstream tool into one program, and
somebody watching will reasonably spot it, so it is better said out loud.

## Running its tests

```
python -m pytest
```

12 tests. They stand on their own: this folder does not borrow the product's
test fixtures, and the product can be tested without this folder being
present.
