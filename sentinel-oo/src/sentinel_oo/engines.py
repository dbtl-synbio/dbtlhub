"""The model adapter. Attached whether used or not, and advisory only.

The default calls nothing. A service with no model configured works, refuses
and accepts exactly as one with a model does, except that it cannot recover a
value that is present in the crate but not in a form any rule can read.

That one job is the whole of what a model is for here. It is given a check
that has already failed, at a location the rules identified, and asked whether
the value is already written down somewhere. Whatever it answers is checked by
the rule engine before it counts.

Three constraints, taken from the `sentinel` framework, and all three are
enforced in code rather than asked for in the prompt:

  The model is shown only the violations it is allowed to act on, so it
  cannot propose a fix for something that must never be fixed.

  A proposal is applied only at the location the rules named. Without this a
  model could answer a double-booked slot by renaming the slot, and the
  re-check would genuinely pass, because renaming does make the identifier
  unique. It would also have written a laboratory record that never happened.

  Answering "nothing can be recovered" is a correct and expected answer. A
  model that always finds something is worse than one that usually finds
  nothing.

The prompt below is one fixed template. Contract fields fill labelled data
slots in it and never become instructions. The reasons are in section 10 of
the specification; the one that matters most is that this service accepts
contracts from the sender, so prompt text in a contract would mean the sender
writing the model's instructions.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from abc import ABC, abstractmethod

NO_MODEL = "none"

PROMPT = """A check failed on a laboratory record.

Missing property:  {property}
On:                {node}
Allowed values:    {allowed}
Why it matters:    {message}

The record:
{excerpt}

If that value is already present somewhere in the record above, including
inside free text, answer with it. If it is not present, answer with nothing.
Answering nothing is correct and expected.

