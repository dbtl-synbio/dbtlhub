"""Model engines: bring whichever model you want, including a local one.

The framework never calls a model by default. `RulesEngine` is deterministic
and offline, and a handover can always be checked with no model at all. This
file is for the case where you *do* want one.

There are three ways people actually have a model to hand, and all three work
the same way here - a command that reads a prompt on stdin and writes an answer
on stdout:

    CommandEngine("claude")    the Claude Code CLI, using your own login
    CommandEngine("codex")     the OpenAI Codex CLI, using your own login
    CommandEngine("ollama")    a model on your own machine: no key, no network

    CommandEngine(argv=["my-tool", "--flag"])        anything else you have

Nothing is hardcoded and no key is read by this file. The CLIs use whatever
login or API key you already have in your own environment; Ollama needs
neither. The key never enters a contract, a crate, a package or the ledger -
only the engine's `name` does, so a run with a model and a run without can be
told apart afterwards.

What the framework guarantees, whatever engine you pass:

  1. The engine is only asked about errors that are NOT blocking.
  2. A patch is applied only if the validator reported that exact path as
     fixable. Anything else is refused and the refusal is in the trace.
  3. The package is re-validated afterwards. The engine is never its own
     authority.
  4. `propose_terms` output is reported, never applied.
  5. The ledger records which engine ran.

So the worst a bad model can do here is waste a turn.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from framework.llm import Engine, Patch


class EngineError(RuntimeError):
    """The command could not be run, or did not answer in the agreed shape."""


@dataclass(frozen=True)
class Runner:
    argv: list[str]
    label: str
    needs: str


# Presets, because these are the three cases people actually have. Each reads
# the prompt on stdin. Add your own, or pass `argv=` and skip this table.
RUNNERS: dict[str, Runner] = {
    "claude": Runner(
        argv=["claude", "-p"],
        label="Claude Code CLI",
        needs="a `claude` login on this machine (`claude auth login`). No API key in this repo."),
    "codex": Runner(
        argv=["codex", "exec", "--skip-git-repo-check"],
        label="OpenAI Codex CLI",
        needs="a `codex` login on this machine. No API key in this repo."),
    "ollama": Runner(
        argv=["ollama", "run", "qwen2.5-coder:3b"],
        label="Ollama, on your own machine",
        needs="`ollama pull qwen2.5-coder:3b`. No key, no network, nothing leaves the laptop."),
}


# --------------------------------------------------------------------------- #
#  The engine
# --------------------------------------------------------------------------- #
@dataclass
class CommandEngine(Engine):
    """Any model reachable as a command line.

        agent = DesignToBuildAgent(profile="bioprospecting",
                                   engine=CommandEngine("claude"))

    `runner` picks a preset from RUNNERS; `argv` overrides it entirely. The
    prompt goes to stdin, the answer is read from stdout, and the first JSON
    value in it is used - CLIs like to add a line of chat around it.
    """
    runner: str = "claude"
    argv: list[str] | None = None
    timeout: int = 300
    last_raw: str = field(default="", repr=False)

    def __post_init__(self):
        if self.argv is None:
            if self.runner not in RUNNERS:
                raise EngineError(
                    f"no preset named {self.runner!r}. Known: "
                    f"{', '.join(RUNNERS)} - or pass argv=[...] for your own.")
            self.argv = list(RUNNERS[self.runner].argv)

    @property
    def name(self) -> str:                      # goes into the ledger
        return f"cmd:{self.runner}"

    def available(self) -> bool:
        return shutil.which(self.argv[0]) is not None

    # ---- the two things an engine is ever asked ---------------------------
    def propose_patches(self, package: dict, report, contract: dict) -> list[Patch]:
        errors = list(report.errors)
        if not errors:
            return []
        answer = self._ask(_patch_prompt(package, errors, contract))
        out = []
        for item in _as_list(answer):
            if not isinstance(item, dict) or "path" not in item:
                continue
            out.append(Patch(
                path=str(item["path"]),
                action="set_field",
                value=item.get("value"),
                reason=str(item.get("reason", ""))[:300],
                confidence=str(item.get("confidence", "low"))))
        return out

    def propose_terms(self, keys: list[str], crate: dict, vocab=None) -> dict:
        if not keys:
            return {}
        from framework.vocab import DEFAULT
        vocab = vocab or DEFAULT
        allowed = sorted(vocab.terms)
        answer = self._ask(_term_prompt(keys, crate, allowed))

        out = {}
        for key, got in (answer or {}).items():
            if key not in keys or not isinstance(got, dict):
                continue
            term = got.get("term")
            # A model may only point at a term core.json already declares. It
            # cannot coin one, and it cannot alias to something nobody agreed.
            # The caller does not apply this anyway - but say no here too, so
            # the refusal is visible rather than implied.
            if term not in vocab.terms:
                out[key] = {"term": None, "confidence": "rejected",
                            "why": f"engine proposed {term!r}, which core.json does "
                                   f"not declare - a model may rename, not coin"}
                continue
            out[key] = {"term": term,
                        "confidence": str(got.get("confidence", "low")),
                        "why": str(got.get("why", ""))[:300]}
        return out

    # ---- running the command ----------------------------------------------
    def _ask(self, prompt: str):
        if not self.available():
            raise EngineError(
                f"{self.argv[0]!r} is not on PATH. "
                f"{RUNNERS[self.runner].needs if self.runner in RUNNERS else ''}")
        try:
            done = subprocess.run(
                self.argv, input=prompt, capture_output=True, text=True,
                timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"{self.argv[0]} did not answer in {self.timeout}s") from exc
        if done.returncode != 0:
            raise EngineError(
                f"{self.argv[0]} exited {done.returncode}: "
                f"{(done.stderr or '').strip()[:400]}")
        # Some CLIs animate a progress spinner on stdout, which leaves cursor
        # escapes in the middle of the answer. Strip them before parsing.
        self.last_raw = _ANSI.sub("", done.stdout)
        return _first_json(self.last_raw)


# --------------------------------------------------------------------------- #
#  Prompts. Short on purpose: the constraints are enforced in code, not asked
#  for politely. What the prompt has to do is explain the shape of the answer
#  and make refusing an easy, named option.
# --------------------------------------------------------------------------- #
PATCH_RULES = """\
You are the repair step of a checking agent that stands between two phases of
a laboratory Design-Build-Test-Learn cycle. A package failed validation.

