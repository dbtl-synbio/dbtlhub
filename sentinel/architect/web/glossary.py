#!/usr/bin/env python3
"""The words this project uses, each with what it is NOT, and where it lives.

    python3 architect/web/glossary.py          # read it in the terminal

WHY IT IS DATA AND NOT A PARAGRAPH
Everyone in the room says "agent" and means four different things by it. A
phase agent and a sentinel are both agents, do opposite jobs, and the whole
design turns on the difference; "contract" and "profile" are two files with
two different authors; and an RO-Crate, a knowledge graph and a handover
package are three names that are sometimes the same object and sometimes not.

So the glossary is a table, and three things are required of every entry:

    what it is          one sentence, no hedging
    what it is NOT      the confusion it is there to prevent
    where it lives      a file in this repository, or a property in the crate

The third is the point. A glossary that cannot be checked drifts away from the
code within a week and is then worse than nothing, because it is believed.
Every `where` that names a file is checked by a test, and a term whose file
has been moved or deleted fails it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Each group is (title, why this group is a group, [terms]).
# A term is (word, icon, what it is, what it is not, where it lives, a link
# into this interface or "").
GROUPS: list[tuple[str, str, list[tuple[str, str, str, str, str, str]]]] = [
    ("Who does what",
     "Four of these are called agents and two of them can refuse. Telling "
     "them apart is the whole design.",
     [
         ("the Architect", "architect",
          "The coordinator. It holds what was agreed, holds the one crate, "
          "and decides what happens after every verdict: go on, go back, ask "
          "the researcher, or stop.",
          "Not a validator and not a scientist. It never checks a handover "
          "and never does the science — it delegates both and records what "
          "came back.",
          "architect/architect.py, with its five parts beside it",
          "/?phase=architect#view"),
         ("a phase agent", "phase_agent",
          "The thing that does the work of one phase — design, build, test or "
          "learn — and writes what it produced into the crate.",
          "Not necessarily a program. A phase agent may be a person, a "
          "robot, or four months of fermentation; the Architect sees the same "
          "result either way.",
          "framework/agents/phase_*.py, and architect/mcp_server.py for one "
          "reached over a protocol",
          "/?phase=design#view"),
         ("a sentinel", "sentinel",
          "The agent standing at one handover. It reads what the upstream "
          "phase produced, holds it to a contract, and may refuse it.",
          "Not an opinion and not a model. The verdict is the validator's: a "
          "language model has no vote in it, and may only propose a repair "
          "the validator then re-checks.",
          "framework/agents/sentinel.py, one class for all four handovers",
          "/?sentinel=design_to_build#view"),
         ("the researcher", "researcher",
          "You. The one who answers the specification, decides what a "
          "refusal means, and whose name the agreed values are attributed to.",
          "Not a user of a wizard. Nothing is prefilled and no answer is "
          "invented on your behalf; where the system cannot know, it asks.",
          "architect/interface.py and the form in architect/forms/",
          "/?view=spec#view"),
         ("an engine", "",
          "Whichever model does the thinking, if any: deterministic rules, a "
          "CLI already logged in on this machine, a local Ollama, or an API "
          "with your own key.",
          "Not required. `no model — deterministic rules` runs the whole "
          "cycle offline, and every verdict in this system is reachable "
          "without a model.",
          "framework/llm.py and architect/web/setup.py",
          ""),
     ]),
    ("What travels, and what it is checked against",
     "A handover is the only thing that crosses a phase boundary. These are "
     "the words for it and for the rules it is held to.",
     [
         ("a handover", "go_on",
          "One phase's work, handed to the next. There are exactly four in a "
          "cycle: design→build, build→test, test→learn, learn→design.",
          "Not a file transfer. It is the moment a receiving phase can "
          "either accept the work or refuse it, which is why each one has an "
          "agent standing on it.",
          "framework/DESIGN_TO_BUILD.md, and HANDOVERS in architect/contract.py",
          ""),
         ("a package", "",
          "The handover itself as an object: the crate plus what sits beside "
          "it — the order, the bindings, the limits, who produced it and when.",
          "Not the same as the crate. Our contracts check paths in the "
          "package — `order.items`, `bindings` — as well as entities in the "
          "crate, and a crate alone fails every one of those.",
          "produced by each phase agent's package(), checked by "
          "framework/validator.py",
          ""),
         ("a contract", "",
          "The file that says what a handover must carry. Written by a "
          "person, in YAML, with the reason for each check beside the check.",
          "Not code. A sentinel for a new handover is a contract file "
          "dropped in a folder and no Python at all.",
          "framework/contracts/*.yaml, and template/MAKE_A_SENTINEL.md for "
          "writing one",
          ""),
         ("a profile", "",
          "What one use case requires on top of the shared contract: its "
          "identifier formats, its mandatory measurements, its storage rules.",
          "Not a second contract. Bioprospecting and biomanufacturing "
          "disagree in a profile rather than by forking the framework.",
          "framework/contracts/profiles/*.json",
          ""),
         ("a workflow", "phase_agent",
          "What the laboratory actually does, step by step, and which step "
          "each handover follows. It decides how many things a run is about.",
          "Not a contract. A contract says what must travel; a workflow says "
          "what happens. A contract with no workflow is a rule with nothing "
          "to apply to.",
          "architect/workflows/*.yaml, recorded in the crate as a "
          "schema:HowTo and a prov:Plan",
          "/?view=workflow#view"),
         ("the specification", "researcher",
          "What was agreed before anything ran: the objective, the target, "
          "the limits, who is answerable, and which laboratory's words the "
          "crate is written in.",
          "Not a settings page. Every field says what it would stop if left "
          "unanswered, and the run will not start while a required one is "
          "empty.",
          "architect/specification.py and architect/forms/",
          "/?view=spec#view"),
     ]),
    ("What comes out",
     "One crate per run, and it only ever grows. Everything below is read "
     "out of it rather than kept somewhere else.",
     [
         ("the crate", "crate",
          "An RO-Crate: one folder with one metadata file describing "
          "everything in it. One per run, append-only, and it is the record.",
          "Not a report produced at the end. It exists from the first phase "
          "and every agent writes into the same one.",
          "runs/<run>/crate/ro-crate-metadata.json, written by "
          "framework/crate_store.py",
          "/?view=crate#view"),
         ("the knowledge graph", "graph",
          "The same crate read as nodes and edges. `runs/<run>/graph/run.nt` "
          "is it lifted to N-Triples for querying.",
          "Not a second database. There is no store behind this: the crate "
          "IS the graph, said twice in two formats.",
          "framework/kg.py, shown by architect/web/kgview.py",
          "/?view=graph#view"),
         ("a verdict", "accepted",
          "What a sentinel decided about one handover: accepted, "
          "accepted_with_flags, or refused.",
          "Not a log line. It is an entity in the crate, with the contract "
          "it was held to and how many checks actually ran — because a "
          "verdict after no checks is a different claim.",
          "dbtl:verdict on a #check/... CreateAction in the crate",
          "/?view=graph#view"),
         ("a finding", "refused",
          "One thing a sentinel reported, in the contract author's own "
          "words, pointing at the entity it is about.",
          "Not an error message from this software. The wording comes from a "
          "contract a person wrote, which is why the field that carries it is "
          "called message_from_contract on the way out.",
          "a PropertyValue hanging off the verdict, with about and dbtl:path",
          "/?view=graph#view"),
         ("a move", "go_on",
          "What the Architect decided to do about a verdict: GO_ON, GO_BACK, "
          "ASK or STOP.",
          "Not the verdict. A refusal does not by itself say what happens "
          "next; deciding that is the Architect's only real job.",
          "Move in architect/contract.py, policy in architect/route.py",
          ""),
         ("the ledger", "ledger",
          "An append-only JSONL per run: every step, every move, every "
          "reason, and which engine ran.",
          "Not a debug log. It is the thing that makes a big-model against "
          "small-model comparison a query rather than a separate experiment.",
          "runs/<run>/architect.jsonl, written by framework/ledger.py",
          ""),
     ]),
    ("How other people's agents join in",
     "The point of the project is that none of this is ours alone.",
     [
         ("MCP", "",
          "The Model Context Protocol: JSON-RPC 2.0 over standard input and "
          "output. The Architect's two sockets — run a phase, check a "
          "handover — speak it, so an agent can be a process rather than a "
          "Python import.",
          "Not a server you deploy. There is no port and no daemon: the "
          "coordinator starts the process, owns it for the run, and ends it.",
          "architect/mcp.py, architect/mcp_server.py, architect/MCP.md",
          ""),
         ("sentinel-oo", "sentinel",
          "A second, independent implementation of a handover check, by Anil "
          "Wipat — deployable as a service and reachable over MCP.",
          "Not a copy of this one. Its rules apply to entities in a crate "
          "where ours apply to paths in a package, and the useful question is "
          "whether the two agree. On six example crates they do, 6/6.",
          "dbtlhub/sentinel-oo, run here by framework/oo_contract.py",
          ""),
         ("a run", "",
          "One turn of the cycle, with a name. Everything it produces lives "
          "in one folder under `runs/`.",
          "Not a session. Closing the browser loses the form and the log and "
          "keeps the crate and the ledger: the disk is the record.",
          "runs/<run>/, named by the specification's own run_id field",
          "/?view=graph#view"),
     ]),
]


def terms() -> list[tuple]:
    """Every term, flat, for a test or a script to walk."""
    return [t for _, _, group in GROUPS for t in group]


def files_named() -> list[tuple[str, Path]]:
    """Each term with a path in its `where`, as (word, path).

    Only the paths: a `where` may also name a crate property, which is not a
    file and is checked by reading a crate rather than the filesystem. What
    this returns is what a test can check cheaply and must.
    """
    import re                                              # noqa: PLC0415

    # A path in this repository, and nothing that merely contains a slash:
    # `#check/... CreateAction` is an entity id and `dbtl:verdict` a property.
    # Both were read as filenames by the first version of this, which then
    # reported a missing file that had never existed.
    looks_like = re.compile(r"^[A-Za-z_][\w./*-]*(\.\w+|/)$")
    out: list[tuple[str, Path]] = []
    for word, _icon, _is, _not, where, _link in terms():
        for piece in where.replace(",", " ").split():
            piece = piece.rstrip(".,")
            if (not looks_like.match(piece) or ":" in piece
                    or piece.startswith(("runs/", "dbtlhub/"))):
                continue
            bare = piece.replace("*", "")
            out.append((word, (ROOT / bare).parent if "*" in piece
                        else ROOT / bare))
    return out


def main() -> None:
    print(f"\n{'=' * 78}\nTHE WORDS, AND WHERE EACH ONE LIVES\n{'=' * 78}")
    for title, why, group in GROUPS:
        print(f"\n{title}\n  {why}\n")
        for word, _icon, is_, not_, where, _link in group:
            print(f"  {word}")
            print(f"      is      {is_}")
            print(f"      is not  {not_}")
            print(f"      lives   {where}")
    missing = [(word, path) for word, path in files_named() if not path.exists()]
    print(f"\n  {len(terms())} terms, {len(files_named())} paths named, "
          f"{len(missing)} of them missing.")
    for word, path in missing:
        print(f"    {word}: {path}")
    print()
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
