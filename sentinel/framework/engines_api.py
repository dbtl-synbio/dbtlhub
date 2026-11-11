#!/usr/bin/env python3
"""One engine that calls a model over HTTP, and the key discipline around it.

    python3 framework/engines_api.py        # the checks below, offline

`framework/engines.py` covers the three cases where you already have a model to
hand as a command: the Claude Code CLI, the Codex CLI, Ollama. None of those
reads an API key - they use a login you already made, or no network at all.
This file covers the fourth case, which is different in kind: you have a key,
and the model is a web service.

    from framework.engines_api import ApiEngine
    agent = DesignToBuildAgent(profile="bioprospecting", engine=ApiEngine())

It uses `urllib.request` from the standard library. Not `requests`, not the
`anthropic` package, and not because either is bad: because requirements.txt
promises that every demo and every script in this framework runs on the Python
standard library alone, and an engine that breaks that promise would make the
whole file a lie. The Messages API is one POST with a JSON body; the SDK's
retries, streaming and typed errors are not worth a dependency here.

WHAT THE FRAMEWORK STILL GUARANTEES, unchanged by this file - the five from
`framework/engines.py`, which are enforced in the agents and the validator and
not by the engine's good behaviour:

  1. The engine is only asked about errors that are NOT blocking.
  2. A patch is applied only if the validator reported that exact path as
     fixable. Anything else is refused and the refusal is in the trace.
  3. The package is re-validated afterwards. The engine is never its own
     authority.
  4. `propose_terms` output is reported, never applied.
  5. The ledger records which engine ran.

So the worst a bad model can do here is still waste a turn. What a *key* can do
is worse, and it is not the validator's business, so it is this file's:

THE KEY
  * It is read from `os.environ[ANTHROPIC_API_KEY]` at the moment of the call,
    and from nowhere else. Not from a file, not from an argument, not from a
    constructor parameter. There is deliberately no `api_key=` field: a key
    that is never an attribute cannot be printed by a dataclass repr, pickled
    into a crate, or dumped by anything that walks an object.
  * It is never written down. `name` is `api:<model>`, and that is the only
    thing that reaches the ledger - enough to tell a run with a model apart
    from a run without, and nothing more.
  * It is sent in the `x-api-key` header, never in the prompt and never in the
    URL. `check_the_key_is_only_a_header` below asserts that.
  * Anything this file raises goes through `redact()` first, because an API
    error can quote the request back at you. `check_an_error_cannot_leak_the_key`
    below asserts that too.
  * No key is a normal state, not a failure. `available()` returns False, the
    error says so in those words, and the framework's default engine stays
    `RulesEngine`: deterministic, offline, no key.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.engines import CommandEngine, EngineError, _first_json  # noqa: E402
from framework.llm import Engine                                       # noqa: E402

# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #
KEY_VAR = "ANTHROPIC_API_KEY"
API_URL = "https://api.anthropic.com/v1/messages"

# The wire format this file was written against. It is a date, not a model
# version, and it pins the shape of the request and the reply.
API_VERSION = "2026-10-21"

# A CHOICE, NOT A REQUIREMENT. Any model id the endpoint serves works here -
# pass `model=` and nothing else changes, because the request body carries only
# the model, a token ceiling and one message. This one is the default because
# the task an engine is asked to do in this framework (decide whether a value
# is derivable, or refuse) is a judgement call, and the comparison this
# framework exists to run is "big model vs small open model on identical code".
DEFAULT_MODEL = "claude-opus-5"

# Generous because on this model reasoning is on by default and shares the
# ceiling with the answer. The answer itself is a short JSON array.
DEFAULT_MAX_TOKENS = 8192

REDACTED = "[redacted]"

# Transient: rate limiting, overload, and anything the server calls its own
# fault. A 400 is not transient and is not retried.
RETRY_ON = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


# --------------------------------------------------------------------------- #
#  The key: read it, and never keep it
# --------------------------------------------------------------------------- #
def api_key() -> str | None:
    """The key, or None, which is a normal answer.

    Read on every call rather than cached, so a key removed from the
    environment stops being used immediately, and so no object in this process
    holds one between calls.
    """
    key = (os.environ.get(KEY_VAR) or "").strip()
    return key or None


_KEY_SHAPED = re.compile(r"sk-ant-[A-Za-z0-9_\-]{4,}")


def redact(text: object, key: str | None = None) -> str:
    """Remove the key from anything about to be shown, raised or logged.

    Two passes, because one is not enough:

      * the exact key, which catches an error that quotes the request back;
      * anything key-shaped, which catches a key this process never had - a
        truncated echo, a different deployment's key in a proxy's error, the
        operator's key in a message written by somebody else's middleware.

    The second pass is the one that matters in practice: you cannot redact a
    secret you do not know you are holding, so redact the shape as well.
    """
    out = str(text)
    for secret in (key, api_key()):
        if secret:
            out = out.replace(secret, REDACTED)
    return _KEY_SHAPED.sub(REDACTED, out)


# --------------------------------------------------------------------------- #
#  The engine
# --------------------------------------------------------------------------- #
@dataclass
class ApiEngine(Engine):
    """The Anthropic Messages API behind the same interface as everything else.

    There is no `api_key` field, and that is the design. See THE KEY above.
    """
    model: str = DEFAULT_MODEL
    timeout: int = 120
    max_tokens: int = DEFAULT_MAX_TOKENS
    retries: int = 2
    last_raw: str = field(default="", repr=False)

    @property
    def name(self) -> str:                      # goes into the ledger
        # The model, never the key. This string is the whole of what a run
        # records about which engine answered.
        return f"api:{self.model}"

    def available(self) -> bool:
        """Whether a key is present. False is a normal state, not an error."""
        return api_key() is not None

    # ---- the two things an engine is ever asked ---------------------------
    # Borrowed from CommandEngine verbatim, on purpose. They hold the rules
    # that make a model engine safe to offer at all - a patch must name a path
    # the validator reported, and a term must be one core.json already
    # declares, with "rejected" recorded when it is not - and those rules must
    # not drift apart between a CLI engine and an HTTP one. One copy, used by
    # both. Both functions touch nothing but `self._ask`, which is the only
    # thing that actually differs here.
    propose_patches = CommandEngine.propose_patches
    propose_terms = CommandEngine.propose_terms

    # ---- the call ---------------------------------------------------------
    def _ask(self, prompt: str):
        key = api_key()
        if key is None:
            raise EngineError(
                f"no model: {KEY_VAR} is not set in this process's environment. "
                f"This is a normal state, not a fault - the framework's default "
                f"engine is RulesEngine, which is deterministic, offline and "
                f"needs no key.")

        # Only three fields. Nothing provider-specific beyond the endpoint and
        # the version header, so swapping `model=` is the whole of what it
        # takes to run this against a different model.
        body = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        self.last_raw = self._post(body, key)
        return _first_json(self.last_raw)

    def _post(self, body: bytes, key: str) -> str:
        request = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={"content-type": "application/json",
                     "anthropic-version": API_VERSION,
                     # The one place the key appears. Not the body, not the URL:
                     # a URL ends up in proxy logs and in every exception that
                     # mentions it.
                     "x-api-key": key})

        delay = 2.0
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                    return _text_of(json.loads(answer.read().decode("utf-8")), key)

            except urllib.error.HTTPError as exc:
                # HTTPError subclasses URLError, so it has to be caught first.
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")
                except Exception:                       # the body is gone
                    pass
                if exc.code in RETRY_ON and attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                # `from None` deliberately. The original exception holds the
                # response we just read, and chaining it would print an object
                # nobody has redacted under "During handling of the above
                # exception". The HTTP code and the server's message, both
                # redacted, are what is useful anyway.
                raise EngineError(redact(
                    f"the API answered {exc.code}: "
                    f"{_message_of(detail) or detail[:400] or exc.reason}",
                    key)) from None

            except urllib.error.URLError as exc:
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise EngineError(redact(
                    f"could not reach {API_URL}: {exc.reason}", key)) from None

        raise EngineError("unreachable")                 # pragma: no cover


# --------------------------------------------------------------------------- #
#  Reading the reply
# --------------------------------------------------------------------------- #
def _text_of(payload: dict, key: str | None = None) -> str:
    """The text the model wrote, out of a Messages API reply."""
    if payload.get("type") == "error":
        raise EngineError(redact(
            f"the API refused the request: "
            f"{(payload.get('error') or {}).get('message', '')}", key))

    stop = payload.get("stop_reason")
    if stop == "refusal":
        # A refusal is an answer. Say so rather than failing to parse JSON.
        raise EngineError("the model declined to answer this prompt "
                          "(stop_reason: refusal)")

    # Only text blocks. On a model that reasons by default the reply also
    # carries `thinking` blocks, which are not the answer and are usually empty.
    parts = [block.get("text", "")
             for block in payload.get("content") or []
             if isinstance(block, dict) and block.get("type") == "text"]
    text = "".join(parts)

    if stop == "max_tokens":
        raise EngineError(
            f"the answer was cut off at max_tokens={payload.get('usage', {}).get('output_tokens')}; "
            f"raise ApiEngine(max_tokens=...) - a truncated JSON answer is not "
            f"a partial answer, it is no answer")
    if not text.strip():
        raise EngineError(f"the reply carried no text (stop_reason: {stop})")
    return text


def _message_of(detail: str) -> str:
    """The server's own message out of an error body, if it is the usual shape."""
    try:
        return str((json.loads(detail).get("error") or {}).get("message", ""))[:400]
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
#  The checks. These are the point of the file, so they run from the file.
#
#      python3 framework/engines_api.py
#
#  Every one of them runs offline. The last one runs only if a key is actually
#  in the environment, and says so when it is not.
# --------------------------------------------------------------------------- #
BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
GREEN, AMBER = "\033[32m", "\033[33m"

