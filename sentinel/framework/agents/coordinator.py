"""The coordinator.

It decomposes the goal into a route through the phases, calls one agent at a
time, records every step in the ledger, and decides what happens when a handover
is escalated. It also owns the Learn -> Design closure: deciding whether to
iterate is coordination, not a handover.

It knows nothing about plates, enzymes or mass spectrometry - only contracts.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Result, Task                 # noqa: E402
from framework.ledger import Ledger                            # noqa: E402


class Coordinator:
    name = "coordinator"

    def __init__(self, run_id: str, *, stop_on_escalation: bool = True):
        self.ledger = Ledger(run_id)
        self.run_id = run_id
        self.stop_on_escalation = stop_on_escalation
        self.escalations: list[tuple[str, Result]] = []
        # Where each package was actually written. The next phase's backlink is
        # filled from this rather than guessed, because a guessed path is a
        # chain that looks right and resolves to nothing.
        self.stored: dict[str, str] = {}

    def step(self, agent, task: Task, *, label: str, store_as: str | None = None) -> Result:
        """Run one agent, record it, store its package if it produced one."""
        result = agent.handle(task)

        stored = None
        package = result.outputs.get("package")
        if store_as and package:
            stored = self.ledger.write_package(store_as, package)
            self.stored[store_as] = stored
            # The run's graph grows with the run. Each handover adds the spine
            # - what it is, what made it, what it was built from, and one node
            # per thing it carries - so by the end of the cycle the whole
            # thing is one graph and not four files joined by hand.
            from framework.kg import append_graph, lift_package
            # Its own file. runs/<id>/graph/run.nt belongs to the crate store,
            # which rewrites it from the crate on every addition - appending
            # here as well meant these triples were written and then silently
            # clobbered. Two writers, one file, and the loser was invisible.
            append_graph(lift_package(package, stored),
                         self.ledger.dir / "graph" / "handovers.nt")

        self.ledger.record(
            step=label, agent=agent.name, engine=result.engine, status=result.status,
            package=stored, errors=result.errors, notes=result.notes,
        )

        if result.status == "escalated":
            self.escalations.append((label, result))
        return result

    def path_of(self, store_as: str) -> str:
        """Where a package this run already stored actually lives."""
        try:
            return self.stored[store_as]
        except KeyError:
            raise KeyError(
                f"no package stored as {store_as!r} in run {self.run_id}. A "
                f"backlink must point at something this run really wrote.") from None

    def should_continue(self, result: Result) -> bool:
        """An escalated handover stops the route by default.

        Carrying a package the validator rejected into the next phase is how a
        bad number ends up in a conclusion. Set stop_on_escalation=False only to
        demonstrate what that costs.
        """
        if result.status == "ok":
            return True
        return not self.stop_on_escalation

    def summary(self) -> dict:
        entries = self.ledger.entries()
        return {
            "run_id": self.run_id,
            "steps": len(entries),
            "escalated": [label for label, _ in self.escalations],
            "engines_used": sorted({e["engine"] for e in entries}),
            "ledger": str(self.ledger.path),
        }
