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
import re
import subprocess
from abc import ABC, abstractmethod

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

    name = "none"

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
    """The default. Calls nothing, opens nothing, proposes nothing."""

    name = "none"

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
