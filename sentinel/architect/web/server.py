#!/usr/bin/env python3
"""The Architect, in a browser: the structured form, the cycle, the questions.

    python3 architect/web/server.py              # then open http://127.0.0.1:8765

Standard library only. `http.server`, no Flask, no FastAPI, no npm, no build
step. The reason is not purity: this has to start on a laptop in a lab that has
no network and no permission to install anything, and an interface that needs a
toolchain is an interface nobody in that room will see.

WHY IT BINDS TO 127.0.0.1 AND NOT 0.0.0.0
There is no authentication here, no CSRF token, and no limit on what a request
can start. A POST to /run executes the real phase agents and writes files under
`runs/`, and a session cookie is the only thing separating one caller from
another. On 0.0.0.0 that is handed to everybody on the network, including the
conference wifi. `--host` exists for the person who has read this paragraph and
decided otherwise; the default refuses on their behalf until they do.

WHY POLLING AND NOT SERVER-SENT EVENTS
Polling. A `ThreadingHTTPServer` gives one thread per request, and an SSE
response holds that thread parked on an open socket for as long as the tab is
open - two tabs and a forgotten laptop are three threads doing nothing, and a
closed tab is not reliably noticed. /state is a small JSON snapshot instead:
each poll is a whole answer, nothing is lost if a poll is missed, the tab can
be closed and reopened mid-run, and `curl` can read the same endpoint in a
loop, which is how this file was verified. The cost is up to a second of
latency on the run log, which nobody filling in a form will notice.

WHAT JAVASCRIPT IS FOR, AND WHAT HAPPENS WITHOUT IT
Two things: the live run log, and the count of required fields still
unanswered as you type. Everything else is a plain form POST with a 303 back,
so with JavaScript off the form still saves, the run still starts, and a
question can still be answered - the page just has to be reloaded to see the
next thing, and it says so. No framework, no CDN, no bundle.

THE LOOK
`architect/theme.py` holds the palette, the font and one icon per kind of
thing, and is imported here and nowhere else. It holds no display names on
purpose: every word on this page - Architect, phase agent, sentinel, RO-Crate,
verdict, handover, Design/Build/Test/Learn - is the word the contracts and the
code already use, so the person reading the screen and the person reading the
repository are talking about the same thing.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
import threading
import traceback
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from typing import Any
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from architect import theme                                           # noqa: E402
from architect.architect import Architect                             # noqa: E402
from architect.contract import Move, PHASES, Question                 # noqa: E402
from architect.interface import (SKIPPED, STOPPED, Interface,         # noqa: E402
                                 Stopped)
from architect.web import kgview                                      # noqa: E402
from architect.web import ring                                        # noqa: E402
from architect.web import setup as setup_mod                          # noqa: E402
from architect.workflows import loader as workflows                   # noqa: E402

STATIC = HERE / "static"
COOKIE_NAME = "dbtl_session"

# A form POST is a few kilobytes of text. Anything larger is either a mistake
# or an attempt to make this process allocate until it dies, and `rfile.read`
# will happily do that if it is handed a large Content-Length.
MAX_BODY = 256 * 1024

# The names a POST may claim to be addressed to. Loopback only by default, so
# another name resolving to this machine cannot drive the interface. `main()`
# adds the bind address when it is told to listen somewhere else, because a
# deliberate `--host` should not lock the person out of their own server.
ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}
ANSWER_TIMEOUT_S = 1800        # a question nobody answers must not park a
                               # thread for ever; after this the run stops
                               # itself, which is what `stop` means anyway.


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# --------------------------------------------------------------------------- #
#  1. The form seam, and whoever supplies a form through it
# --------------------------------------------------------------------------- #
def _load_seam():
    """Get `Form`, `Section`, `Field`, `Kind`, `Filled` from `architect.forms`.

    Normally a plain import. The fallback exists because of a name clash this
    layer cannot control: `architect/forms.py` is the seam, and the structured
    forms are being written into a directory `architect/forms/`. If that
    directory ever gains an `__init__.py` it becomes a package and shadows the
    module, and the import above stops finding `Kind`. Loading the file by path
    keeps this interface working either way rather than failing in a way that
    looks like the form is broken.
    """
    try:
        from architect import forms as module          # noqa: PLC0415
        if all(hasattr(module, name) for name in
               ("Form", "Section", "Field", "Kind", "Filled")):
            return module
    except Exception:
        pass
    spec = importlib.util.spec_from_file_location(
        "architect_forms_seam", ROOT / "architect" / "forms.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seam = _load_seam()
Field, Form, Kind, Section, Filled = (_seam.Field, _seam.Form, _seam.Kind,
                                      _seam.Section, _seam.Filled)

# AND THAT IS WHY NOTHING BELOW COMPARES A KIND WITH `is`.
# `architect/forms/` is a package, so the fallback above loads `forms.py` a
# second time under its own name - which means there are two `Kind` enums in
# this process, and a field built by the loader carries the OTHER one.
# `Kind.STEPS is Kind.STEPS` was False, silently, and every list and steps
# field in this interface was rendered and parsed as a plain string. Both
# enums are `str` valued, so `.value` is the comparison that holds whichever
# class a field happens to carry.

LOADER_PATH = ROOT / "architect" / "forms" / "loader.py"
# The names a loader is likely to expose. Guessing a function name is not
# elegant, but the alternative is this interface being unusable until the two
# files agree, and a form that renders from a YAML the moment the YAML exists
# is worth a short list of spellings.
LOADER_CALLABLES = ("load_form", "load_instance", "load_template", "load",
                    "read_form", "form", "template")

# Two things the generic `Field` has no room for and the fallback form below
# has to say anyway: the long explanation behind a question, and what an option
# means in words. Kept beside the form rather than inside it, because a form
# that comes from the YAML loader will carry its own wording and must not be
# decorated with ours.
DETAILS: dict[str, str] = {}
OPTION_HINTS: dict[tuple[str, str], str] = {}


def _looks_like_form(obj: Any) -> bool:
    return (hasattr(obj, "sections") and hasattr(obj, "all_fields")
            and hasattr(obj, "required_keys"))


def _pick_form(result: Any) -> Any | None:
    if _looks_like_form(result):
        return result
    if isinstance(result, dict):
        for key in ("bioprospecting", "template"):
            if _looks_like_form(result.get(key)):
                return result[key]
        return next((v for v in result.values() if _looks_like_form(v)), None)
    if isinstance(result, (list, tuple)):
        return next((v for v in result if _looks_like_form(v)), None)
    return None


def _from_loader() -> tuple[Any | None, str]:
    """Try the structured forms someone else is writing. Never required.

    Everything here is wrapped: a loader half-written, a YAML half-valid, or a
    signature we guessed wrong about must leave the interface working on the
    fallback form rather than showing a stack trace to a researcher.
    """
    if not LOADER_PATH.is_file():
        return None, f"{LOADER_PATH.relative_to(ROOT)} does not exist yet"
    try:
        spec = importlib.util.spec_from_file_location(
            "architect_forms_loader", LOADER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return None, f"architect/forms/loader.py did not import: {exc!r}"

    yamls = sorted(LOADER_PATH.parent.glob("*.y*ml"))
    instances = [p for p in yamls if "template" not in p.name]
    candidates = instances + [p for p in yamls if p not in instances]
    tried: list[str] = []
    for name in LOADER_CALLABLES:
        function = getattr(module, name, None)
        if not callable(function):
            continue
        arguments: list[tuple] = [(p,) for p in candidates]
        arguments += [(str(p),) for p in candidates]
        arguments += [(p.stem,) for p in candidates]
        arguments += [()]
        for args in arguments:
            try:
                form = _pick_form(function(*args))
            except Exception as exc:
                shown = Path(str(args[0])).name if args else ""
                tried.append(f"{name}({shown}) raised "
                             f"{exc.__class__.__name__}: {exc}"[:160])
                continue
            if form is not None:
                shown = args[0] if args else ""
                return form, (f"architect/forms/loader.py: "
                              f"{name}({shown!r})" if shown else
                              f"architect/forms/loader.py: {name}()")
    # The first failure, verbatim. "No form came back" on its own sends
    # somebody reading this page to the wrong file; "the YAML did not parse at
    # line 12" sends them to the right one.
    return None, ("architect/forms/loader.py imported but no form came back: "
                  + (tried[0] if tried else "no loader function recognised"))


def _fallback_form() -> Any:
    """A form derived from the questions the Architect already asks.

    This is a stand-in, and it is built rather than written so that it cannot
    drift: every question in the middle section is one of `consultation.SLOTS`,
    with that slot's own wording, its own options and its own reason. The
    structured YAML template will replace it; until then the interface shows
    the real questions instead of a mock-up of them.

    What is required here follows one stated rule: a slot is required when
    leaving it unanswered leaves an open question at the first handover - that
    is, the first eight by consequence, minus the ones that only apply in some
    runs. The template will say so per field instead of by a rule.
    """
    from architect.consultation import SLOTS                    # noqa: PLC0415

    labs = sorted(p.stem for p in
                  (ROOT / "framework" / "vocabulary" / "labs").glob("*.json"))

    run = Section(
        key="run", title="The run",
        intent="Who is accountable for this run, and what it is for.",
        fields=[
            Field(key="objective", label="What is this run trying to find out?",
                  kind=Kind.LONGTEXT, required=True,
                  placeholder="find thermostable ene-reductases in hot "
                              "spring sediment",
                  why_it_is_asked=(
                      "The Architect opens the consultation from it and the "
                      "ledger records it. Without it the crate is a record "
                      "nobody can match back to a question."),
                  feeds=["consultation.open(objective=...)", "ledger"]),
            Field(key="researcher", label="Who is answering for this run?",
                  kind=Kind.TEXT, required=True, placeholder="your name",
                  why_it_is_asked=(
                      "Every row in the ledger is recorded against a name, and "
                      "every answer below is attributed to it. An approval with "
                      "no name on it is not an approval."),
                  feeds=["Architect(researcher=...)", "ledger.actor"]),
            Field(key="lab", label="Which lab's vocabulary applies?",
                  kind=Kind.CHOICE, options=labs,
                  why_it_is_asked=(
                      "Local spellings - freezer_temp, gps_lat - have to "
                      "resolve to agreed terms. The handover treats a key "
                      "nobody has mapped as a failure, not a warning."),
                  feeds=["phase agent lab=...",
                         "framework.vocab.load_vocabulary"]),
        ])

    decisions = Section(
        key="decisions", title="The decisions",
        intent="What you decide, in the order in which it changes what the "
               "later phases do. Nothing here has an answer until you give it "
               "one.",
        fields=[])
    for slot in SLOTS:
        options = [str(value) for _, value in slot.options]
        for (text, value) in slot.options:
            OPTION_HINTS[(slot.key, str(value))] = text
        DETAILS[slot.key] = slot.detail
        feeds = [f"specification.agreed[{slot.key!r}]"]
        if slot.key in ("library_size", "replicates"):
            feeds.append(f"handover limits[] quantity={slot.key}")
        decisions.fields.append(Field(
            key=slot.key, label=slot.headline, kind=Kind.CHOICE,
            options=options,
            phase=(slot.affects[0] if len(slot.affects) == 1 else None),
            required=(slot.rank <= 8 and slot.needed_when is None),
            default=(next((str(v) for t, v in slot.options
                           if t == slot.recommended), None)),
            why_it_is_asked=slot.because, feeds=feeds))

    bench = Section(
        key="bench", title="The bench",
        intent="What exists in the lab. Kept on the specification as you "
               "stated it, not inferred from anything.",
        fields=[
            Field(key="instruments", label="Instruments this run uses",
                  kind=Kind.LIST,
                  placeholder="one per line, e.g. OT-2 liquid handler",
                  why_it_is_asked=(
                      "What is on the bench decides what Build can be asked "
                      "for. The consultation keeps this verbatim rather than "
                      "guessing it from the protocol."),
                  feeds=["specification.reading.kept['instruments']"]),
            Field(key="steps", label="Your own numbered workflow",
                  kind=Kind.STEPS,
                  placeholder="one step per line, in order",
                  why_it_is_asked=(
                      "The Architect reports where a run has got to in your "
                      "vocabulary rather than in phase names. These are those "
                      "words, and nothing else can supply them."),
                  feeds=["specification.reading.kept['steps']", "Form.steps"]),
            Field(key="candidates_to_design",
                  label="How many candidates should Design generate?",
                  kind=Kind.NUMBER, phase="design", placeholder="6",
                  why_it_is_asked=(
                      "Design has to select within the library size and say "
                      "which candidates it dropped. It cannot drop any if it "
                      "only ever generated as many as it is allowed to order."),
                  feeds=["phase input n", "design_panel(n)"]),
            Field(key="screen_temperature",
                  label="Temperature the screen is run at",
                  kind=Kind.QUANTITY, unit="degC", phase="test",
                  placeholder="55",
                  why_it_is_asked=(
                      "A quantity that arrives without its unit is refused at "
                      "the handover, so this form fixes the unit and asks only "
                      "for the number. It travels on the handover's limits, "
                      "where the sentinel can see it."),
                  feeds=["handover limits[] quantity=screen_temperature"]),
        ])

    crate = Section(
        key="crate", title="Starting from a crate that already exists",
        intent="A use case with its own RO-Crate is not going to adopt a new "
               "one to be allowed to use this.",
        fields=[
            Field(key="adopt_existing",
                  label="Continue from a crate that already exists?",
                  kind=Kind.BOOL,
                  why_it_is_asked=(
                      "An adopted crate becomes this store's crate, so the "
                      "same three refusals - overwrite, identifier collision, "
                      "dangling reference - defend it. Answer no and a new "
                      "crate is created for this run."),
                  feeds=["Architect.adopt"]),
            Field(key="adopt_path", label="Path to that crate",
                  kind=Kind.TEXT,
                  placeholder="runs/<id>/ro-crate-metadata.json",
                  why_it_is_asked=(
                      "Read only: nothing is ever written back to the file a "
                      "crate was adopted from. What could not be interpreted "
                      "is reported rather than adopted in silence."),
                  feeds=["Architect.adopt(path)"]),
        ])

    rehearsal = Section(
        key="rehearsal", title="Rehearsal",
        intent="A sentinel only demonstrates that it refuses when there is "
               "something to refuse. Nothing is injected unless you tick it.",
        fields=[
            Field(key="rehearse_faults",
                  label="Faults to inject into this run, on purpose",
                  kind=Kind.MULTI,
                  options=["missing_units", "unknown_item", "dropped_well"],
                  why_it_is_asked=(
                      "With one of these ticked a handover is refused and the "
                      "Architect puts the decision to you. It is the only way "
                      "to see that half of the system work without waiting for "
                      "a real mistake. Every injected fault is named in the "
                      "ledger."),
                  feeds=["phase input faults"]),
        ])

    return Form(
        name="architect-web-fallback",
        title="DBTL specification",
        description=(
            "Derived from the Architect's own consultation questions, because "
            "architect/forms/*.yaml was not loadable when this page was "
            "served. The questions, options and reasons are the real ones."),
        sections=[run, decisions, bench, crate, rehearsal])


def load_form() -> tuple[Any, str]:
    form, why = _from_loader()
    if form is not None:
        return form, why
    return _fallback_form(), f"fallback form ({why})"


FORM, FORM_SOURCE = load_form()

# Keys this layer consumes itself and therefore does not hand to the
# consultation. Handing them over would get them reported back as keys the
# consultation could not interpret, which would be true and useless: they are
# not decisions about the science, they are how this deployment is run.
CONSUMED_HERE = {"researcher", "recorded_by", "run_id", "lab", "site",
                 "rehearse_faults", "adopt_existing", "adopt_path",
                 "candidates_to_design", "screen_temperature"}

# What the run needs from the filled form, and the field keys it will accept
# for each. A table rather than a chain of `or`s, because the keys legitimately
# differ between forms: the bioprospecting instance says `container_id` and
# `recorded_by` where the fallback says `container` and `researcher`, and
# neither is wrong - a form names things in the words of the people filling it
# in. What this layer must not do is guess: a key that is in no list here is
# handed to the consultation and reported, never quietly interpreted.
WANTS: dict[str, tuple[str, ...]] = {
    "researcher": ("researcher", "recorded_by", "decided_by"),
    "run_id": ("run_id",),
    "objective": ("objective",),
    "profile": ("profile",),
    "lab": ("lab", "site"),
    "container": ("container", "container_id"),
    "panel_size": ("candidates_to_design", "library_size"),
    "temperature": ("screen_temperature",),
    "faults": ("rehearse_faults",),
    "adopt": ("adopt_existing",),
    "adopt_path": ("adopt_path",),
}


def wanted(values: dict[str, Any], what: str) -> tuple[Any, str]:
    """The first answered field the run accepts for `what`, and which it was.

    The second value is returned so the log can say where a number came from.
    A run that says "6 candidates" and will not say why is a run nobody can
    check.
    """
    for key in WANTS.get(what, ()):
        value = values.get(key)
        if value not in ("", [], None):
            return value, key
    return None, ""


def safe_run_id(raw: str, fallback: str) -> str:
    """A run id that cannot leave `runs/`.

    It becomes a directory name, so a researcher typing `../../etc` must not be
    able to write there. Anything outside the allowed characters is dropped
    rather than replaced, and an empty result falls back to the session's own
    id.
    """
    cleaned = "".join(c for c in str(raw) if c.isalnum() or c in "-_.")
    cleaned = cleaned.strip(".-_")[:48]
    return cleaned or fallback


# --------------------------------------------------------------------------- #
#  2. One session, one Architect
# --------------------------------------------------------------------------- #
# Sessions live in this dict, in memory, keyed by the id in the cookie.
#
# ON RESTART THEY ARE LOST. Every filled-in form, every run log and every
# Architect instance goes when the process stops, and the next request gets a
# new empty session. That is acceptable for a laptop interface in front of a
# research system and it is stated rather than hidden: what matters survives
# anyway, because the crate and the ledger are written to disk under
# `runs/<run_id>/` by the crate store and by `Architect.write_ledger`. A run
# interrupted by a restart leaves its crate exactly where it had got to.
SESSIONS: dict[str, "Session"] = {}
SESSIONS_LOCK = threading.Lock()


def _default_workflow():
    """The workflow a new session starts on, or None if none can be read.

    None is survivable: every panel that shows a workflow checks for it, and
    the run falls back to the form's own panel size. A missing PyYAML should
    cost you the demonstrations, not the interface.
    """
    try:
        return workflows.load("bioprospecting")
    except Exception:                             # noqa: BLE001
        try:
            return next(iter(workflows.load_all()), None)
        except Exception:                         # noqa: BLE001
            return None


class Session:
    """What one browser is doing: a form being filled, and at most one run."""

    def __init__(self, session_id: str):
        self.id = session_id
        # Asked before the form, because a person who fills in a panel of 96
        # enzymes and only then learns that no model is reachable has spent
        # the interesting part of their attention on the boring failure.
        self.setup = setup_mod.Setup()
        # Which cycle this run is a turn of. One is loaded by default rather
        # than left empty, because an empty workflow teaches nobody what a
        # workflow is, and this one is a record of real work.
        self.workflow = _default_workflow()
        self.workflow_problems: list[str] = []
        self.workflow_source = "the demonstration workflows on disk"
        self.filled = Filled(form=FORM)
        self.log: list[dict] = []
        self.crate_growth: list[dict] = []
        # The crate as it stood after the last phase, kept so the next one can
        # say what IT added rather than only how big the whole thing got.
        self.last_snapshot: dict | None = None
        # Which entity the knowledge-graph panel is looking at, if any.
        self.focus: str = ""
        # And which run's crate it is showing. Empty means this session's.
        self.looking_at: str = ""
        # Which single view is on show, and which phase or sentinel is open.
        # One at a time: the page used to stack every panel down one scroll.
        self.view: str = "cycle"
        self.phase: str = ""
        self.sentinel: str = ""
        # Which palette. Both carry the same key names, so nothing below
        # knows which is in force.
        self.theme: str = theme.DEFAULT_THEME
        self.arch: Architect | None = None
        self.run_id = f"web-{session_id[:6]}"
        # How many runs this browser has started. It names them apart, so a
        # second one never lands in the first one's crate.
        self.runs_started = 1
        self.thread: threading.Thread | None = None
        self.finished = False
        self.question: Question | None = None   # what is being asked
        self.awaiting = False                   # the run thread is waiting
        self.transcript: list[dict] = []
        self._answer: list[str] = []
        self._answered = threading.Event()
        self._lock = threading.Lock()

    # ---- starting over -----------------------------------------------------
    def restart(self, keep_specification: bool = True) -> str:
        """Clear the run so another one can start. Returns what it did.

        A NEW RUN ID, ALWAYS. The crate is append-only and `CrateStore` opens
        whatever is already at that path, so running again under the same id
        adds to the previous crate rather than starting one - which is correct
        behaviour and the wrong thing to get by accident. It was met exactly
        that way: a second run under `BP-round-1` went from 448 entities to
        743 and the growth column stopped meaning what it said.

        NOTHING ON DISK IS TOUCHED. The previous run's crate, graph and ledger
        stay where they are, and the graph panel can still be pointed at them.
        Starting again is not the same as undoing, and a button that quietly
        deleted a finished run would be the one mistake this whole system is
        built to make impossible.
        """
        said = []
        base = self.run_id.rsplit("-run", 1)[0]
        self.arch = None
        self.log = []
        self.crate_growth = []
        self.last_snapshot = None
        self.transcript = []
        self.question = None
        self.awaiting = False
        self.finished = False
        self.thread = None
        self.focus = ""
        self.looking_at = ""
        self._answer = []
        self._answered.clear()

        self.runs_started += 1
        self.run_id = f"{base}-run{self.runs_started}"
        said.append(f"a new run: {self.run_id}")

        # The FORM's run id wins at the start of a cycle, because the
        # researcher named the run and this interface does not get to
        # overrule them. So the new name goes into the form, where they can
        # see it and change it - rather than into a variable the next cycle
        # silently overwrites. Without this the second run appended to the
        # first one's crate: 448 entities became 1039, and the growth column
        # stopped meaning what it said.
        if self.filled.values.get("run_id"):
            self.filled.values["run_id"] = self.run_id
            self.filled.provenance["run_id"] = {
                "source": "started over", "at": now_iso(), "by": "the interface"}
            said.append("the form's run id now says so too")

        if not keep_specification:
            self.filled = Filled(form=FORM)
            self.workflow = _default_workflow()
            self.workflow_problems = []
            self.workflow_source = "the demonstration workflows on disk"
            said.append("the specification and the workflow are cleared")
        else:
            said.append("the specification and the workflow are kept")
        return "; ".join(said)

    # ---- the log the browser reads ----------------------------------------
    def note(self, text: str, kind: str = "note", state: str = "") -> None:
        with self._lock:
            self.log.append({"at": clock(), "kind": kind, "state": state,
                             "text": str(text)})

    def say(self, text: str = "") -> None:
        """`output_fn` for `Interface`: its words go into the run log verbatim.

        One log row per call, newlines and all. The terminal interface wraps
        its own prose at 76 columns; splitting that into a row per line would
        leave single words sitting on their own looking like a defect, so the
        row keeps the shape the interface gave it and the CSS honours it.
        """
        if str(text).strip():
            self.note(str(text).rstrip(), kind="architect")

    # ---- the question, and the answer coming back -------------------------
    def read_answer(self, prompt: str) -> str:
        """`input_fn` for `Interface`: blocks until the browser posts one.

        Nothing is returned on a timeout except `stop`, the same word a person
        would type. A question that times out is not answered on anybody's
        behalf - the run ends, and the ledger says it ended.
        """
        with self._lock:
            self.awaiting = True
        try:
            if not self._answered.wait(ANSWER_TIMEOUT_S):
                self.note(f"no answer in {ANSWER_TIMEOUT_S}s - the run stops "
                          f"rather than choose for you", kind="note")
                return "stop"
            self._answered.clear()
            return self._answer.pop() if self._answer else ""
        finally:
            with self._lock:
                self.awaiting = False

    def submit_answer(self, raw: str) -> bool:
        """Hand one typed answer to whatever is waiting for it."""
        with self._lock:
            if not self.awaiting:
                return False
        self.note(raw if raw else "(nothing chosen)", kind="researcher")
        self._answer.append(raw)
        self._answered.set()
        return True

    # ---- state ------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def entities(self) -> int:
        if self.arch is None:
            return 0
        try:
            return len(self.arch.memory.snapshot().get("@graph", []))
        except Exception:
            return 0


def session_for(session_id: str | None) -> tuple["Session", bool]:
    """The session this cookie names, or a new one. Second value: is it new."""
    with SESSIONS_LOCK:
        if session_id and session_id in SESSIONS:
            return SESSIONS[session_id], False
        new_id = token_urlsafe(12)
        SESSIONS[new_id] = Session(new_id)
        return SESSIONS[new_id], True


# --------------------------------------------------------------------------- #
#  3. Reading the form back out of a POST
# --------------------------------------------------------------------------- #
def values_from_post(posted: dict[str, list[str]]) -> dict[str, Any]:
    """One value per field, in the type its `Kind` says it is.

    Anything the form does not define is dropped. A blank is stored as the
    empty string rather than as a default, which is what makes
    `Filled.missing()` able to tell "not answered" from "answered with a 0".
    """
    values: dict[str, Any] = {}
    for field in FORM.all_fields():
        raw = posted.get(field.key, [])
        if field.kind.value == "multi":
            values[field.key] = [v for v in raw if v]
            continue
        text = (raw[0] if raw else "").strip()
        if field.kind.value in ("list", "steps"):
            values[field.key] = [line.strip() for line in text.splitlines()
                                 if line.strip()]
        elif field.kind.value == "bool":
            # Not a checkbox. A checkbox has a default - unticked - and this
            # form is not allowed one, so a bool is two radios and neither is
            # chosen until somebody chooses it.
            values[field.key] = (True if text == "yes"
                                 else False if text == "no" else "")
        elif field.kind.value in ("number", "quantity"):
            values[field.key] = text          # kept as typed; see `as_number`
        else:
            values[field.key] = text
    return values


def as_number(value: Any) -> float | int | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def workflow_from(values: dict[str, Any]) -> dict[str, Any]:
    """The filled form as something `consultation.read_workflow` can read.

    It is handed over as a workflow rather than written into the specification
    directly, on purpose: `read_workflow` already decides what it understands,
    reports what it recognised but could not interpret, and lists verbatim the
    keys it has no meaning for. A web layer that mapped fields onto slots
    itself would be a second, invisible copy of that judgement.
    """
    workflow: dict[str, Any] = {}
    for key, value in values.items():
        if key in CONSUMED_HERE or value in ("", [], None):
            continue
        workflow[key] = value
    return workflow


# --------------------------------------------------------------------------- #
#  4. The run: four phases, with the questions put to the browser
# --------------------------------------------------------------------------- #
def start_run(session: Session, from_phase: str | None = None,
              reason: str = "") -> None:
    """Start the cycle in its own thread, so the page stays answerable.

    Refuses to start while required fields have no answer. The missing list is
    the whole point of a form, and starting anyway would make it decoration.
    """
    if session.running:
        session.note("a run is already going", kind="note")
        return
    missing = session.filled.missing()
    if missing:
        session.note(f"the run did not start: {len(missing)} required "
                     f"field(s) have no answer", kind="refused",
                     state="refused")
        for field in missing:
            session.note(f"{field.label} - {field.why_it_is_asked}",
                         kind="refused")
        return
    session.finished = False
    session.thread = threading.Thread(target=_run, args=(session, from_phase,
                                                         reason), daemon=True)
    session.thread.start()


def _run(session: Session, from_phase: str | None = None,
         reason: str = "") -> None:
    try:
        _cycle(session, from_phase=from_phase, reason=reason)
    except Stopped as stopped:
        session.note(str(stopped), kind="stop", state="stop")
    except Exception:
        # A traceback belongs in the log the researcher is already reading.
        # Hiding it would leave them watching a run that silently stopped.
        session.note("the run raised, and the rest of the cycle did not "
                     "happen:", kind="refused", state="refused")
        for line in traceback.format_exc().strip().splitlines()[-6:]:
            session.note(line, kind="refused")
    finally:
        session.question = None
        session.finished = True
        if session.arch is not None:
            try:
                session.note(f"ledger written to "
                             f"{session.arch.write_ledger()}", kind="ledger")
            except Exception as exc:
                session.note(f"the ledger could not be written: {exc}",
                             kind="refused", state="refused")
        session.note("the run has ended", kind="note")


def _cycle(session: Session, from_phase: str | None = None,
           reason: str = "") -> None:
    """One turn of the cycle, or a return to one phase of the one before it.

    `from_phase` is a deliberate return, asked for by the researcher after
    seeing what happened - which is a different thing from the Architect's own
    GO_BACK, and both are kept. The Architect goes back when a sentinel refuses
    something it can name; a person goes back because they looked at the result
    and were not satisfied, which no contract can detect.

    NOTHING IS UNDONE. The same Architect and the same crate carry on: a repeat
    ADDS a second attempt beside the first, and both stay readable. An
    append-only crate that quietly replaced a phase's work on a retry would be
    append-only in name. That is why the reason is required and goes into the
    ledger - a repeat with no reason recorded is indistinguishable from a loop.
    """
    from architect.wiring import phase_runner, sentinel_checker     # noqa: PLC0415

    values = dict(session.filled.values)
    researcher = str(wanted(values, "researcher")[0] or "researcher")
    profile = str(wanted(values, "profile")[0] or "")
    returning = from_phase is not None and session.arch is not None

    if returning:
        arch = session.arch
        session.note(f"{researcher} sent the run back to {from_phase}: "
                     f"{reason or 'no reason given'}", kind="ask", state="ask")
        session.note("nothing is undone. The crate keeps what the earlier "
                     "attempt wrote, and this one is added beside it.",
                     kind="crate")
        arch.ledger.append({
            "at": now_iso(), "step": "returned", "phase": from_phase,
            "by": researcher, "because": reason or "no reason given",
            "move": "go_back", "asked_by": "the researcher",
        })
    else:
        named_run, _ = wanted(values, "run_id")
        session.run_id = safe_run_id(named_run or "", session.run_id)
        arch = Architect(session.run_id, researcher=researcher)
        session.arch = arch
        session.note(f"Architect for run {session.run_id}, answering to "
                     f"{researcher}", kind="architect")

    # ---- a crate somebody else wrote, if there is one ---------------------
    # Skipped on a return: it was adopted once, and adopting it again would
    # be a second claim that the same crate arrived from somewhere else.
    adopt, _ = wanted(values, "adopt") if not returning else (None, "")
    adopt_path, _ = wanted(values, "adopt_path")
    if adopt is True and adopt_path:
        adoption = arch.adopt(str(adopt_path))
        session.note(f"adopted {adopt_path}: {adoption}", kind="crate")

    # ---- the consultation -------------------------------------------------
    # Also skipped on a return. What was agreed is still agreed; asking again
    # would invite a different answer to the same question inside one run.
    workflow = workflow_from(values)
    questions = [] if returning else arch.consult(
        objective=str(wanted(values, "objective")[0] or ""),
        workflow=workflow or None)
    reading = getattr(arch.spec, "reading", None)
    if reading is not None and not returning:
        session.note(f"read the form as a workflow: understood "
                     f"{len(reading.understood)} decision(s), kept "
                     f"{len(reading.kept)} description key(s), could not "
                     f"interpret {len(reading.unread)} key(s)",
                     kind="architect")
        for unread in reading.unread[:6]:
            session.note(f"not interpreted: {unread}", kind="flagged",
                         state="accepted_with_flags")

    # The terminal interface, driven by the browser. Its rules are the ones
    # that matter here and they are not re-implemented: no default on an empty
    # answer, a recommendation still has to be chosen, an unreadable answer is
    # re-asked rather than guessed at, and why / skip / stop always work.
    ui = Interface(input_fn=session.read_answer, output_fn=session.say,
                   researcher=researcher)

    if questions:
        session.note(f"{len(questions)} question(s) the form did not settle, "
                     f"in the order of consequence", kind="ask", state="ask")
        answers = []
        for question in questions:
            session.question = question
            answers.append(ui.ask(question))
            session.question = None
        arch.answer(answers)
        session.note(f"{len(answers)} answer(s) applied; "
                     f"{len(arch.open_questions)} still open", kind="architect")

    # ---- what the phase agents are given ----------------------------------
    # The Architect does not interpret these; wiring them from the form is this
    # deployment's job, which is why the mapping is here and is short.
    flow = session.workflow
    if flow is not None:
        session.note(f"this run is one turn of {flow.name}: {len(flow.steps)} "
                     f"steps, from {session.workflow_source}", kind="architect")
        # The plan goes into the crate before the run it is a plan for. Until
        # this existed the workflow drove the run and vanished, so the crate
        # recorded what happened and not what it was supposed to be - and
        # nothing downstream could tell the difference.
        try:
            if returning:
                raise RuntimeError("already recorded for this run")
            landed = workflows.record_in(arch.memory.store, flow,
                                         by=researcher)
            session.note(f"the plan is in the crate: "
                         f"{len(landed.added)} entities as schema:HowTo and "
                         f"prov:Plan, at {flow.crate_id()}", kind="crate")
        except Exception as exc:                          # noqa: BLE001
            if not returning:
                session.note(f"the plan could not be written into the crate: "
                             f"{exc}", kind="flagged",
                             state="accepted_with_flags")
        for handover in ("design_to_build", "build_to_test",
                         "test_to_learn", "learn_to_design"):
            step = flow.handover_step(handover)
            if step is not None:
                session.note(f"handover {step.handover_number} "
                             f"({handover}) follows step {step.number}, "
                             f"{step.name}", kind="sentinel")
        for step in flow.manual_steps():
            session.note(f"step {step.number} is partly done by hand: "
                         f"{', '.join(step.manual_parts)}", kind="note")

    raw_size, size_from = wanted(values, "panel_size")
    panel_size = as_number(raw_size)
    # The workflow decides how big a run is, when it has committed to a
    # number. The form's panel size stays as the answer for a workflow that
    # counts nothing - the blank one counts nothing on purpose.
    from_flow = flow.starting_count() if flow is not None else None
    if from_flow:
        panel_size, size_from = from_flow, f"the {flow.name} workflow"
    elif panel_size is None:
        panel_size, size_from = 6, "the phase agent's own default"
    session.note(f"Design generates {int(panel_size)} candidate(s), from "
                 f"{size_from}", kind="phase_agent")
    inputs: dict[str, Any] = {"n": int(panel_size)}

    container, _ = wanted(values, "container")
    if container:
        inputs["container"] = str(container)

    faults, _ = wanted(values, "faults")
    if faults:
        inputs["faults"] = set(faults)
        session.note(f"rehearsal: injecting "
                     f"{', '.join(sorted(inputs['faults']))}", kind="flagged",
                     state="accepted_with_flags")

    temperature, temperature_key = wanted(values, "temperature")
    number = as_number(temperature)
    if number is not None:
        field = FORM.field(temperature_key)
        inputs["limits"] = [{
            "quantity": temperature_key, "value": number,
            # The unit is the form's, not the researcher's. That is the whole
            # point of a QUANTITY: the number cannot arrive bare.
            "unit": (field.unit if field and field.unit else "degC"),
            "from": getattr(arch.spec, "spec_id", "spec:web"),
            "stated_by": researcher}]
    try:
        from usecases.bioprospecting import instruments as bp     # noqa: PLC0415
        inputs["panel"] = bp.design_panel(int(panel_size))
    except Exception as exc:
        session.note(f"no candidate panel available ({exc}); the phase agent "
                     f"will use its own", kind="flagged",
                     state="accepted_with_flags")

    lab, _ = wanted(values, "lab")
    # What the setup screen chose. `engine_object()` falls back to RulesEngine
    # and says so in its notes rather than raising: an unreachable model is a
    # reason to run deterministically, not a reason not to run.
    engine = session.setup.engine_object()
    for line in session.setup.notes[-2:]:
        session.note(line, kind="note")
    session.note(f"the engine for this run: {engine.name}", kind="architect")
    runner = phase_runner(profile=profile or "bioprospecting",
                          lab=(str(lab) if lab else None),
                          engine=engine, **inputs)
    checker = sentinel_checker(profile=profile or "bioprospecting")

    # ---- the four phases --------------------------------------------------
    order = list(PHASES)
    index = order.index(from_phase) if from_phase in order else 0
    guard = 0
    while index < len(order) and guard < 2 * len(order) + 4:
        guard += 1
        phase = order[index]
        session.note(f"{phase} starting", kind="phase_agent")
        decision = arch.run_phase(phase, runner, checker)
        step = arch.history[-1]

        for line in step.notes:
            session.note(line, kind="phase_agent")
        if step.verdict is not None:
            session.note(f"{phase} -> {theme.ICONS.get('sentinel','')} "
                         f"{step.verdict.value}", kind="sentinel",
                         state=step.verdict.value)
        else:
            session.note(f"{phase}: nothing was handed over, so no sentinel "
                         f"ran", kind="sentinel")
        session.note(f"{decision.move.value.upper()}"
                     + (f" ({decision.target_phase})"
                        if decision.target_phase else "")
                     + f" - {decision.because}",
                     kind="architect", state=decision.move.value)

        before = session.crate_growth[-1]["entities"] if session.crate_growth else 0
        total = session.entities()
        # What this phase added, by kind, not only how many. "+100" says the
        # graph got bigger; "+100 schema:MediaObject" says what it got.
        now_crate = arch.memory.snapshot()
        changed = kgview.what_changed(session.last_snapshot, now_crate)
        session.last_snapshot = now_crate
        session.crate_growth.append({"phase": phase, "entities": total,
                                     "added": total - before,
                                     "by_kind": changed["by_kind"][:6]})
        session.note(f"RO-Crate: {total} entities (+{total - before} from "
                     f"{phase})", kind="crate")

        if decision.move is Move.STOP:
            break
        if decision.move is Move.GO_BACK and decision.target_phase in order:
            # `route.py` guards against a loop: a phase re-run for the same
            # finding code is not sent back twice. So this obeys and does not
            # second-guess it.
            index = order.index(decision.target_phase)
            continue
        if decision.move is Move.ASK and decision.question is not None:
            session.question = decision.question
            answer = ui.ask(decision.question)
            session.question = None
            session.transcript = ui.transcript()
            _record_answer(arch, phase, researcher, answer.chosen)
            if answer.chosen == SKIPPED:
                session.note("left unresolved; it stays in what has no answer",
                             kind="note")
            elif answer.chosen.lower().startswith("[stop]"):
                session.note("that option ends the run, and it does",
                             kind="stop", state="stop")
                break
            else:
                session.note("recorded in the ledger. Carrying the chosen "
                             "repair out is not wired, so the next phase "
                             "starts from the package as it stands - that is "
                             "a gap, not a silent success.", kind="note")
        index += 1

    session.transcript = ui.transcript()
    session.note(arch.summary(), kind="architect")
    for line in arch.advice() or []:
        session.note(line, kind="architect")


def _record_answer(arch: Architect, phase: str, researcher: str,
                   chosen: str) -> None:
    """Put the researcher's answer in the ledger, shaped like every other row.

    `Architect._record` writes these rows and is the Architect's own business;
    appending one from here keeps the shape identical without reaching into it
    for anything but the list it publishes.
    """
    arch.ledger.append({
        "at": now_iso(), "run_id": arch.run_id, "phase": phase,
        "actor": researcher, "verdict": None, "move": Move.ASK.value,
        "target": phase,
        "because": f"the researcher answered: {chosen}",
        "notes": ["answered in the web interface",
                  "the chosen action was recorded, not carried out"],
    })


# --------------------------------------------------------------------------- #
#  5. The page
# --------------------------------------------------------------------------- #
def url(value: Any) -> str:
    """One query-string value, percent-encoded.

    `esc()` is for HTML and leaves `#` alone, which is correct there and
    catastrophic in a URL: an entity id like `#check/design_to_build-1` put
    raw into `?focus=` makes the browser treat everything from the `#` as a
    fragment, so neither the focus nor anything after it ever reaches the
    server. Every link into the graph silently did nothing, and the page just
    stayed where it was.
    """
    from urllib.parse import quote                              # noqa: PLC0415
    return quote(str(value), safe="")


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def icon(kind: str) -> str:
    glyph = theme.icon(kind)
    return (f'<span class="icon" aria-hidden="true">{esc(glyph)}</span> '
            if glyph else "")


def missing_report(filled: Any) -> list[dict]:
    """Every required field with no answer, and what each one would stop."""
    return [{"key": f.key, "label": f.label, "phase": f.phase or "",
             "stops": f.why_it_is_asked,
             "section": next((s.title for s in FORM.sections
                              if f in s.fields), "")}
            for f in filled.missing()]


def render_missing(items: list[dict]) -> str:
    if not items:
        return ('<p class="ok">Nothing required is unanswered. The cycle can '
                'be started.</p>')
        # No answer is invented to get to this state: it says the fields were
        # answered, not that the answers were good.
    rows = "\n".join(
        f'<li><a href="#field-{esc(i["key"])}">{esc(i["label"])}</a>'
        f'<span class="stops">{esc(i["stops"])}</span>'
        + (f'<span class="phase">{esc(i["phase"])}</span>' if i["phase"] else "")
        + "</li>" for i in items)
    return (f'<p class="count"><strong id="missing-count">{len(items)}</strong> '
            f'required field(s) have no answer. Each one, and what it would '
            f'stop:</p>\n<ul class="missing">{rows}</ul>')


def render_control(field: Any, value: Any) -> str:
    """One control per field, honouring its kind. Never a preselected value.

    Everything a researcher has already typed is shown back. A recommendation
    is marked and is not selected: `checked` appears nowhere in this function.
    """
    name, fid = esc(field.key), f"field-{esc(field.key)}"
    place = f' placeholder="{esc(field.placeholder)}"' if field.placeholder else ""

    if field.kind.value == "longtext":
        return (f'<textarea id="{fid}" name="{name}" rows="3"{place}>'
                f'{esc(value or "")}</textarea>')
    if field.kind.value in ("list", "steps"):
        text = "\n".join(value) if isinstance(value, list) else (value or "")
        ordered = ("one per line, in order" if field.kind.value == "steps"
                   else "one per line")
        return (f'<textarea id="{fid}" name="{name}" rows="4"{place}>'
                f'{esc(text)}</textarea>'
                f'<span class="hint">{ordered}</span>')
    if field.kind.value == "number":
        return (f'<input id="{fid}" name="{name}" type="number" step="any" '
                f'inputmode="decimal" value="{esc(value or "")}"{place}>')
    if field.kind.value == "quantity":
        # The unit is shown and is not editable. It is the form's statement,
        # not the researcher's: a quantity whose unit can be retyped is a
        # quantity that arrives in whatever unit somebody felt like.
        return (f'<span class="quantity">'
                f'<input id="{fid}" name="{name}" type="number" step="any" '
                f'inputmode="decimal" value="{esc(value or "")}"{place}>'
                f'<span class="unit">{esc(field.unit or "")}</span></span>'
                f'<span class="hint">the unit is fixed by the form</span>')
    if field.kind.value == "bool":
        out = [f'<span class="options">']
        for word in ("yes", "no"):
            chosen = value is (word == "yes")
            mark = " checked" if chosen and value != "" else ""
            out.append(f'<label class="option"><input type="radio" '
                       f'name="{name}" value="{word}"{mark}> {word}</label>')
        out.append("</span>")
        return "".join(out)
    if field.kind.value in ("choice", "multi"):
        kind = "radio" if field.kind.value == "choice" else "checkbox"
        chosen = value if isinstance(value, list) else [value]
        out = [f'<span class="options">']
        for option in field.options:
            mark = " checked" if option in chosen and option != "" else ""
            hint = OPTION_HINTS.get((field.key, option), "")
            recommended = (field.default is not None
                           and option == field.default)
            out.append(
                f'<label class="option"><input type="{kind}" name="{name}" '
                f'value="{esc(option)}"{mark}> <code>{esc(option)}</code>'
                + (f'<span class="option-why">{esc(hint)}</span>' if hint else "")
                + ('<span class="recommended">recommended - and still has to '
                   'be clicked</span>' if recommended else "")
                + "</label>")
        out.append("</span>")
        return "".join(out)
    return (f'<input id="{fid}" name="{name}" type="text" '
            f'value="{esc(value or "")}"{place}>')


def render_form(session: Session) -> str:
    out = ['<form method="post" action="/save" id="spec-form">']
    for section in FORM.sections:
        out.append(f'<fieldset><legend>{esc(section.title)}</legend>'
                   f'<p class="intent">{esc(section.intent)}</p>')
        for field in section.fields:
            value = session.filled.values.get(field.key, "")
            flags = []
            if field.required:
                flags.append('<span class="req">required</span>')
            if field.phase:
                flags.append(f'<span class="phase">{esc(field.phase)}</span>')
            detail = DETAILS.get(field.key, "")
            out.append(
                f'<div class="field" id="field-{esc(field.key)}">'
                f'<label class="label" for="field-{esc(field.key)}">'
                f'{esc(field.label)}</label>'
                + ("".join(flags))
                + (f'<p class="detail">{esc(detail)}</p>' if detail else "")
                + f'<p class="why">{icon("architect")}why it is asked: '
                  f'{esc(field.why_it_is_asked)}</p>'
                + render_control(field, value)
                + (f'<p class="feeds">feeds: '
                   f'{esc(", ".join(field.feeds))}</p>' if field.feeds else "")
                + "</div>")
        out.append("</fieldset>")
    out.append('<p class="actions"><button type="submit">Save the '
               'specification</button> '
               '<span class="hint">saving changes nothing in the lab; it is '
               'what the run is started from</span></p></form>')
    return "\n".join(out)


def render_question(session: Session) -> str:
    question = session.question
    if question is None:
        return ""
    def recommended(option: str) -> bool:
        """Is this the option the Architect would take? Display only.

        `conversation.py` recommends by tag - "[1a]" - while the option itself
        is the whole sentence that starts with that tag, so a plain equality
        marks nothing. This matches the tag and marks it. It has no part in
        reading the answer: that is still `Interface`, matching the exact text
        or the number, which is what keeps a near miss from being accepted.
        """
        tag = (question.recommended or "").strip()
        return bool(tag) and (option == tag or option.startswith(tag))

    options = "\n".join(
        f'<label class="option"><input type="radio" name="choice" '
        f'value="{esc(option)}"> <span class="n">{i}</span> {esc(option)}'
        + ('<span class="recommended">recommended - and still has to be '
           'clicked</span>' if recommended(option) else "")
        + "</label>"
        for i, option in enumerate(question.options, start=1))
    waiting = ("waiting for your answer" if session.awaiting
               else "the run is about to ask this")
    return f"""
