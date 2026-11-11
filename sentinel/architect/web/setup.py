#!/usr/bin/env python3
"""The questions the interface asks before anything runs: which model, whose key.

    python3 architect/web/setup.py          # the probes below, offline

WHY THIS COMES FIRST
The specification form asks what the researcher wants to do. This asks what is
going to do it. Those are different questions and mixing them was wrong: a
person who fills in a panel of 96 enzymes and only then discovers that no model
is reachable has wasted the interesting part of their attention on the boring
failure. So the interface opens here, the answers are cheap, and every option
says what it needs before it is chosen.

FIVE OPTIONS, AND THE FIRST ONE IS NOT A MODEL
`RulesEngine` is deterministic, offline, and enough to check every handover in
this framework. It is listed first and marked ready, always, because a person
should be able to see the whole cycle run before deciding whether a model is
worth a key. The other four are the four ways people actually have a model to
hand: the Claude Code CLI, the Codex CLI, Ollama on the laptop, or an API key.

THE KEY
It goes into this process's environment and nowhere else.

  * Not into the Session, so it cannot be rendered by accident.
  * Not into the ledger, the crate, or any package - `framework/engines_api.py`
    keeps that promise by never having an `api_key` attribute at all, and this
    file keeps its half by never storing one either.
  * Not back into the HTML. `state()` reports presence and length. Four
    characters of a key are four characters of a key, so not even those.
  * Not to disk. Setting it is per-process and dies with the server, which is
    the correct lifetime for a secret pasted into a form.

A key is still a secret in a browser POST, so the module refuses to accept one
over anything but a loopback connection: see `key_post_is_allowed`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.engines import RUNNERS, CommandEngine, EngineError   # noqa: E402
from framework.engines_api import (API_URL, DEFAULT_MODEL, KEY_VAR,  # noqa: E402
                                   ApiEngine, api_key, redact)
from framework.llm import RulesEngine                               # noqa: E402

# The models the API option offers. Ordered most capable first, because the
# person choosing has usually not thought about it and the default should be
# the one that gets the answer right. Any other id can be typed in instead -
# this is a shortlist, not a whitelist, and the engine passes `model` through.
MODELS: list[tuple[str, str]] = [
    ("claude-opus-5-5", "most capable"),
    ("claude-sonnet-5-5", "faster, cheaper, usually enough"),
    ("claude-haiku-5-5", "cheapest"),
    ("claude-fable-5-1", "small"),
]
if DEFAULT_MODEL not in [m for m, _ in MODELS]:
    MODELS.append((DEFAULT_MODEL, "this framework's default"))

OLLAMA_DEFAULT = "qwen2.5-coder:3b"


# --------------------------------------------------------------------------- #
#  What is actually reachable from here
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Ready:
    """Whether an option can be used right now, and what to do if not.

    `ready=False` is a normal state and never an error: four of the five
    options need something this machine may not have, and saying so plainly is
    the whole job of this screen.
    """
    ready: bool
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    needs: str                 # what it requires, in one line
    leaves_machine: bool       # does a prompt go over the network?
    wants_key: bool = False
    wants_model: bool = False

    def probe(self) -> Ready:
        return _PROBES[self.key]()


OPTIONS: list[Option] = [
    Option("rules", "no model - deterministic rules",
           "nothing. Offline, and enough to check every handover.",
           leaves_machine=False),
    Option("claude", RUNNERS["claude"].label,
           RUNNERS["claude"].needs, leaves_machine=True),
    Option("codex", RUNNERS["codex"].label,
           RUNNERS["codex"].needs, leaves_machine=True),
    Option("ollama", RUNNERS["ollama"].label,
           RUNNERS["ollama"].needs, leaves_machine=False, wants_model=True),
    Option("api", "Anthropic API, with your own key",
           f"a key in {KEY_VAR}. Choose this and press the button: the box to "
           f"paste it into, and the list of models, appear on the next screen. "
           f"Two steps on purpose, so this one works with JavaScript off.",
           leaves_machine=True, wants_key=True, wants_model=True),
]

OPTION = {o.key: o for o in OPTIONS}


def _probe_command(name: str) -> Ready:
    """Is the CLI on PATH? Asked with `which`, not by running it.

    Running `claude -p` to find out whether `claude` works would start a model
    turn to answer a question about a file path, which is the kind of cost this
    screen exists to avoid.
    """
    argv = RUNNERS[name].argv
    found = shutil.which(argv[0])
    if found:
        return Ready(True, f"{argv[0]} found at {found}")
    return Ready(False, f"{argv[0]} is not on PATH", RUNNERS[name].needs)


def _probe_ollama() -> Ready:
    base = _probe_command("ollama")
    if not base.ready:
        return base
    pulled = ollama_models()
    if not pulled:
        return Ready(True, "ollama found, no model pulled yet",
                     f"ollama pull {OLLAMA_DEFAULT}")
    return Ready(True, f"ollama found, {len(pulled)} model(s) pulled: "
                       f"{', '.join(pulled[:4])}")


def _probe_api() -> Ready:
    if api_key() is None:
        return Ready(False, f"{KEY_VAR} is not set in this process",
                     "paste a key below, or export it before starting the server")
    return Ready(True, f"a key is present in {KEY_VAR} "
                       f"({len(api_key())} characters). Never shown, never stored.")


_PROBES = {
    "rules": lambda: Ready(True, "always ready: no model, no key, no network"),
    "claude": lambda: _probe_command("claude"),
    "codex": lambda: _probe_command("codex"),
    "ollama": _probe_ollama,
    "api": _probe_api,
}


def ollama_models() -> list[str]:
    """Models already on this machine. Empty on any trouble, never raising.

    This runs while a page is being rendered, so it is given three seconds and
    no opinions: a slow or broken `ollama` must not be able to hang the
    interface.
    """
    if shutil.which("ollama") is None:
        return []
    try:
        done = subprocess.run(["ollama", "list"], capture_output=True,
                              text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    out = []
    for line in (done.stdout or "").splitlines()[1:]:
        tag = line.split()[0] if line.split() else ""
        if tag:
            out.append(tag)
    return out


# --------------------------------------------------------------------------- #
#  The answers
# --------------------------------------------------------------------------- #
@dataclass
class Setup:
    """What the researcher chose. Note what is not here: the key.

    `engine` and `model` are written into the ledger as the engine's own
    `name`, because a run with a model and a run without have to be
    distinguishable afterwards. The key is not part of that record and is not
    part of this object - it lives in the environment and only there.
    """
    engine: str = "rules"
    model: str = ""
    answered: bool = False
    verified: str = ""          # what a `verify()` actually proved, if asked
    notes: list[str] = field(default_factory=list)

    # ---- the questions, in the order they are asked ----------------------
    def questions(self) -> list[dict]:
        """The screen, as data. The server renders it; it decides nothing."""
        chosen = OPTION.get(self.engine)
        qs = [{
            "key": "engine",
            "headline": "What should do the thinking?",
            "why": "A handover can be checked with no model at all. Pick that "
                   "first if you want to see the cycle run before you spend a "
                   "key on it.",
            "kind": "choice",
            "options": [{
                "key": o.key, "label": o.label, "needs": o.needs,
                "leaves_machine": o.leaves_machine,
                "ready": o.probe().ready, "detail": o.probe().detail,
                "fix": o.probe().fix,
            } for o in OPTIONS],
            "value": self.engine,
        }]
        if chosen is not None and chosen.wants_key:
            qs.append({
                "key": "api_key",
                "headline": f"Your key for {API_URL}",
                "why": "It goes into this process's environment and nowhere "
                       "else: not to disk, not into the crate, not into the "
                       "ledger, and never back into this page.",
                "kind": "secret",
                "value": "",
                "present": api_key() is not None,
            })
        if chosen is not None and chosen.wants_model:
            qs.append({
                "key": "model",
                "headline": "Which model?",
                "why": "Written into the ledger with every step it touches, so "
                       "a later reader can tell which answers came from which.",
                "kind": "choice_or_text",
                "options": ([{"key": m, "label": m, "needs": why}
                             for m, why in MODELS]
                            if chosen.key == "api" else
                            [{"key": m, "label": m, "needs": "pulled locally"}
                             for m in ollama_models()] or
                            [{"key": OLLAMA_DEFAULT,
                              "needs": f"not pulled yet: ollama pull {OLLAMA_DEFAULT}",
                              "label": OLLAMA_DEFAULT}]),
                "value": self.model or self.default_model(),
            })
        return qs

    def default_model(self) -> str:
        if self.engine == "api":
            return MODELS[0][0]
        if self.engine == "ollama":
            return (ollama_models() or [OLLAMA_DEFAULT])[0]
        return ""

    def state(self) -> dict:
        """Safe to render, safe to log, safe to put in a JSON response.

        The one thing a caller might want and cannot have is the key.
        """
        ready = OPTION[self.engine].probe() if self.engine in OPTION else Ready(
            False, f"unknown engine {self.engine!r}")
        return {
            "engine": self.engine,
            "engine_label": OPTION[self.engine].label
            if self.engine in OPTION else self.engine,
            "model": self.model,
            "answered": self.answered,
            "ready": ready.ready,
            "detail": ready.detail,
            "fix": ready.fix,
            "leaves_machine": OPTION[self.engine].leaves_machine
            if self.engine in OPTION else True,
            "key_present": api_key() is not None,
            "verified": self.verified,
            "notes": list(self.notes),
        }

    # ---- building the thing itself ----------------------------------------
    def engine_object(self):
        """The `Engine` the agents will be given.

        Falls back to `RulesEngine` rather than raising, and says so in
        `notes`: a model that turned out to be unreachable is a reason to run
        deterministically, not a reason to refuse to run.
        """
        if self.engine == "rules":
            return RulesEngine()
        try:
            if self.engine == "api":
                return ApiEngine(model=self.model or MODELS[0][0])
            if self.engine in RUNNERS:
                argv = list(RUNNERS[self.engine].argv)
                if self.engine == "ollama" and self.model:
                    argv[-1] = self.model       # `ollama run <model>`
                return CommandEngine(runner=self.engine, argv=argv)
        except EngineError as exc:
            self.notes.append(f"{self.engine}: {redact(exc)} - using rules instead")
            return RulesEngine()
        self.notes.append(f"unknown engine {self.engine!r} - using rules instead")
        return RulesEngine()

    def verify(self) -> str:
        """One real, minimal call, because the researcher asked for one.

        A probe says a key is present and a CLI is on PATH. Neither says the
        key is valid or the CLI is logged in, and the only honest way to learn
        that is to spend one tiny call on it. So this is a separate action the
        person triggers, never something the screen does on its own.
        """
        if self.engine == "rules":
            self.verified = "nothing to verify: no model is used"
            return self.verified
        engine = self.engine_object()
        if isinstance(engine, RulesEngine):
            self.verified = "could not build that engine; see notes"
            return self.verified
        if isinstance(engine, ApiEngine):
            engine = ApiEngine(model=engine.model, max_tokens=16, retries=0)
        try:
            answer = engine._ask(PING)
        except Exception as exc:                 # noqa: BLE001 - reported, not raised
            self.verified = f"FAILED: {redact(exc)[:300]}"
            return self.verified
        ok = isinstance(answer, dict) and answer.get("ok") is True
        self.verified = (f"OK: {engine.name} answered"
                         if ok else
                         f"answered, but not in the agreed shape: "
                         f"{redact(answer)[:160]}")
        return self.verified


PING = ('Reply with exactly this JSON and nothing else: {"ok": true}')


# --------------------------------------------------------------------------- #
#  Taking the answers
# --------------------------------------------------------------------------- #
def key_post_is_allowed(client_host: str) -> bool:
    """A key may only be pasted from the machine the server runs on.

    The interface binds to 127.0.0.1 by default, but a container, a port
    forward or a `--host 0.0.0.0` can put it on a network, and a secret in a
    form field posted over plain HTTP across a network is a secret in plain
    text on that network. Refusing is the only safe answer, and the screen says
    to export the variable before starting the server instead.
    """
    return client_host in ("127.0.0.1", "::1", "localhost")


def apply(setup: Setup, values: dict, client_host: str = "127.0.0.1") -> Setup:
    """Take the posted answers. The only function that ever sees a key.

    It puts it in the environment and drops it. Note the deliberate asymmetry:
    an empty key field does NOT clear a key already in the environment,
    because the field is empty every time the page is re-rendered and the
    researcher did not mean "forget my key" by not retyping it.
    """
    engine = str(values.get("engine") or setup.engine or "rules").strip()
    if engine not in OPTION:
        setup.notes.append(f"ignored unknown engine {engine!r}")
        engine = setup.engine
    setup.engine = engine

    model = str(values.get("model") or "").strip()
    setup.model = model or setup.default_model()

    raw = values.get("api_key")
    key = str(raw or "").strip()
    if key:
        if not key_post_is_allowed(client_host):
            setup.notes.append(
                f"refused a key posted from {client_host}: a key is only "
                f"accepted from this machine. Export {KEY_VAR} before "
                f"starting the server instead.")
        else:
            os.environ[KEY_VAR] = key
            setup.notes.append(
                f"{KEY_VAR} set for this process only ({len(key)} characters). "
                f"It is not on disk and not in the ledger.")
    del raw, key                                  # not kept, not returned

    setup.answered = True
    setup.verified = ""                           # a new choice is unproven
    return setup


# --------------------------------------------------------------------------- #
def main() -> None:
    """What this machine can actually do, right now."""
    print(f"\n{'=' * 74}\nWHAT CAN DO THE THINKING, ON THIS MACHINE\n{'=' * 74}\n")
    for o in OPTIONS:
        r = o.probe()
        mark = "ready" if r.ready else "not ready"
        net = "leaves the machine" if o.leaves_machine else "stays local"
        print(f"  [{mark:^9}] {o.label}")
        print(f"              {r.detail}")
        if r.fix:
            print(f"              fix: {r.fix}")
        print(f"              {net}\n")

    print(f"{'=' * 74}\nTHE KEY IS NOT IN THE ANSWERS\n{'=' * 74}\n")
    before = os.environ.get(KEY_VAR)
    s = apply(Setup(), {"engine": "api", "model": "claude-sonnet-5-5",
                        "api_key": "sk-ant-notarealkey-0000"})
    blob = json.dumps(s.state()) + json.dumps(s.__dict__, default=str)
    assert "notarealkey" not in blob, "a key reached something renderable"
    print("  posted a key, then serialised the whole Setup and its state():")
    print(f"    the key appears in neither ({len(blob)} characters checked)")
    print(f"    state() says only: key_present={s.state()['key_present']}, "
          f"engine={s.state()['engine']}, model={s.state()['model']}")
    print(f"    notes: {s.notes[-1]}")

    s2 = apply(Setup(engine="api"), {"engine": "api",
                                     "api_key": "sk-ant-x"}, client_host="10.0.0.9")
    print(f"\n  the same POST from 10.0.0.9: {s2.notes[-1]}")

    if before is None:
        os.environ.pop(KEY_VAR, None)
    else:
        os.environ[KEY_VAR] = before
    print(f"\n  environment left as it was found: "
          f"{KEY_VAR} {'set' if os.environ.get(KEY_VAR) else 'unset'}\n")


if __name__ == "__main__":
    main()
