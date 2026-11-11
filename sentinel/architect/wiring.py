#!/usr/bin/env python3
"""The real phase agents and the real sentinels, behind the Architect's seams.

    python3 architect/wiring.py

`Architect.run_phase(phase, runner, checker)` takes two callables. This file
supplies them from what already exists, and supplies nothing else: the phase
agents in `framework/agents/phase_*_crate.py` and the four sentinels in
`framework/agents/sentinel_*.py` are used unchanged.

The one thing worth understanding is why the phase agent's own sentinel is
switched off here.

A `PhaseAgent` normally submits to its sentinel itself and hands back whatever
came of it. That is right when the phase agent is in charge. It is wrong under
an Architect, because then the verdict would be consumed inside the phase and
the Architect would see only a status - it could not weigh the findings, could
not decide to go back rather than ask, and could not word a question about
something it never saw. So the runner calls `produce()` and `package()` and
stops; the checker runs the sentinel; and the decision happens in one place
that can see both.

The phase agents remain usable the other way round. Nothing here changes them.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from architect.architect import HANDOVER_OF, PhaseResult              # noqa: E402
from architect.contract import Checked, Finding, Verdict              # noqa: E402
from framework.agents.base import Task                                # noqa: E402
from framework.agents.phase_build_crate import BuildPhaseAgent        # noqa: E402
from framework.agents.phase_design_crate import DesignPhaseAgent      # noqa: E402
from framework.agents.phase_learn_crate import LearnPhaseAgent        # noqa: E402
from framework.agents.phase_test_crate import TestPhaseAgent          # noqa: E402
from framework.agents.sentinel import Sentinel                        # noqa: E402

PHASE_AGENTS = {"design": DesignPhaseAgent, "build": BuildPhaseAgent,
                "test": TestPhaseAgent, "learn": LearnPhaseAgent}


# --------------------------------------------------------------------------- #
#  The four phase agents, as runners
# --------------------------------------------------------------------------- #
def phase_runner(profile: str = "bioprospecting", lab: str | None = None,
                 engine=None, **phase_inputs):
    """A `Runner` that drives the real phase agent for whichever phase is asked.

    `phase_inputs` carries whatever a particular phase needs that the Architect
    does not know about - a panel, an upstream package. The Architect does not
    interpret them, which is the point: it must not need to understand the
    science to orchestrate it.

    `engine` is whichever model the person chose, or None for the default
    `RulesEngine`: deterministic, offline, and enough to check every handover.
    It is passed to the phase agent, not to the sentinel - the sentinel's
    verdict is the validator's, and a model has no vote in it.
    """
    made: dict[str, object] = {}

    def run(phase: str, arch) -> PhaseResult:
        agent = PHASE_AGENTS[phase](profile=profile, lab=lab, engine=engine)
        agent.sentinel = None          # the Architect does the checking

        task = Task(goal=f"run {phase}",
                    inputs={"run_id": arch.run_id, **phase_inputs,
                            **_upstream_for(phase, made, arch)})
        store = arch.memory.store      # one crate; the phase writes into it

        entities, action, files = agent.produce(task, store)

        def build_package() -> dict | None:
            # Called by the Architect after the entities are in the crate, so
            # the package carries a crate that contains what it hands over.
            package = agent.package(task, store)
            if package is not None:
                made[phase] = package
            return package

        return PhaseResult(entities=entities, action=action,
                           make_package=build_package, by=agent.name,
                           notes=[f"{len(entities)} entit{'y' if len(entities) == 1 else 'ies'} "
                                  f"written by {agent.name}"])
    return run


def _upstream_for(phase: str, made: dict, arch) -> dict:
    """What a phase needs from the one before it.

    Named here rather than inside each agent because it is a statement about
    the order of the cycle, and the cycle is the Architect's business.
    """
    if phase == "build":
        return {"design_package": _stored(arch, "design")}
    if phase == "test":
        return {"package": made.get("build"), "build_package": _stored(arch, "build")}
    if phase == "learn":
        return {"package": made.get("test"), "test_package": _stored(arch, "test")}
    return {}


def _stored(arch, phase: str) -> str:
    """Where the Architect wrote that phase's package. Never constructed."""
    return str(Path("runs") / arch.run_id / f"{phase}_handover.json")


