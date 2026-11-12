#!/usr/bin/env python3
"""Both sentinels, the same crates, side by side.

    python3 scripts/compare_sentinels.py

Two implementations now guard the Design -> Build handover: this framework's
and Anil Wipat's `sentinel-oo`. They were written independently, their
contracts share no check names, and the useful question is not which is right
but whether they AGREE - because a handover one accepts and the other refuses
is a handover nobody can hand over.

This runs HIS engine, not our reading of it: `sentinel-oo` is imported from
the sibling checkout and asked to validate, with `repair_budget=0` so no model
is involved and the verdict is the rules alone. Nothing in his repository is
written to. If it is not on disk, this says so and stops.

WHAT IT PRINTS
  * each crate, our verdict and his, and whether they agree
  * the same again for his contract run by BOTH engines, which is the tighter
    test: one contract file, two readers, and any disagreement there is a bug
    in our reader rather than a difference of opinion
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OO = Path.home() / "Research" / "dbtlhub" / "sentinel-oo"
CRATES = (Path.home() / "Research" / "dbtlhub" / "bioprospecting"
          / "exampleROcrates" / "design-to-build")

sys.path.insert(0, str(ROOT))


def folders() -> list[Path]:
    out = [CRATES / "valid"] + sorted((CRATES / "invalid").glob("*/"))
    return [f for f in out if (f / "ro-crate-metadata.json").is_file()]


def ours(folder: Path) -> tuple[str, list[str]]:
    """Our verdict, through the script a person would actually run."""
    done = subprocess.run([sys.executable, "scripts/check_crate.py", str(folder)],
                          cwd=ROOT, capture_output=True, text=True)
    said = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout)
    verdict = ("refused" if "REFUSED" in said else
               "accepted" if "ACCEPTED" in said else "?")
    return verdict, sorted(set(re.findall(r"^\s+!\s+\S+\s+(\w+)", said, re.M)))


def main() -> int:
    if not (OO / "src").is_dir():
        print(f"\n  {OO} is not here. This compares against a sibling "
              f"checkout of dbtlhub; clone it beside this one.\n")
        return 2
    sys.path.insert(0, str(OO / "src"))
    from sentinel_oo import __version__ as his_version        # noqa: PLC0415
    from sentinel_oo.contract import ContractRegistry         # noqa: PLC0415
    from sentinel_oo.crate import Crate                       # noqa: PLC0415
    from sentinel_oo.rules import ContractChecks              # noqa: PLC0415
    from framework import oo_contract as adapter              # noqa: PLC0415

    his = ContractRegistry.from_dir(OO / "examples" / "contracts").get(
        "design_to_build")
    read_by_us = adapter.load(OO / "examples" / "contracts" / "design_to_build.yaml")

    print(f"\n{'=' * 88}\nTWO CONTRACTS, SIX CRATES\n{'=' * 88}\n")
    print(f"  ours: 13 checks   &middot;   his: {len(his.requirements)} "
          f"requirements, {his.name}/{his.version} (sentinel-oo {his_version})\n"
          .replace("&middot;", "·"))
    print(f"  {'crate':<28}{'ours':<34}{'sentinel-oo':<30}{'agree'}")
    print(f"  {'-' * 92}")

    agreed = 0
    for folder in folders():
        report = ContractChecks().validate(Crate.from_path(folder), his)
        his_verdict = ("refused" if report.blocking else
                       "flagged" if report.flags else "accepted")
        his_found = sorted({getattr(v.requirement, "name", "?")
                            for v in report.violations})
        our_verdict, our_found = ours(folder)
        same = our_verdict == his_verdict
        agreed += same
        print(f"  {folder.name:<28}"
              f"{(our_verdict + ' · ' + ', '.join(our_found[:1]))[:33]:<34}"
              f"{(his_verdict + ' · ' + ', '.join(his_found[:1]))[:29]:<30}"
              f"{'yes' if same else 'NO'}")

    print(f"\n  {agreed}/{len(folders())} verdicts agree, between two contracts "
          f"that share no check names.\n")

    # ---- the tighter test -------------------------------------------------
    print(f"{'=' * 88}\nHIS CONTRACT, READ BY BOTH ENGINES\n{'=' * 88}\n")
    print("  A disagreement here is not a difference of opinion. It is a bug\n"
          "  in our reader, because it is one file.\n")
    print(f"  {'crate':<28}{'his engine':<22}{'our reader':<22}{'agree'}")
    print(f"  {'-' * 92}")
    matched = 0
    for folder in folders():
        report = ContractChecks().validate(Crate.from_path(folder), his)
        his_names = sorted({getattr(v.requirement, "name", "?")
                            for v in report.violations})
        crate = json.loads((folder / "ro-crate-metadata.json").read_text())
        our_names = sorted({e.code for e in
                            adapter.check(read_by_us, crate, base=folder)})
        same = his_names == our_names
        matched += same
        print(f"  {folder.name:<28}{len(his_names):<22}{len(our_names):<22}"
              f"{'yes' if same else 'NO'}")
        if not same:
            print(f"      only his:  {sorted(set(his_names) - set(our_names))}")
            print(f"      only ours: {sorted(set(our_names) - set(his_names))}")

    print(f"\n  {matched}/{len(folders())} agree finding for finding.\n")
    return 0 if matched == len(folders()) else 1


if __name__ == "__main__":
    sys.exit(main())