The only acceptable patch is one whose value is DERIVABLE from information
already present - a unit the profile states, a checksum computable from the
data. If supplying a value would mean inventing an observation nobody made -
which well a sample sat in, which step produced a sequence, a measurement that
was never taken - you must NOT patch it. Returning an empty list is a correct
and expected answer, and renaming something to make an error go away is the
worst possible answer: it hides the collision and writes a laboratory record
that never happened.

Answer with a JSON array and nothing else:

[{"path": "<exact path from the error list>", "value": <the value>,
  "reason": "<why this is derivable, one sentence>",
  "confidence": "high" | "low"}]

Use [] if nothing is safely derivable. Never invent a path."""

TERM_RULES = """\
You are mapping keys a laboratory invented onto terms from an agreed
vocabulary, so that data from different labs can be queried together.

You may ONLY choose a term from the allowed list. You may not invent one. If
no term in the list is right, say so with "term": null - that is a useful
answer, because it tells a human a new term has to be agreed.

Your answer is a SUGGESTION FOR A HUMAN. It is recorded and never applied
automatically, and the handover stays failed until somebody confirms it.

Answer with a JSON object and nothing else:

{"<key>": {"term": "<curie from the allowed list, or null>",
           "why": "<one sentence>", "confidence": "high" | "low"}}"""


def _patch_prompt(package: dict, errors, contract: dict) -> str:
    from framework.llm import _resolve, _split
    lines = []
    for err in errors:
        where = _resolve(package, _split(err.path)[:-1])
        lines.append({
            "path": err.path,
            "code": err.code,
            "message": err.message,
            "fix_hint": err.fix_hint,
            "the object this path sits in": _trim(where),
        })
    return (f"{PATCH_RULES}\n\n"
            f"Contract: {contract.get('$id')}\n"
            f"Use case profile: {package.get('profile')}\n\n"
            f"The errors you may act on (and ONLY these paths):\n"
            f"{json.dumps(lines, indent=2, default=str)[:12000]}\n")


def _term_prompt(keys: list[str], crate: dict, allowed: list[str]) -> str:
    context = {}
    for entity in (crate or {}).get("@graph", [])[:60]:
        if not isinstance(entity, dict):
            continue
        for key in keys:
            if key in entity:
                context.setdefault(key, {"seen_on": entity.get("@type"),
                                         "example_value": entity[key]})
    return (f"{TERM_RULES}\n\n"
            f"Keys to map: {json.dumps(keys)}\n\n"
            f"How each key is used in the data:\n{json.dumps(context, default=str)[:3000]}\n\n"
            f"Allowed terms:\n{json.dumps(allowed, indent=1)[:6000]}\n")


# --------------------------------------------------------------------------- #
#  Reading an answer out of whatever the CLI printed
# --------------------------------------------------------------------------- #
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\r")


def _loads(chunk: str):
    """json.loads, then one forgiving retry.

    Small local models wrap long lines, which puts a raw newline inside a JSON
    string and makes the document invalid even though the answer is right.
    Escaping those is a kindness, not a reinterpretation: it changes no value.
    """
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        pass
    out, in_string, escaped = [], False, False
    for ch in chunk:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            elif ch in "\n\r\t":
                out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
                continue
        elif ch == '"':
            in_string = True
        out.append(ch)
    return json.loads("".join(out))


def _first_json(text: str):
    """The first JSON array or object in the output, fenced or bare."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        try:
            return _loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        while start != -1:
            depth, in_string, escaped = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return _loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise EngineError(f"no JSON in the answer: {text.strip()[:300]!r}")


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("patches", "result", "results"):
            if isinstance(value.get(key), list):
                return value[key]
        return [value] if "path" in value else []
    return []


def _trim(value, limit: int = 1200):
    """Keep the object if it is small; otherwise send a truncated rendering."""
    text = json.dumps(value, default=str)
    return value if len(text) <= limit else text[:limit] + "...(truncated)"
