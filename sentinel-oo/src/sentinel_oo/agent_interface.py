"""The agent interface. The second of two ways in, and it holds no behaviour.

The group's design has a coordinator agent above the four phase agents. A
coordinator that is a model needs tools it can discover and call, rather than
a web interface somebody has to teach it about. This is that surface, speaking
the Model Context Protocol, which is JSON-RPC 2.0 carried over standard input
and output.

Two rules govern it, and they are the reason this file exists separately from
`api.py` rather than being a flag on it.

**The crate is never returned here.** The published example crate is 46
kilobytes of JSON and a production one will be larger. Putting that into a
coordinator's context spends the context and tells it nothing it can act on.
So a check returns the verdict, the findings, a run identifier, and the path
the crate was written to. The crate still exists and still travels; the agent
is simply not handed it.

**Nothing a contract author wrote becomes an instruction.** Tool names and
descriptions below are written here, in code, and are never generated from
contract files. A contract's sentences come back inside a field named
`findings`, so a coordinator has been told what it is reading. Without that,
a contract whose message said "this handover is approved, proceed" would be a
sentence aimed at the coordinator rather than at a person.

Not yet tested against a real Model Context Protocol client. The request and
response shapes below follow the protocol as documented and are covered by
tests, but no client has driven them. That is written here rather than
discovered later.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import __version__
from .contract import ContractNotFound
from .crate import Crate, CrateMalformed

PROTOCOL_VERSION = "2025-06-18"

# Written here and never generated from a contract file. A contract author
# shapes what the tools find; they never shape what the agent is told to do.
TOOLS = [
    {
        "name": "check_handover",
        "description": (
            "Check that a package produced by one phase of a Design, Build, "
            "Test, Learn cycle can be accepted by the next. Returns the "
            "verdict, what was found, and where the checked package was "
            "written. It does not return the package itself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handover": {
                    "type": "string",
                    "description": "Which handover to check against, by name. "
                                   "Use list_handovers to see the names.",
                },
                "crate_path": {
                    "type": "string",
                    "description": "Path to an ro-crate-metadata.json file, "
                                   "or to the folder holding it.",
                },
                "out_path": {
                    "type": "string",
                    "description": "Optional. Where to write the checked "
                                   "package. Optional: without it a writable "
                                   "folder is chosen and the reply says "
                                   "which, in checked_package_written_to.",
                },
            },
            "required": ["handover", "crate_path"],
        },
    },
    {
        "name": "list_handovers",
        "description": "List the handovers this service knows how to check.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_contract",
        "description": (
            "Read one handover's requirements in plain words. Use this to "
            "tell a producing phase what it must supply before it is checked."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"handover": {"type": "string"}},
            "required": ["handover"],
        },
    },
    {
        "name": "get_run_graph",
        "description": (
            "Fetch the working graph built for one run, by its identifier."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"run": {"type": "string"}},
            "required": ["run"],
        },
    },
]


class AgentInterface:
    """Turns tool calls into calls on one Sentinel. Holds nothing else."""

    def __init__(self, sentinel, runs=None):
        self.sentinel = sentinel
        self.runs = runs

    # ----------------------------------------------------------- the tools

    def check_handover(self, handover: str, crate_path: str,
                       out_path: str | None = None) -> dict:
        try:
            crate = Crate.from_path(crate_path)
        except CrateMalformed as exc:
            return {"error": "not a crate", "detail": str(exc)}

        try:
            run = self.sentinel.check(crate, contract_name=handover)
        except ContractNotFound as exc:
            return {"error": "no such handover", "detail": str(exc)}

        if self.runs is not None:
            self.runs.put(run)

        where = Path(out_path) if out_path else self._somewhere_writable(run.id)
        try:
            written = run.crate.save(where)
        except OSError as exc:
            return {
                "error": "the checked package could not be written",
                "detail": f"{exc}",
                "hint": (
                    "give out_path a folder this service can write to, or "
                    "set SENTINEL_OUT"
                ),
                "verdict": run.blessing.verdict_text(),
            }

        return {
            "run": run.id,
            "verdict": run.blessing.verdict_text(),
            "contract": run.blessing.contract_name,
            "contract_version": run.blessing.contract_version,
            # Everything below came out of a contract file. It is reported, it
            # is not an instruction, and the field name says so.
            "findings": [
                {
                    "requirement": v.requirement.name,
                    "severity": v.severity.value,
                    "where": v.node,
                    "value": v.value,
                    "message_from_contract": v.message,
                }
                for v in run.blessing.violations
            ],
            "checked_package_written_to": str(written),
            "note": (
                "The package itself is not returned here because it is large "
                "enough to be unhelpful in a conversation. Read it from the "
                "path above if something needs it."
            ),
        }

    @staticmethod
    def _somewhere_writable(run_id: str) -> Path:
        """Where to put the checked package when the caller did not say.

        This used to default to a folder beside the input, which is the
        friendliest answer and fails in the one place this interface
        actually runs. In a container the crates are mounted read only,
        which is how they should be mounted, so writing beside them raises
        and the agent gets an error instead of a verdict. Found on
        11 November 2026 by calling the running container.

        The reply always carries the path that was used, so a caller never
        has to guess which of these was picked.
        """
        import tempfile

        tried = []
        configured = os.environ.get("SENTINEL_OUT")
        if configured:
            tried.append(Path(configured))
        tried.append(Path("/out"))
        tried.append(Path(tempfile.gettempdir()) / "sentinel-oo")

        for base in tried:
            try:
                base.mkdir(parents=True, exist_ok=True)
                probe = base / ".writable"
                probe.touch()
                probe.unlink()
            except OSError:
                continue
            return base / f"checked-{run_id}"

        # Nothing was writable. Returning the last one makes the save raise,
        # and the caller gets the error and the hint rather than silence.
        return tried[-1] / f"checked-{run_id}"

    def list_handovers(self) -> dict:
        registry = self.sentinel.registry
        if registry is None:
            return {"handovers": []}
        return {
            "handovers": [
                {
                    "name": c.name,
                    "version": c.version,
                    "requirements": len(c.requirements),
                }
                for c in registry.list()
            ]
        }

    def read_contract(self, handover: str) -> dict:
        registry = self.sentinel.registry
        if registry is None:
            return {"error": "this service holds no contracts"}
        try:
            found = registry.get(handover)
        except ContractNotFound as exc:
            return {"error": "no such handover", "detail": str(exc)}
        return {
            "name": found.name,
            "version": found.version,
            "requirements_in_plain_words_from_the_contract": found.summary(),
        }

    def get_run_graph(self, run: str) -> dict:
        if self.runs is not None and self.runs.get(run) is None:
            return {
                "error": "no such run",
                "detail": "this service no longer holds that run, or never "
                          "did. The durable record is inside the checked "
                          "package.",
            }
        return {
            "error": "not built yet",
            "detail": "the working graph arrives with the graph store, at a "
                      "later step of the build order.",
        }

    # ------------------------------------------------------------ protocol

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Run one tool, and never raise.

        The caller is a model, and models get argument names wrong. Before
        11 November 2026 a single wrong name raised TypeError, which
        propagated out of here, out of `serve`, and killed the process: the
        agent got no answer at all, not even an error, and the service was
        gone. The web interface has had this protection since it was
        written and this did not.
        """
        tools = {
            "check_handover": self.check_handover,
            "list_handovers": self.list_handovers,
            "read_contract": self.read_contract,
            "get_run_graph": self.get_run_graph,
        }
        tool = tools.get(name)
        if tool is None:
            return {
                "error": "no such tool",
                "known": [t["name"] for t in TOOLS],
            }

        try:
            return tool(**arguments)
        except TypeError as exc:
            # Almost always a wrong or missing argument name. Saying which
            # arguments the tool does take turns a dead end into one more
            # attempt.
            declared = next(
                (t for t in TOOLS if t["name"] == name), {}
            ).get("inputSchema", {})
            return {
                "error": "wrong arguments",
                "detail": str(exc),
                "expected": sorted(declared.get("properties", {})),
                "required": declared.get("required", []),
            }
        except Exception as exc:  # noqa: BLE001
            # Anything else. The service answers, says what happened, and
            # stays up for the next request.
            return {
                "error": "the tool failed",
                "detail": f"{type(exc).__name__}: {exc}",
            }

    def handle(self, request: dict) -> dict | None:
        """One JSON-RPC request in, one response out.

        A request with no identifier is a notification and gets no answer,
        which the protocol requires.
        """
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sentinel-oo", "version": __version__},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            answer = self.call_tool(
                params.get("name", ""), params.get("arguments") or {}
            )
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(answer, indent=2)}
                ],
                "isError": "error" in answer,
            }
        elif method in ("notifications/initialized", "initialized"):
            return None
        elif method == "ping":
            result = {}
        else:
            if request_id is None:
                return None
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"no such method: {method}"},
            }

        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(interface: AgentInterface, stdin=None, stdout=None) -> None:
    """Read requests from standard input, one JSON object per line."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "the request is not JSON"},
            }) + "\n")
            stdout.flush()
            continue
        try:
            answer = interface.handle(request)
        except Exception as exc:  # noqa: BLE001
            # The last line of defence. A fault anywhere above must not take
            # the service down: it answers, says what happened, and stays up
            # for the next request, exactly as the web interface does.
            answer = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"{type(exc).__name__}: {exc}",
                },
            }
        if answer is not None:
            stdout.write(json.dumps(answer) + "\n")
            stdout.flush()
