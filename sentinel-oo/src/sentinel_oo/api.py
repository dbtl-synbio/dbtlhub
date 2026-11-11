"""The web interface. One of two ways in, and it holds no behaviour.

Everything here turns a request into a call on the orchestrator and turns what
comes back into a response. If a rule ever appears in this file it is in the
wrong place, for the same reason a rule in the orchestrator would be.

Built on Python's standard library rather than a web framework. The service is
meant to run with nothing installed, and a framework would be the first thing
that is not true of. The cost is that the routes are matched by hand below,
which is about forty lines.

The OpenAPI document is generated from the same table that does the routing,
so the two cannot drift apart. The project outline promises "a minimal OpenAPI
service", and a document written separately from the code would be a promise
kept on paper only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from . import __version__
from .contract import ContractNotFound
from .engines import NO_MODEL
from .crate import Crate, CrateMalformed


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str
    name: str
    summary: str
    handler: Callable
    returns: str = "application/json"

    @property
    def regex(self):
        return re.compile(self.pattern)

    @property
    def path(self) -> str:
        """The pattern written the way OpenAPI writes it."""
        return re.sub(r"\(\?P<(\w+)>[^)]+\)", r"{\1}", self.pattern).strip("^$")


class Api:
    """Routes requests to one Sentinel. Holds nothing else."""

    def __init__(self, sentinel, runs=None):
        self.sentinel = sentinel
        self.runs = runs
        self.routes = [
            Route("POST", r"^/check/(?P<contract>[\w.-]+)$", "check",
                  "Check a crate against one handover's contract and return "
                  "the crate with the record written into it.",
                  self.check),
            Route("GET", r"^/contracts$", "contracts",
                  "What this service knows how to check.", self.contracts),
            Route("GET", r"^/contracts/(?P<name>[\w.-]+)$", "contract",
                  "One contract, in the form it was written and in plain "
                  "words.", self.contract),
            Route("GET", r"^/runs$", "runs",
                  "Which runs this service still holds.", self.run_list),
            Route("GET", r"^/graph/(?P<run>[\w-]+)$", "graph",
                  "The working graph built for one run.", self.graph),
            Route("GET", r"^/health$", "health",
                  "Whether it is alive, what it was built from and which "
                  "model engine is configured.", self.health),
            Route("GET", r"^/openapi.json$", "openapi",
                  "This document.", self.openapi),
        ]

    # ------------------------------------------------------------ handlers
    # Each returns (status, body). A body that is bytes is sent as it is.

    def check(self, params, body):
        try:
            crate = Crate.from_bytes(body)
        except CrateMalformed as exc:
            return 400, {
                "error": "not a crate",
                "detail": str(exc),
                "hint": "the body should be the contents of an "
                        "ro-crate-metadata.json file",
            }

        try:
            run = self.sentinel.check(crate, contract_name=params["contract"])
        except ContractNotFound as exc:
            return 404, {"error": "no such contract", "detail": str(exc)}

        if self.runs is not None:
            self.runs.put(run)

        return 200, {
            "run": run.id,
            "verdict": run.blessing.verdict_text(),
            "findings": [
                {
                    "requirement": v.requirement.name,
                    "severity": v.severity.value,
                    "where": v.node,
                    "value": v.value,
                    "message": v.message,
                }
                for v in run.blessing.violations
            ],
            "crate": json.loads(run.crate.to_json()),
        }

    def contracts(self, params, body):
        registry = self.sentinel.registry
        if registry is None:
            return 200, {"contracts": [], "checksum": None}
        return 200, {
            "contracts": [
                {
                    "name": c.name,
                    "version": c.version,
                    "requirements": len(c.requirements),
                }
                for c in registry.list()
            ],
            "checksum": registry.checksum(),
        }

    def contract(self, params, body):
        registry = self.sentinel.registry
        if registry is None:
            return 404, {"error": "this service holds no contracts"}
        try:
            found = registry.get(params["name"])
        except ContractNotFound as exc:
            return 404, {"error": "no such contract", "detail": str(exc)}
        return 200, {
            "name": found.name,
            "version": found.version,
            "checksum": found.checksum,
            "description": found.description,
            "summary": found.summary(),
            # What this contract is for. A crate containing none of these is
            # refused before any requirement is applied, so a caller reading
            # this needs to see it.
            "expects": list(found.expects),
            "requirements": [
                {
                    "name": r.name,
                    "applies_to": r.applies_to,
                    "reads": r.reads,
                    "must": r.must,
                    "severity": r.severity,
                    "message": r.message,
                    # These four used to be left out, so a producing team
                    # reading this could not see which values are restricted,
                    # what range a number must be in, or which values a model
                    # may be asked to recover. Noticed on 11 November 2026
                    # while writing the API manual.
                    "one_of": list(r.one_of) if r.one_of else None,
                    "of_type": r.of_type,
                    "between": list(r.between) if r.between else None,
                    "repairable": r.repairable,
                }
                for r in found.requirements
            ],
        }

    def run_list(self, params, body):
        if self.runs is None:
            return 200, {"runs": [], "held": 0, "limit": 0}
        return 200, {
            "runs": self.runs.list(),
            "held": len(self.runs),
            "limit": self.runs.limit,
        }

    def graph(self, params, body):
        """Not built yet, and saying so is better than pretending.

        The working graph arrives with the step of the build order that
        introduces a graph store. Until then this endpoint exists so that the
        shape of the interface is settled, and it tells the truth about why
        there is nothing behind it.
        """
        if self.runs is not None and self.runs.get(params["run"]) is None:
            return 404, {
                "error": "no such run",
                "detail": "this service no longer holds that run, or never "
                          "did. The durable record is in the crate that was "
                          "returned.",
            }
        return 501, {
            "error": "not built yet",
            "detail": "the working graph arrives with the graph store, at a "
                      "later step of the build order. Nothing is served here "
                      "rather than something that is not the graph.",
        }

    def health(self, params, body):
        """Including which of three states the model is in.

        A deployment that wanted a model and cannot reach one used to look
        exactly like one that wanted none: both reported "none" and both
        carried on quietly. That is how an instance can appear to be working
        while doing none of what it was deployed to do.

        The three states are told apart and named, and the answer is still
        200 in all three, because being without a model is a deliberate
        state and not a failure. Nothing here affects a verdict.
        """
        build = self.sentinel.build
        engine = getattr(self.sentinel, "engine", None)
        name = getattr(engine, "name", NO_MODEL)

        if name == NO_MODEL:
            model = {"state": "none configured", "engine": NO_MODEL}
        elif engine.available():
            model = {"state": "reachable", "engine": name}
        else:
            model = {
                "state": "configured but not answering",
                "engine": name,
                "detail": getattr(engine, "last_error", None),
                "effect": (
                    "checks run normally and no verdict changes. A value "
                    "recorded only in free text cannot be recovered."
                ),
            }

        return 200, {
            "alive": True,
            "service": "sentinel-oo",
            "version": __version__,
            "image_tag": build.image_tag,
            "git_commit": build.git_commit,
            "rules_checksum": build.rules_checksum,
            "model": model,
            # Kept so that anything already reading this field still works.
            "model_engine": name,
            "contracts": (
                len(self.sentinel.registry) if self.sentinel.registry else 0
            ),
        }

    def openapi(self, params, body):
        return 200, self.describe()

    # -------------------------------------------------------------- routing

    def dispatch(self, method: str, path: str, body: bytes):
        for route in self.routes:
            found = route.regex.match(path)
            if found is None:
                continue
            if route.method != method:
                return 405, {
                    "error": "wrong method",
                    "detail": f"{path} answers {route.method}, not {method}",
                }
            return route.handler(found.groupdict(), body)
        return 404, {
            "error": "no such path",
            "known": sorted({r.path for r in self.routes}),
        }

    def describe(self) -> dict:
        """The OpenAPI document, built from the routes above."""
        paths: dict = {}
        for route in self.routes:
            entry = paths.setdefault(route.path, {})
            entry[route.method.lower()] = {
                "operationId": route.name,
                "summary": route.summary,
                "parameters": [
                    {
                        "name": name,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for name in route.regex.groupindex
                ],
                "responses": {"200": {"description": "the answer"}},
            }
        return {
            "openapi": "3.1.0",
            "info": {
                "title": "sentinel-oo",
                "version": __version__,
                "description": (
                    "Decides whether one phase of a Design, Build, Test, "
                    "Learn cycle can accept what the previous phase "
                    "produced. A crate goes in and a crate comes out, "
                    "carrying a record of what was checked."
                ),
            },
            "paths": paths,
        }


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = f"sentinel-oo/{__version__}"

        def _answer(self, status: int, payload):
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _run(self, method: str):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            try:
                status, payload = api.dispatch(method, self.path.split("?")[0], body)
            except Exception as exc:  # noqa: BLE001
                # A fault here must not take the service down. It answers,
                # says what happened, and stays up for the next request.
                status, payload = 500, {
                    "error": "the service failed while answering",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            if isinstance(payload, dict) and "run" in payload:
                self.send_response(status)
                body_out = json.dumps(payload, indent=2).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Sentinel-Run", str(payload["run"]))
                self.send_header("Content-Length", str(len(body_out)))
                self.end_headers()
                self.wfile.write(body_out)
                return
            self._answer(status, payload)

        # Every method the route table uses, plus the ones a caller might
        # reasonably try. They all go through the same dispatcher, which
        # answers 405 and names the method the route does take.
        #
        # Without the last three, Python's base handler answers them itself,
        # with status 501 and a page of HTML, from a service that otherwise
        # only ever returns JSON. Found on 11 November 2026 while writing the
        # API manual: the test for a wrong method called the dispatcher
        # directly, so it passed while the running server did something else.
        def do_GET(self):  # noqa: N802
            self._run("GET")

        def do_POST(self):  # noqa: N802
            self._run("POST")

        def do_PUT(self):  # noqa: N802
            self._run("PUT")

        def do_PATCH(self):  # noqa: N802
            self._run("PATCH")

        def do_DELETE(self):  # noqa: N802
            self._run("DELETE")

        def log_message(self, fmt, *args):
            # One line per request, on standard error, without the date the
            # default handler prints twice.
            print(f"  {self.command} {self.path} {fmt % args}", flush=True)

    return Handler


def serve(api: Api, host: str = "0.0.0.0", port: int = 8080):
    server = ThreadingHTTPServer((host, port), make_handler(api))
    print(f"sentinel-oo {__version__} listening on {host}:{port}", flush=True)
    for route in api.routes:
        print(f"  {route.method:4} {route.path}", flush=True)
    server.serve_forever()
