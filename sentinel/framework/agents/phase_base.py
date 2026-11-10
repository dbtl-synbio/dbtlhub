"""The phase agent: does the work, writes the crate, then asks to be checked.

A sentinel agent stands between two phases and decides whether the work can
travel. A phase agent is the other half, and it has three jobs in this order:

    1. produce   run the phase - the science, which this framework does not touch
    2. record    write what it produced into the run's one crate, with the
                 action that produced it
    3. hand over package what the next phase needs, and give it to the sentinel

The sentinel is a *submodule* here, not a superclass. That ordering matters:
the phase agent is in charge, and the check is something it submits to rather
than something that wraps it. It also means a phase agent is free to be
clever - choosing which assays to run, optimising a library under a budget -
because whatever it decides still has to survive the same check.

Writing the crate is step 2 and not an afterthought. A phase that produces
results and leaves somebody else to describe them is how the description ends
up being written by whoever is least able to write it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Agent, Result, Task                  # noqa: E402
from framework.crate_store import CrateStore                           # noqa: E402
from framework.llm import Engine, RulesEngine                          # noqa: E402


class PhaseAgent(Agent):
    phase: str = ""
    sentinel_class = None          # the sentinel this phase hands over to

    def __init__(self, profile: str = "bioprospecting",
                 engine: Engine | None = None, lab: str | None = None):
        self.profile = profile
        self.engine = engine or RulesEngine()
        self.lab = lab
        self.sentinel = (self.sentinel_class(profile=profile, engine=self.engine)
                         if self.sentinel_class else None)

    # ---- the two things a phase has to write -------------------------------
    def produce(self, task: Task, store: CrateStore) -> tuple[list[dict], dict, list[str]]:
        """Run the phase. Return (entities, the action that made them, files).

        This is the only place the science lives. Everything else in this class
        is bookkeeping that should look the same in every phase.
        """
        raise NotImplementedError

    def package(self, task: Task, store: CrateStore) -> dict | None:
        """What the next phase is given. Return None if this phase hands over
        nothing - the last phase of a run, or one still being written."""
        return None

    # ---- the part that should look the same everywhere ---------------------
    def handle(self, task: Task) -> Result:
        run_id = task.inputs.get("run_id", "adhoc")
        store = CrateStore(run_id)
        before = len(store)

        entities, action, files = self.produce(task, store)
        added = store.add(self.phase, entities, action=action, files=files)
        trace = [f"{self.phase}: wrote into the run crate - {added.summary()} "
                 f"({before} -> {len(store)} entities)"]

        if not added.ok:
            # Not a failed check: a later phase tried to change something an
            # earlier one recorded. That is a disagreement about what happened,
            # and no contract can settle it.
            reasons = ([f"would overwrite {c}" for c in added.conflicts]
                       + [f"two different things share one @id: {c}"
                          for c in added.collisions]
                       + [f"points at nothing: {d}" for d in added.dangling])
            if added.conflicts:
                why = ("this phase would change a value another phase already "
                       "recorded. Fill a gap, yes; overwrite, no.")
            elif added.collisions:
                why = ("this phase wrote one identifier for two different "
                       "things. Merging them would hide whatever caused the "
                       "collision - a shifted deck, a relabelled tube - and "
                       "leave a crate that says they were the same thing.")
            else:
                why = ("this phase wrote a reference to an entity the crate "
                       "does not contain. In one shared crate that is a join "
                       "to nothing, and nothing downstream would notice.")
            return Result(
                status="escalated", outputs={"store": store},
                engine=self.engine.name, errors=reasons,
                notes=trace + [f"ESCALATE: {why}"])

        if added.action:
            trace.append(f"{self.phase}: recorded as {added.action}")

        package = self.package(task, store)
        if package is None or self.sentinel is None:
            return Result(status="ok", outputs={"store": store, "crate": store.crate},
                          engine=self.engine.name, notes=trace)

        # The check the phase submits to. Same validator, same contract, same
        # refusals - the phase agent gets no special treatment for having
        # written the crate itself.
        checked = self.sentinel.handle(Task(
            goal=f"hand over from {self.phase}",
            inputs={"package": package, "run_id": run_id},
            max_repairs=task.max_repairs))

        return Result(
            status=checked.status,
            outputs={"store": store, "crate": store.crate,
                     "package": checked.outputs.get("package", package)},
            engine=checked.engine,
            errors=checked.errors,
            notes=trace + [f"submitted to {self.sentinel.name}"]
                  + [f"  {n}" for n in checked.notes],
        )
