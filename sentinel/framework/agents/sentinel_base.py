"""The sentinel agent, generalised.

Every phase transition does the same four things in the same order:

    translate  reshape what the upstream phase emitted into the contract's shape
    validate   ask the validator - never itself - whether that worked
    repair     fix what was flagged, within a budget, inventing nothing
    escalate   hand the rest to a human, and stop the route

Only `translate` differs between handovers. So it is the only method a team has
to write: subclass, set `contract_name`, implement `translate`, done. That is
what makes "four contracts, four sentinel agents" a week's work for two pairs
instead of four separate codebases.

An error is never auto-fixed if its code is in `never_autofix`, or if the
contract's own `fix_hint` begins with "not auto-fixable". The second route means
the decision lives in the contract, in prose a reviewer reads, rather than in a
Python set only the author knows about.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Agent, Result, Task                 # noqa: E402
from framework.llm import Engine, RulesEngine, apply_patch            # noqa: E402
from framework.validator import Report, load_contract, validate       # noqa: E402

BLOCKING_PREFIX = "not auto-fixable"


class SentinelAgent(Agent):
    contract_name: str = ""
    never_autofix: set[str] = set()

    def __init__(self, profile: str = "bioprospecting", engine: Engine | None = None):
        self.profile = profile
        self.engine = engine or RulesEngine()
        self.contract = load_contract(self.contract_name, profile=profile)
        self.consumes = [self.contract_name]
        self.produces = [self.contract_name]

    # ---- the only part a handover has to write ----------------------------
    def translate(self, task: Task) -> tuple[dict, list[str]]:
        """Return (package, notes). Default: the upstream phase already emitted one."""
        return task.inputs["package"], []

    def is_blocking(self, err) -> bool:
        return (err.code in self.never_autofix
                or (err.fix_hint or "").startswith(BLOCKING_PREFIX))

    # ---- the part nobody should write twice --------------------------------
    def handle(self, task: Task) -> Result:
        package, trace = self.translate(task)

        report = validate(package, self.contract)
        trace.append(f"validate against {self.contract['$id']} "
                     f"[profile {self.profile}] -> "
                     + ("PASS" if report.ok else
                        f"FAIL, {len(report.blocking)} error(s)")
                     + (f" + {len(report.flags)} flag(s)" if report.flags else ""))

        attempt = 0
        while not report.ok and attempt < task.max_repairs:
            attempt += 1
            # Only blocking errors are candidates for repair. A flag is not a
            # defect to be patched away - it is something true about the data
            # that the next phase has to be told.
            fixable = [e for e in report.blocking if not self.is_blocking(e)]
            if not fixable:
                trace.append(f"repair {attempt}: every remaining error needs a "
                             f"decision, not a patch")
                break

            # The engine sees only the errors it is allowed to act on, and may
            # only write where the validator pointed. Without this, a model
            # could "fix" a double-booked well by renaming it - and the
            # re-validation would pass, because renaming genuinely does make the
            # key unique. It would also have fabricated a lab record. The rule
            # has to be a constraint here, not a comment in the contract.
            allowed = {e.path for e in fixable}
            patches = self.engine.propose_patches(package, Report(fixable), self.contract)
            if not patches:
                trace.append(f"repair {attempt}: engine '{self.engine.name}' proposed "
                             f"no patch for {sorted({e.code for e in fixable})}")
                break

            applied = 0
            for patch in patches:
                if patch.path not in allowed:
                    trace.append(f"repair {attempt}: REFUSED {patch.path} - the "
                                 f"validator did not report that path as fixable")
                    continue
                if apply_patch(package, patch):
                    applied += 1
                    trace.append(f"repair {attempt}: {patch.path} <- "
                                 f"{_short(patch.value)} ({patch.reason})")
            # The validator is the authority: re-check, never trust the patch.
            report = validate(package, self.contract)
            trace.append(f"repair {attempt}: {applied} patch(es) applied, "
                         f"re-validate -> {len(report.blocking)} error(s) left")

        for flag in report.flags:
            trace.append(f"FLAG: {flag.message}"
                         + (f" - {flag.fix_hint}" if flag.fix_hint else ""))

        if report.ok:
            if report.flags:
                trace.append(f"accepted with {len(report.flags)} flag(s): the "
                             f"package is valid and the receiving phase has "
                             f"been told what it is receiving")
            return Result(status="ok", outputs={"package": package},
                          engine=self.engine.name, notes=trace,
                          errors=[str(f) for f in report.flags])

        return Result(
            status="escalated",
            outputs={"package": package},
            errors=[str(e) for e in report.errors],
            engine=self.engine.name,
            notes=trace + [
                f"ESCALATE: {len(report.blocking)} error(s) need a decision",
                *dict.fromkeys(f"  {e.code}: {e.fix_hint}"
                               for e in report.errors if e.fix_hint),
            ],
        )


def _short(value, limit: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."