# --------------------------------------------------------------------------- #
#  The four sentinels, as checkers
# --------------------------------------------------------------------------- #
def sentinel_checker(profile: str = "bioprospecting"):
    """A `Checker` that runs the real sentinel and reports what it found.

    It validates rather than calling `handle()`, for one reason: `handle()`
    may repair, and a repair is a change to the package. Under an Architect the
    decision to change something belongs to the Architect, so the check here is
    read-only and the repair step stays available to whoever wants it.
    """
    # One object for the whole run. It loads the contract for whichever
    # handover it is given - the only thing that differs between them - and
    # writes its own act into the crate, so a crate nobody checked is visibly
    # different from one that passed.
    sentinel = Sentinel(profile=profile)
    VERDICT = {"accepted": Verdict.ACCEPTED,
               "accepted_with_flags": Verdict.ACCEPTED_WITH_FLAGS,
               "refused": Verdict.REFUSED}

    def check(handover: str, package: dict, arch) -> Checked:
        seen = sentinel.check_and_record(handover, package)
        findings = [Finding(code=e.code, path=e.path, message=e.message,
                            blocking=(e.severity == "error"),
                            fix_hint=e.fix_hint or "")
                    for e in seen.report.errors]
        return Checked(handover=handover, verdict=VERDICT[seen.verdict],
                       findings=findings,
                       trace=[f"{sentinel.name} against {seen.contract_id} "
                              f"[profile {profile}], recorded in the crate"])
    return check


# --------------------------------------------------------------------------- #
def _findings_of(arch) -> list[str]:
    """What the last check actually reported, for the demonstration."""
    for note in reversed(arch.ledger):
        if note.get("notes"):
            return [n for n in note["notes"] if n.startswith(("rerun", "asked", "flag"))][:3]
    return []


def main() -> None:
    import shutil
    from architect.architect import Architect
    from usecases.bioprospecting import instruments as bp

    run_id = "wired"
    shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)

    print(f"\n{'=' * 76}\nTHE REAL AGENTS, UNDER THE ARCHITECT\n{'=' * 76}\n")
    arch = Architect(run_id, researcher="Marco")
    arch.consult(objective="find thermostable ene-reductases in hot spring sediment")

    runner = phase_runner(profile="bioprospecting", lab="newcastle",
                          n=6, panel=bp.design_panel(6))
    checker = sentinel_checker(profile="bioprospecting")

    for phase in ("design", "build", "test", "learn"):
        decision = arch.run_phase(phase, runner, checker)
        step = arch.history[-1]
        verdict = step.verdict.value.upper() if step.verdict else "no check"
        print(f"  {phase:<7} {verdict:<22} -> {decision.move.value.upper()}")
        print(f"          {decision.because[:140]}")
        if decision.question is not None:
            print(f"          asks: {decision.question.headline[:110]}")
        print()

    crate = arch.memory.snapshot()
    print(f"{'=' * 76}\n  one crate: {len(crate['@graph'])} entities")
    print(f"  {arch.summary()}")
    print(f"  ledger: {arch.write_ledger()}")

    # ---- and now with the sentinels given something to refuse -------------
    print(f"\n{'=' * 76}\nTHE SAME AGENTS, WITH FAULTS THE SENTINELS CATCH"
          f"\n{'=' * 76}\n")
    broken_id = run_id + "-broken"
    shutil.rmtree(ROOT / "runs" / broken_id, ignore_errors=True)
    broken = Architect(broken_id, researcher="Marco")
    broken.consult(objective="the same panel, with three faults injected")

    faulted = phase_runner(profile="bioprospecting", lab="newcastle", n=6,
                           panel=bp.design_panel(6),
                           faults={"missing_units", "unknown_item", "dropped_well"})
    for phase in ("design", "build"):
        decision = broken.run_phase(phase, faulted, checker)
        step = broken.history[-1]
        verdict = step.verdict.value.upper() if step.verdict else "no check"
        print(f"  {phase:<7} {verdict:<22} -> {decision.move.value.upper()}")
        for finding in _findings_of(broken):
            print(f"          {finding}")
        print(f"          {decision.because[:150]}")
        if decision.question is not None:
            print(f"          asks: {decision.question.headline[:110]}")
        print()
    print(f"  {broken.summary()}\n")


if __name__ == "__main__":
    main()
