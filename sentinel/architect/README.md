# The Architect

The centre of the agreed picture. Eight agents stand around it: four that do
the work and may be people rather than programs, and four that check what the
first four produced and may refuse it. The Architect does neither job.

```bash
python3 architect/architect.py        # the loop, with the verdicts scripted
```

It owns five things and nothing else.

| | | |
|---|---|---|
| 1 | [`consultation.py`](consultation.py) | getting to a first design, with the researcher in the room |
| 2 | [`specification.py`](specification.py) | what was agreed, and what the process requires regardless |
| 3 | [`conversation.py`](conversation.py) | what to say when a check fails |
| 4 | [`route.py`](route.py) | go on, go back, ask, stop |
| 5 | [`memory.py`](memory.py) | the crate that grows, including one it adopted |

[`contract.py`](contract.py) holds the seams between them: `Verdict`, `Move`,
`Finding`, `Checked`, `Question`, `Decision`, `Step`, and one `Protocol` per
part. It was written before the parts, which is the only reason five modules
written separately fit together.

Each part runs on its own and shows what it does:

```bash
python3 architect/consultation.py     # both ways in: from nothing, and from a workflow
python3 architect/specification.py    # what is agreed vs what cannot be negotiated
python3 architect/conversation.py     # findings turned into something a person can decide
python3 architect/route.py            # the policy over a scripted sequence, loop caught
python3 architect/memory.py           # adopting the two real crates in this project
python3 architect/interface.py        # the questions put to a person, scripted
python3 architect/wiring.py           # the real phase agents and sentinels, under it
```

## Two sockets, and one protocol for reaching them

Everything around the Architect arrives through one of two callables, fixed
in `contract.py` and `architect.py`:

```python
Runner  = Callable[[phase, Architect], PhaseResult]            # does the work
Checker = Callable[[handover, package, Architect], Checked]    # checks it
```

That is why a phase run by a person and a phase run by a program are the same
object to it. What those sockets were not, until 13 November 2026, is
reachable from outside this process: to plug an agent in you had to write
Python here and import it.

| | |
|---|---|
| [`mcp.py`](mcp.py) | the client — `Server`, `checker_over_mcp()`, `runner_over_mcp()` |
| [`mcp_server.py`](mcp_server.py) | this framework's sentinels and phase agents **as** a server |
| [`MCP.md`](MCP.md) | the picture, the four tools, what is proven and what is not |

```bash
python3 architect/mcp.py                     # this Architect drives sentinel-oo
python3 architect/mcp_server.py --self-test  # our agents, driven over a pipe
```

In-process stays the default and stays fastest. The protocol is chosen, per
phase or per handover.

## The rules worth knowing before reading the code

**A phase agent may be a person.** `run_phase` takes a callable. In a real
deployment that callable is a phase agent, a container, or an email to
somebody who types the answer back. A centre that can only call Python
functions cannot admit a human workflow, and the agreed picture says it must.

**What was agreed and what is required are kept apart, structurally.** The
researcher decides the target, the equipment, the budget. The process requires
that a measurement carries its unit and a prediction states its uncertainty.
The first is negotiable; the second is not, and `specification.py` raises
rather than let the second be set from the first. Changing a requirement is a
change to a profile or a contract — a group decision with a reviewer, not a
line in one run's specification.

**The policy is one file and one ordered list.** `route.py` is the piece a
group will argue about, so it reads on its own: ten rules, first match wins,
each rule's docstring is its reason, and that reason is carried verbatim into
the ledger. It also guards against loops — a phase re-run for the same finding
code is not sent back a second time, because a second identical failure is
determinism, not a transient.

**Nothing is repaired by inventing it.** Where the only fix would fabricate a
record, `conversation.py` says so and offers the three honest options: find the
record, drop the item, or accept the gap and state it.

**An adopted crate is as protected as one we wrote.** `memory.py` makes a
foreign crate *become* the store's crate, so the crate store's three refusals —
overwrite, identifier collision, dangling reference — defend it identically. It
reports what it took on rather than adopting in silence: size, dialect, whether
a profile is declared, and what it could not interpret.

## What is not done

- **The interface is a terminal only.** `interface.py` shows a question and
  reads an answer, and is driven by injected `input_fn`/`output_fn` so it can
  be scripted. There is no web page and no chat.
- **No run has been driven by a person end to end.** `wiring.py` connects the
  four real phase agents and the four real sentinels, but the questions in it
  are not answered — they are collected and counted.
- **The researcher is a string.** Approvals are recorded as text, not as a
  signed act. Anybody can type anybody's name.
- **A model is nowhere, deliberately.** Each part names the seam where one
  would help — `guess_profile`, `interpret_free_text`, `map_unknown_key`,
  `rank_questions`, `phrasing_hook` — and every one defaults to off. Nothing
  here reads an API key.
- **`route.py` and `conversation.py` have no tests of their own.** The demos
  assert their way through a scripted sequence, which is not the same thing.
