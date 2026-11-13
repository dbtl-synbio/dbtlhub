# One way in: phase agents and sentinels over MCP

The Architect talks to the researcher. Everything else talks to the Architect,
and until now "talking to the Architect" meant being Python in this
repository. That is the wrong shape for a project whose subject is
interoperability: it makes the Architect the owner of everybody's code.

So the two sockets it already had now speak a protocol.

```
                       the researcher
                             │
                      the Architect  ──── the crate that grows
                             │
            ┌────────────────┴────────────────┐
         Runner                            Checker
      "run this phase"                 "check this handover"
            │                                │
      ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌  Model Context Protocol  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
            │                                │
   a phase agent:                   a sentinel:
   ours, another lab's,             ours (architect/mcp_server.py),
   a person, a four-month           sentinel-oo, anyone's
   fermentation
```

JSON-RPC 2.0, one object per line, on standard input and output, protocol
`2025-06-18`. No port, no daemon, no authentication: the Architect starts the
process, owns it for the run, and ends it.

**Nothing changes by default.** The in-process wiring stays the default and
stays the fastest path. This is chosen, per phase or per handover.

## Driving somebody else's sentinel

```python
from architect import mcp
from architect.wiring import phase_runner

with mcp.Server(mcp.sentinel_oo()) as his:            # his, from source
    check = mcp.checker_over_mcp(his)
    arch.run_phase("design", phase_runner(lab="newcastle"), check)
```

```bash
python3 architect/mcp.py        # all six example crates, over the pipe
```

| crate | verdict over MCP |
|---|---|
| `valid` | accepted |
| `dangling-reference` | refused · `everything_the_crate_lists_is_present` |
| `edge-handling-in-prose` | refused · `edge_handling_is_recorded` |
| `missing-conformsto` | refused · `declares_a_profile` |
| `missing-gene-calling-mode` | refused · `edge_handling_is_recorded` |
| `mode-in-prose` | refused · `edge_handling_is_recorded` |

The same six verdicts `scripts/compare_sentinels.py` gets in process. Nothing
of his is imported: they came over a pipe.

## Being driven

```bash
python3 architect/mcp_server.py --profile bioprospecting --lab newcastle
python3 architect/mcp_server.py --self-test      # our client drives our server
```

```json
{"mcpServers": {"dbtl-sentinel": {
  "command": "python3",
  "args": ["architect/mcp_server.py", "--profile", "bioprospecting"]}}}
```

| Tool | What it does |
|---|---|
| `check_handover` | one of the four sentinels, with our contracts |
| `list_handovers` | what this knows how to check, read off the contracts folder |
| `read_contract` | the contract itself, so a caller can see the rules |
| `run_phase` | one phase of the cycle, run by this framework's agent |

The first three are named and shaped as `sentinel-oo` names them, so a
coordinator written for his service drives ours without knowing. Where he
returns a field we have no equivalent for, we leave it out rather than invent
one.

## `run_phase` is a proposal, not a standard

Nothing outside this project defines a tool for running a phase of a DBTL
cycle. This one takes `phase`, `run_id`, the `crate` so far and what was
`agreed`; it gives back the entities the phase produced, the action that
produced them, the files, and **the handover package**, which is the useful
half. Said plainly because a proposal that reads like a standard is how a
project ends up with two of them.

The phase agent works on a copy of the crate and only what it *added* comes
back. A phase reached over a protocol must not be able to rewrite the
coordinator's record of the run.

## Two things building this found

**A crate passed by value loses its files.** `hold data` asks whether the file
an entity stands for exists and is not empty — a question about a folder, not
about JSON. Writing our in-memory crate into an empty scratch directory and
pointing `sentinel-oo` at it refused his own `valid` example for files it
could not see. So the checker sends the run's real crate directory, flushed
first. With no crate on disk it sends the copy, and that demand then reports
honestly that it could not be run.

**Our contracts need more than the crate.** His rules are about entities in a
crate; ours are about paths in a package — `order.items`, `bindings`,
`produced_by`. Sent a crate alone, every one of those reported that it matched
nothing, and a handover that was sound came back refused. The client now reads
each server's `tools/list` schema and sends `package` only to a server that
declares it. The first version of our own server did not declare it, and the
schema check is what caught that.

## What is proven, and what is not

**Proven.** `checker_over_mcp` against `sentinel-oo`'s agent interface — a
real MCP server written by somebody else, whose manual said it had never been
tried against a real client. On 13 November 2026 it was, by this code, and it
answered correctly at the first attempt. Six crates, verdicts matching the
in-process comparison. Also: the Architect's own `run_phase` with a sentinel a
process away, the act landing in the crate that grows.

**Not proven.** `runner_over_mcp` has no outside witness: no phase agent
anywhere speaks MCP yet, so it is tested only against our own server. And the
containerised form (`docker run -i --rm sentinel-oo:dev --agent-interface`) is
a `Spec` with a different argv and has not been run here — the image is not
built on this machine.
