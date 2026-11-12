#!/usr/bin/env python3
"""Scaffold a new handover: a contract and its checking agent, from the template.

    python3 scripts/new_handover.py test_to_learn \
        --number 3 --label "screening results" --from test --to learn

Writes two files, both marked TODO and neither guessing at your use case:

    framework/contracts/test_to_learn.schema.json
    framework/agents/sentinel_t2l.py

The point of a scaffolder rather than "copy this file": the envelope is
identical in every handover contract, and identical by construction beats
identical by discipline. Three people copying a file by hand produce three
slightly different envelopes within a week, and then the coordinator has to
special-case each of them.

It refuses to overwrite. If a contract already exists, edit it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "template"
CONTRACTS = ROOT / "framework" / "contracts"
AGENTS = ROOT / "framework" / "agents"


def abbreviate(name: str) -> str:
    """'test_to_learn' -> 't2l'  ·  'design_to_build' -> 'd2b'"""
    parts = name.split("_to_")
    if len(parts) == 2:
        return f"{parts[0][0]}2{parts[1][0]}"
    return name[:3]


def make_contract(name: str, number: int, lbl: str, src: str, dst: str) -> dict:
    text = (TEMPLATE / "handover_contract.schema.json").read_text()
    contract = json.loads(text)

    contract["$id"] = f"dbtl:{name}/0.1.0"
    contract["x-handover"].update(
        {"number": number, "name": lbl, "from": src, "to": dst})
    contract["title"] = f"{src.title()} -> {dst.title()} handover (generic)"
    contract["properties"]["contract"]["const"] = name
    for check in contract["x-dbtl-checks"]:
        if "from_profile" in check:
            check["from_profile"] = f"required_quantities.{name}"
    # Name the backlink after the phase it points at - design_ref, build_ref.
    props = contract["properties"]
    props[f"{src}_ref"] = props.pop("TODO_ref")
    contract["required"].append(f"{src}_ref")
    return contract


def make_agent(name: str, abbr: str, lbl: str, src: str, dst: str) -> str:
    text = (TEMPLATE / "handover_agent.py").read_text()
    head = (
        f'"""The {src.title()} -> {dst.title()} sentinel agent'
        f' (Handover: {lbl}).\n\n'
        f'    SCAFFOLDED — every TODO below is a decision nobody has taken yet.\n\n'
        f'Everything a handover agent does in common lives in\n'
        f'`framework.agents.sentinel_base.SentinelAgent`: translate, validate,\n'
        f'repair within a budget, escalate. This file only declares what differs.\n'
        f'"""\n'
    )
    body = text[text.index('from __future__ import annotations'):]
    body = body.replace('sys.path.insert(0, str(Path(__file__).resolve().parent.parent))',
                        'sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))')
    body = body.replace('name = "sentinel_XXX"', f'name = "sentinel_{abbr}"')
    body = body.replace('contract_name = "XXX_to_YYY"', f'contract_name = "{name}"')
    body = body.replace('class HandoverAgent(SentinelAgent):',
                        f'class {src.title()}To{dst.title()}Agent(SentinelAgent):')
    body = body.replace('"TODO_ref": {},', f'"{src}_ref": {{}},   # TODO the backlink')
    body = body.replace('HandoverAgent(profile=', f'{src.title()}To{dst.title()}Agent(profile=')
    return head + body


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="e.g. test_to_learn")
    ap.add_argument("--number", type=int, required=True,
                    help="the handover number the use case gives it")
    ap.add_argument("--label", required=True,
                    help='what the use case calls it, e.g. "screening results"')
    ap.add_argument("--from", dest="src", required=True, help="upstream phase")
    ap.add_argument("--to", dest="dst", required=True, help="downstream phase")
    ap.add_argument("--dialect", choices=("dbtl", "sentinel-oo"), default="dbtl",
                    help="which contract language to write. `dbtl` checks "
                         "paths in a package; `sentinel-oo` checks entities "
                         "in a crate, by type. The one sentinel runs either.")
    ap.add_argument("--with-agent", action="store_true",
                    help="also scaffold a Python agent. You almost certainly "
                         "do not need one: the sentinel guards any contract "
                         "it finds on disk, and a handover that needs code is "
                         "a handover somebody has to maintain.")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z]+_to_[a-z]+", args.name):
        sys.exit(f"name must look like 'test_to_learn', got {args.name!r}")

    abbr = abbreviate(args.name)
    if args.dialect == "sentinel-oo":
        contract_path = CONTRACTS / f"{args.name}.oo.yaml"
    else:
        contract_path = CONTRACTS / f"{args.name}.schema.json"
    agent_path = AGENTS / f"sentinel_{abbr}.py"

    wanted = [contract_path] + ([agent_path] if args.with_agent else [])
    for path in wanted:
        if path.exists():
            sys.exit(f"{path.relative_to(ROOT)} already exists — edit it rather than "
                     f"scaffolding over it")

    if args.dialect == "sentinel-oo":
        contract_path.write_text(
            make_oo_contract(args.name, args.label, args.src, args.dst))
    else:
        contract_path.write_text(json.dumps(
            make_contract(args.name, args.number, args.label, args.src, args.dst),
            indent=2) + "\n")
    print(f"wrote {contract_path.relative_to(ROOT)}")

    if args.with_agent:
        agent_path.write_text(
            make_agent(args.name, abbr, args.label, args.src, args.dst))
        print(f"wrote {agent_path.relative_to(ROOT)}")
    else:
        print(f"\n  No Python was written, and none is needed. The one "
              f"sentinel reads\n  framework/contracts/ and guards whatever it "
              f"finds there:\n\n"
              f"      Sentinel(profile=...).check({args.name!r}, package)\n")
    print(f"""
Next, in this order:

  1. framework/contracts/{args.name}.schema.json
     Replace TODO_items with what this handover actually carries, and
     {args.src}_ref with the backlink to the {args.src} package. Keep the
     envelope and the measurement shape exactly as they are.

  2. framework/contracts/profiles/*.json
     Add required_quantities.{args.name} to BOTH profiles, and any
     identifier patterns the contract refers to with x-pattern. If the two
     use cases need different things here, that is correct — it is what the
     profile is for.

  3. framework/agents/sentinel_{abbr}.py
     Fill NEVER_AUTOFIX. Delete translate() entirely if the upstream phase
     already emits a package in the contract's shape — that is the normal
     case, and sentinel_b2t.py is the example of it.

  4. A deliberately broken package, and a test that it fails for the reason
     you expect. A check nobody has seen fail is a check nobody trusts.
""")



