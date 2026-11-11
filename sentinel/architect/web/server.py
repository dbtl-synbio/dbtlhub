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

STATIC = HERE / "static"
COOKIE_NAME = "dbtl_session"
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


class Session:
    """What one browser is doing: a form being filled, and at most one run."""

    def __init__(self, session_id: str):
        self.id = session_id
        self.filled = Filled(form=FORM)
        self.log: list[dict] = []
        self.crate_growth: list[dict] = []
        self.arch: Architect | None = None
        self.run_id = f"web-{session_id[:6]}"
        self.thread: threading.Thread | None = None
        self.finished = False
        self.question: Question | None = None   # what is being asked
        self.awaiting = False                   # the run thread is waiting
        self.transcript: list[dict] = []
        self._answer: list[str] = []
        self._answered = threading.Event()
        self._lock = threading.Lock()

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
        if field.kind is Kind.MULTI:
            values[field.key] = [v for v in raw if v]
            continue
        text = (raw[0] if raw else "").strip()
        if field.kind in (Kind.LIST, Kind.STEPS):
            values[field.key] = [line.strip() for line in text.splitlines()
                                 if line.strip()]
        elif field.kind is Kind.BOOL:
            # Not a checkbox. A checkbox has a default - unticked - and this
            # form is not allowed one, so a bool is two radios and neither is
            # chosen until somebody chooses it.
            values[field.key] = (True if text == "yes"
                                 else False if text == "no" else "")
        elif field.kind in (Kind.NUMBER, Kind.QUANTITY):
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
def start_run(session: Session) -> None:
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
    session.thread = threading.Thread(target=_run, args=(session,), daemon=True)
    session.thread.start()


def _run(session: Session) -> None:
    try:
        _cycle(session)
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


def _cycle(session: Session) -> None:
    from architect.wiring import phase_runner, sentinel_checker     # noqa: PLC0415

    values = dict(session.filled.values)
    researcher = str(wanted(values, "researcher")[0] or "researcher")
    profile = str(wanted(values, "profile")[0] or "")
    named_run, _ = wanted(values, "run_id")
    session.run_id = safe_run_id(named_run or "", session.run_id)
    arch = Architect(session.run_id, researcher=researcher)
    session.arch = arch
    session.note(f"Architect for run {session.run_id}, answering to "
                 f"{researcher}", kind="architect")

    # ---- a crate somebody else wrote, if there is one ---------------------
    adopt, _ = wanted(values, "adopt")
    adopt_path, _ = wanted(values, "adopt_path")
    if adopt is True and adopt_path:
        adoption = arch.adopt(str(adopt_path))
        session.note(f"adopted {adopt_path}: {adoption}", kind="crate")

    # ---- the consultation -------------------------------------------------
    workflow = workflow_from(values)
    questions = arch.consult(objective=str(wanted(values, "objective")[0] or ""),
                             workflow=workflow or None)
    reading = getattr(arch.spec, "reading", None)
    if reading is not None:
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
    raw_size, size_from = wanted(values, "panel_size")
    panel_size = as_number(raw_size)
    if panel_size is None:
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
    runner = phase_runner(profile=profile or "bioprospecting",
                          lab=(str(lab) if lab else None), **inputs)
    checker = sentinel_checker(profile=profile or "bioprospecting")

    # ---- the four phases --------------------------------------------------
    order = list(PHASES)
    index, guard = 0, 0
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
        session.crate_growth.append({"phase": phase, "entities": total,
                                     "added": total - before})
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

    if field.kind is Kind.LONGTEXT:
        return (f'<textarea id="{fid}" name="{name}" rows="3"{place}>'
                f'{esc(value or "")}</textarea>')
    if field.kind in (Kind.LIST, Kind.STEPS):
        text = "\n".join(value) if isinstance(value, list) else (value or "")
        ordered = ("one per line, in order" if field.kind is Kind.STEPS
                   else "one per line")
        return (f'<textarea id="{fid}" name="{name}" rows="4"{place}>'
                f'{esc(text)}</textarea>'
                f'<span class="hint">{ordered}</span>')
    if field.kind is Kind.NUMBER:
        return (f'<input id="{fid}" name="{name}" type="number" step="any" '
                f'inputmode="decimal" value="{esc(value or "")}"{place}>')
    if field.kind is Kind.QUANTITY:
        # The unit is shown and is not editable. It is the form's statement,
        # not the researcher's: a quantity whose unit can be retyped is a
        # quantity that arrives in whatever unit somebody felt like.
        return (f'<span class="quantity">'
                f'<input id="{fid}" name="{name}" type="number" step="any" '
                f'inputmode="decimal" value="{esc(value or "")}"{place}>'
                f'<span class="unit">{esc(field.unit or "")}</span></span>'
                f'<span class="hint">the unit is fixed by the form</span>')
    if field.kind is Kind.BOOL:
        out = [f'<span class="options">']
        for word in ("yes", "no"):
            chosen = value is (word == "yes")
            mark = " checked" if chosen and value != "" else ""
            out.append(f'<label class="option"><input type="radio" '
                       f'name="{name}" value="{word}"{mark}> {word}</label>')
        out.append("</span>")
        return "".join(out)
    if field.kind in (Kind.CHOICE, Kind.MULTI):
        kind = "radio" if field.kind is Kind.CHOICE else "checkbox"
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


