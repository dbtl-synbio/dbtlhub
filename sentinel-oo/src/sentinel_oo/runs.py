"""What the service still holds from recent runs.

Bounded on purpose. The durable record of a run is written into the crate that
was returned, and that crate has gone to whoever asked. What is kept here is
for looking at a run again shortly afterwards, while somebody is still working
on it, and nothing more depends on it.

Bounded by a count rather than by a clock, so that no decision in this service
depends on what time it is. A run either is still held or is not, and a service
restarted at any moment behaves the same way.
"""

from __future__ import annotations

from collections import OrderedDict


class RunStore:
    """The last N runs. The oldest is dropped when the next arrives."""

    def __init__(self, limit: int = 20):
        if limit < 0:
            raise ValueError("a run store cannot hold fewer than no runs")
        self.limit = limit
        self._runs: OrderedDict = OrderedDict()

    def put(self, run) -> None:
        if self.limit == 0:
            return
        self._runs[run.id] = run
        self._runs.move_to_end(run.id)
        while len(self._runs) > self.limit:
            self._runs.popitem(last=False)

    def get(self, run_id: str):
        """The run, or None. A run that has fallen out is gone, not an error:
        the caller asked a reasonable question and the answer is no."""
        return self._runs.get(run_id)

    def list(self) -> list[str]:
        """Newest first, which is the order somebody debugging wants."""
        return list(reversed(self._runs))

    def __len__(self) -> int:
        return len(self._runs)
