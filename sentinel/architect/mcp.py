#!/usr/bin/env python3
"""The Architect's uniform socket: phase agents and sentinels over MCP.

    python3 architect/mcp.py            # talk to sentinel-oo and show what happens

WHAT THIS IS FOR
The Architect already has exactly two sockets, and they are the right two:

    Runner  = Callable[[phase, Architect], PhaseResult]     does the work
    Checker = Callable[[handover, package, Architect], Checked]   checks it

Everything around the Architect goes through one or the other, which is why a
phase run by a person and a phase run by a program are the same object to it.
What those sockets are NOT, today, is reachable from outside this process: to
plug an agent in you have to write Python in this repository and import it.
That makes the Architect the centre of a diagram and the owner of everybody's
code, which is the opposite of an interoperability project.

This module makes the two sockets speak a protocol instead. A phase agent or a
sentinel becomes a process the Architect starts and talks to over the Model
Context Protocol - JSON-RPC 2.0, one object per line, on standard input and
output. Then:

    * Newcastle's build agent can be Newcastle's, in Newcastle's language,
      and still run in this cycle
    * `sentinel-oo`, which already speaks MCP, can guard a handover here
      without this framework importing a line of it
    * a phase that is four months of fermentation can be a server that says
      "not yet" until it is done
    * and our own agents can be driven by somebody else's coordinator, which
      is `architect/mcp_server.py`, the other half of this

NOTHING CHANGES BY DEFAULT. The in-process wiring stays the default and stays
the fastest path. This is chosen, per handover or per phase.

WHAT IS PROVEN AND WHAT IS NOT
`checker_over_mcp` is tested against Anil Wipat's `sentinel-oo` agent
interface, which is a real MCP server written by somebody else. His manual
said it had never been tried against a real client; on 13 November 2026 it
was, by this code, and it answered correctly at the first attempt.

`runner_over_mcp` has no such outside witness: no phase agent anywhere speaks
MCP yet, so the tool it calls - `run_phase` - is a shape proposed here and
implemented in `architect/mcp_server.py`. It is tested against that. Said
plainly because a proposal that reads like a standard is how a project ends
up with two of them.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from architect.architect import PhaseResult                      # noqa: E402
from architect.contract import Checked, Finding, Verdict         # noqa: E402

PROTOCOL = "2025-06-18"
START_TIMEOUT_S = 30.0
CALL_TIMEOUT_S = 300.0        # a phase agent may be slow; a dead one is worse


class McpError(RuntimeError):
    """The server refused, failed, or did not answer.

    Carries what the server said rather than a summary of it: an error from
    somebody else's agent is evidence about their agent, and rewording it
    loses the only thing that makes it useful.
    """


# --------------------------------------------------------------------------- #
#  The client
# --------------------------------------------------------------------------- #
@dataclass
class Spec:
    """How to start one server. A command, its arguments, its environment."""
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    name: str = ""
    cwd: str | None = None

    def __post_init__(self) -> None:
        self.name = self.name or Path(self.argv[0]).name


class Server:
    """One MCP server, as a child process, for as long as it is needed.

    Opened once per run rather than once per call: a server that has to be
    started for every handover cannot hold a model in memory, and the time
    spent starting it would be most of the time spent checking.
    """

    def __init__(self, spec: Spec):
        self.spec = spec
        self.info: dict = {}
        self._id = 0
        self._stderr: list[str] = []
        if shutil.which(spec.argv[0]) is None and not Path(spec.argv[0]).exists():
            raise McpError(f"{spec.argv[0]!r} is not on this machine, so the "
                           f"server {spec.name!r} cannot be started")
        self.process = subprocess.Popen(
            spec.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            cwd=spec.cwd, env={**os.environ, **spec.env})
        # Drained in a thread, because a server that writes a lot to stderr
        # fills the pipe and blocks for ever while looking merely slow.
        self._drain = threading.Thread(target=self._read_stderr, daemon=True)
        self._drain.start()
        self.info = self._request("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "dbtl-architect", "version": "0.1.0"},
        }, timeout=START_TIMEOUT_S)
        self._notify("notifications/initialized")

    # ---- the protocol ------------------------------------------------------
    def _read_stderr(self) -> None:
        for line in self.process.stderr:                    # pragma: no cover
            self._stderr.append(line.rstrip())
            del self._stderr[:-50]

    def _send(self, message: dict) -> None:
        if self.process.poll() is not None:
            raise McpError(f"{self.spec.name} has stopped "
                           f"(exit {self.process.returncode}). "
                           f"{self.said() or 'It said nothing.'}")
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise McpError(f"{self.spec.name} closed its input: {exc}. "
                           f"{self.said()}") from exc

    def _notify(self, method: str, params: dict | None = None) -> None:
        """A message with no id. The protocol says it gets no answer."""
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(self, method: str, params: dict | None = None, *,
                 timeout: float = CALL_TIMEOUT_S) -> dict:
        self._id += 1
        wanted = self._id
        self._send({"jsonrpc": "2.0", "id": wanted, "method": method,
                    "params": params or {}})
        answer: list[dict] = []

        def read() -> None:
            while True:
                line = self.process.stdout.readline()
                if not line:
                    return
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue      # a server that also prints is not an error
                if message.get("id") == wanted:
                    answer.append(message)
                    return

        waiter = threading.Thread(target=read, daemon=True)
        waiter.start()
        waiter.join(timeout)
        if not answer:
            gone = self.process.poll()
            if gone is not None:
                # It died rather than went quiet, and the difference matters:
                # a missing dependency in somebody else's server looks exactly
                # like a slow one unless the exit is reported.
                raise McpError(
                    f"{self.spec.name} stopped without answering {method!r} "
                    f"(exit {gone}). {self.said() or 'It said nothing.'}")
            raise McpError(
                f"{self.spec.name} did not answer {method!r} within "
                f"{timeout:g}s and is still running. "
                f"{self.said() or 'It said nothing on stderr.'}")
        message = answer[0]
        if "error" in message:
            fault = message["error"]
            raise McpError(f"{self.spec.name} refused {method!r}: "
                           f"{fault.get('message', fault)}")
        return message.get("result", {})

    # ---- what a caller uses ------------------------------------------------
    def tools(self) -> list[dict]:
        return self._request("tools/list").get("tools", [])

    def call(self, tool: str, arguments: dict, *,
             timeout: float = CALL_TIMEOUT_S) -> Any:
        """Run one tool and return what it said, parsed if it is JSON.

        A tool that reports `isError` is raised rather than returned. A
        REFUSED verdict is NOT that: a refusal is the answer working.
        """
        result = self._request("tools/call",
                               {"name": tool, "arguments": arguments},
                               timeout=timeout)
        blocks = result.get("content") or []
        text = "\n".join(b.get("text", "") for b in blocks
                         if isinstance(b, dict) and b.get("type", "text") == "text")
        if result.get("isError"):
            raise McpError(f"{self.spec.name}.{tool} failed: {text or result}")
        try:
            return json.loads(text) if text.strip() else result
        except json.JSONDecodeError:
            return text

    def said(self) -> str:
        return " / ".join(self._stderr[-5:])

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
            except Exception:                              # noqa: BLE001
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:              # pragma: no cover
                self.process.kill()
        # The other two pipes as well, or a long-lived coordinator leaks a
        # file descriptor per server it has ever started.
        for pipe in (self.process.stdout, self.process.stderr):
            try:
                pipe.close()
            except Exception:                              # noqa: BLE001
                pass

    def __enter__(self) -> "Server":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# --------------------------------------------------------------------------- #
#  Known servers
# --------------------------------------------------------------------------- #
def sentinel_oo(contracts: Path | str | None = None,
                *, by: str = "the Architect") -> Spec:
    """Anil Wipat's `sentinel-oo`, run from the sibling checkout.

    From source, not from the container: the image has to be built and the
    paths it is given are paths inside it, which is a second thing to get
    right before anything works at all. `docker run -i --rm ... sentinel-oo:dev
    --agent-interface` is the deployed form and this client speaks to it
    identically - it is a `Spec` with a different argv.
    """
    from framework.oo_contract import dbtlhub                   # noqa: PLC0415
    hub = dbtlhub()
    if hub is None:
        raise McpError("the dbtlhub checkout is not on this machine, so "
                       "sentinel-oo cannot be started from source")
    source = hub / "sentinel-oo" / "src"
    if not source.is_dir():
        raise McpError(f"{source} is not here")
    return Spec(argv=[sys.executable, "-m", "sentinel_oo", "--agent-interface",
                      "--by", by],
                env={"PYTHONPATH": str(source),
                     "SENTINEL_CONTRACTS": str(
                         contracts or hub / "sentinel-oo" / "examples" / "contracts")},
                name="sentinel-oo")


def ours(profile: str = "bioprospecting", lab: str | None = None) -> Spec:
    """This framework's own agents, as a server. The other half of the socket.

    Same protocol in both directions, so a team can plug their sentinel into
    this Architect and plug these phase agents into their coordinator, and
    neither of us has to import the other.
    """
    argv = [sys.executable, str(ROOT / "architect" / "mcp_server.py"),
            "--profile", profile]
    if lab:
        argv += ["--lab", lab]
    return Spec(argv=argv, name="dbtl-sentinel", cwd=str(ROOT))


# --------------------------------------------------------------------------- #
#  Socket 1: a sentinel over MCP
# --------------------------------------------------------------------------- #
VERDICTS = {"ACCEPTED": Verdict.ACCEPTED, "REFUSED": Verdict.REFUSED,
            "ACCEPTED_WITH_FLAGS": Verdict.ACCEPTED_WITH_FLAGS,
            "accepted": Verdict.ACCEPTED, "refused": Verdict.REFUSED,
            "accepted_with_flags": Verdict.ACCEPTED_WITH_FLAGS}


def _finding_from(raw: dict) -> Finding:
    """One of their findings, in the Architect's terms.

    `message_from_contract` is his field name and the reason for it is worth
    keeping: a reader can tell the wording came from a contract somebody
    wrote, and is not an instruction from the service. We read either name.
    """
    severity = str(raw.get("severity", "refuse")).lower()
    return Finding(
        code=str(raw.get("requirement") or raw.get("code") or "unnamed"),
        path=str(raw.get("where") or raw.get("path") or ""),
        message=str(raw.get("message_from_contract") or raw.get("message") or ""),
        blocking=severity in ("refuse", "error"),
        fix_hint=str(raw.get("fix_hint") or ""))


def _accepts(server: Server, tool: str) -> set[str]:
    """What one tool says it takes, from the server's own `tools/list`.

    Asked once and remembered. A client that guesses at another team's
    arguments is a client that breaks the day they add one; a client that
    reads the schema is why the schema is published.
    """
    cache = getattr(server, "_schemas", None)
    if cache is None:
        cache = {t["name"]: set((t.get("inputSchema") or {})
                                .get("properties", {}))
                 for t in server.tools()}
        server._schemas = cache                             # noqa: SLF001
    return cache.get(tool, set())


def checker_over_mcp(server: Server, *, workspace: Path | str | None = None,
                     merge_back: bool = True):
    """A `Checker` that asks an MCP server for the verdict.

    The seam is not free, and the cost is worth naming. His tool takes a path
    on HIS filesystem and writes the checked crate somewhere else; ours takes
    a package in memory and expects the sentinel's act to land in the crate
    that is growing. So each check writes the crate out, calls the tool, and
    reads back what the server added, merging only entities that are new.

    `merge_back=False` keeps the verdict and leaves our crate untouched, which
    is what you want when the server is somebody else's and the run is only
    being compared.

    A CRATE PASSED BY VALUE LOSES ITS FILES. His `hold data` demand asks
    whether the file an entity stands for exists and is not empty, which is a
    question about a folder, not about JSON. Writing our in-memory crate into
    an empty scratch directory and pointing him at that refuses a sound crate
    for the files it cannot see - measured, on his own `valid` example, which
    he accepts when given the real folder. So the real folder is what this
    sends: the run's own crate directory, flushed first so that what he reads
    is what we hold. The scratch copy is the fallback for an Architect that
    has no crate on disk, and then `hold data` reports honestly that it could
    not be run.
    """
    import tempfile                                            # noqa: PLC0415
    folder = Path(workspace or tempfile.mkdtemp(prefix="architect-mcp-"))
    folder.mkdir(parents=True, exist_ok=True)

    def check(handover: str, package: dict, arch) -> Checked:
        crate = package.get("crate") or {"@graph": []}
        store = getattr(getattr(arch, "memory", None), "store", None)
        here = None
        if package.get("crate_dir"):
            here = Path(package["crate_dir"])
        elif store is not None:
            try:
                store.flush()
                here = store.dir
            except Exception:                              # noqa: BLE001
                here = None
        if here is None:
            here = folder / f"{getattr(arch, 'run_id', 'run')}-{handover}"
            here.mkdir(parents=True, exist_ok=True)
            (here / "ro-crate-metadata.json").write_text(
                json.dumps(crate, indent=1) + "\n", encoding="utf-8")
        out = folder / f"{getattr(arch, 'run_id', 'run')}-{handover}-checked"

        arguments: dict[str, Any] = {"handover": handover,
                                     "crate_path": str(here),
                                     "out_path": str(out)}
        # What else this server says it takes, read from its own schema rather
        # than assumed. It matters: HIS contracts are about entities in a
        # crate, OURS are about paths in a package - `order.items`, `bindings`
        # - and a crate alone makes every one of those report that it matched
        # nothing. A server that declares `package` gets the package.
        takes = _accepts(server, "check_handover")
        if "crate" in takes:
            arguments["crate"] = crate
        if "package" in takes:
            arguments["package"] = {k: v for k, v in package.items()
                                    if k not in ("crate", "crate_dir")}
        answer = server.call("check_handover", arguments)
        if not isinstance(answer, dict):
            raise McpError(f"{server.spec.name} answered check_handover with "
                           f"{type(answer).__name__}, not an object: {answer!r:.200}")

        findings = [_finding_from(f) for f in answer.get("findings") or []]
        said = str(answer.get("verdict", "")).strip()
        verdict = VERDICTS.get(said)
        if verdict is None:
            raise McpError(f"{server.spec.name} reported a verdict this "
                           f"Architect does not know: {said!r}")
        if verdict is Verdict.ACCEPTED and findings:
            verdict = Verdict.ACCEPTED_WITH_FLAGS

        trace = [f"{server.spec.name} "
                 f"{answer.get('contract', handover)}"
                 f"/{answer.get('contract_version', '?')}, over MCP"]
        written = answer.get("checked_package_written_to")
        if merge_back and written:
            trace.append(_merge(Path(written), arch, handover))
        elif written:
            trace.append(f"its checked crate is at {written}; not merged")
        return Checked(handover=handover, verdict=verdict, findings=findings,
                       trace=trace)

    return check


def _merge(written: Path, arch, handover: str) -> str:
    """Bring back what the server wrote into our crate, and nothing else.

    Only entities whose `@id` we have not got: the crate is append-only and a
    sentinel does not get to revise what a phase recorded. Said in the trace
    either way, because a merge that happened silently and a merge that did
    not happen look identical in the crate afterwards.
    """
    store = getattr(getattr(arch, "memory", None), "store", None)
    if store is None:
        return "nothing to merge into: this Architect has no crate store"
    path = written if written.is_file() else written / "ro-crate-metadata.json"
    if not path.is_file():
        return f"it reported writing {written}, and there is no file there"
    try:
        theirs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"its checked crate could not be read ({exc})"

    here = {e.get("@id") for e in store.crate.get("@graph", [])
            if isinstance(e, dict)}
    fresh = [e for e in theirs.get("@graph") or []
             if isinstance(e, dict) and e.get("@id") not in here]
    if not fresh:
        return "it added nothing to the crate that was not already there"
    report = store.add(handover, fresh)
    store.flush()
    if not report.ok:
        return (f"its {len(fresh)} new entit"
                f"{'y' if len(fresh) == 1 else 'ies'} were refused by this "
                f"crate: {', '.join(report.dangling or report.conflicts)[:160]}")
    return (f"merged {len(report.added)} entit"
            f"{'y' if len(report.added) == 1 else 'ies'} it wrote into this crate")


# --------------------------------------------------------------------------- #
#  Socket 2: a phase agent over MCP
# --------------------------------------------------------------------------- #
def runner_over_mcp(servers: dict[str, Server], *, fallback=None):
    """A `Runner` that asks an MCP server to run a phase.

    `servers` is per phase, because that is the point: design may be a model
    in this repository, build may be a laboratory's own agent in another
    language, and test may be a person. A phase with no server listed falls
    back to `fallback`, which is normally the in-process runner - a cycle in
    which one phase moved to a protocol must keep working.

    The tool is `run_phase` and it is OURS: nothing outside this project
    defines one, and `architect/mcp_server.py` implements it. It takes the
    phase, the run, the crate so far, and what was agreed; it gives back
    entities, the action that made them, and who made them.
    """
    def run(phase: str, arch) -> PhaseResult:
        server = servers.get(phase)
        if server is None:
            if fallback is None:
                raise McpError(f"no server for the {phase} phase and no "
                               f"fallback runner was given")
            return fallback(phase, arch)

        store = getattr(getattr(arch, "memory", None), "store", None)
        answer = server.call("run_phase", {
            "phase": phase,
            "run_id": getattr(arch, "run_id", "run"),
            "crate": (store.crate if store is not None else {"@graph": []}),
            "agreed": _agreed(arch)})
        if not isinstance(answer, dict):
            raise McpError(f"{server.spec.name} answered run_phase with "
                           f"{type(answer).__name__}, not an object")

        entities = [e for e in answer.get("entities") or [] if isinstance(e, dict)]
        by = str(answer.get("by") or server.spec.name)
        notes = [str(n) for n in answer.get("notes") or []]
        notes.append(f"{len(entities)} entit"
                     f"{'y' if len(entities) == 1 else 'ies'} from {by}, over MCP")

        package = answer.get("package")
        return PhaseResult(entities=entities, action=answer.get("action"),
                           package=package if isinstance(package, dict) else None,
                           by=by, notes=notes)
    return run


def _agreed(arch) -> dict:
    """What the specification settled, as plain JSON for a server to read."""
    spec = getattr(arch, "spec", None)
    for attempt in ("to_seed", "as_dict", "agreed"):
        maker = getattr(spec, attempt, None)
        if callable(maker):
            try:
                value = maker()
            except Exception:                              # noqa: BLE001
                continue
            if isinstance(value, dict):
                return value
    return {}


# --------------------------------------------------------------------------- #
def main() -> int:
    """Talk to `sentinel-oo` over MCP and show every step of it."""
    from framework.oo_contract import dbtlhub                   # noqa: PLC0415
    hub = dbtlhub()
    if hub is None:
        print("\n  the dbtlhub checkout is not here; nothing to talk to.\n")
        return 2
    crates = hub / "bioprospecting" / "exampleROcrates" / "design-to-build"

    print(f"\n{'=' * 78}\nTHE ARCHITECT, SPEAKING MCP TO SOMEBODY ELSE'S "
          f"SENTINEL\n{'=' * 78}\n")
    with Server(sentinel_oo()) as server:
        who = server.info.get("serverInfo", {})
        print(f"  connected to {who.get('name')}/{who.get('version')}, "
              f"protocol {server.info.get('protocolVersion')}")
        print(f"  tools: {', '.join(t['name'] for t in server.tools())}\n")

        check = checker_over_mcp(server, merge_back=False)

        class Nowhere:          # an Architect with no crate: verdict only
            run_id = "mcp-demo"
            memory = None
            spec = None

        for folder in [crates / "valid"] + sorted((crates / "invalid").glob("*/")):
            if not (folder / "ro-crate-metadata.json").is_file():
                continue
            crate = json.loads(
                (folder / "ro-crate-metadata.json").read_text(encoding="utf-8"))
            # The folder, not only the crate: the files it names are part of
            # what is being handed over, and one of his demands reads them.
            seen = check("design_to_build",
                         {"crate": crate, "crate_dir": folder}, Nowhere())
            codes = ", ".join(f.code for f in seen.findings[:2]) or "nothing"
            print(f"  {folder.name:<28}{seen.verdict.value:<22}{codes}")

    print("\n  Nothing of his was imported. The verdicts above came over a "
          "pipe.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