<section class="panel ask" id="question">
  <h2>{icon("ask")}A question for you</h2>
  <p class="who">asked by: {esc(question.asked_by)} - {esc(waiting)}</p>
  <h3>{esc(question.headline)}</h3>
  {f'<p class="detail">{esc(question.detail)}</p>' if question.detail else ''}
  <form method="post" action="/answer">
    <div class="options">{options}</div>
    <p class="hint">Nothing is selected, and nothing is chosen for you. You may
      also type the option's number or its exact text.</p>
    <p><label for="typed">typed answer</label>
       <input id="typed" name="typed" type="text" autocomplete="off"></p>
    <p class="actions">
      <button type="submit" name="way_out" value="">Answer</button>
      <button type="submit" name="way_out" value="why">why - say more, then
        ask again</button>
      <button type="submit" name="way_out" value="skip">skip - leave it
        unresolved</button>
      <button type="submit" name="way_out" value="stop">stop - end the
        run</button>
    </p>
  </form>
</section>"""


def _live_crate(session: Session) -> dict:
    """The crate this page is about: the session's, or a run from disk."""
    if session.looking_at:
        try:
            return kgview.load(session.looking_at)
        except FileNotFoundError:
            pass
    return session.arch.memory.snapshot() if session.arch else {"@graph": []}


