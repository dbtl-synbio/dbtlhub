#!/usr/bin/env python3
"""Walk one run backwards, from the last handover to the ground.

    python3 scripts/trace.py <run-id>
    python3 scripts/trace.py --list

The question this answers: a number appears in a Learn -> Design
recommendation. Which sediment core is behind it?

Handover 1 deliberately sends the synthesis vendor almost nothing - sequences
and wells. Everything else stays with us, and from that moment on it is only
reachable through a chain of backlinks: every package names the package it was
built from, and the first one names the crate. If one link does not resolve,
the context is gone, and it is gone silently: each package on its own still
validates perfectly.

So this is not a nicety. It is the check that the whole arrangement rests on,
and it can only be made at the end, across packages, which is why no single
contract can make it.

Exit code 1 if any link is broken.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RUNS = ROOT / "runs"
BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, AMBER, BLUE = "\033[31m", "\033[32m", "\033[33m", "\033[34m"

# Which backlink each contract uses, and what it must point at.
BACKLINK = {
    "learn_to_design": ("test_ref", "test_to_learn"),
    "test_to_learn": ("build_ref", "build_to_test"),
    "build_to_test": ("design_ref", "design_to_build"),
    "design_to_build": ("crate_ref", None),      # the end of the package chain
}


class Break(Exception):
    """A link that does not resolve. Carries what was expected and what was found."""


def resolve(path: str) -> Path:
    """Package paths are stored relative to the project root."""
    candidate = (ROOT / path) if not Path(path).is_absolute() else Path(path)
    return candidate


def load(path: str) -> dict:
    target = resolve(path)
    if not target.exists():
        raise Break(f"names {path!r}, and there is no such file")
    try:
        return json.loads(target.read_text())
    except json.JSONDecodeError as exc:
        raise Break(f"{path}: not readable as JSON ({exc})") from exc


def packages_of(run_id: str) -> list[dict]:
    ledger = RUNS / run_id / "ledger.jsonl"
    if not ledger.exists():
        sys.exit(f"no ledger for run {run_id!r}. Try --list.")
    out = []
    for line in ledger.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def last_package(entries: list[dict]) -> str | None:
    for entry in reversed(entries):
        if entry.get("package"):
            return entry["package"]
    return None


# --------------------------------------------------------------------------- #
def walk(start: str) -> tuple[list[tuple], list[str]]:
    """Follow backlinks until the crate. Returns (hops, problems)."""
    hops, problems = [], []
    path = start
    seen = set()

    while path:
        if path in seen:
            problems.append(f"the chain loops back on {path}")
            break
        seen.add(path)
        try:
            package = load(path)
        except Break as exc:
            problems.append(str(exc))
            break

        name = package.get("contract", "?")
        hops.append(("package", name, path, package))
        field, expect = BACKLINK.get(name, (None, None))
        if field is None:
            problems.append(f"{path}: contract {name!r} declares no backlink, so "
                            f"the chain stops here and nothing further is reachable")
            break

        ref = package.get(field)
        if not isinstance(ref, dict):
            problems.append(f"{path}: no {field}, so what it was built from is "
                            f"not stated")
            break

        if expect is None:                      # design_to_build -> the crate
            hops.append(("crate", field, ref.get("path", "?"), package))
            break

        nxt = ref.get("package")
        if not nxt:
            problems.append(f"{path}: {field} states no package path")
            break
        # The link has to say what it points at, or a wrong file would be
        # followed without complaint.
        declared = ref.get("contract")
        if declared and declared != expect:
            problems.append(f"{path}: {field} claims contract {declared!r}, "
                            f"expected {expect!r}")
        path = nxt

    return hops, problems


def to_the_ground(package: dict) -> list[str]:
    """Inside the Design crate, walk one ordered sequence back to the sample."""
    crate = package.get("crate")
    bindings = package.get("bindings") or []
    if not crate or not bindings:
        return []
    from framework.kg import provenance_of
    try:
        return provenance_of(crate, bindings[0]["crate_entity"])
    except Exception:
        return []


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--list", action="store_true", help="runs on disk")
    args = ap.parse_args()

    if args.list or not args.run_id:
        print(f"\n{BOLD}Runs on disk{OFF}")
        for d in sorted(p for p in RUNS.glob("*") if (p / "ledger.jsonl").exists()):
            entries = packages_of(d.name)
            last = last_package(entries)
            print(f"  {d.name:<32}{DIM}{len(entries)} step(s), "
                  f"last package: {last or 'none'}{OFF}")
        print()
        return

    entries = packages_of(args.run_id)
    start = last_package(entries)
    if not start:
        sys.exit(f"run {args.run_id!r} stored no package - nothing to trace")

    print(f"\n{BOLD}Tracing {args.run_id} backwards{OFF}")
    print(f"{DIM}from the last package stored, following each backlink until the "
          f"crate{OFF}\n")

    hops, problems = walk(start)

    for kind, name, path, package in hops:
        if kind == "crate":
            print(f"  {BLUE}└─ crate{OFF}        {path}")
            chain = to_the_ground(package)
            if chain:
                print(f"     {DIM}and inside it, one ordered sequence back to the "
                      f"ground:{OFF}")
                for i, node in enumerate(chain):
                    print(f"       {DIM}{i:>2}.{OFF} {node}")
            continue
        run = package.get("run_id", "?")
        print(f"  {GREEN}●{OFF} {name:<18}{DIM}{path}{OFF}")
        print(f"    {DIM}run {run} · produced by {package.get('produced_by', {}).get('agent', '?')}"
              f" · engine {package.get('produced_by', {}).get('engine', '?')}{OFF}")

    print()
    if problems:
        print(f"  {RED}{BOLD}CHAIN BROKEN{OFF}")
        for problem in problems:
            print(f"    {RED}!{OFF} {problem}")
        print(f"\n{DIM}  Each package above still validates on its own. That is the "
              f"point:\n  a broken chain is invisible to every single-package "
              f"check there is.{OFF}\n")
        sys.exit(1)

    print(f"  {GREEN}{BOLD}CHAIN INTACT{OFF}  -  {len(hops)} link(s), "
          f"last handover back to the crate")
    print(f"{DIM}  Everything Handover 1 kept out of the vendor's order is still "
          f"reachable\n  from the far end of the cycle.{OFF}\n")


if __name__ == "__main__":
    main()
