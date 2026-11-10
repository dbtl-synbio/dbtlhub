#!/usr/bin/env python3
"""Run Handover 1 against a real Design -> Build crate on disk.

    python3 scripts/check_crate.py                      # the use case's own crate
    python3 scripts/check_crate.py path/to/crate-folder

With no argument it reads
`bioprospecting/exampleROcrates/design-to-build-simple/`, which is the crate
Anil Wipat wrote for the bioprospecting use case. That is the point of this
script: the handover is checked against somebody else's crate, not only
against the one we generate ourselves.

Nothing about the agent changes. The crate is written in a different dialect -
provenance through CreateAction rather than PROV properties, metadata in named
PropertyValue entries rather than flat keys - and that difference is declared
in the profile, where a use case's differences belong.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.agents.base import Task                                # noqa: E402
from framework.agents.coordinator import Coordinator                  # noqa: E402
from framework.agents.sentinel_d2b import DesignToBuildAgent          # noqa: E402
from framework.validator import validate                              # noqa: E402
from usecases.bioprospecting.prc_crate import (BREAKAGES, DEFAULT,  # noqa: E402
                                                CrateError, damage, load)

BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, AMBER = "\033[31m", "\033[32m", "\033[33m"


def _break_all(crate, items, report, args) -> None:
    """One line per breakage: what was done, and what the handover did about it."""
    print(f"\n{BOLD}The use case's own crate, and three deliberate faults{OFF}")
    print(f"{DIM}{report['root']}{OFF}\n")
    rows = [("as published", None)] + [(k, k) for k in sorted(BREAKAGES)]
    for label, kind in rows:
        slug = label.replace(" ", "-")
        used, missing = ((crate, report["files_missing"]) if kind is None
                         else damage(crate, kind, report["root"]))
        agent = DesignToBuildAgent(profile=args.profile, lab=args.lab)
        result = Coordinator(f"break-{slug}").step(
            agent, Task(goal="hand over", inputs={
                "crate": used, "items": items, "run_id": f"break-{slug}",
                "files_missing": missing}, max_repairs=2), label="d2b")
        ok = result.status == "ok"
        mark = f"{GREEN}ACCEPTED{OFF}" if ok else f"{RED}REFUSED {OFF}"
        # Ask the validator for the codes rather than parsing its printout:
        # a path like '.gene calling mode' has spaces in it, and a column
        # offset is not a data format.
        checked = validate(result.outputs["package"], agent.contract)
        codes = sorted({e.code for e in checked.blocking})
        flagged = len(checked.flags)
        note = (f"{DIM}the order can go out{OFF}" if ok
                else f"{len(codes)} error(s): {', '.join(codes)}")
        if flagged:
            note += f"  {AMBER}+{flagged} flag(s){OFF}"
        print(f"  {label:<28}{mark}  {note}")
    print(f"\n{DIM}  Two of those three faults pass every RO-Crate validator "
          f"there is.{OFF}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", default=None,
                    help=f"crate folder (default: {DEFAULT})")
    ap.add_argument("--profile", default="bioprospecting")
    ap.add_argument("--lab", default=None, help="a lab vocabulary file to add")
    ap.add_argument("--break", dest="breakage", choices=sorted(BREAKAGES),
                    help="damage the crate on the way in, and see it refused")
    ap.add_argument("--break-all", action="store_true",
                    help="every breakage in turn, one line each")
    args = ap.parse_args()

    try:
        crate, items, report = load(args.folder)
    except CrateError as exc:
        sys.exit(f"{RED}{exc}{OFF}")

    if args.break_all:
        return _break_all(crate, items, report, args)

    missing = report["files_missing"]
    if args.breakage:
        crate, missing = damage(crate, args.breakage, report["root"])
        print(f"\n{AMBER}{BOLD}DAMAGED ON PURPOSE: {args.breakage}{OFF}")
        print(f"  {DIM}{BREAKAGES[args.breakage]}{OFF}")

    print(f"\n{BOLD}The crate as read from disk{OFF}")
    print(f"  folder            {report['root']}")
    print(f"  entities          {report['entities']} in @graph")
    print(f"  conforms to       {', '.join(report['conforms_to']) or '-'}")
    print(f"  files promised    {report['files_promised']}")
    if missing:
        print(f"  {RED}files missing     {', '.join(missing)}{OFF}")
        print(f"  {DIM}a relative @id is a promise the file is present, and no "
              f"profile validator checks it{OFF}")
    else:
        print(f"  {GREEN}files missing     none{OFF}")
    print(f"  plate rows        {report['plate_rows']}  "
          f"({report['constructs']} constructs, {report['proteins']} proteins)")

    run_id = "crate-" + Path(report["root"]).name
    coord = Coordinator(run_id)
    agent = DesignToBuildAgent(profile=args.profile, lab=args.lab)
    result = coord.step(
        agent,
        Task(goal="hand this crate over to Build",
             inputs={"crate": crate, "items": items, "run_id": run_id,
                     "files_missing": missing},
             max_repairs=2),
        label="handover d2b", store_as="d2b")

    print(f"\n{BOLD}Handover 1{OFF}  {DIM}profile {args.profile}"
          f"{', lab ' + args.lab if args.lab else ''}{OFF}")
    for note in result.notes:
        print(f"  {note}")
    for err in result.errors:
        print(f"  {RED}!{OFF} {err}")

    ok = result.status == "ok"
    colour = GREEN if ok else RED
    flags = [e for e in result.errors if "[flag]" in e]
    if ok:
        tail = ("  -  the order can go to the vendor" if not flags else
                f"  -  the order can go, and Build is told about "
                f"{len(flags)} flagged item(s)")
    else:
        tail = f"  -  {len(result.errors)} error(s) need a decision"
    print(f"\n  {colour}{BOLD}{'ACCEPTED' if ok else 'REFUSED'}{OFF}{tail}")

    if result.status == "ok":
        view = agent.provider_view(result.outputs["package"])
        print(f"\n{BOLD}What would actually leave the building{OFF}")
        print(f"  {DIM}container {view['container_id']}, format "
              f"{view['format']}{OFF}")
        flagged = {b["design_item_id"] for b, e in
                   zip(result.outputs["package"]["bindings"], range(99))
                   if any(f"bindings[{e}]" in x for x in flags)}
        for line, binding in zip(view["items"],
                                 result.outputs["package"]["bindings"]):
            mark = (f"  {AMBER}← flagged{OFF}"
                    if binding["design_item_id"] in flagged else "")
            print(f"    {line['order_item_id']}  {line['position']:<4}"
                  f"{line['sequence_type']:<5}{line['length_bp']:>6} bp  "
                  f"{line['sequence_sha256'][:23]}...{mark}")
        print(f"  {DIM}No coordinates, no freezer, no collector. Those stay "
              f"with us, and the crate keeps them queryable.{OFF}")
    print()


if __name__ == "__main__":
    main()