def render_sentinel_card(session: Session, handover: str) -> str:
    """What one sentinel actually did, read out of the crate.

    The crate is the record, not a service and not this process's memory, so
    this works for a run that finished yesterday exactly as for one going on
    now. It reports `held to` and `checks applied` because a verdict alone
    cannot tell a reader "it was checked and passed" from "nothing ran" -
    the distinction `sentinel-oo` is careful about and this was not.
    """
    crate = _live_crate(session)
    graph = [e for e in crate.get("@graph", []) if isinstance(e, dict)]
    index = {e.get("@id"): e for e in graph}
    acts = [e for e in graph
            if str(e.get("@id", "")).startswith(f"#check/{handover}-")
            and e.get("@type") == "CreateAction"]

    out = [f'<p class="intent">The sentinel at <code>{esc(handover)}</code>. '
           f'One agent stands at every handover and loads the contract for '
           f'that one; what varies is what it checks against, which is data.'
           f'</p>']
    if not acts:
        out.append('<p class="hint">It has not run in this crate. That is '
                   'not the same as having passed, which is why this says so '
                   'rather than showing nothing.</p>')
        return "".join(out)

    for act in reversed(acts):           # most recent first
        verdict = str(act.get("dbtl:verdict", ""))
        ink = {"accepted": "ok", "accepted_with_flags": "flag",
               "refused": "no"}.get(verdict, "hint")
        mark = {"accepted": icon("accepted"),
                "accepted_with_flags": icon("flagged"),
                "refused": icon("refused")}.get(verdict, "")
        held = act.get("dbtl:heldTo") or [act.get("dbtl:contract", "?")]
        held = [held] if isinstance(held, str) else held
        applied = act.get("dbtl:checksApplied")

        out.append(f'<div class="verdict-card">'
                   f'<p class="{ink}">{mark}<strong>{esc(verdict.upper())}'
                   f'</strong> &middot; {esc(act.get("description", ""))}</p>')
        out.append('<table class="shape"><tbody>')
        out.append(f'<tr><td>held to</td><td>'
                   + "<br>".join(f'<code>{esc(h)}</code>' for h in held)
                   + '</td></tr>')
        if applied is not None:
            out.append(f'<tr><td>checks applied</td><td>{esc(applied)}'
                       f'<span class="hint">a verdict after no checks is not '
                       f'the same claim as one after {esc(applied)}</span>'
                       f'</td></tr>')
        out.append(f'<tr><td>profile</td><td>'
                   f'<code>{esc(act.get("dbtl:profile", "?"))}</code></td></tr>')
        out.append(f'<tr><td>when</td><td>{esc(act.get("startTime", "?"))} '
                   f'&rarr; {esc(act.get("endTime", "?"))}</td></tr>')
        out.append(f'<tr><td>recorded as</td><td>'
                   f'<a href="/?focus={url(act["@id"])}&amp;view=graph#view">'
                   f'<code>{esc(act["@id"])}</code></a>'
                   f'<span class="hint">follow it into the graph</span>'
                   f'</td></tr>')
        out.append('</tbody></table>')

        refs = act.get("object") or []
        refs = [refs] if isinstance(refs, dict) else refs
        if not refs:
            out.append('<p class="ok">Nothing to report: every check it '
                       'applied was satisfied.</p>')
        else:
            out.append(f'<p class="hint">{len(refs)} finding(s), in the '
                       f'contract author\'s own words:</p>'
                       '<table class="findings"><tbody>')
            for ref in refs:
                found = index.get(ref.get("@id") if isinstance(ref, dict)
                                  else ref)
                if found is None:
                    continue
                severity = str(found.get("dbtl:severity", ""))
                row_ink = "no" if severity == "error" else "flag"
                about = found.get("about")
                where = (f'<a href="/?focus={url(about["@id"])}&amp;view=graph#view">'
                         f'<code>{esc(found.get("dbtl:path", ""))}</code></a>'
                         if isinstance(about, dict) else
                         f'<code>{esc(found.get("dbtl:path", ""))}</code>')
                out.append(
                    f'<tr class="{row_ink}"><td>{esc(severity)}</td>'
                    f'<td><strong>{esc(found.get("name", ""))}</strong>'
                    f'<span class="said">{esc(found.get("value", ""))}</span>'
                    + (f'<span class="hint">{esc(found.get("description"))}'
                       f'</span>' if found.get("description") else '')
                    + f'</td><td>{where}</td></tr>')
            out.append('</tbody></table>')
        out.append('</div>')
    return "".join(out)


