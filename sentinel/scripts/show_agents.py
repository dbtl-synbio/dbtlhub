#!/usr/bin/env python3
"""Look at the four handover agents without reading any code.

    python3 scripts/show_agents.py                      the four, side by side
    python3 scripts/show_agents.py --handover 1         one in full
    python3 scripts/show_agents.py --profile biomanufacturing

Nothing here is a description maintained by hand. Every line is read from the
agent classes and the contract files as they are right now, so if the table says
a check exists, it exists. A diagram in a slide drifts from the code within a
week; this cannot.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BLOCKING_PREFIX = "not auto-fixable"

# module, class - the only hand-written thing in this file
AGENTS = [
    ("framework.agents.sentinel_d2b", "DesignToBuildAgent"),
    ("framework.agents.sentinel_b2t", "BuildToTestAgent"),
    ("framework.agents.sentinel_t2l", "TestToLearnAgent"),
    ("framework.agents.sentinel_l2d", "LearnToDesignAgent"),
]

BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, AMBER, BLUE = "\033[31m", "\033[32m", "\033[33m", "\033[34m"


def load(profile: str):
    out = []
    for module, cls_name in AGENTS:
        cls = getattr(importlib.import_module(module), cls_name)
        agent = cls(profile=profile)
        out.append((agent, agent.contract))
    return sorted(out, key=lambda p: p[1]["x-handover"]["number"])


def blocking_codes(contract, agent) -> set:
    """Every error this agent will refuse to patch, from both routes."""
    codes = set(agent.never_autofix)
    for check in contract.get("x-dbtl-checks", []):
        if (check.get("fix_hint") or "").startswith(BLOCKING_PREFIX):
            codes.add(check.get("code"))
    return codes


def todo_count(contract) -> int:
    return json.dumps(contract).count("TODO")


def overview(pairs, profile: str) -> None:
    print(f"\n{BOLD}The four handovers{OFF}  {DIM}profile: {profile}{OFF}\n")
    print(f"{DIM}Every agent does the same four steps, in this order:{OFF}")
    print(f"  {BLUE}translate{OFF} -> {BLUE}validate{OFF} -> {BLUE}repair{OFF} "
          f"(bounded) -> {BLUE}escalate{OFF}  {DIM}(framework/agents/sentinel_base.py){OFF}\n")

    head = f"  {'':<4}{'sentinel':<15}{'contract':<17}{'checks':<8}{'blocking':<10}state"
    print(BOLD + head + OFF)
    print(DIM + "  " + "-" * (len(head) - 2) + OFF)

    for agent, contract in pairs:
        h = contract["x-handover"]
        checks = contract.get("x-dbtl-checks", [])
        blocking = blocking_codes(contract, agent)
        todos = todo_count(contract)
        has_translate = "translate" in type(agent).__dict__

        if todos:
            state, colour = f"scaffolded, {todos} TODO", RED
        elif has_translate:
            state, colour = "working, custom translate()", GREEN
        else:
            state, colour = "working, no logic", GREEN

        print(f"  H{h['number']:<3}{agent.name:<15}{agent.contract_name:<17}"
              f"{len(checks):<8}{len(blocking):<10}{colour}{state}{OFF}")
        print(f"  {DIM}{'':<4}{h['name']}{OFF}")
    print()
    print(f"{DIM}  --handover N for one in full.{OFF}\n")


def detail(agent, contract, profile: str) -> None:
    h = contract["x-handover"]
    print(f"\n{BOLD}Handover {h['number']}: {h['name']}{OFF}")
    print(f"{DIM}{h['from']} -> {h['to']}  ·  {contract['$id']}  ·  "
          f"profile {profile}{OFF}\n")

    print(f"{BOLD}What it carries{OFF}")
    for name, sub in contract.get("properties", {}).items():
        if name in ("contract", "contract_version", "profile", "run_id",
                    "produced_by", "produced_at"):
            continue
        need = "required" if name in contract.get("required", []) else "optional"
        desc = (sub.get("description") or "").split(".")[0]
        print(f"  {name:<18}{DIM}{need:<10}{desc[:52]}{OFF}")

    print(f"\n{BOLD}What the validator checks beyond the schema{OFF}")
    blocking = blocking_codes(contract, agent)
    for check in contract.get("x-dbtl-checks", []):
        code = check.get("code", "?")
        mark = f"{RED}never auto-fixed{OFF}" if code in blocking else f"{AMBER}may be patched{OFF}"
        print(f"  {check['kind']:<22}{code:<26}{mark}")
        print(f"    {DIM}{check.get('message', '')}{OFF}")

    wanted = (agent.contract.get("x-dbtl-profile", {})
              .get("required_quantities", {}).get(agent.contract_name))
    if wanted:
        print(f"\n{BOLD}What {profile} says this handover is incomplete without{OFF}")
        for req in wanted:
            print(f"  {req['quantity']:<30}{req.get('unit', ''):<12}"
                  f"{DIM}{req.get('method_hint', '')}{OFF}")

    print(f"\n{BOLD}Where a model could act, and what stops it{OFF}")
    print(f"  engine            {agent.engine.name}"
          f"{DIM}   (propose_patches, propose_terms){OFF}")
    print(f"  {DIM}A patch is applied only if the validator reported that exact path as"
          f"\n  fixable, and the package is re-validated afterwards. Everything in red"
          f"\n  above is refused before the engine is even asked.{OFF}")

    todos = todo_count(contract)
    if todos:
        print(f"\n{RED}  {todos} TODO still in this contract — scaffolded, "
              f"nobody has filled it in.{OFF}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--handover", type=int, help="1, 2, 3 or 4")
    ap.add_argument("--profile", default="bioprospecting",
                    choices=["bioprospecting", "biomanufacturing"])
    args = ap.parse_args()

    pairs = load(args.profile)
    if args.handover:
        for agent, contract in pairs:
            if contract["x-handover"]["number"] == args.handover:
                return detail(agent, contract, args.profile)
        sys.exit(f"no handover {args.handover}")
    overview(pairs, args.profile)


if __name__ == "__main__":
    main()