FAKE_KEY = "sk-ant-api03-FAKEKEYFORTHETESTABOVE-0123456789abcdef"


class _Env:
    """Set or unset the key for the duration of a check, then put it back."""

    def __init__(self, value: str | None):
        self.value, self.before = value, os.environ.get(KEY_VAR)

    def __enter__(self):
        if self.value is None:
            os.environ.pop(KEY_VAR, None)
        else:
            os.environ[KEY_VAR] = self.value
        return self

    def __exit__(self, *_):
        if self.before is None:
            os.environ.pop(KEY_VAR, None)
        else:
            os.environ[KEY_VAR] = self.before
        return False


def check_no_key_is_a_normal_state() -> str:
    """With no key the engine is unavailable and says so without alarm."""
    with _Env(None):
        engine = ApiEngine()
        assert engine.available() is False, "available() lied about having no key"
        try:
            engine._ask("anything")
        except EngineError as exc:
            assert "normal state" in str(exc), f"the message blames the user: {exc}"
            assert "RulesEngine" in str(exc), "it does not say what to use instead"
            return str(exc).split(".")[0]
    raise AssertionError("asking with no key did not raise")


def check_the_name_carries_the_model_and_not_the_key() -> str:
    """The ledger learns which model ran, and nothing else."""
    with _Env(FAKE_KEY):
        engine = ApiEngine()
        assert engine.name == f"api:{DEFAULT_MODEL}", engine.name
        for rendering in (engine.name, repr(engine), str(engine.__dict__)):
            assert FAKE_KEY not in rendering, "the key is visible in an engine rendering"
        return engine.name


