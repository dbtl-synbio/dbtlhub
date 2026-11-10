"""The run ledger: an append-only record of every step.

It is three things at once:
  - the provenance of a run,
  - the artefact to show on Friday,
  - and the model comparison, for free - every entry records the engine used,
    so "how often did the small model need a repair" is a query, not an experiment.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.dir = RUNS / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "ledger.jsonl"

    def record(self, *, step: str, agent: str, engine: str = "none",
               status: str = "ok", **extra) -> dict:
        entry = {"at": now(), "run_id": self.run_id, "step": step, "agent": agent,
                 "engine": engine, "status": status, **extra}
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
        return entry

    def write_package(self, name: str, package: dict) -> str:
        """Store a handover package on disk and return its relative path.

        Packages go to disk on purpose: two teams can hand work over as files,
        without running each other's code.
        """
        out = self.dir / name
        out.mkdir(parents=True, exist_ok=True)
        path = out / "handover.json"
        path.write_text(json.dumps(package, indent=1))
        return str(path.relative_to(RUNS.parent))

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
