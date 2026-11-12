#!/usr/bin/env python3
"""One sentinel. Four contracts. The same checks, against different things.

    python3 framework/agents/sentinel.py

There were four sentinel classes. They were never four agents: three of them
were a name, a contract name and a set of codes, with no logic at all, and the
fourth differed only by having a `translate()`. Four names for one behaviour is
four places to change when the behaviour changes, and it invited the reading
that each handover is guarded by a different thing.

It is not. The same agent stands at every handover and loads the contract for
that one. What varies is what it checks against, which is data, not code.

AND IT HANDS THE CRATE ON, RICHER
A refusal that exists only as a message in a terminal is not a record. So the
sentinel writes what it did into the crate it was given: which contract, which
version, what was found, and the verdict. The crate that comes out is the one
that went in, plus the fact that it was checked - and a crate nobody checked
is then visibly different from one that passed.

It still writes nothing of its own about the science. It records its own act,
which is a different thing and the only thing it is entitled to record.

The four old classes still exist and still work. They now inherit from this.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.validator import (Error, Report, load_contract,      # noqa: E402
                                 validate)

HANDOVERS = ("design_to_build", "build_to_test", "test_to_learn",
             "learn_to_design")

ACCEPTED = "accepted"
ACCEPTED_WITH_FLAGS = "accepted_with_flags"
REFUSED = "refused"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Checked:
    """What the sentinel decided, and everything needed to say why."""
    handover: str
    contract_id: str
    profile: str
    verdict: str
    report: Report
    at: str = field(default_factory=now)
    # Every agreement this handover was held to, ours first. More than one
    # means two sentinels' contracts were applied to the same package.
    held_to: tuple = ()

    @property
    def blocking(self):
        return self.report.blocking

    @property
    def flags(self):
        return self.report.flags

    def summary(self) -> str:
        bits = [f"{len(self.blocking)} error(s)"] if self.blocking else []
        if self.flags:
            bits.append(f"{len(self.flags)} flag(s)")
        return f"{self.verdict.upper()}" + (f" - {', '.join(bits)}" if bits else "")


class Sentinel:
    """The one sentinel. Give it a handover; it loads that contract."""

    name = "sentinel"

    def __init__(self, profile: str = "bioprospecting", also=None):
        """`also` is a folder of `sentinel-oo` contracts to guard as well.

        Two sentinels now guard the same handovers: this one and Anil Wipat's
        `sentinel-oo`. Their contracts look at different objects - his
        requirements apply to entities in a crate, by type; ours apply to
        paths in a package - which is why a comparison of the two Design ->
        Build contracts found thirteen checks on one side, twenty on the
        other, and two in common.

        Reimplementing his twenty as ours would make a second copy that
        drifts. So his file is run as it is: when a handover has a contract on
        both sides, this sentinel holds the package to both and reports them
        together, naming which agreement each finding came from. A handover
        that satisfies one and not the other is refused, and the trace says
        which.
        """
        self.profile = profile
        self._contracts: dict[str, dict] = {}
        self._foreign_dir = Path(also) if also else None
        self._foreign: dict[str, object] = {}

    def contract(self, handover: str) -> dict:
        """Loaded once per handover and kept, because the files do not change
        during a run and reading them four times per cycle buys nothing."""
        if handover not in HANDOVERS:
            raise ValueError(f"{handover!r} is not one of {HANDOVERS}")
        if handover not in self._contracts:
            self._contracts[handover] = load_contract(handover, profile=self.profile)
        return self._contracts[handover]

    # ---- the other side's contract, if there is one -----------------------
    def foreign(self, handover: str):
        """The `sentinel-oo` contract for this handover, or None.

        None is a normal answer: a handover the other side has not written a
        contract for is guarded by ours alone, and that is said in the trace
        rather than left to be assumed.
        """
        if self._foreign_dir is None:
            return None
        if handover not in self._foreign:
            from framework import oo_contract                   # noqa: PLC0415
            found = oo_contract.available(self._foreign_dir)
            self._foreign[handover] = (oo_contract.load(found[handover])
                                       if handover in found else None)
        return self._foreign[handover]

    # ---- the check ---------------------------------------------------------
    def check(self, handover: str, package: dict) -> Checked:
        contract = self.contract(handover)
        report = validate(package, contract)

        other = self.foreign(handover)
        if other is not None:
            from framework import oo_contract                   # noqa: PLC0415
            crate = package.get("crate")
            if isinstance(crate, dict):
                base = package.get("crate_ref", {}).get("folder")
                for error in oo_contract.check(
                        other, crate, base=Path(base) if base else None):
                    # Stamped with whose agreement it came from. Two contracts
                    # reporting into one list, with no way to tell them apart,
                    # would make a disagreement between them unreadable.
                    report.errors.append(Error(
                        error.path, f"{other.name}:{error.code}",
                        f"[sentinel-oo {other.version}] {error.message}",
                        error.fix_hint, error.severity))

        if report.blocking:
            verdict = REFUSED
        elif report.flags:
            verdict = ACCEPTED_WITH_FLAGS
        else:
            verdict = ACCEPTED
        held_to = [contract.get("$id", "?")]
        if other is not None:
            held_to.append(other.id)
        return Checked(handover=handover, contract_id=contract.get("$id", "?"),
                       profile=self.profile, verdict=verdict, report=report,
                       held_to=tuple(held_to))

    # ---- handing the crate on, richer --------------------------------------
    def record(self, crate: dict, checked: Checked) -> dict:
        """Write the check into the crate, and return the crate.

        In place, and returned, so a caller can write either way round without
        being wrong. What goes in is one action and one PropertyValue per
        finding - the sentinel's own act, not a claim about the science.
        """
        graph = crate.setdefault("@graph", [])
        index = {e.get("@id"): e for e in graph if isinstance(e, dict)}

        serial = sum(1 for e in graph
                     if isinstance(e, dict)
                     and str(e.get("@id", "")).startswith("#check/"))
        ref = f"#check/{checked.handover}-{serial + 1}"

        findings = []
        for i, error in enumerate(checked.report.errors, start=1):
            pv = f"{ref}/finding-{i}"
            findings.append({"@id": pv})
            graph.append({
                "@id": pv, "@type": "PropertyValue",
                "name": error.code, "value": error.message,
                "dbtl:path": error.path,
                "dbtl:severity": error.severity,
                "description": error.fix_hint or "",
            })

        action = {
            "@id": ref,
            "@type": "CreateAction",
            "name": f"checked the {checked.handover} handover",
            "description": checked.summary(),
            "instrument": {"@id": "#tool/sentinel"},
            "endTime": checked.at,
            "actionStatus": ("http://schema.org/CompletedActionStatus"
                             if checked.verdict != REFUSED else
                             "http://schema.org/FailedActionStatus"),
            "dbtl:verdict": checked.verdict,
            "dbtl:contract": checked.contract_id,
            "dbtl:profile": checked.profile,
            "object": findings,
        }
        graph.append(action)

        if "#tool/sentinel" not in index:
            graph.append({"@id": "#tool/sentinel",
                          "@type": "SoftwareApplication",
                          "name": "the sentinel", "version": "0.1.0"})

        root = _root(index)
        if root is not None:
            mentions = root.setdefault("mentions", [])
            if {"@id": ref} not in mentions:
                mentions.append({"@id": ref})
        return crate

    def check_and_record(self, handover: str, package: dict) -> Checked:
        """The usual way round: check the package, then write the check into
        the crate the package carries, if it carries one."""
        checked = self.check(handover, package)
        crate = package.get("crate")
        if isinstance(crate, dict):
            self.record(crate, checked)
        return checked


def _root(index: dict) -> dict | None:
    descriptor = index.get("ro-crate-metadata.json", {})
    about = descriptor.get("about")
    ref = about.get("@id") if isinstance(about, dict) else "./"
    return index.get(ref) or index.get("./")


# --------------------------------------------------------------------------- #
def main() -> None:
    import json
    sentinel = Sentinel(profile="bioprospecting")

    print(f"\n{'=' * 74}\nONE SENTINEL, FOUR CONTRACTS\n{'=' * 74}\n")
    for handover in HANDOVERS:
        contract = sentinel.contract(handover)
        checks = contract.get("x-dbtl-checks", [])
        print(f"  {handover:<18}{contract['$id']:<28}{len(checks)} checks")
    print(f"\n  one object, {len(sentinel._contracts)} contracts loaded, "
          f"same code path for all four.\n")

    print(f"{'=' * 74}\nAND IT HANDS THE CRATE ON, RICHER\n{'=' * 74}\n")
    package = {
        "contract": "build_to_test", "contract_version": "0.2.0",
        "profile": "bioprospecting", "run_id": "sentinel-demo",
        "produced_at": now(),
        "produced_by": {"agent": "phase_build", "tool": "t", "engine": "none"},
        "design_ref": {"package": "p", "contract": "design_to_build",
                       "run_id": "sentinel-demo", "items": []},
        "samples": [],
        "crate": {"@graph": [
            {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
             "about": {"@id": "./"}},
            {"@id": "./", "@type": "Dataset", "name": "a run"}]},
    }
    before = len(package["crate"]["@graph"])
    checked = sentinel.check_and_record("build_to_test", package)
    after = len(package["crate"]["@graph"])

    print(f"  verdict      {checked.summary()}")
    print(f"  crate        {before} -> {after} entities\n")
    for entity in package["crate"]["@graph"]:
        if str(entity.get("@id", "")).startswith("#check/") and \
                entity.get("@type") == "CreateAction":
            print("  what it wrote about itself:")
            print("   ", json.dumps({k: v for k, v in entity.items()
                                     if k not in ("object",)}, indent=4)
                  .replace("\n", "\n    "))
            break
    print(f"""
  A refusal that exists only in somebody's terminal is not a record. The
  crate now says it was checked, against which contract, by what, and what
  was found - so a crate nobody checked is visibly different from one that
  passed.
""")


if __name__ == "__main__":
    main()