def check_the_key_is_only_a_header() -> str:
    """The key goes in x-api-key. It is not in the prompt and not in the URL."""
    seen: dict = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = (request.data or b"").decode("utf-8")
        return io.BytesIO(json.dumps({
            "type": "message", "stop_reason": "end_turn",
            "content": [{"type": "thinking", "thinking": ""},
                        {"type": "text", "text": '[{"path": "a.unit", "value": "mg/L"}]'}],
        }).encode("utf-8"))

    with _Env(FAKE_KEY):
        real, urllib.request.urlopen = urllib.request.urlopen, fake_urlopen
        try:
            answer = ApiEngine()._ask("a prompt with no secret in it")
        finally:
            urllib.request.urlopen = real

    assert answer == [{"path": "a.unit", "value": "mg/L"}], answer
    assert FAKE_KEY not in seen["body"], "the key was sent in the request body"
    assert FAKE_KEY not in seen["url"], "the key was sent in the URL"
    carriers = [h for h, v in seen["headers"].items() if FAKE_KEY in v]
    assert carriers == ["X-api-key"], f"the key travelled in {carriers}"
    return f"header {carriers[0]} only; body and URL clean"


def check_an_error_cannot_leak_the_key() -> str:
    """The one that matters: an API error that quotes the key back is redacted.

    This is not hypothetical. A gateway in front of a model, a misconfigured
    proxy, or an authentication error that helpfully echoes the credential it
    rejected will all put the key in a response body, and that body is what an
    engine would otherwise raise, print, and write into a run's notes.
    """
    body = json.dumps({"error": {
        "type": "authentication_error",
        "message": f"invalid x-api-key: {FAKE_KEY} (and a second copy: {FAKE_KEY})"}})

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            API_URL, 401, "Unauthorized", {}, io.BytesIO(body.encode("utf-8")))

    with _Env(FAKE_KEY):
        real, urllib.request.urlopen = urllib.request.urlopen, fake_urlopen
        try:
            ApiEngine(retries=0)._ask("anything")
        except EngineError as exc:
            message = str(exc)
        else:
            raise AssertionError("a 401 did not raise")
        finally:
            urllib.request.urlopen = real

    assert FAKE_KEY not in message, f"THE KEY LEAKED: {message}"
    assert "FAKEKEY" not in message, f"part of the key leaked: {message}"
    assert "sk-ant-" not in message, f"a key-shaped string leaked: {message}"
    assert "401" in message, "the error no longer says what went wrong"
    assert REDACTED in message, "nothing was redacted, so nothing was there?"
    return message