def render_phase_card(session: Session, phase: str) -> str:
    """One phase: what it did, what it handed over, and who checked it."""
    if phase == "architect":
        crate = _live_crate(session)
        out = ['<p class="intent">The Architect holds what was agreed, holds '
               'the one crate, and decides what follows every verdict. It '
               'does not do the science and it does not check anything: the '
               'phase agents do the first and the sentinel does the second.'
               '</p>']
        out.append(render_crate(session))
        if session.arch is not None:
            out.append(f'<p class="hint">{esc(session.arch.summary())}</p>')
        out.append(f'<p class="hint">{len(crate.get("@graph", []))} entities '
                   f'in the crate right now.</p>')
        return "".join(out)

    flow = session.workflow
    steps = [s for s in (flow.steps if flow else []) if s.phase == phase]
    handover = ring.HANDOVER_AFTER.get(phase, "")
    did = [row for row in session.crate_growth if row["phase"] == phase]

    out = [f'<p class="intent">{esc(phase.title())} &mdash; what the lab does '
           f'here, what it hands over, and who checks it.</p>']

    if did:
        total = did[-1]["entities"]
        added = sum(row["added"] for row in did)
        out.append(f'<p>It has run {len(did)} time(s) and added '
                   f'<strong>{added}</strong> entities; the crate stood at '
                   f'{total} after the last one.</p>')
        kinds = did[-1].get("by_kind") or []
        if kinds:
            out.append('<p class="hint">what it added: '
                       + ", ".join(f"{n}&times; {esc(k)}" for k, n in kinds)
                       + '</p>')
    else:
        out.append('<p class="hint">It has not run in this session.</p>')

    if steps:
        out.append(f'<table class="steps"><caption>its {len(steps)} step(s) '
                   f'in the {esc(flow.name)} workflow</caption><tbody>')
        for step in steps:
            out.append(
                f'<tr><td>{step.number}</td><td>{esc(step.name)}'
                + (f'<span class="hint">{esc(step.note)}</span>'
                   if step.note else '')
                + (f'<span class="hint">routes: '
                   f'{esc(" or ".join(step.routes))}</span>'
                   if step.routes else '')
                + f'</td><td>{esc(", ".join(step.manual_parts))}</td>'
                + f'<td class="n">{step.count_observed or ""}</td></tr>')
        out.append('</tbody></table>')

    if handover:
        out.append(f'<p class="actions">'
                   f'<a href="/?sentinel={esc(handover)}#view">'
                   f'{icon("sentinel")}what the sentinel at '
                   f'<code>{esc(handover)}</code> did</a></p>')
    out.append(f'<p class="actions"><a href="/?view=redo&phase={esc(phase)}'
               f'#view">{icon("go_back")}send the run back to {esc(phase)}'
               f'</a></p>')
    return "".join(out)


