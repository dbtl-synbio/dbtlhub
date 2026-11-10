"""One crate per run, that grows.

The earlier arrangement gave each handover its own package and its own crate,
joined by backlinks. It worked, and checking that the backlinks resolved was a
job in itself. This is the other arrangement, and it is simpler: there is one
crate for the whole run, every phase adds its own part to it, and that crate
*is* the knowledge graph. Nothing has to be joined afterwards because nothing
was ever separate.

What a phase adds:

    entities   the things it made - proteins, constructs, samples, readings
    an action  one CreateAction recording the run that made them, with the
               instrument, the time, and what it consumed and produced

The store is append-only in intent. An entity may be *extended* by a later
phase - Build adds a well position to a construct Design described - but a
value already written is never silently replaced: `add` reports what it
changed, and a conflict is returned rather than applied, because overwriting a
recorded value is how a laboratory record quietly becomes wrong.

Every addition also goes straight into `graph/run.nt`, so the graph and the
crate never drift: they are written in the same call.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

CONTEXT = ["https://w3id.org/ro/crate/1.1/context",
           "https://w3id.org/ro/terms/workflow-run/context"]
PROFILE = "https://w3id.org/ro/wfrun/process/0.6"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Addition:
    """What one phase actually changed, so the trace can say so."""
    added: list[str] = field(default_factory=list)
    extended: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    dangling: list[str] = field(default_factory=list)
    action: str = ""

    @property
    def ok(self) -> bool:
        return not self.conflicts and not self.dangling

    def summary(self) -> str:
        parts = [f"{len(self.added)} new"]
        if self.extended:
            parts.append(f"{len(self.extended)} extended")
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} CONFLICT")
        if self.dangling:
            parts.append(f"{len(self.dangling)} DANGLING")
        return ", ".join(parts)


def _refs(value) -> list[str]:
    """Every @id a property value points at."""
    if isinstance(value, dict):
        return [value["@id"]] if "@id" in value else []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_refs(item))
        return out
    return []


class CrateStore:
    """The run's single crate, on disk, opened or created."""

    def __init__(self, run_id: str, root: Path | None = None):
        self.run_id = run_id
        self.dir = (root or RUNS) / run_id / "crate"
        self.path = self.dir / "ro-crate-metadata.json"
        self.graph_path = (root or RUNS) / run_id / "graph" / "run.nt"
        self.crate = self._open()

    # ---- the crate itself --------------------------------------------------
    def _open(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "@context": list(CONTEXT),
            "@graph": [
                {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
                 "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                 "about": {"@id": "./"}},
                # The profile is declared on the ROOT, not on the descriptor:
                # the descriptor says which version of RO-Crate the file
                # follows, the root says how to read the content.
                {"@id": "./", "@type": "Dataset",
                 "name": f"DBTL run {self.run_id}",
                 "description": "One crate for the whole cycle. Each phase adds "
                                "its own entities and the action that made them. "
                                "SIMULATED unless stated otherwise.",
                 "datePublished": now(),
                 "conformsTo": {"@id": PROFILE},
                 "mentions": [], "hasPart": []},
            ],
        }

    @property
    def index(self) -> dict:
        return {e["@id"]: e for e in self.crate["@graph"]
                if isinstance(e, dict) and "@id" in e}

    @property
    def root(self) -> dict:
        return self.index["./"]

    # ---- adding ------------------------------------------------------------
    def add(self, phase: str, entities: list[dict], *, action: dict | None = None,
            files: list[str] | None = None) -> Addition:
        """Add one phase's entities, and the action that produced them."""
        report = Addition()
        index = self.index

        for entity in entities:
            ref = entity.get("@id")
            if not ref:
                continue
            existing = index.get(ref)
            if existing is None:
                self.crate["@graph"].append(dict(entity))
                index[ref] = self.crate["@graph"][-1]
                report.added.append(ref)
                continue
            # Already there. Fill gaps, never overwrite: a later phase may know
            # more about a construct than Design did, but it does not get to
            # change what Design recorded.
            changed = False
            for key, value in entity.items():
                if key in ("@id",):
                    continue
                if key not in existing or existing[key] in (None, "", [], {}):
                    existing[key] = value
                    changed = True
                elif existing[key] != value:
                    report.conflicts.append(f"{ref}.{key}")
            if changed:
                report.extended.append(ref)

        if action:
            action = dict(action)
            action.setdefault("@type", "CreateAction")
            action.setdefault("endTime", now())
            ref = action.setdefault("@id", f"#action/{phase}-{len(self.crate['@graph'])}")
            if ref not in index:
                self.crate["@graph"].append(action)
            mentions = self.root.setdefault("mentions", [])
            if {"@id": ref} not in mentions:
                mentions.append({"@id": ref})
            report.action = ref

        for part in (files or []):
            parts = self.root.setdefault("hasPart", [])
            if {"@id": part} not in parts:
                parts.append({"@id": part})

        # Every @id this addition points at must be in the crate. In a crate
        # that grows, a reference to something that does not exist yet is not
        # a forward declaration - it is a sequence joined to nothing, and it
        # is silent: the entity validates, the graph just has a hole in it.
        index = self.index
        for entity in entities:
            for key, value in entity.items():
                if key in ("@id", "@type"):
                    continue
                for ref in _refs(value):
                    if ref not in index and not ref.startswith(("http://", "https://")):
                        report.dangling.append(f"{entity.get('@id')}.{key} -> {ref}")
        for value in (action or {}).values():
            for ref in _refs(value):
                if ref not in index and not ref.startswith(("http://", "https://")):
                    report.dangling.append(f"{report.action or 'action'} -> {ref}")

        if report.ok:
            self._write()
            self._append_graph()
        return report

    # ---- persistence -------------------------------------------------------
    def _write(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.crate, indent=1) + "\n")

    def _append_graph(self) -> None:
        """Rewrite the graph from the crate.

        Rewritten rather than appended: an extended entity would otherwise
        leave both its old and its new statement in the file, and a graph that
        holds two answers to the same question is worse than no graph.
        """
        from framework.kg import lift, to_ntriples
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_text(to_ntriples(lift(self.crate)))

    def checksum(self) -> str:
        from framework.kg import crate_checksum
        return crate_checksum(self.crate)

    def entities_of(self, kind: str) -> list[dict]:
        return [e for e in self.crate["@graph"]
                if isinstance(e, dict)
                and kind in ([e.get("@type")] if isinstance(e.get("@type"), str)
                             else (e.get("@type") or []))]

    def __len__(self) -> int:
        return len(self.crate["@graph"])
