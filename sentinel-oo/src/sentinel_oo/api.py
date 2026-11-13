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
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from . import __version__
from .contract import ContractNotFound
from .engines import NO_MODEL
from pathlib import Path

from .crate import Crate, CrateMalformed
from .graph import of as graph_of


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


def _looks_like_a_zip(body: bytes) -> bool:
    """Told apart by what the bytes are, not by a header a caller may omit."""
    return body[:2] == b"PK"


# PROTOTYPE, 12 November 2026: the page for people. Exploratory, on its own
# branch so the version on main is unchanged. The page is one HTML file plus
# the drawing library beside it, both inside the package so they travel with
# it, and the page reads only the JSON addresses this service already answers.
PAGE_DIR = Path(__file__).parent / "page"

PAGE_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


@dataclass(frozen=True)
class Page:
    """A reply that is a file for a browser rather than JSON."""

    body: bytes
    content_type: str


@dataclass(frozen=True)
class Zipped:
    """A reply that is a crate rather than JSON.

    The verdict and the count of findings go in headers, so a pipeline can
    decide what to do without unpacking anything, and the body is the crate
    to hand on.
    """

    body: bytes
    run: str
    verdict: str
    findings: int


class Api:
    """Routes requests to one Sentinel. Holds nothing else."""

    def __init__(self, sentinel, runs=None):
        self.sentinel = sentinel
        self.runs = runs
        self.routes = [
            Route("GET", r"^/$", "page",
                  "A page for people: what this instance holds, what it has "
                  "checked recently, and a picture of each check.",
                  self.page, returns="text/html"),
            # Any name is accepted by the pattern, kept simple so the
            # OpenAPI path is written correctly, and `_page_file` then
            # refuses everything that is not a shipped file by exact name.
            Route("GET", r"^/page/(?P<file>[\w.-]+)$",
                  "page_file",
                  "A file the page needs, such as its drawing library.",
                  self.page_file, returns="text/javascript"),
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
        """A crate in, a checked crate out, in whichever of two forms.

        A zipped crate carries its data files, so the contract can check
        them and the reply can be handed straight to the next process in
        the workflow. That is what a handover is: the data, not a
        description of it.

        A bare `ro-crate-metadata.json` still works, for a caller that has
        nothing else, and then the data was never here. A contract that
        checks the data says so rather than passing, because a check that
        could not run must not look like a check that passed.
        """
        if _looks_like_a_zip(body):
            return self._check_zipped(params, body)

        try:
            crate = Crate.from_bytes(body)
        except CrateMalformed as exc:
            return 400, {
                "error": "not a crate",
                "detail": str(exc),
                "hint": "the body should be a zipped crate, or the contents "
                        "of an ro-crate-metadata.json file",
            }

        try:
            run = self.sentinel.check(
                crate, contract_name=params["contract"],
                # Who is asking, if they said: POST /check/{name}?by=...
                # Recorded as their claim about themselves, since this
                # service authenticates nobody.
                ran_by=params.get("by"),
            )
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

    def _check_zipped(self, params, body):
        """The whole crate, in and out.

        The reply is the zip itself rather than JSON, because the thing the
        caller wants back is the crate. The verdict and the findings travel
        in headers so a pipeline can read them without unpacking anything.
        """
        import shutil
        import tempfile

        from .crate import pack, unpack

        workspace = tempfile.mkdtemp(prefix="sentinel-oo-")
        try:
            try:
                crate = unpack(body, Path(workspace) / "in")
            except CrateMalformed as exc:
                return 400, {
                    "error": "not a crate",
                    "detail": str(exc),
                    "hint": "a zipped crate holds an ro-crate-metadata.json, "
                            "at the top or inside one folder, with its data "
                            "files beside it",
                }

            try:
                run = self.sentinel.check(
                    crate, contract_name=params["contract"]
                )
            except ContractNotFound as exc:
                return 404, {"error": "no such contract", "detail": str(exc)}

            if self.runs is not None:
                self.runs.put(run)

            return 200, Zipped(
                body=pack(run.crate),
                run=run.id,
                verdict=run.blessing.verdict_text(),
                findings=len(run.blessing.violations),
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    HOLDS_NOTHING = (
        "This service holds no contracts, so it would refuse every handover "
        "it was given. A deployment supplies a folder of contract files and "
        "mounts it at /contracts."
    )

    def contracts(self, params, body):
        """What this instance knows how to check.

        **An instance holding nothing says so.** It used to answer with an
        empty list and a checksum, and that checksum was the SHA-256 of
        nothing at all, the same on every machine that ever ran it. A reader
        saw a service answering, with a checksum, and had no reason to doubt
        it.
        """
        registry = self.sentinel.registry
        held = [] if registry is None else registry.list()
        if not held:
            return 200, {
                "contracts": [],
                "checksum": None,
                "holds_nothing": True,
                "warning": self.HOLDS_NOTHING,
            }
        return 200, {
            "contracts": [
                {
                    "name": c.name,
                    "version": c.version,
                    "requirements": len(c.requirements),
                }
                for c in held
            ],
            "checksum": registry.checksum(),
            "holds_nothing": False,
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

    def page(self, params, body):
        return self._page_file("index.html")

    def page_file(self, params, body):
        return self._page_file(params["file"])

    def _page_file(self, name: str):
        """Only a file that is actually in the page folder, by exact name.

        The address pattern already refuses slashes, and this refuses
        anything else that is not one of the files shipped with the page.
        """
        shipped = {p.name: p for p in PAGE_DIR.iterdir() if p.is_file()} \
            if PAGE_DIR.is_dir() else {}
        found = shipped.get(name)
        if found is None:
            return 404, {"error": "no such page file", "known": sorted(shipped)}
        kind = PAGE_TYPES.get(found.suffix, "application/octet-stream")
        return 200, Page(body=found.read_bytes(), content_type=kind)

    def run_list(self, params, body):
        if self.runs is None:
            return 200, {"runs": [], "recent": [], "held": 0, "limit": 0}
        recent = []
        for run_id in self.runs.list():
            run = self.runs.get(run_id)
            if run is None:
                continue
            b = run.blessing
            # The crate's own name for itself, from its root entity, so a
            # person can tell one row from another.
            crate_name = next(
                (str(e.get("name")) for e in run.crate
                 if str(e.get("@id", "")) == "./" and e.get("name")),
                None,
            )
            recent.append({
                "run": run_id,
                "crate": crate_name,
                "verdict": b.verdict_text(),
                "contract": b.contract_name,
                "contract_version": b.contract_version,
                "started": b.started,
                "ended": b.ended,
                "findings": len(b.violations),
                "model": b.model_text(),
            })
        return 200, {
            # Kept as a plain list of identifiers so anything already
            # reading it still works. `recent` is the prototype's addition.
            "runs": self.runs.list(),
            "recent": recent,
            "held": len(self.runs),
            "limit": self.runs.limit,
        }

    def graph(self, params, body):
        """One run's crate as boxes and the lines between them.

        Built on 11 November 2026. This address had always answered "not
        built yet", because the original plan put the graph in a store that
        was never written. The store is not needed: everything the picture
        needs is already inside the crate this service handed back, so the
        work is reading that crate and rearranging it.

        **The crate is still the lasting copy.** This service keeps only the
        last few runs, and a caller holding a checked crate can build the
        same picture with no service at all, by importing
        `sentinel_oo.graph` and calling `of(crate)`.
        """
        if self.runs is None:
            return 404, {
                "error": "this service keeps no runs",
                "detail": "it was started without a run store. Build the "
                          "graph from the crate you were handed instead: "
                          "sentinel_oo.graph.of(crate).",
            }
        run = self.runs.get(params["run"])
        if run is None:
            return 404, {
                "error": "no such run",
                "detail": "this service no longer holds that run, or never "
                          "did. The durable record is in the crate that was "
                          "returned, and sentinel_oo.graph.of(crate) builds "
                          "this same answer from it.",
                "runs_it_still_holds": self.runs.list(),
            }
        return 200, graph_of(run.crate, run=params["run"])

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
        } | (
            # An instance with nothing mounted is alive and useless, and the
            # one place a deployment looks must say which it is.
            {"holds_nothing": True, "warning": self.HOLDS_NOTHING}
            if not (self.sentinel.registry and len(self.sentinel.registry))
            else {"holds_nothing": False}
        )

    def openapi(self, params, body):
        return 200, self.describe()

    # -------------------------------------------------------------- routing

    def dispatch(self, method: str, path: str, body: bytes,
                 query: dict | None = None):
        """Route one request.

        `query` carries anything after the `?`. The server used to throw it
        away before calling this, so a handler could not read it at all.
        Values from the path win over values from the query, because a path
        is part of the address and a query is a caller's suggestion.
        """
        for route in self.routes:
            found = route.regex.match(path)
            if found is None:
                continue
            if route.method != method:
                return 405, {
                    "error": "wrong method",
                    "detail": f"{path} answers {route.method}, not {method}",
                }
            params = dict(query or {})
            params.update(found.groupdict())
            return route.handler(params, body)
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
                address, _, raw_query = self.path.partition("?")
                query = {
                    k: v[0] for k, v in urllib.parse.parse_qs(raw_query).items()
                }
                status, payload = api.dispatch(method, address, body, query)
            except Exception as exc:  # noqa: BLE001
                # A fault here must not take the service down. It answers,
                # says what happened, and stays up for the next request.
                status, payload = 500, {
                    "error": "the service failed while answering",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            if isinstance(payload, Page):
                self.send_response(status)
                self.send_header("Content-Type", payload.content_type)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload.body)))
                self.end_headers()
                self.wfile.write(payload.body)
                return

            if isinstance(payload, Zipped):
                # The reply is the crate itself, to hand to the next
                # process. The verdict travels in headers so a pipeline can
                # act on it without unpacking anything.
                self.send_response(status)
                self.send_header("Content-Type", "application/zip")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="checked-{payload.run}.zip"')
                self.send_header("X-Sentinel-Run", payload.run)
                self.send_header("X-Sentinel-Verdict", payload.verdict)
                self.send_header("X-Sentinel-Findings", str(payload.findings))
                self.send_header("Content-Length", str(len(payload.body)))
                self.end_headers()
                self.wfile.write(payload.body)
                return

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
