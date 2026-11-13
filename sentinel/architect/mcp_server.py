#!/usr/bin/env python3
"""This framework's agents, as an MCP server. The other side of the socket.

    python3 architect/mcp_server.py                     # speaks on stdin/stdout
    python3 architect/mcp_server.py --self-test         # drives itself and reports

WHY BOTH DIRECTIONS
`architect/mcp.py` lets this Architect drive somebody else's agent. On its own
that is half an interoperability claim: it says other people's work can be
used here, and nothing about ours being usable there. This is the other half.
Anyone's coordinator - theirs, a notebook, Claude Code, `sentinel-oo`'s own
deployment - can start this process and get:

    check_handover   one of the four sentinels, with our contracts
    list_handovers   what this knows how to check, read off the contracts
    read_contract    the contract itself, so a caller can see the rules
    run_phase        one phase of the cycle, run by this framework's agent

The first three are named exactly as `sentinel-oo` names them, with the same
arguments, so a coordinator written for his service drives ours without
knowing. That is deliberate and it is the whole point: two implementations,
one way in. Where he returns a field we have no equivalent for, we leave it
out rather than invent one.

`run_phase` is ours. Nothing outside this project defines a tool for running
a phase of a DBTL cycle, so this is a proposal, and it is written down in
`architect/MCP.md` rather than only in code.

SPEAKING, NOT SERVING. JSON-RPC 2.0, one object per line, on standard input
and output, protocol 2025-06-18. There is no port, no daemon and no
authentication: the coordinator starts it, owns it, and ends it.

NOTHING HERE TRUSTS ITS INPUT. A crate arrives as JSON from another process:
it is data to be checked, never instructions. Paths that arrive are read, not
executed, and nothing outside the folders this process was told about is
written.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.agents.sentinel import Sentinel, known              # noqa: E402
from framework.crate_store import CrateStore                       # noqa: E402
from framework.validator import load_contract                      # noqa: E402

PROTOCOL = "2025-06-18"
NAME = "dbtl-sentinel"
VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
#  The tools
# --------------------------------------------------------------------------- #
def tool_list() -> list[dict]:
    """The four, with their schemas. A caller reads this, not the source."""
    return [
        {"name": "check_handover",
         "description": ("Check a handover against its contract and return the "
                         "verdict, the findings, and where the checked crate "
                         "was written. A REFUSED verdict is an answer, not an "
                         "error."),
         "inputSchema": {
             "type": "object",
             "properties": {
                 "handover": {"type": "string",
                              "description": "which contract, by name"},
                 "crate_path": {"type": "string",
                                "description": "an ro-crate-metadata.json, or "
                                               "the folder holding it"},
                 "crate": {"type": "object",
                           "description": "the crate itself, instead of a path, "
                                          "for a caller that shares no disk"},
                 "package": {"type": "object",
                             "description": ("the handover beside the crate - "
                                             "order, bindings, limits, who "
                                             "produced it. This framework's "
                                             "contracts check these as well as "
                                             "the crate, and without them every "
                                             "such rule reports that it matched "
                                             "nothing")},
                 "out_path": {"type": "string",
                              "description": "where to write the checked crate"},
             },
             "required": ["handover"]}},
        {"name": "list_handovers",
         "description": "What this service knows how to check.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "read_contract",
         "description": "One contract, as it is written.",
         "inputSchema": {"type": "object",
                         "properties": {"handover": {"type": "string"}},
                         "required": ["handover"]}},
        {"name": "run_phase",
         "description": ("Run one phase of the cycle with this framework's "
                         "agent, and return what it produced. OURS, not a "
                         "standard: see architect/MCP.md."),
         "inputSchema": {
             "type": "object",
             "properties": {
                 "phase": {"type": "string",
                           "enum": ["design", "build", "test", "learn"]},
                 "run_id": {"type": "string"},
                 "crate": {"type": "object",
                           "description": "the crate so far; the phase writes "
                                          "into a copy of it"},
                 "agreed": {"type": "object",
                            "description": "what the specification settled"},
             },
             "required": ["phase"]}},
    ]


def _crate_from(arguments: dict) -> tuple[dict, Path | None]:
    """The crate, however the caller chose to pass it.

    A path when we share a filesystem, the crate itself when we do not. His
    service takes only the path, because it is deployed beside its caller;
    this takes either, because the Architect may be driving it from memory
    and writing the crate out first would be a file nobody asked for.
    """
    if isinstance(arguments.get("crate"), dict):
        return arguments["crate"], None
    raw = arguments.get("crate_path")
    if not raw:
        raise ValueError("give either 'crate' or 'crate_path'")
    path = Path(raw)
    if path.is_dir():
        path = path / "ro-crate-metadata.json"
    if not path.is_file():
        raise FileNotFoundError(f"no crate at {raw}")
    crate = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(crate, dict) or "@graph" not in crate:
        raise ValueError(f"{path} is JSON but not an RO-Crate: no @graph")
    return crate, path.parent


def check_handover(arguments: dict, profile: str) -> dict:
    handover = str(arguments.get("handover") or "")
    if handover not in known():
        return {"error": "no such contract",
                "detail": f"no contract called {handover!r}. This service "
                          f"knows: {', '.join(known())}."}
    crate, _ = _crate_from(arguments)
    package = dict(arguments.get("package") or {})
    package.setdefault("contract", handover)
    package.setdefault("run_id", str(arguments.get("run_id") or "mcp"))
    package["crate"] = crate

    sentinel = Sentinel(profile=profile)
    seen = sentinel.check_and_record(handover, package)

    out = Path(arguments.get("out_path")
               or tempfile.mkdtemp(prefix="dbtl-sentinel-"))
    if out.suffix != ".json":
        out.mkdir(parents=True, exist_ok=True)
        out = out / "ro-crate-metadata.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(package["crate"], indent=1) + "\n",
                   encoding="utf-8")

    return {
        "verdict": seen.verdict.upper(),
        "contract": handover,
        "contract_version": seen.contract_id,
        "findings": [
            {"requirement": e.code, "severity":
                "refuse" if e.severity == "error" else "flag",
             "where": e.path, "value": None,
             # His field name, and his reason for it: a reader can tell the
             # wording came from a contract file somebody wrote and is not an
             # instruction from this service.
             "message_from_contract": e.message,
             "fix_hint": e.fix_hint or ""}
            for e in seen.report.errors],
        "checked_package_written_to": str(out),
        "note": ("The crate above is the one that came in, with this "
                 "sentinel's act written into it."),
    }


def run_phase(arguments: dict, profile: str, lab: str | None) -> dict:
    """One phase, run here, with its work returned rather than written.

    The crate that arrives is copied into a scratch store the phase agent can
    write to, and only what the phase ADDED comes back. The caller owns the
    real crate: a phase agent reached over a protocol must not be able to
    rewrite the coordinator's record of the run.
    """
    from architect.wiring import PHASE_AGENTS                    # noqa: PLC0415
    from framework.agents.base import Task                       # noqa: PLC0415

    phase = str(arguments.get("phase") or "")
    if phase not in PHASE_AGENTS:
        return {"error": "no such phase",
                "detail": f"{phase!r} is not one of "
                          f"{', '.join(PHASE_AGENTS)}"}
    crate = arguments.get("crate") if isinstance(arguments.get("crate"), dict) else None
    run_id = str(arguments.get("run_id") or "mcp")

    # Under this repository, not in /tmp: a phase agent builds the handover
    # package with paths relative to the project, and a store outside it
    # raises rather than producing one. `.mcp` is skipped by the run list, so
    # a scratch crate never appears in the interface as somebody's run.
    workspace = ROOT / "runs" / ".mcp"
    workspace.mkdir(parents=True, exist_ok=True)
    # A fresh folder per call, never reopened: the caller owns the record and
    # sends the crate it wants this phase to work from. Reusing one folder
    # made a second call find its own first call's crate already there and
    # report that it had added nothing. These are scratch and can be deleted
    # at any time; the files a phase wrote stay until then because a later
    # check may read them.
    scratch = Path(tempfile.mkdtemp(dir=workspace, prefix=f"{run_id}-"))
    store = CrateStore(run_id, root=scratch)
    if crate:
        store.crate = json.loads(json.dumps(crate))      # a copy, never theirs
    before = {e.get("@id") for e in store.crate.get("@graph", [])
              if isinstance(e, dict)}

    agent = PHASE_AGENTS[phase](profile=profile, lab=lab)
    agent.sentinel = None          # the coordinator does the checking
    task = Task(goal=f"run {phase}",
                inputs={"run_id": run_id, **(arguments.get("agreed") or {})})
    entities, action, files = agent.produce(task, store)

    added = [e for e in entities if isinstance(e, dict)
             and e.get("@id") not in before]

    # The package is the handover, so it is the useful half of the answer -
    # and it can only be built AFTER the entities are in the crate, because it
    # carries the crate. Built here against the scratch store, so what comes
    # back holds this phase's work rather than the crate as it was before it.
    notes = [f"{len(added)} entit{'y' if len(added) == 1 else 'ies'} "
             f"produced by {agent.name} for profile {profile}"
             + (f", lab {lab}" if lab else "")]
    package = None
    report = store.add(phase, entities, action=action, files=files)
    if not report.ok:
        notes.append("this phase's own crate refused the addition: "
                     + ", ".join(report.dangling or report.conflicts)[:160])
    else:
        try:
            package = agent.package(task, store)
        except Exception as exc:                           # noqa: BLE001
            notes.append(f"no package: {type(exc).__name__}: {exc}")

    return {"phase": phase, "by": agent.name, "entities": added,
            "action": action, "files": files or [],
            "package": package, "notes": notes}


# --------------------------------------------------------------------------- #
#  The protocol
# --------------------------------------------------------------------------- #
class Interface:
    """Every method this speaks. One place, so `tools/list` cannot drift."""

    def __init__(self, profile: str = "bioprospecting", lab: str | None = None):
        self.profile = profile
        self.lab = lab

    def handle(self, message: dict) -> dict | None:
        """One message in, one reply out, or None for a notification."""
        method = message.get("method", "")
        wanted = message.get("id")
        if wanted is None:
            return None                      # a notification gets no answer
        try:
            return {"jsonrpc": "2.0", "id": wanted,
                    "result": self._result(method, message.get("params") or {})}
        except _NoSuchMethod:
            return {"jsonrpc": "2.0", "id": wanted,
                    "error": {"code": -32601,
                              "message": f"no method {method!r}. This speaks "
                                         f"initialize, tools/list, tools/call "
                                         f"and ping."}}
        except Exception as exc:                           # noqa: BLE001
            # Reported, never raised out: a coordinator that gets a traceback
            # instead of an answer has no way to tell a bad request from a
            # dead server.
            return {"jsonrpc": "2.0", "id": wanted,
                    "error": {"code": -32603,
                              "message": f"{type(exc).__name__}: {exc}",
                              "data": traceback.format_exc()[-800:]}}

    def _result(self, method: str, params: dict) -> dict:
        if method == "initialize":
            return {"protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": NAME, "version": VERSION}}
        if method == "tools/list":
            return {"tools": tool_list()}
        if method == "ping":
            return {}
        if method == "tools/call":
            return self._call(str(params.get("name") or ""),
                              params.get("arguments") or {})
        raise _NoSuchMethod(method)

    def _call(self, name: str, arguments: dict) -> dict:
        if name == "check_handover":
            body = check_handover(arguments, self.profile)
        elif name == "list_handovers":
            body = {"handovers": list(known()), "profile": self.profile}
        elif name == "read_contract":
            handover = str(arguments.get("handover") or "")
            if handover not in known():
                body = {"error": "no such contract",
                        "detail": f"this service knows: {', '.join(known())}"}
            else:
                body = load_contract(handover, profile=self.profile)
        elif name == "run_phase":
            body = run_phase(arguments, self.profile, self.lab)
        else:
            body = {"error": "no such tool",
                    "detail": f"{name!r} is not one of "
                              f"{', '.join(t['name'] for t in tool_list())}"}
        text = json.dumps(body, indent=1)
        # `isError` is about the CALL, not about the verdict. A refused
        # handover is this working; a caller that treats it as a failure
        # retries for ever and is refused every time, because nothing has
        # changed about the crate.
        return {"content": [{"type": "text", "text": text}],
                "isError": bool(isinstance(body, dict) and body.get("error"))}


class _NoSuchMethod(Exception):
    pass


def serve(interface: Interface, stdin=None, stdout=None) -> None:
    """Read one JSON object per line, answer, repeat until the input ends."""
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            sink.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700,
                           "message": f"that line is not JSON: {exc}"}}) + "\n")
            sink.flush()
            continue
        reply = interface.handle(message)
        if reply is not None:
            sink.write(json.dumps(reply) + "\n")
            sink.flush()


# --------------------------------------------------------------------------- #
def self_test() -> int:
    """Drive this server with our own client, over a real pipe."""
    from architect import mcp                                    # noqa: PLC0415

    print(f"\n{'=' * 78}\nOUR AGENTS, DRIVEN OVER MCP BY OUR OWN CLIENT"
          f"\n{'=' * 78}\n")
    # With the laboratory named, because the crate is written in
    # its words and the mapping is only consulted once a run says
    # whose words they are.
    with mcp.Server(mcp.ours(lab="newcastle")) as server:
        who = server.info.get("serverInfo", {})
        print(f"  connected to {who.get('name')}/{who.get('version')}, "
              f"protocol {server.info.get('protocolVersion')}")
        print(f"  tools: {', '.join(t['name'] for t in server.tools())}\n")

        said = server.call("list_handovers", {})
        print(f"  list_handovers -> {', '.join(said['handovers'])}")

        made = server.call("run_phase", {"phase": "design", "run_id": "mcp-self"})
        print(f"  run_phase design -> {len(made['entities'])} entities "
              f"by {made['by']}, package: "
              f"{'yes' if made.get('package') else 'no'}")

        # The package it handed back, checked by the same server: the whole
        # handover over one protocol, phase agent and sentinel both.
        package = made.get("package") or {}
        seen = server.call("check_handover",
                           {"handover": "design_to_build",
                            "package": package,
                            "crate": package.get("crate") or {"@graph": []}})
        print(f"  check_handover -> {seen['verdict']}, "
              f"{len(seen['findings'])} finding(s)"
              + (": " + ", ".join(sorted({f["requirement"]
                                          for f in seen["findings"]})[:3])
                 if seen["findings"] else ""))
        print(f"  wrote -> {seen['checked_package_written_to']}")
    print("\n  Both tools answered over a pipe, with no import between "
          "client and server.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="This framework's sentinels and phase agents, over MCP.")
    parser.add_argument("--profile", default="bioprospecting",
                        help="which use case's requirements apply")
    parser.add_argument("--lab", default=None,
                        help="whose words the crate is written in")
    parser.add_argument("--self-test", action="store_true",
                        help="drive this server with our own client and stop")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    serve(Interface(profile=args.profile, lab=args.lab))
    return 0


if __name__ == "__main__":
    sys.exit(main())