Reply with JSON and nothing else: {{"value": "..."}} or {{}}
"""

EXCERPT_LIMIT = 4000


class Engine(ABC):
    """What a model adapter must do. Nothing here decides anything."""

    name = NO_MODEL

    def available(self) -> bool:
        """Whether a model is actually reachable. Overridden where it can be
        found out. Asked by `GET /health`, never by a check."""
        return False

    @abstractmethod
    def propose_value(self, crate, violation, contract=None) -> str | None:
        """A value that is already in the crate, or None.

        None is not a failure. It is the answer whenever nothing is there.

        The contract is passed so that everything it knows about the value
        can be put in front of the model, in particular which words are
        permitted. Without that the model is guessing at the vocabulary, and
        a right answer in the wrong words is rejected.
        """


class NullEngine(Engine):
    """Calls nothing, opens nothing, proposes nothing.

    Not the default any more. It is what a deployment gets when it asks for
    no model, and what every test uses that is not about the model.
    """

    name = NO_MODEL

    def propose_value(self, crate, violation, contract=None) -> str | None:
        return None


class ScriptedEngine(Engine):
    """Answers from a dictionary it was handed.

    Not a convenience. It is how every test involving the model path stays
    the same on every machine and every run, with no key, no network and no
    model installed.
    """

    name = "scripted"

    def __init__(self, answers: dict[str, str]):
        self.answers = dict(answers)
        self.asked: list[str] = []

    def propose_value(self, crate, violation, contract=None) -> str | None:
        wanted = violation.requirement.named_value or violation.requirement.property
        self.asked.append(f"{violation.requirement.name}@{violation.node}")
        return self.answers.get(wanted)


class CommandEngine(Engine):
    """A model reachable as a command line, such as Ollama.

    Ollama is a program that runs a model on your own machine. Nothing leaves
    the machine, no key is needed, and the model is pinned by name so a run
    repeats.
    """

    def __init__(self, model: str = "qwen2.5:14b",
                 command: list[str] | None = None,
                 timeout: int = 120):
        self.model = model
        self.command = command or ["ollama", "run", model]
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"command:{self.model}"

    def ask(self, prompt: str) -> str:
        """Run the model. Any failure is an empty answer, never an exception.

        A model being slow, broken or absent must never refuse a good crate.
        """
        try:
            done = subprocess.run(
                self.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return done.stdout if done.returncode == 0 else ""

    def propose_value(self, crate, violation, contract=None) -> str | None:
        return read_answer(self.ask(build_prompt(crate, violation, contract)))


def _seconds(given, variable: str, fallback: int) -> int:
    """How long to wait, from the argument, the environment, or the default.

    A deployment sets these without anything being rebuilt. Nonsense in the
    environment falls back to the default rather than stopping a service
    from starting: a mistyped number must not be the reason handovers cannot
    be checked.
    """
    if given is not None:
        return int(given)
    try:
        wanted = int(os.environ.get(variable, "") or fallback)
    except ValueError:
        return fallback
    return wanted if wanted > 0 else fallback


def _is_a_timeout(exc: BaseException) -> bool:
    """Whether waiting ran out, as opposed to anything else going wrong.

    urllib raises several different things for this depending on where the
    wait expired, so the test is made once here rather than in each caller.
    """
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    return "timed out" in str(exc).lower()


class HttpEngine(Engine):
    """A model reached over the network, which is how a deployment reaches one.

    This is the default, because a sentinel without a model is not what this
    project is about. The model runs in its own container, and that container
    does not have to be on this machine: a model worth using wants a GPU, and
    the machine with the GPU is usually not the machine running the service.

    Two settings, both environment variables, so a deployment points at its
    own model without anything being rebuilt:

        SENTINEL_MODEL_URL   http://model:11434   a container alongside
                             http://gpu-box:11434 a machine with a GPU
        SENTINEL_MODEL       which model to use, pinned by name so a run
                             repeats

    Set SENTINEL_MODEL_URL to nothing to run with no model at all.

    Ollama's interface is used because it is what the measured models ran
    under, it needs no key, and nothing leaves the network it is on.

    **Being unreachable is not an error.** A model that is absent, slow,
    broken or wrong must never change a verdict, and a failure here is
    reported as "I found nothing", which is a correct and expected answer.
    Whether it was reachable is reported separately, by `available()`, so a
    deployment can tell the difference between a model that found nothing and
    a model that was never there.
    """

    DEFAULT_URL = "http://model:11434"
    DEFAULT_MODEL = "qwen2.5:14b"

    # How long to wait for an answer, in seconds. Two numbers, because the
    # first answer and every later one are not the same job.
    #
    # The first call has to load the model before it can answer anything. On
    # an NVIDIA card on 11 November 2026 that loading took about 19 seconds
    # of a 39.6 second first answer. On a processor alone it is slower
    # again.
    #
    # Later calls go to a model already loaded. The same question that took
    # 39.6 seconds cold came back in 67 milliseconds warm.
    #
    # It was one number, 300 seconds, for both. A check is what a pipeline
    # waits for, so that was 300 seconds a handover could block for while a
    # model nobody could see failed to answer.
    DEFAULT_FIRST_TIMEOUT = 180
    DEFAULT_TIMEOUT = 60

    def __init__(self, url: str | None = None, model: str | None = None,
                 timeout: int | None = None,
                 first_timeout: int | None = None):
        if url is None:
            url = os.environ.get("SENTINEL_MODEL_URL", self.DEFAULT_URL)
        self.url = (url or "").rstrip("/")
        self.model = model or os.environ.get("SENTINEL_MODEL",
                                             self.DEFAULT_MODEL)
        self.timeout = _seconds(
            timeout, "SENTINEL_MODEL_TIMEOUT", self.DEFAULT_TIMEOUT
        )
        self.first_timeout = _seconds(
            first_timeout, "SENTINEL_MODEL_FIRST_TIMEOUT",
            self.DEFAULT_FIRST_TIMEOUT
        )
        self.last_error: str | None = None
        # Whether this engine has ever had an answer, which is how it knows
        # the model is loaded and the shorter wait applies.
        self.answered_once = False
        # Whether the last attempt ran out of time rather than failing
        # outright. Kept apart because the record must not say a model
        # looked and found nothing when a model was still thinking when we
        # stopped waiting.
        self.timed_out = False

    @property
    def name(self) -> str:
        if not self.url:
            return NO_MODEL
        return f"{self.model} at {self.url}"

    def available(self) -> bool:
        """Is a model actually there? Asked by `GET /health`, never by a check.

        A deployment that wanted a model and cannot reach one is in a
        different state from one that wanted none, and it should be able to
        say so rather than looking identical.
        """
        if not self.url:
            return False
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=5) as r:
                json.loads(r.read().decode())
            self.last_error = None
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def ask(self, prompt: str) -> str:
        """Send the prompt. Any failure is an empty answer, never an exception."""
        if not self.url:
            return ""
        waiting = self.timeout if self.answered_once else self.first_timeout
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Nothing invented. The job is to read a value that is already
            # in the record, so there is nothing for a high temperature to
            # help with and a great deal for it to spoil.
            "options": {"temperature": 0},
        }).encode()
        request = urllib.request.Request(
            f"{self.url}/api/generate", data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=waiting) as r:
                answer = json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001
            # A server that accepts the connection and then says nothing
            # looks like this, and so does one that answers with something
            # that is not JSON. Both are things a real model host does.
            self.timed_out = _is_a_timeout(exc)
            self.last_error = (
                f"{type(exc).__name__}: {exc}"
                + (f" (waited {waiting} seconds)" if self.timed_out else "")
            )
            return ""

        self.last_error = None
        self.timed_out = False
        self.answered_once = True
        if not isinstance(answer, dict):
            # Something answered, but not this interface. Treated as finding
            # nothing, and said so rather than crashing a check.
            self.last_error = (
                f"the model server answered with {type(answer).__name__} "
                "rather than an object, so there was nothing to read"
            )
            return ""
        return answer.get("response", "") or ""

    def propose_value(self, crate, violation, contract=None) -> str | None:
        return read_answer(self.ask(build_prompt(crate, violation, contract)))


# ------------------------------------------------------------ the prompt


def permitted_values(requirement, contract) -> tuple[str, ...]:
    """Every word the contract allows for this value, from any requirement.

    The requirement being repaired often says only that the value must be
    recorded, while a second requirement about the same value says which
    words mean anything. Showing the model only the first leaves it guessing
    at the vocabulary, and a right answer in the wrong words is thrown away.
    """
    reads = requirement.named_value or requirement.property
    allowed: list[str] = list(requirement.one_of or ())
    if contract is not None:
        for other in contract.requirements:
            if (other.named_value or other.property) != reads:
                continue
            if other.applies_to != requirement.applies_to:
                continue
            for value in other.one_of or ():
                if value not in allowed:
                    allowed.append(value)
    return tuple(allowed)


def build_prompt(crate, violation, contract=None) -> str:
    """Fill the fixed template from the contract and the violation.

    Every piece of contract text lands in a labelled data slot. The
    instructions sit outside the slots and nobody writing a contract can edit
    them.
    """
    from .crate import as_plain

    requirement = violation.requirement
    entity = crate.get(violation.node)

    excerpt = "{}"
    if entity is not None:
        # The entity plus whatever it points at, since a value may be hanging
        # off it rather than written on it.
        from .rules import values_of

        nearby = [as_plain(entity)]
        for key in entity:
            if key.startswith("@"):
                continue
            for reference in values_of(entity, key):
                target = crate.get(reference)
                if target is not None:
                    nearby.append(as_plain(target))
        excerpt = json.dumps(nearby, indent=2)

    if len(excerpt) > EXCERPT_LIMIT:
        excerpt = excerpt[:EXCERPT_LIMIT] + "\n... (trimmed)"

    return PROMPT.format(
        property=requirement.named_value or requirement.property,
        node=violation.node,
        allowed=", ".join(permitted_values(requirement, contract)) or
                "not restricted, so answer with exactly what the record says",
        message=requirement.message,
        excerpt=excerpt,
    )


def read_answer(text: str) -> str | None:
    """The value out of whatever the model said, or None.

    Small models wrap output, add prose around the JSON, and fence it in
    backticks. None of that is an error worth raising: the answer is either
    findable or it is not.
    """
    if not text or not text.strip():
        return None

    for candidate in _json_objects(text):
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(parsed, dict):
            continue
        value = parsed.get("value")
        if value is None or str(value).strip() == "":
            return None
        return str(value).strip()
    return None


def _json_objects(text: str):
    """Every balanced {...} in the text, outermost first."""
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    for start in starts:
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    yield text[start:end + 1]
                    break