def make_oo_contract(name: str, label: str, src: str, dst: str) -> str:
    """A contract in `sentinel-oo`'s language, which this framework also runs.

    Written as YAML with the reasons beside the rules, because that is what
    the file is for. The five demands are the whole vocabulary: a language
    that can say anything can also say things nobody can check.
    """
    return f"""# {src.title()} -> {dst.title()}: {label}
#
# A `sentinel-oo` contract. Its requirements apply to ENTITIES IN A CRATE, by
# type, which is the difference from the `dbtl` dialect - that one checks paths
# in a package. Both are run by the same sentinel:
#
#     Sentinel(profile=..., also="<the folder holding this file>")
#
# The five demands are the whole vocabulary, on purpose:
#
#     be recorded                     optionally one_of: [...]
#     be unique
#     point at something in the crate  optionally of_type: SomeType
#     be a number between              needs between: [low, high]
#     hold data                        the file exists and is not empty
#
# `applies_to` is `root`, `descriptor`, or `type:SomeType`.
# What a requirement reads is either `property:` written on the entity, or
# `named_value:` hanging off it as a PropertyValue - which is how a Process
# Run Crate records most numbers.

contract: {name}
version: 0.1.0
description: >-
  TODO: what this handover is for, in one or two sentences a person outside
  this project would understand.

# The types this contract is written for. A crate holding none of them is
# refused outright: every requirement about an absent type would match nothing
# and pass, and a handover accepted without having been checked is worse than
# one refused.
expects:
  - TODO_SomeType

requires:
  - name: TODO_every_thing_records_its_identifier
    applies_to: type:TODO_SomeType
    property: identifier
    must: be recorded
    severity: refuse
    message: >-
      TODO: the sentence a person reads when this fails. Write it as the
      person who will have to fix it, not as the person who wrote the rule.

  - name: TODO_no_two_things_share_an_identifier
    applies_to: type:TODO_SomeType
    property: identifier
    must: be unique
    severity: refuse
    message: >-
      TODO: two of these carry the same identifier, so nothing downstream can
      tell them apart.
"""


if __name__ == "__main__":
    main()