def render_restart(session: Session) -> str:
    """Start another run. Two buttons, because they are different decisions.

    Keeping the specification is the usual one: run the same project again
    with another workflow, or after changing a field. Clearing it is the
    other: a different project entirely, back to the first question.

    Neither touches disk. Starting again is not undoing, and a button that
    quietly deleted a finished run would be the single mistake this system
    exists to prevent.
    """
    if session.running:
        return ('<p class="hint">A run is going. Starting over waits for it '
                'to end — answer its question with <code>stop</code>, or '
                'press the button below to ask it to stop.</p>'
                '<form method="post" action="/restart" class="restart">'
                '<button type="submit">Ask the run to stop</button></form>')

    # Something has RUN, which is not the same as something having happened:
    # answering the engine question and loading the example both write to the
    # log, and neither is a run to start over from. The Architect existing is.
    done = session.arch is not None or session.finished
    return (
        f'<form method="post" action="/restart" class="restart">'
        f'<button type="submit" name="how" value="keep"'
        f'{"" if done else " disabled"}>Start another run</button>'
        f'<span class="hint">keeps the engine, the specification and the '
        f'workflow &middot; a new run id, so this one is not added to the '
        f'last one&rsquo;s crate</span>'
        f'<button type="submit" name="how" value="scratch"'
        f'{"" if done else " disabled"}>Start from scratch</button>'
        f'<span class="hint">back to the first question, with the form and '
        f'the workflow cleared</span>'
        f'</form>'
        + ('' if done else '<p class="hint">These wake up once something has '
                           'run.</p>')
        + '<p class="hint">Neither deletes anything. The crate, the graph and '
          'the ledger of every earlier run stay on disk, and the knowledge '
          'graph panel can still be pointed at them.</p>')


def _theme_switch(session: Session) -> str:
    """Dark or light, as links rather than a control.

    A link because it works with JavaScript off, can be bookmarked, and can
    be sent to somebody who wants the light one - which is the usual reason
    anybody asks: a screenshot bound for a paper cannot be black.
    """
    out = []
    for name, label in (("matrix", "dark"), ("paper", "light")):
        if name == session.theme:
            out.append(f'<strong>{label}</strong>')
        else:
            keep = (f"&run={esc(session.looking_at)}"
                    if session.looking_at else "")
            out.append(f'<a href="/?theme={name}{keep}">{label}</a>')
    return "theme: " + " &middot; ".join(out)


def render_log(session: Session) -> str:
    if not session.log:
        return ('<p class="hint">Nothing has run yet. The log appears here, '
                'one line per thing that happened.</p>')
    rows = []
    for row in session.log:
        colour = (f' style="color:{theme.colour(row["state"], session.theme)}"'
                  if row["state"] else "")
        rows.append(f'<li class="{esc(row["kind"])}"{colour}>'
                    f'<span class="at">{esc(row["at"])}</span>'
                    f'{icon(row["kind"])}'
                    f'<span class="said">{esc(row["text"])}</span></li>')
    return f'<ul class="log">{"".join(rows)}</ul>'


