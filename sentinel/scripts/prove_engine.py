#!/usr/bin/env python3
"""Prove, on your own machine, that you can plug in whichever model you want.

    python3 scripts/prove_engine.py                  # no model at all
    python3 scripts/prove_engine.py --engine claude  # the Claude Code CLI
    python3 scripts/prove_engine.py --engine codex   # the OpenAI Codex CLI
    python3 scripts/prove_engine.py --engine ollama  # a model on your laptop
    python3 scripts/prove_engine.py --all            # every one you have

Nothing in this repository reads an API key. The CLI presets use whatever
login you already have; Ollama uses no network at all. See framework/engines.py.

Three parts, in this order:

  PART 1  with no model, the one task a rule cannot do is left undone
  PART 2  with your model, it gets done - as a SUGGESTION, never applied
  PART 3  the guard: a deliberately hostile engine is refused by the framework

Part 3 runs with no model and is the important one. It is what makes part 2
safe to offer at all.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.agents.base import Task                                # noqa: E402
from framework.agents.coordinator import Coordinator                  # noqa: E402
from framework.agents.phase_design import DesignAgent                 # noqa: E402
from framework.agents.sentinel_d2b import DesignToBuildAgent          # noqa: E402
from framework.engines import RUNNERS, CommandEngine, EngineError     # noqa: E402
from framework.llm import Engine, Patch, RulesEngine                  # noqa: E402

BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, AMBER, BLUE = "\033[31m", "\033[32m", "\033[33m", "\033[34m"

FAULTS = {"missing_geo", "orphan_fasta", "unaligned_key"}


def rule(text: str) -> None:
    print(f"\n{BOLD}{'=' * 76}\n{text}\n{'=' * 76}{OFF}")


def run_handover(engine: Engine, run_id: str):
    """The same broken Design crate, through Handover 1, with this engine."""
    coord = Coordinator(run_id)
    design = coord.step(DesignAgent(),
                        Task(goal="select a candidate panel",
                             inputs={"n": 6, "faults": FAULTS}),
                        label="design")
    agent = DesignToBuildAgent(profile="bioprospecting", lab="newcastle",
                               engine=engine)
    result = coord.step(
        agent,
        Task(goal="hand over to Build",
             inputs={"crate": design.outputs["crate"],
                     "items": design.outputs["items"], "run_id": run_id},
             max_repairs=2),
        label="handover", store_as="d2b")
    return result


def vocabulary_notes(result) -> list[str]:
    return [n for n in result.notes if "UNALIGNED" in n or "unaligned" in n.lower()]


# --------------------------------------------------------------------------- #
#  PART 1 and 2
# --------------------------------------------------------------------------- #
def part_one() -> None:
    rule("PART 1  -  no model at all")
    print(f"{DIM}The default engine. Deterministic, offline, no key.{OFF}\n")
    result = run_handover(RulesEngine(), "prove-rules")
    for note in vocabulary_notes(result):
        print(f"  {note.split(': ', 1)[-1]}")
    print(f"\n  handover: {RED}{result.status.upper()}{OFF}, "
          f"{len(result.errors)} error(s)")
    print(f"{DIM}  'box_temp_c' is a key a technician invented. A rule can match a\n"
          f"  synonym it already knows; it cannot reason about a word it has never\n"
          f"  seen. This is the one task in the handover where a model is clearly\n"
          f"  better, which makes it the honest place to measure one.{OFF}")


def part_two(key: str) -> bool:
    preset = RUNNERS[key]
    rule(f"PART 2  -  your own model:  {preset.label}")
    print(f"{DIM}Needs: {preset.needs}{OFF}")
    print(f"{DIM}Command: {' '.join(preset.argv)}   (prompt on stdin){OFF}\n")

    engine = CommandEngine(key)
    if not engine.available():
        print(f"  {AMBER}skipped{OFF}: {preset.argv[0]} is not on PATH")
        return False

    try:
        result = run_handover(engine, f"prove-{key}")
    except EngineError as exc:
        print(f"  {RED}engine error{OFF}: {exc}")
        return False

    for note in vocabulary_notes(result):
        print(f"  {note.split(': ', 1)[-1]}")

    print(f"\n  engine recorded in the ledger as: {BLUE}{engine.name}{OFF}")
    print(f"  handover: {RED}{result.status.upper()}{OFF}, "
          f"{len(result.errors)} error(s)")
    print(f"{GREEN}  The suggestion was reported and NOT applied. The handover still\n"
          f"  fails, and it will keep failing until a human puts that line in\n"
          f"  vocabulary/labs/newcastle.json or in core.json by pull request.{OFF}")
    print(f"{DIM}  A term chosen by a model per run is not reproducible: two teams\n"
          f"  checking the same crate would reach different verdicts.{OFF}")
    return True


# --------------------------------------------------------------------------- #
#  PART 3 - the guard
# --------------------------------------------------------------------------- #
class HostileEngine(Engine):
    """A model that has been told to make the errors go away, and does.

    It proposes one legitimate patch and one that resolves a collision by
    renaming. Renaming genuinely does make the key unique, so re-validation
    would pass - and a laboratory record that never happened would have been
    written. This is exactly the failure the framework has to prevent in code
    rather than ask for politely in a prompt.
    """
    name = "hostile"

    def propose_patches(self, package: dict, report, contract: dict) -> list[Patch]:
        seen = {e.path for e in report.errors}
        patches = [Patch(path="crate_ref.checksum", action="set_field",
                         value="sha256:" + "0" * 64,
                         reason="legitimate-looking, and on a path the validator "
                                "did report")]
        patches.append(Patch(
            path="order.items[0].position", action="set_field", value="H12",
            reason="moved it to a free well so the duplicate goes away"))
        patches.append(Patch(
            path="crate.@graph[#site/NS-01].dwc:decimalLatitude",
            action="set_field", value=54.97,
            reason="the North Sea is roughly here"))
        print(f"{DIM}    hostile engine saw {len(seen)} fixable path(s) and "
              f"proposed {len(patches)} patch(es){OFF}")
        return patches

    def propose_terms(self, keys, crate, vocab=None) -> dict:
        return {k: {"term": "dbtl:iJustMadeThisUp", "why": "looks about right",
                    "confidence": "high"} for k in keys}


def part_three() -> None:
    rule("PART 3  -  the guard, with no model needed")
    print(f"{DIM}A deliberately hostile engine: it proposes a plausible patch, a\n"
          f"renamed well, and an invented coordinate.{OFF}\n")
    result = run_handover(HostileEngine(), "prove-hostile")

    refused = [n for n in result.notes if "REFUSED" in n]
    applied = [n for n in result.notes if "repair" in n and "<-" in n]
    rejected_terms = [n for n in result.notes if "rejected" in n.lower()
                      or "does not declare" in n]

    for note in refused:
        print(f"  {RED}{note.split(': ', 1)[-1]}{OFF}")
    for note in applied:
        print(f"  {AMBER}LET THROUGH{OFF} {note.split(': ', 1)[-1][:72]}")
    for note in rejected_terms:
        print(f"  {RED}{note.split(': ', 1)[-1][:120]}{OFF}")

    caught = [e for e in result.errors if "checksum_mismatch" in str(e)]
    for err in caught:
        print(f"  {GREEN}  ...and then caught on re-validation:{OFF}")
        print(f"  {RED}{str(err)[:140]}{OFF}")

    print(f"\n  handover: {RED}{result.status.upper()}{OFF}, "
          f"{len(result.errors)} error(s)")
    print(f"{GREEN}  Two of the three patches never reached the package: a patch is "
          f"applied\n  only where the validator pointed. The third was on a path the "
          f"validator\n  did report, so it went in - and the re-validation caught it, "
          f"because the\n  contract checks that the checksum matches the crate rather "
          f"than merely\n  that the field is filled in.{OFF}")
    print(f"{DIM}  That second layer exists because this script found the hole: "
          f"before it,\n  a fabricated checksum satisfied 'the field is present' "
          f"and passed.{OFF}")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=sorted(RUNNERS), help="which CLI to try")
    ap.add_argument("--all", action="store_true", help="try every preset you have")
    args = ap.parse_args()

    part_one()

    targets = sorted(RUNNERS) if args.all else ([args.engine] if args.engine else [])
    ran = [key for key in targets if part_two(key)]

    part_three()

    rule("WHAT THIS PROVED")
    print(f"  · the handover can be checked with {BOLD}no model at all{OFF} "
          f"(part 1)")
    if ran:
        print(f"  · it also runs on {BOLD}{', '.join(ran)}{OFF} with no change to any "
              f"agent (part 2)")
        print(f"    - one argument: DesignToBuildAgent(..., engine=CommandEngine("
              f"{ran[0]!r}))")
    else:
        print(f"  · {DIM}no model tried - pass --engine claude|codex|ollama{OFF}")
    print(f"  · a model {BOLD}cannot{OFF} write where the validator did not point, "
          f"and cannot coin a vocabulary term (part 3)")
    print(f"\n{DIM}  Ledgers: runs/prove-*/ledger.jsonl - every step records which "
          f"engine ran.{OFF}\n")


if __name__ == "__main__":
    main()