def render_log(session: Session) -> str:
    if not session.log:
        return ('<p class="hint">Nothing has run yet. The log appears here, '
                'one line per thing that happened.</p>')
    rows = []
    for row in session.log:
        colour = (f' style="color:{theme.colour(row["state"])}"'
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
    rows = "".join(
        f'<tr><td>{esc(row["phase"])}</td><td class="n">{row["entities"]}</td>'
        f'<td class="n">+{row["added"]}</td></tr>'
        for row in session.crate_growth)
    return (f'<table class="crate"><caption>{icon("crate")}entities in the '
            f'RO-Crate after each phase</caption><thead><tr><th>phase</th>'
            f'<th>entities</th><th>added</th></tr></thead><tbody>{rows}'
            f'</tbody></table>')


def render_page(session: Session) -> str:
    items = missing_report(session.filled)
    palette = "".join(f"  --{key}: {value};\n"
                      for key, value in theme.PALETTE.items())
    status = ("a run is going" if session.running else
              "the run has ended" if session.finished else "nothing running")
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
<body>
<div class="rain" aria-hidden="true"></div>
<header>
  <h1>{icon("architect")}{esc(theme.PROJECT)}</h1>
  <p class="tagline">{esc(theme.TAGLINE)}</p>
  <p class="hint">The Architect holds what was agreed and decides what follows
    every verdict. Four phase agents do the work - Design, Build, Test, Learn -
    and any of them may be a person. Four sentinels check each handover and may
    refuse it. One RO-Crate grows.</p>
  <p class="hint">session <code>{esc(session.id)}</code> &middot; run
    <code>{esc(session.run_id)}</code> &middot; {esc(status)} &middot; form
    from <code>{esc(FORM_SOURCE)}</code></p>
</header>
<main>
{render_question(session)}
<section class="panel" id="missing-panel">
  <h2>What is still missing</h2>
  {render_missing(items)}
</section>

<section class="panel" id="form-panel">
  <h2>{esc(FORM.title)}</h2>
  <p class="intent">{esc(FORM.description)}</p>
  <p class="hint">Every field says why it is asked, because that is the whole
    difference between a form and an open prompt. Nothing is prefilled and no
    option is preselected.</p>
  {render_form(session)}
</section>

<section class="panel" id="run-panel">
  <h2>{icon("phase_agent")}The cycle</h2>
  <form method="post" action="/run">
    <button type="submit"{' disabled' if session.running else ''}>Run the four
      phases</button>
    <span class="hint">{'a run is already going' if session.running else
      ('needs ' + str(len(items)) + ' more answer(s)') if items else
      'Design, Build, Test, Learn, each followed by its sentinel'}</span>
  </form>
  <p class="hint">With JavaScript the log below updates itself. Without it,
    reload the page to see where the run has got to:
    <a href="/">reload</a>.</p>
  <div id="log">{render_log(session)}</div>
</section>

<section class="panel" id="crate-panel">
  <h2>{icon("crate")}The crate</h2>
  <div id="crate">{render_crate(session)}</div>
  <p class="actions">
    <a href="/crate.json" download>{icon("crate")}download the RO-Crate
      (JSON)</a>
    <a href="/ledger.jsonl" download>{icon("ledger")}download the ledger
      (JSONL)</a>
  </p>
  <p class="hint">The ledger carries the reason for every decision verbatim,
    as <code>route.py</code> wrote it.</p>
</section>
</main>
<footer>
  <p class="hint">State lives on the server, one Architect per session. If this
    process restarts, the form and the log are gone; the crate and the ledger
    are on disk under <code>runs/{esc(session.run_id)}/</code>.</p>
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
        if new_session:
            self.send_header("Set-Cookie",
                             f"{COOKIE_NAME}={new_session}; Path=/; "
                             f"HttpOnly; SameSite=Lax")
        if download:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{download}"')
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

    def _body(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        return parse_qs(raw, keep_blank_values=True)

    # ---- GET --------------------------------------------------------------
    def do_GET(self) -> None:                                  # noqa: N802
        path = urlparse(self.path).path
        session, is_new = self._session()
        cookie = session.id if is_new else None

        if path == "/":
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
                         colour=(theme.colour(row["state"])
                                 if row["state"] else ""))
                    for row in session.log],
        }

    # ---- POST -------------------------------------------------------------
    def do_POST(self) -> None:                                 # noqa: N802
        path = urlparse(self.path).path
        session, is_new = self._session()
        cookie = session.id if is_new else None
        posted = self._body()

        if path == "/save":
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