def render_crate(session: Session) -> str:
    if not session.crate_growth:
        return ('<p class="hint">The crate grows one phase at a time. The '
                'count per phase appears here.</p>')
    biggest = max(row["entities"] for row in session.crate_growth) or 1
    rows = []
    for row in session.crate_growth:
        kinds = ", ".join(f"{n}&times; {esc(k)}"
                          for k, n in (row.get("by_kind") or []))
        # A bar, because the shape of the growth is the thing: four phases
        # that each add a little look nothing like one that adds everything.
        width = int(100 * row["entities"] / biggest)
        rows.append(
            f'<tr><td>{esc(row["phase"])}</td>'
            f'<td class="n">{row["entities"]}</td>'
            f'<td class="n">+{row["added"]}</td>'
            f'<td class="bar"><span style="width:{width}%"></span></td></tr>'
            + (f'<tr class="kinds"><td></td><td colspan="3">{kinds}</td></tr>'
               if kinds else ""))
    return (f'<table class="crate"><caption>{icon("crate")}entities in the '
            f'RO-Crate after each phase, and what each one added</caption>'
            f'<thead><tr><th>phase</th><th>entities</th><th>added</th>'
            f'<th></th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _replace_phase_steps(flow, phase: str, text: str):
    """One phase's steps rewritten, the rest of the workflow untouched.

    `text` is one step per line, optionally `name | manual: a, b | routes: x, y`.
    The handover marker is carried over from the step that had it, onto the new
    last step of the phase - because which step ends a phase is a fact about
    the phase, and a researcher rewriting their bench protocol should not have
    to remember to re-mark it.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    old = [s for s in flow.steps if s.phase == phase]
    ending = next((s for s in old if s.handover_after), None)

    fresh = []
    for i, line in enumerate(lines):
        bits = [b.strip() for b in line.split("|")]
        name = bits[0].lstrip("0123456789. ").strip() or f"step {i + 1}"
        manual, routes = (), ()
        for extra in bits[1:]:
            low = extra.lower()
            if low.startswith("manual:"):
                manual = tuple(x.strip() for x in extra.split(":", 1)[1].split(",")
                               if x.strip())
            elif low.startswith("routes:"):
                routes = tuple(x.strip() for x in extra.split(":", 1)[1].split(",")
                               if x.strip())
        fresh.append({"name": name, "phase": phase, "manual_parts": list(manual),
                      "routes": list(routes)})
    if ending is not None:
        fresh[-1]["handover_after"] = ending.handover_after
        fresh[-1]["handover_number"] = ending.handover_number

    out, number = [], 0
    for step in flow.steps:
        if step.phase == phase:
            continue
        out.append(step)
    # Rebuild in phase order, renumbering: the numbers are positions, not
    # names, so they have to be recomputed rather than preserved.
    rebuilt = []
    for ph in workflows.PHASES:
        if ph == phase:
            rebuilt.extend(fresh)
        else:
            rebuilt.extend({
                "name": s.name, "phase": s.phase, "note": s.note,
                "count_observed": s.count_observed,
                "manual_parts": list(s.manual_parts), "routes": list(s.routes),
                "handover_after": s.handover_after,
                "handover_number": s.handover_number,
                "carried_out": s.carried_out,
            } for s in out if s.phase == ph)
    for item in rebuilt:
        number += 1
        item["number"] = number
    return workflows.from_dict({
        "name": flow.name, "title": flow.title, "use_case": flow.use_case,
        "based_on": flow.based_on, "description": flow.description,
        "source": f"{flow.source} - {phase} steps rewritten in the interface",
        "steps": rebuilt})


def render_redo(session: Session) -> str:
    """Sending the run back to a phase, on purpose, with the steps rewritten.

    The Architect already goes back by itself when a sentinel refuses something
    it can name. This is the other case, which no contract can detect: the
    result was valid and the researcher is not satisfied with it.
    """
    if session.arch is None:
        return ('<p class="hint">This appears once a run has happened. '
                'Nothing can be sent back before there is something to send '
                'back.</p>')
    flow = session.workflow
    out = ['<p class="hint">Nothing is undone. The crate keeps what the '
           'earlier attempt wrote and this one is added beside it, so the '
           'two stay comparable - an append-only crate that replaced a '
           'phase\'s work on a retry would be append-only in name only.</p>',
           '<form method="post" action="/redo">']
    out.append('<fieldset><legend>Which phase, and why</legend>')
    for phase in PHASES:
        done = any(row["phase"] == phase for row in session.crate_growth)
        out.append(
            f'<label class="choice"><input type="radio" name="phase" '
            f'value="{esc(phase)}"{" checked" if phase == "design" else ""}> '
            f'<strong>{esc(phase)}</strong>'
            f'<span class="hint">'
            + ("it has run; everything from here on runs again"
               if done else "it has not run yet in this run")
            + '</span></label>')
    out.append('<label>why you are sending it back'
               '<input type="text" name="reason" spellcheck="false" '
               'placeholder="the panel was too narrow to say anything about '
               'thermostability"></label>'
               '<p class="hint">Required, and it goes into the ledger. A '
               'repeat with no reason recorded cannot be told apart from a '
               'retry loop by anybody reading the run afterwards.</p>'
               '</fieldset>')

    if flow is not None:
        example = "\n".join(
            s.name + (f" | manual: {', '.join(s.manual_parts)}"
                      if s.manual_parts else "")
            + (f" | routes: {', '.join(s.routes)}" if s.routes else "")
            for s in flow.steps if s.phase == "design")
        out.append(
            '<details class="own"><summary>Rewrite that phase\'s steps too'
            '</summary>'
            '<p class="hint">One step per line. Add <code>| manual: a, b</code> '
            'or <code>| routes: x, y</code> after a step. The handover marker '
            'moves to the new last step by itself. Leave it empty to re-run '
            'the phase unchanged. The whole workflow is re-checked against '
            'the same five rules, because changing one phase can break a rule '
            'that spans the cycle.</p>'
            f'<label>the steps of the phase you picked'
            f'<textarea name="steps" rows="8" spellcheck="false" '
            f'placeholder="{esc(example)}"></textarea></label></details>')

    out.append('<p class="actions"><button type="submit">Send it back</button>'
               '<span class="hint">it runs again from there to the end of the '
               'cycle</span></p></form>')
    return "".join(out)


def render_kg(session: Session) -> str:
    """The knowledge graph itself: where it is, its shape, and one hop of it.

    There is no second database. The RO-Crate IS the graph, and this panel
    says so with the two paths rather than leaving a reader to assume there is
    a store somewhere they have not been shown.

    No picture of the whole thing. Four hundred nodes drawn at once is a grey
    cloud that looks like insight and answers nothing; a count by type and one
    entity's neighbourhood each answer a question and stay readable.
    """
    # Which crate this panel is showing: this session's run, or any run on
    # disk the person picked. Looking at a graph should not require making
    # one first - somebody who opens this to SEE something would otherwise
    # have to run a cycle before there was anything to look at.
    showing, crate = session.run_id, None
    if session.looking_at:
        try:
            crate = kgview.load(session.looking_at)
            showing = session.looking_at
        except FileNotFoundError:
            crate = None
    if crate is None and session.arch is not None:
        crate = session.arch.memory.snapshot()

    on_disk = kgview.runs_on_disk()
    picker = ['<form method="get" action="/" class="focus-form">'
              '<label>look at a run on disk'
              '<select name="run"><option value="">'
              '&mdash; this session&rsquo;s run &mdash;</option>']
    for name, size in on_disk[:20]:
        chosen = ' selected' if name == session.looking_at else ''
        picker.append(f'<option value="{esc(name)}"{chosen}>{esc(name)} '
                      f'&middot; {size} entities</option>')
    picker.append('</select></label><p class="actions">'
                  '<button type="submit">Show it</button>'
                  '<span class="hint">the crate on disk, read as it stands. '
                  'Nothing is run.</span></p></form>')

    if crate is None:
        return ('<p class="hint">There is no graph in this session yet - it '
                'appears as soon as the first phase has written into the '
                'crate. You can look at an earlier run in the meantime:</p>'
                + "".join(picker))
    where = kgview.paths(showing)
    marks = kgview.landmarks(crate)
    links = kgview.edges(crate)
    graph = [e for e in crate.get("@graph", []) if isinstance(e, dict)]

    out = [f'<p class="hint">There is no separate graph database. The RO-Crate '
           f'<em>is</em> the knowledge graph, and it is on disk in two forms '
           f'that are the same thing said twice:</p>'
           f'<ul class="where"><li><code>{esc(where["crate"])}</code>'
           f'<span class="hint">JSON-LD, the authority, append-only</span></li>'
           f'<li><code>{esc(where["graph"])}</code>'
           f'<span class="hint">the same lifted to N-Triples, rewritten on '
           f'every change, for querying</span></li></ul>']

    out.append(f'<p>{len(graph)} entities, {len(links)} internal edges.</p>')

    out.append('<table class="shape"><caption>what is in it</caption><tbody>')
    for kind, count in kgview.shape(crate)[:12]:
        out.append(f'<tr><td class="n">{count}</td><td>{esc(kind)}</td></tr>')
    out.append('</tbody></table>')

    # ---- where to start ---------------------------------------------------
    starts = []
    if marks["plan"]:
        starts.append((marks["plan"][0], "the plan this run followed"))
    starts.append((marks["root"], "the root of the crate"))
    for check in marks["checks"]:
        starts.append((check["id"],
                       f'the sentinel at {check["contract"]} - {check["verdict"]}'))
    out.append('<p class="hint">Follow one thing rather than look at all of '
               'them. Provenance is read backwards, so both directions are '
               'shown.</p><ul class="starts">')
    for ref, what in starts[:8]:
        out.append(f'<li><a href="/?focus={url(ref)}&amp;view=graph#view">'
                   f'<code>{esc(ref)}</code></a> '
                   f'<span class="hint">{esc(what)}</span></li>')
    out.append('</ul>')

    out.extend(picker)
    out.append('<form method="get" action="/" class="focus-form">'
               '<label>or an entity id<input type="text" name="focus" '
               f'value="{esc(session.focus or "")}" spellcheck="false" '
               'placeholder="#sample/BP1-A01"></label>'
               '<p class="actions"><button type="submit">Look at it</button>'
               '</p></form>')

    # ---- the neighbourhood ------------------------------------------------
    if session.focus:
        near = kgview.neighbourhood(crate, session.focus)
        if not near["found"]:
            out.append(f'<p class="no">{icon("refused")}nothing in this crate '
                       f'has the id <code>{esc(session.focus)}</code></p>')
        else:
            # The picture first. A table of edges answers the same question
            # and nobody reads it: a graph that is only ever tabulated is a
            # graph nobody has seen.
            out.append(kgview.draw(near))
            out.append(f'<div class="chosen"><p><code>{esc(near["id"])}</code> '
                       f'&middot; {esc(", ".join(near["types"]))}</p>')
            if near["name"]:
                out.append(f'<p><strong>{esc(near["name"])}</strong></p>')
            if near["literals"]:
                out.append('<table class="shape"><tbody>' + "".join(
                    f'<tr><td>{esc(k)}</td><td>{esc(str(v)[:120])}</td></tr>'
                    for k, v in list(near["literals"].items())[:12])
                    + '</tbody></table>')
            for title, key in (("it points at", "points_at"),
                               ("points at it", "pointed_at_by")):
                items = near[key]
                out.append(f'<p class="hint">{len(items)} {esc(title)}:</p>'
                           '<table class="shape"><tbody>')
                for edge in items[:14]:
                    out.append(
                        f'<tr><td>{esc(edge["property"])}</td>'
                        f'<td><a href="/?focus={url(edge["id"])}&amp;view=graph#view">'
                        f'<code>{esc(edge["id"])}</code></a></td>'
                        f'<td class="hint">{esc(edge["kind"])}</td></tr>')
                if len(items) > 14:
                    out.append(f'<tr><td></td><td class="hint">and '
                               f'{len(items) - 14} more</td><td></td></tr>')
                out.append('</tbody></table>')
            out.append('</div>')
    return "".join(out)


def render_setup(session: Session) -> str:
    """The questions that come before the form: what will do the thinking.

    Every option says what it needs and whether it is reachable from this
    machine, probed now rather than claimed - so "not ready" is information
    the person can act on instead of a failure they meet later.
    """
    state = session.setup.state()
    out = [f'<form method="post" action="/setup" id="setup-form">']

    for question in session.setup.questions():
        out.append(f'<fieldset><legend>{esc(question["headline"])}</legend>')
        out.append(f'<p class="intent">{esc(question["why"])}</p>')

        if question["kind"] == "secret":
            if question["present"]:
                out.append('<p class="hint">A key is already in this '
                           'process. Leave this empty to keep it.</p>')
            out.append(
                '<label>paste it here'
                '<input type="password" name="api_key" autocomplete="off" '
                'spellcheck="false" placeholder="sk-ant-..."></label>'
                '<p class="hint">It goes into this process\'s environment and '
                'nowhere else: not to disk, not into the crate, not into the '
                'ledger, and never back into this page. It dies when the '
                'server stops.</p>')
        elif question["kind"] == "choice":
            for option in question["options"]:
                checked = ' checked' if option["key"] == question["value"] else ''
                mark = (f'<span class="ok">{icon("accepted")}ready</span>'
                        if option["ready"] else
                        f'<span class="no">{icon("refused")}not ready</span>')
                where = ("stays on this machine" if not option["leaves_machine"]
                         else "prompts leave this machine")
                out.append(
                    f'<label class="choice"><input type="radio" name="engine" '
                    f'value="{esc(option["key"])}"{checked}> '
                    f'<strong>{esc(option["label"])}</strong> {mark}'
                    f'<span class="hint">{esc(option["needs"])}</span>'
                    f'<span class="hint">{esc(option["detail"])}'
                    + (f' &middot; fix: {esc(option["fix"])}' if option["fix"] else '')
                    + f' &middot; {esc(where)}</span></label>')
        else:                                   # choice_or_text
            for option in question["options"]:
                checked = ' checked' if option["key"] == question["value"] else ''
                out.append(
                    f'<label class="choice"><input type="radio" name="model" '
                    f'value="{esc(option["key"])}"{checked}> '
                    f'<code>{esc(option["label"])}</code>'
                    f'<span class="hint">{esc(option["needs"])}</span></label>')
            out.append('<label>or type another model id'
                       '<input type="text" name="model_typed" '
                       'autocomplete="off" placeholder="any id the engine '
                       'accepts"></label>')
        out.append('</fieldset>')

    out.append('<p class="actions"><button type="submit">Use this</button>'
               '<span class="hint">nothing runs yet: this only decides what '
               'would</span></p></form>')

    # What is settled, and the one thing a probe cannot tell you.
    out.append('<div class="chosen">')
    out.append(f'<p>chosen: <strong>{esc(state["engine_label"])}</strong>'
               + (f' &middot; <code>{esc(state["model"])}</code>'
                  if state["model"] else '')
               + f' &middot; {esc(state["detail"])}</p>')
    if state["fix"]:
        out.append(f'<p class="hint">fix: {esc(state["fix"])}</p>')
    if state["engine"] != "rules":
        out.append(
            '<form method="post" action="/verify">'
            '<button type="submit">Test it with one real call</button>'
            '<span class="hint">a probe knows a key is present; only a call '
            'knows it works</span></form>')
    if state["verified"]:
        bad = state["verified"].startswith("FAILED")
        out.append(f'<p class="{"no" if bad else "ok"}">'
                   f'{icon("refused") if bad else icon("accepted")}'
                   f'{esc(state["verified"])}</p>')
    out.append('</div>')
    return "".join(out)


PHASE_ICON = {"design": "⧉", "build": "⧉", "test": "⧉", "learn": "⧉"}


def render_workflow(session: Session) -> str:
    """The demonstrations, and the door out of them.

    Four workflows ship with this interface. Three describe a real use case and
    one is a blank to rewrite, and all four are held to the same five rules -
    numbered steps, the four phases in order, exactly four handovers each on
    the last step of its phase, and counts that only go down. A workflow the
    researcher writes is checked against those same rules and refused in the
    same words, because a system that validates handovers and waves its own
    inputs through is only half honest.
    """
    flow = session.workflow
    out = ['<div class="flows">']

    # ---- pick one ---------------------------------------------------------
    out.append('<form method="post" action="/workflow" class="pick-flow">')
    for other in workflows.load_all():
        chosen = ' checked' if flow is not None and other.name == flow.name else ''
        marks = other.problems()
        state = (f'<span class="ok">{icon("accepted")}{len(other.steps)} steps</span>'
                 if not marks else
                 f'<span class="no">{icon("refused")}{len(marks)} problem(s)</span>')
        out.append(
            f'<label class="choice"><input type="radio" name="pick" '
            f'value="{esc(other.name)}"{chosen}> '
            f'<strong>{esc(other.title or other.name)}</strong> {state}'
            f'<span class="hint">{esc(other.use_case)} &middot; '
            f'{esc(other.source[:150])}</span></label>')
    out.append('<p class="actions"><button type="submit">Use this workflow'
               '</button><span class="hint">it decides how many things the run '
               'is about, and which step each handover follows</span></p>'
               '</form>')

    if flow is None:
        out.append('<p class="hint">No workflow could be read. The run will '
                   'use the panel size from the form below.</p></div>')
        return "".join(out)

    # ---- what the chosen one says ----------------------------------------
    out.append(f'<div class="chosen"><p><strong>{esc(flow.title)}</strong></p>'
               f'<p class="hint">{esc(flow.description)}</p>'
               f'<p class="hint">source: {esc(flow.source)}</p>')
    for bad in session.workflow_problems:
        out.append(f'<p class="no">{icon("refused")}{esc(bad)}</p>')
    out.append('</div>')

    out.append('<table class="steps"><thead><tr><th>#</th><th>step</th>'
               '<th>phase</th><th>left</th><th>by hand</th></tr></thead><tbody>')
    previous = None
    for step in flow.steps:
        lost = ""
        if step.count_observed is not None:
            lost = str(step.count_observed)
            if previous is not None and previous > step.count_observed:
                lost += (f' <span class="no">&minus;{previous - step.count_observed}'
                         f'</span>')
            previous = step.count_observed
        row = (f'<tr class="phase-{esc(step.phase)}">'
               f'<td>{step.number}</td>'
               f'<td>{esc(step.name)}'
               + (f'<span class="hint">{esc(step.note)}</span>' if step.note else '')
               + (f'<span class="hint">routes: '
                  f'{esc(" or ".join(step.routes))}</span>' if step.routes else '')
               + '</td>'
               f'<td>{esc(step.phase)}</td>'
               f'<td>{lost}</td>'
               f'<td>{esc(", ".join(step.manual_parts))}</td></tr>')
        out.append(row)
        if step.is_handover:
            number = step.handover_number or "?"
            out.append(
                f'<tr class="handover-row"><td>{icon("sentinel")}</td>'
                f'<td colspan="4">handover {number} &middot; '
                f'<code>{esc(step.handover_after)}</code> &middot; the sentinel '
                f'checks it here, and the crate grows by what it finds</td></tr>')
    out.append('</tbody></table>')

    counted = flow.attrition()
    if counted:
        unexplained = sum(lost or 0 for _, _, lost in counted)
        out.append(f'<p class="hint">{icon("flagged")}{unexplained} thing(s) '
                   f'disappear between the counted steps. A Build handover that '
                   f'cannot say why is incomplete - this is the gap, shown '
                   f'before the run rather than after it.</p>')

    # ---- or write your own ------------------------------------------------
    out.append(
        '<details class="own"><summary>Write your own workflow</summary>'
        '<p class="hint">Paste YAML in the same shape. It is checked against '
        'the same five rules the four above pass, and refused in the same '
        'words if it does not. Start from the blank one and rename the steps.'
        '</p>'
        '<form method="post" action="/workflow">'
        '<label>your workflow'
        '<textarea name="yaml" rows="14" spellcheck="false" '
        'placeholder="name: my_cycle&#10;title: ...&#10;steps:&#10;'
        '  - number: 1&#10;    name: Decide what to make&#10;'
        '    phase: design"></textarea></label>'
        '<p class="actions"><button type="submit">Check and use it</button>'
        '<span class="hint">nothing runs yet</span></p></form></details>')

    out.append('</div>')
    return "".join(out)


VIEWS = (("cycle", "the cycle"), ("spec", "specification"),
         ("workflow", "workflow"), ("crate", "the crate"),
         ("graph", "knowledge graph"), ("redo", "send it back"))


def render_overview(session: Session, items: list[dict]) -> str:
    """The band that never goes away: the shape, the state, the next move.

    Overview first, then detail. The whole system is a ring - four phases,
    a sentinel at each boundary, one crate in the middle - and a reader needs
    that shape in their head before any panel below means anything. It was
    drawn on slides for days before it was ever on the screen.

    Everything urgent lives here too, because a page where the question is
    eight panels down is a page where the question is missed.
    """
    crate = _live_crate(session)
    # The growth belongs to THIS session's run. Handing it alongside a crate
    # read from disk mixes two runs into one drawing - it showed "design:
    # 1038 entities added" over a crate of 435, which is two answers to one
    # question. When looking at disk, the crate alone is asked.
    state = ring.read(crate, None if session.looking_at
                      else session.crate_growth)
    focus = (f"sentinel:{session.sentinel}" if session.sentinel else
             f"phase:{session.phase}" if session.phase else "")

    status = ("a run is going" if session.running else
              "the run has ended" if session.finished else "nothing running")
    out = [f'<div class="overview">',
           ring.draw(state, focus=focus),
           '<div class="overview-side">']

    out.append(f'<p class="status {"going" if session.running else ""}">'
               f'{esc(status)}</p>')
    if session.looking_at:
        out.append(f'<p class="hint">looking at <code>'
                   f'{esc(session.looking_at)}</code> on disk &middot; '
                   f'<a href="/?run=">back to this session</a></p>')
    if state["plan"]:
        out.append(f'<p class="hint">{icon("phase_agent")}'
                   f'{esc(state["plan"])}</p>')

    out.append('<form method="post" action="/run">'
               f'<button type="submit"'
               f'{" disabled" if session.running or items else ""}>'
               f'Run the four phases</button>'
               f'<span class="hint">'
               + ('a run is already going' if session.running else
                  f'<a href="/?view=spec#view">{len(items)} answer(s) still '
                  f'missing</a>' if items else
                  'Design, Build, Test, Learn, each followed by its sentinel')
               + '</span></form>')
    out.append('<p class="hint">Click a phase or a sentinel on the ring to '
               'see what it did.</p>')
    out.append('</div></div>')
    return "".join(out)


def _view_title(session: Session) -> tuple[str, str]:
    """The heading of the one card on show, and its icon."""
    if session.sentinel:
        return f"the sentinel at {session.sentinel}", "sentinel"
    if session.phase:
        return (("the Architect" if session.phase == "architect"
                 else f"the {session.phase} phase"),
                "architect" if session.phase == "architect" else "phase_agent")
    return dict(VIEWS).get(session.view, "the cycle"), {
        "cycle": "phase_agent", "spec": "researcher", "workflow": "phase_agent",
        "crate": "crate", "graph": "graph", "redo": "go_back",
    }.get(session.view, "phase_agent")


def render_view(session: Session, items: list[dict]) -> str:
    """One view at a time. Each is a real URL, so it can be sent to somebody."""
    if session.sentinel:
        return render_sentinel_card(session, session.sentinel)
    if session.phase:
        return render_phase_card(session, session.phase)

    if session.view == "spec":
        return (f'<p class="intent">{esc(FORM.description)}</p>'
                f'<p class="hint">Every field says why it is asked, because '
                f'that is the whole difference between a form and an open '
                f'prompt. Nothing is prefilled and no option is '
                f'preselected.</p>'
                f'<form method="post" action="/example" class="example-form">'
                f'<button type="submit">Load the worked example</button>'
                f'<span class="hint">the answers from Anil Wipat\'s cycle, '
                f'which are what each field\'s own placeholder says.</span>'
                f'</form>{render_missing(items)}{render_form(session)}')
    if session.view == "workflow":
        return (f'<p class="intent">A contract says what must travel between '
                f'two phases. A workflow says what the lab does in each phase '
                f'and which step the handover follows. Both are needed: a '
                f'contract with no workflow is a rule with nothing to apply '
                f'to.</p>{render_workflow(session)}')
    if session.view == "crate":
        return (f'{render_crate(session)}'
                f'<p class="actions">'
                f'<a href="/crate.json" download>{icon("crate")}download the '
                f'RO-Crate (JSON)</a>'
                f'<a href="/ledger.jsonl" download>{icon("ledger")}download '
                f'the ledger (JSONL)</a></p>'
                f'<p class="hint">The ledger carries the reason for every '
                f'decision verbatim, as <code>route.py</code> wrote it.</p>')
    if session.view == "graph":
        return render_kg(session)
    if session.view == "redo":
        return render_redo(session)

    # the cycle: the log, and the controls around it
    return (f'<p class="hint">With JavaScript the log updates itself. '
            f'Without it, reload to see where the run has got to: '
            f'<a href="/">reload</a>.</p>'
            f'{render_restart(session)}'
            f'<div id="log">{render_log(session)}</div>')


def render_page(session: Session) -> str:
    items = missing_report(session.filled)
    palette = "".join(f"  --{key}: {value};\n"
                      for key, value in theme.palette(session.theme).items())
    title, title_icon = _view_title(session)

    if not session.setup.answered and not session.looking_at:
        body = (f'<section class="card" id="view">'
                f'<h2>{icon("architect")}Before anything runs</h2>'
                f'{render_setup(session)}</section>')
        nav = ""
    else:
        here = (session.sentinel or session.phase or session.view)
        nav = '<nav class="views">' + "".join(
            f'<a href="/?view={name}#view"'
            f'{" class=\"here\"" if here == name else ""}>{esc(label)}</a>'
            for name, label in VIEWS) + '</nav>'
        body = (
            f'{render_question(session)}'
            f'{render_overview(session, items)}'
            f'{nav}'
            f'<section class="card" id="view">'
            f'<h2>{icon(title_icon)}{esc(title)}</h2>'
            f'{render_view(session, items)}</section>'
            f'<details class="setup-again"><summary>{icon("architect")}'
            f'what will do the thinking</summary>{render_setup(session)}'
            f'</details>')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(theme.PROJECT)} - the Architect</title>
<link rel="stylesheet" href="/static/app.css">
<style>
:root {{
{palette}  --font: {theme.FONT_STACK};
}}
</style>
</head>
<body data-theme="{esc(session.theme)}">
<div class="rain" aria-hidden="true"></div>
<header>
  <h1>{icon("architect")}{esc(theme.PROJECT)}</h1>
  <p class="tagline">{esc(theme.TAGLINE)}</p>
  <p class="hint">{_theme_switch(session)} &middot; run
    <code>{esc(session.run_id)}</code> &middot; form from
    <code>{esc(FORM_SOURCE)}</code></p>
</header>
<main>
{body}
</main>
<footer>
  <p class="hint">State lives on the server, one Architect per session. The
    crate and the ledger are on disk under
    <code>runs/{esc(session.run_id)}/</code>.</p>
</footer>
<script src="/static/app.js" defer></script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
#  6. The server
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "DBTLArchitect/1.0"
    protocol_version = "HTTP/1.1"

    # ---- plumbing ---------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    def _session(self) -> tuple[Session, bool]:
        raw = self.headers.get("Cookie", "")
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:
            pass
        morsel = jar.get(COOKIE_NAME)
        return session_for(morsel.value if morsel else None)

    def _send(self, body: bytes, kind: str = "text/html; charset=utf-8",
              status: int = HTTPStatus.OK, new_session: str | None = None,
              download: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Everything this page needs is served from this origin: two static
        # files and inline styles. Saying so costs four headers and takes away
        # the whole class of "something else got onto the page" - which matters
        # more now that a page here can be holding an API key in a form field.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; img-src 'self' data:; "
                         "form-action 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if new_session:
            self.send_header("Set-Cookie",
                             f"{COOKIE_NAME}={new_session}; Path=/; "
                             f"HttpOnly; SameSite=Lax")
        if download:
            # Re-sanitised here even though every caller builds it from a
            # `safe_run_id`. A header assembled by string interpolation should
            # not depend on a promise made somewhere else in the file.
            clean = "".join(c for c in str(download)
                            if c.isalnum() or c in "-_.") or "download"
            self.send_header("Content-Disposition",
                             f'attachment; filename="{clean[:120]}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, new_session: str | None = None) -> None:
        self._send(json.dumps(payload, indent=1).encode(),
                   "application/json; charset=utf-8", new_session=new_session)

    def _redirect(self, where: str = "/", new_session: str | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        if new_session:
            self.send_header("Set-Cookie",
                             f"{COOKIE_NAME}={new_session}; Path=/; "
                             f"HttpOnly; SameSite=Lax")
        self.end_headers()

    def _body(self) -> dict[str, list[str]] | None:
        """The posted form, or None when the request is not one.

        Returns None after answering the request itself, so a caller does
        exactly nothing more. `int()` on a header the client controls raises,
        and an unbounded Content-Length is an invitation to allocate until this
        process dies - neither should reach the routing table.
        """
        raw_length = (self.headers.get("Content-Length") or "0").strip()
        try:
            length = int(raw_length)
        except ValueError:
            self._send(b"a Content-Length that is not a number\n",
                       "text/plain; charset=utf-8", HTTPStatus.BAD_REQUEST)
            return None
        if length < 0 or length > MAX_BODY:
            self._send(f"a form here is a few kilobytes; "
                       f"{MAX_BODY // 1024} KB is the limit\n".encode(),
                       "text/plain; charset=utf-8",
                       HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        return parse_qs(raw, keep_blank_values=True)

    def _drain(self) -> None:
        """Read and throw away the body of a request being refused."""
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        except ValueError:
            length = 0
        if length > 0:
            self.rfile.read(length)

    def _not_from_this_machine(self) -> str:
        """Empty when the POST is fine; otherwise why it is being refused.

        A reason rather than a boolean, because this rejects a legitimate
        request as readily as a hostile one and a person meeting it needs to
        know which header was wrong.

        A cookie with `SameSite=Lax` is sent on a cross-site POST in some
        browsers' reading of it, and `/run` here starts real agents while
        `/setup` accepts an API key. So the Origin, when the browser sends one,
        has to be this server's own; and the Host has to be the loopback name
        the page was loaded from, which is what stops another name resolving to
        127.0.0.1 and driving this interface.
        """
        host = (self.headers.get("Host") or "").strip()
        name = host.rsplit(":", 1)[0].strip("[]").lower()
        if name not in ALLOWED_HOSTS:
            return f"Host {host!r} is not one of {sorted(ALLOWED_HOSTS)}"
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        if not origin or origin == "null":
            return ""            # no Origin header: a plain form POST
        if origin in (f"http://{host}", f"https://{host}"):
            return ""
        # The same machine under one of its other loopback names is still this
        # machine. A page served from localhost:8765 posting to 127.0.0.1:8765
        # is the single most likely way a person meets this check, and calling
        # that cross-site would be a lie.
        port = host.rsplit(":", 1)[1] if ":" in host else ""
        here = {f"{scheme}://{n}{':' + port if port else ''}"
                for scheme in ("http", "https") for n in ALLOWED_HOSTS}
        if origin in here:
            return ""
        return f"Origin {origin!r} is not this server"

    # ---- GET --------------------------------------------------------------
    def do_GET(self) -> None:                                  # noqa: N802
        path = urlparse(self.path).path
        session, is_new = self._session()
        cookie = session.id if is_new else None

        if path == "/":
            # `?focus=` moves the knowledge-graph panel to one entity. A GET
            # because it is a view, which means it can be linked, bookmarked
            # and sent to somebody else.
            query = parse_qs(urlparse(self.path).query)
            wanted = query.get("theme")
            if wanted is not None and wanted[0] in theme.PALETTES:
                session.theme = wanted[0]

            # `run` first, because changing which crate is shown has to clear
            # a focus that belonged to the previous one - and `focus` second,
            # so that `?run=x&focus=y` means both. The first version cleared
            # the focus whenever `run` was present at all, which quietly made
            # exactly that link do only half of what it said.
            run = query.get("run")
            if run is not None:
                # Through `safe_run_id`, so a name from a query string cannot
                # reach outside `runs/`.
                chosen = (safe_run_id(run[0].strip(), "")
                          if run[0].strip() else "")
                if chosen != session.looking_at:
                    session.focus = ""
                session.looking_at = chosen
            asked = query.get("focus")
            if asked is not None:
                session.focus = asked[0].strip()[:200]
                session.view = "graph"

            # A view, a phase or a sentinel. Naming one clears the others,
            # because "one view at a time" has to be true of the state and
            # not only of the rendering.
            chosen_view = query.get("view")
            if chosen_view is not None:
                session.view = chosen_view[0].strip()[:20] or "cycle"
                session.phase = session.sentinel = ""
            phase = query.get("phase")
            if phase is not None:
                session.phase = phase[0].strip()[:20]
                session.sentinel = ""
            seen = query.get("sentinel")
            if seen is not None:
                session.sentinel = seen[0].strip()[:40]
                session.phase = ""
            self._send(render_page(session).encode(), new_session=cookie)
        elif path.startswith("/static/"):
            self._static(path)
        elif path == "/state":
            self._json(self._state(session), new_session=cookie)
        elif path == "/missing":
            items = missing_report(session.filled)
            self._json({"missing": len(items), "fields": items,
                        "ready": session.filled.ready()}, new_session=cookie)
        elif path == "/crate.json":
            crate = (session.arch.memory.snapshot() if session.arch
                     else {"@context": None, "@graph": [],
                           "note": "no run yet: there is no crate"})
            self._send(json.dumps(crate, indent=1).encode(),
                       "application/json; charset=utf-8",
                       download=f"{session.run_id}-ro-crate-metadata.json")
        elif path == "/ledger.jsonl":
            rows = session.arch.ledger if session.arch else []
            body = "".join(json.dumps(row) + "\n" for row in rows)
            self._send(body.encode(), "application/x-ndjson; charset=utf-8",
                       download=f"{session.run_id}-architect.jsonl")
        elif path == "/transcript.json":
            self._json({"transcript": session.transcript})
        else:
            self._send(b"not here\n", "text/plain; charset=utf-8",
                       HTTPStatus.NOT_FOUND)

    do_HEAD = do_GET

    def _static(self, path: str) -> None:
        name = path.rsplit("/", 1)[-1]
        # An allowlist rather than a path join: the two files that exist are
        # the two files that may be served, and no request can walk out of the
        # directory because no request names the directory.
        kinds = {"app.css": "text/css; charset=utf-8",
                 "app.js": "application/javascript; charset=utf-8"}
        if name not in kinds or not (STATIC / name).is_file():
            self._send(b"not here\n", "text/plain; charset=utf-8",
                       HTTPStatus.NOT_FOUND)
            return
        self._send((STATIC / name).read_bytes(), kinds[name])

    def _state(self, session: Session) -> dict:
        items = missing_report(session.filled)
        question = session.question
        return {
            "running": session.running, "finished": session.finished,
            "awaiting": session.awaiting,
            "question": (None if question is None else
                         {"headline": question.headline,
                          "asked_by": question.asked_by,
                          "options": list(question.options),
                          "recommended": question.recommended}),
            "missing": len(items), "fields": items,
            "entities": session.entities(),
            "crate": list(session.crate_growth),
            # The colour of a state is resolved here, from theme.py, so the
            # browser never holds a second copy of what amber and red mean.
            "log": [dict(row, icon=theme.icon(row["kind"]),
                         colour=(theme.colour(row["state"], session.theme)
                                 if row["state"] else ""))
                    for row in session.log],
        }

    # ---- POST -------------------------------------------------------------
    def do_POST(self) -> None:                                 # noqa: N802
        path = urlparse(self.path).path
        session, is_new = self._session()
        cookie = session.id if is_new else None

        refused = self._not_from_this_machine()
        if refused:
            # The body has to go somewhere even when the request is refused.
            # This is HTTP/1.1 with keep-alive: a body left in the socket is
            # read as the START of the next request, so the refusal would
            # corrupt whatever the browser asked for next. Found exactly that
            # way - a 403 followed by a 501 on "engine=apiGET /state".
            self._drain()
            self.log_message('refused a POST: %s', refused)
            self._send(f"this interface only accepts posts from the machine it "
                       f"runs on, and only under the name the page was loaded "
                       f"from ({refused}). /run starts real agents and /setup "
                       f"accepts a key, so a request from anywhere else is "
                       f"refused.\n".encode(),
                       "text/plain; charset=utf-8", HTTPStatus.FORBIDDEN)
            return

        posted = self._body()
        if posted is None:
            return                      # _body answered the request itself

        if path == "/setup":
            setup_mod.apply(session.setup, {
                "engine": (posted.get("engine") or [""])[0],
                "model": (posted.get("model_typed") or [""])[0].strip()
                         or (posted.get("model") or [""])[0],
                "api_key": (posted.get("api_key") or [""])[0],
            }, client_host=self.client_address[0])
            # The key is now in the environment or was refused; `posted` still
            # holds the string the browser sent, so it goes before anything
            # else can keep a reference to it.
            posted = {}
            state = session.setup.state()
            session.note(f"engine: {state['engine_label']}"
                         + (f", model {state['model']}" if state["model"] else "")
                         + (" - stays on this machine" if not state["leaves_machine"]
                            else " - prompts leave this machine"),
                         kind="architect")
            for line in session.setup.notes[-3:]:
                session.note(line, kind="note")
            self._redirect("/#setup-panel", new_session=cookie)
        elif path == "/workflow":
            picked = (posted.get("pick") or [""])[0].strip()
            written = (posted.get("yaml") or [""])[0]
            if written.strip():
                # A workflow the researcher wrote. It is read, then checked
                # against the same rules the four demonstrations pass, and
                # refused in the same words - the interface does not get to
                # hold its own inputs to a lower standard than its handovers.
                try:
                    import yaml as _yaml                   # noqa: PLC0415
                    flow = workflows.from_dict(_yaml.safe_load(written) or {})
                except Exception as exc:                   # noqa: BLE001
                    session.workflow_problems = [f"it could not be read: {exc}"]
                    session.note(f"the workflow you wrote could not be read: "
                                 f"{exc}", kind="refused", state="refused")
                else:
                    session.workflow_problems = flow.problems()
                    if flow.problems():
                        session.note(f"the workflow you wrote was refused: "
                                     f"{len(flow.problems())} problem(s)",
                                     kind="refused", state="refused")
                        for bad in flow.problems():
                            session.note(bad, kind="refused")
                    else:
                        session.workflow = flow
                        session.workflow_source = "written here"
                        session.note(f"workflow accepted: {flow.name}, "
                                     f"{len(flow.steps)} steps, written here",
                                     kind="architect", state="accepted")
            elif picked:
                try:
                    session.workflow = workflows.load(picked)
                    session.workflow_problems = []
                    session.workflow_source = f"{picked}.yaml on disk"
                    flow = session.workflow
                    session.note(f"workflow: {flow.title} ({len(flow.steps)} "
                                 f"steps, {flow.starting_count() or 'no'} "
                                 f"counted things)", kind="architect")
                except Exception as exc:                   # noqa: BLE001
                    session.note(f"no workflow named {picked!r}: {exc}",
                                 kind="refused", state="refused")
            self._redirect("/#workflow-panel", new_session=cookie)
        elif path == "/example":
            # Load the worked example. Not invented answers: every field in
            # `architect/forms/bioprospecting.yaml` carries a placeholder,
            # and those placeholders ARE the worked cycle's own answers -
            # 96 candidates, Twist, the OT-2, the two build routes. So this
            # fills from them, and from the first option of a choice, and the
            # log says which came from where. Nothing is hidden behind a
            # button that says "example".
            filled, guessed = {}, []
            for field in FORM.all_fields():
                if field.placeholder:
                    filled[field.key] = field.placeholder
                elif field.options:
                    filled[field.key] = (list(field.options)
                                         if field.kind.value == "multi"
                                         else field.options[0])
                    guessed.append(field.key)
                elif field.kind.value == "steps":
                    # The form asks for the numbered steps, and the workflow
                    # IS the numbered steps. Filling this from anywhere else
                    # would put the same cycle in the interface twice and let
                    # the two drift apart.
                    flow = session.workflow
                    filled[field.key] = (
                        [f"{s.number}. {s.name} [{s.phase}]"
                         for s in flow.steps] if flow else [])
                elif field.kind.value == "bool":
                    filled[field.key] = False
                    guessed.append(field.key)
            session.filled.values = filled
            session.filled.provenance = {
                key: {"source": "the worked example", "at": now_iso(),
                      "by": "architect/forms/bioprospecting.yaml"}
                for key in filled}
            try:
                session.workflow = workflows.load("bioprospecting")
                session.workflow_source = "bioprospecting.yaml on disk"
                session.workflow_problems = []
            except Exception:                              # noqa: BLE001
                pass
            session.note(f"loaded the worked example: {len(filled)} field(s) "
                         f"from the form's own placeholders, which are the "
                         f"answers from Anil Wipat's cycle", kind="architect")
            if guessed:
                session.note(f"{len(guessed)} field(s) had no example answer "
                             f"and took the first option instead: "
                             f"{', '.join(guessed[:8])}", kind="note")
            self._redirect("/#form-panel", new_session=cookie)
        elif path == "/restart":
            how = (posted.get("how") or ["keep"])[0].strip()
            if session.running:
                # A thread cannot be killed from here, and pretending it can
                # would leave a run writing into a crate the page says is
                # finished. `stop` is the word the interface already uses and
                # the run ends itself on it.
                if session.awaiting:
                    session.submit_answer("stop")
                    session.note("asked the run to stop. Press it again once "
                                 "it has ended.", kind="stop", state="stop")
                else:
                    session.note("a run is going and it is not waiting for an "
                                 "answer. Let it finish, or answer its next "
                                 "question with `stop`.", kind="note")
            else:
                said = session.restart(keep_specification=(how != "scratch"))
                session.note(f"started over: {said}", kind="architect")
                session.note("nothing on disk was touched. The previous "
                             "run's crate, graph and ledger are still there, "
                             "and the graph panel can still be pointed at "
                             "them.", kind="crate")
                if how == "scratch":
                    session.setup = setup_mod.Setup()
            self._redirect("/", new_session=cookie)
        elif path == "/redo":
            phase = (posted.get("phase") or [""])[0].strip().lower()
            why = (posted.get("reason") or [""])[0].strip()
            steps = (posted.get("steps") or [""])[0]
            if session.running:
                session.note("a run is going; wait for it before sending it "
                             "back", kind="note")
            elif session.arch is None:
                session.note("there is nothing to send back: no run has "
                             "happened yet", kind="refused", state="refused")
            elif phase not in PHASES:
                session.note(f"{phase!r} is not one of {list(PHASES)}",
                             kind="refused", state="refused")
            elif not why:
                # The reason is not politeness. A repeat with no reason in the
                # ledger cannot be told apart from a loop by anybody reading
                # the run afterwards, including us.
                session.note("say why. A repeat with no reason recorded is "
                             "indistinguishable from a retry loop",
                             kind="refused", state="refused")
            else:
                if steps.strip() and session.workflow is not None:
                    # The steps of that phase, rewritten. The whole workflow is
                    # rebuilt and re-checked, because changing one phase can
                    # break a rule that spans the cycle - moving a handover, or
                    # a count that now climbs.
                    edited = _replace_phase_steps(session.workflow, phase, steps)
                    bad = edited.problems() if edited else ["it could not be read"]
                    if bad:
                        session.note(f"the rewritten {phase} steps were "
                                     f"refused: {len(bad)} problem(s)",
                                     kind="refused", state="refused")
                        for line in bad:
                            session.note(line, kind="refused")
                        self._redirect("/#redo-panel", new_session=cookie)
                        return
                    session.workflow = edited
                    session.workflow_source = f"{phase} steps rewritten here"
                    session.note(f"the {phase} steps were rewritten and pass "
                                 f"the same five rules", kind="architect",
                                 state="accepted")
                start_run(session, from_phase=phase, reason=why)
            self._redirect("/#redo-panel", new_session=cookie)
        elif path == "/verify":
            # One real, minimal call. A probe knows a key is present; only a
            # call knows it works, and the researcher asked to be able to test
            # their own key, so the button exists and nothing presses it for
            # them.
            said = session.setup.verify()
            session.note(f"verified the engine: {said}", kind="note",
                         state=("refused" if said.startswith("FAILED") else ""))
            self._redirect("/#setup-panel", new_session=cookie)
        elif path == "/save":
            session.filled.values = values_from_post(posted)
            session.filled.provenance = {
                key: {"source": "web form", "at": now_iso(),
                      "by": str(session.filled.values.get("researcher") or
                               "unknown")}
                for key in session.filled.values}
            self._redirect("/#missing-panel", new_session=cookie)
        elif path == "/missing":
            # The draft is not saved: typing in the form must not quietly
            # become an answer. The count comes from the same `Filled.missing`
            # the page uses, so there is one definition of missing.
            draft = Filled(form=FORM, values=values_from_post(posted))
            items = missing_report(draft)
            self._json({"missing": len(items), "fields": items,
                        "ready": draft.ready()}, new_session=cookie)
        elif path == "/run":
            start_run(session)
            self._redirect("/#run-panel", new_session=cookie)
        elif path == "/answer":
            way_out = (posted.get("way_out") or [""])[0].strip()
            typed = (posted.get("typed") or [""])[0].strip()
            chosen = (posted.get("choice") or [""])[0].strip()
            # Order: a way out is a button that was clicked on purpose; a typed
            # answer beats a radio nobody moved. Nothing is defaulted, and an
            # empty answer is passed through so `Interface` can refuse it.
            raw = way_out or typed or chosen
            if not session.submit_answer(raw):
                session.note("an answer arrived with no question waiting for "
                             "it; it was not used", kind="note")
            self._redirect("/#question", new_session=cookie)
        else:
            self._send(b"not here\n", "text/plain; charset=utf-8",
                       HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="The Architect's web interface (standard library only).")
    parser.add_argument("--host", default="127.0.0.1",
                        help="default 127.0.0.1: there is no authentication "
                             "here and /run executes real agents")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    # A deliberate `--host` must not lock the person out of their own server:
    # posts are refused unless the Host header is one of these names, and the
    # default set is loopback only. Said out loud, because widening it is a
    # real decision - in a container this is how the published port works.
    if args.host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.add(args.host)
        print(f"\n  posts will also be accepted for the name {args.host!r}. "
              f"There is no authentication here.")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"\n  {theme.PROJECT} - {theme.TAGLINE}")
    print(f"  the Architect, in a browser: http://{args.host}:{args.port}/")
    print(f"  form: {FORM_SOURCE}")
    print(f"  {len(FORM.all_fields())} field(s) in {len(FORM.sections)} "
          f"section(s), {len(FORM.required_keys())} required")
    print("  state is in memory: a restart loses the form and the log, and "
          "keeps the crate and the ledger on disk.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