def check_redaction_also_catches_a_key_this_process_never_had() -> str:
    """A key from somewhere else is still a key. Shape alone is enough."""
    other = "sk-ant-api03-SOMEBODY-ELSES-KEY-abcdef0123456789"
    with _Env(None):
        out = redact(f"upstream said: {other}")
    assert other not in out and "sk-ant-" not in out, out
    return out


def check_a_truncated_answer_is_not_a_partial_answer() -> str:
    """Cut off at max_tokens is an error, not half a patch list."""
    try:
        _text_of({"stop_reason": "max_tokens", "usage": {"output_tokens": 8192},
                  "content": [{"type": "text", "text": '[{"path": "a.u'}]})
    except EngineError as exc:
        assert "max_tokens" in str(exc)
        return str(exc)[:96]
    raise AssertionError("a truncated answer was accepted")


OFFLINE_CHECKS = [
    check_no_key_is_a_normal_state,
    check_the_name_carries_the_model_and_not_the_key,
    check_the_key_is_only_a_header,
    check_an_error_cannot_leak_the_key,
    check_redaction_also_catches_a_key_this_process_never_had,
    check_a_truncated_answer_is_not_a_partial_answer,
]


def _live_check() -> str:
    """One real call, only if a key is really there. Costs a few tokens."""
    from framework.vocab import DEFAULT
    engine = ApiEngine()
    crate = {"@graph": [{"@id": "#s/1", "@type": "BioSample", "box_temp_c": -80}]}
    got = engine.propose_terms(["box_temp_c"], crate, DEFAULT)
    answer = got.get("box_temp_c") or {}
    assert engine.last_raw, "the model answered nothing"
    assert FAKE_KEY not in engine.last_raw
    return (f"{engine.name} mapped box_temp_c -> {answer.get('term')!r} "
            f"[{answer.get('confidence')}] {str(answer.get('why', ''))[:90]}")


def main() -> int:
    print(f"\n{BOLD}{'=' * 76}\nApiEngine: WHAT HAPPENS TO THE KEY\n{'=' * 76}{OFF}\n")
    failed = 0
    for check in OFFLINE_CHECKS:
        try:
            detail = check()
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {check.__name__}\n        {exc}")
        else:
            print(f"  {GREEN}pass{OFF}  {check.__name__}")
            print(f"        {DIM}{redact(detail)[:150]}{OFF}")

    print(f"\n{BOLD}{'=' * 76}\nAGAINST THE REAL API\n{'=' * 76}{OFF}\n")
    if api_key() is None:
        print(f"  {AMBER}not run{OFF}  {KEY_VAR} is not set, so nothing was sent "
              f"anywhere.\n           The six checks above are the offline paths, "
              f"and they all ran.\n           This is the state the container runs "
              f"in by default.")
    else:
        try:
            print(f"  {GREEN}pass{OFF}  one real call\n        {DIM}{redact(_live_check())}{OFF}")
        except Exception as exc:                 # noqa: BLE001 - reported, not raised
            failed += 1
            print(f"  FAIL  one real call\n        {redact(exc)[:300]}")

    print(f"\n  {failed} failure(s)\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
