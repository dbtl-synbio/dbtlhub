"""5. The crate that grows, and the graph over it.

The Architect holds one crate. Not one per handover, not one per phase: one,
which every phase adds to, and which *is* the knowledge graph. That mechanism
already exists in `framework.crate_store.CrateStore`, so this module does not
reimplement it - it wraps it, and adds the one thing the Architect needs that
the store does not do:

    it can start from a crate that already exists.

That is the requirement that shapes this file. A group with its own RO-Crate is
not going to abandon it in order to be allowed to use this system, so `adopt`
takes somebody else's crate - a dict, or a path to an `ro-crate-metadata.json`,
or to the directory holding one - and the run continues inside it.

Three consequences, which are most of the code below:

  * Adoption is not silent. `adopt` returns a report: how many entities, which
    dialect the crate looks like, whether a profile is declared and where, and
    everything it could not interpret. A reader of somebody else's data who
    says nothing is a reader who has made an assumption on their behalf.

  * An adopted value is as protected as one we wrote. The store's three
    refusals - overwrite, collision, dangling reference - apply to the adopted
    graph from the moment it is adopted, because the adopted crate simply
    *becomes* the store's crate. No separate code path, so no second standard.

  * The adoption itself goes into the crate: where it came from, when, and the
    checksum of what arrived. The source file is never touched; everything is
    written to this run's own directory. If the two ever diverge, the record in
    the crate is what lets somebody find out which one they are holding.

Reading a crate's provenance is `framework.kg.provenance_of`, which already
walks both dialects in use here (PROV properties, schema.org `isBasedOn` /
`isPartOf`, and `CreateAction` object/result walked backwards). `ask` calls it.
There is deliberately no second traversal in this file.

Standard library only, no network, no model.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# `_refs` is the store's own "every @id this value points at". Imported rather
# than rewritten: two slightly different ref-walkers would eventually disagree
# about what counts as a dangling reference, and then the store's refusal and
# this module's report would say different things about the same crate.
from framework.crate_store import Addition, CrateStore, _refs, now   # noqa: E402
from framework.kg import align_crate, crate_checksum, provenance_of  # noqa: E402

RO_CRATE = re.compile(r"https?://w3id\.org/ro/crate/([0-9.]+)")
WORKFLOW_RUN_CONTEXT = "https://w3id.org/ro/terms/workflow-run/context"
CRATE_FILE = "ro-crate-metadata.json"

#: How many offending items a report prints before it says "and N more".
SHOWN = 8


class AdoptionRefused(ValueError):
    """The crate was not adopted, and the memory is unchanged.

    Raised instead of returning a half-adopted state: a Memory that holds some
    of somebody else's crate is worse than one that holds none of it.
    """


# --------------------------------------------------------------------------- #
#  What adoption found
# --------------------------------------------------------------------------- #
@dataclass
class Adoption:
    """The report `adopt` hands back. Every field is an observation, not a fix.

    `dialect` is a guess and says so when it prints: there is no field in a
    crate that states its dialect, only signals - the context URLs, where
    `conformsTo` sits, and which properties are used to say "this came from
    that". The guess is reported so a human can contradict it.
    """
    source: str
    checksum: str                       # of the crate as it arrived
    nodes: int = 0                      # entries in @graph
    entities: int = 0                   # entries with an @id, i.e. addressable
    actions: int = 0                    # CreateActions, the provenance spine
    crate_version: str = "unknown"
    profile: str | None = None
    profile_declared_on: str = "none"   # "root" | "descriptor" | "none"
    provenance: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)
    uninterpreted: list[str] = field(default_factory=list)
    unaligned: list[str] = field(default_factory=list)
    at: str = ""

    @property
    def clean(self) -> bool:
        """Nothing in the crate defeated the reader. Not the same as valid."""
        return not self.uninterpreted

    def dialect(self) -> str:
        bits = [f"RO-Crate {self.crate_version}"]
        if WORKFLOW_RUN_CONTEXT in self.context:
            bits.append("workflow-run context")
        if self.profile:
            # The last two segments, so the version stays visible: "process/0.6"
            # and "process/0.5" are different instructions for a reader.
            bits.append(f"profile {'/'.join(self.profile.rstrip('/').split('/')[-2:])}"
                        f" declared on the {self.profile_declared_on}")
        else:
            bits.append("no profile declared")
        return ", ".join(bits)

    def report(self) -> str:
        lines = [
            f"adopted: {self.source}",
            f"  at             {self.at}",
            f"  checksum       {self.checksum}",
            f"  size           {self.entities} entities in {self.nodes} graph "
            f"nodes, {self.actions} CreateAction(s)",
            f"  looks like     {self.dialect()}",
            f"  provenance     {', '.join(self.provenance) or 'NONE FOUND'}",
        ]
        for label, items in (("uninterpreted", self.uninterpreted),
                             ("unaligned keys", self.unaligned)):
            lines.append(f"  {label:<14} {len(items) or 'none'}")
            for item in items[:SHOWN]:
                lines.append(f"      - {item}")
            if len(items) > SHOWN:
                lines.append(f"      ... and {len(items) - SHOWN} more")
        return "\n".join(lines)

    def __str__(self) -> str:                                  # print(adoption)
        return self.report()


# --------------------------------------------------------------------------- #
#  Reading somebody else's crate
# --------------------------------------------------------------------------- #
def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(node: dict) -> list[str]:
    return [t for t in _as_list(node.get("@type")) if isinstance(t, str)]


def _survey(crate: dict, source: str) -> tuple[Adoption, str | None]:
    """Describe a crate without changing it. Returns (report, root id or None).

    The root id is returned because it is not guaranteed to be `./`, and three
    things downstream need it: the store's `mentions`, the adoption record, and
    the honest statement in the report when there is no root at all.
    """
    found = Adoption(source=source, checksum=crate_checksum(crate), at=now())
    graph = crate.get("@graph")
    if not isinstance(graph, list):
        found.uninterpreted.append("no @graph array: nothing to adopt")
        return found, None

    found.nodes = len(graph)
    found.context = [c for c in _as_list(crate.get("@context")) if isinstance(c, str)]

    index: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for position, node in enumerate(graph):
        if not isinstance(node, dict):
            found.uninterpreted.append(f"@graph[{position}] is not an object")
            continue
        ref = node.get("@id")
        if not isinstance(ref, str) or not ref:
            found.uninterpreted.append(f"@graph[{position}] has no @id "
                                       f"({sorted(node)[:3]}...)")
            continue
        seen[ref] = seen.get(ref, 0) + 1
        index[ref] = node
        if "CreateAction" in _types(node):
            found.actions += 1
    found.entities = len(index)
    for ref, count in seen.items():
        if count > 1:
            # Two nodes under one @id: the index keeps the last and the other
            # disappears. Everything built on this crate would then be built on
            # a graph quietly missing a node.
            found.uninterpreted.append(f"duplicate @id, {count} nodes: {ref}")

    # The descriptor says which RO-Crate version the file follows; its `about`
    # says which node is the root. The profile - how to read the *content* -
    # belongs on the root. One of our two example crates declares it there and
    # the other declares nothing, which is exactly the case to report.
    descriptor = index.get(CRATE_FILE) or next(
        (n for n in index.values() if "CreativeWork" in _types(n)
         and _refs(n.get("about"))), None)
    root_id = None
    if descriptor is None:
        found.uninterpreted.append(f"no metadata descriptor ({CRATE_FILE})")
    else:
        root_id = next(iter(_refs(descriptor.get("about"))), None)
    if root_id is None and "./" in index:
        root_id = "./"
    if root_id is None or root_id not in index:
        found.uninterpreted.append(
            f"no root dataset{f' for {root_id}' if root_id else ''}: the "
            f"adoption cannot be recorded on the root, only in the graph")
        root_id = root_id if root_id in index else None

    for where, node in (("descriptor", descriptor), ("root", index.get(root_id or ""))):
        for ref in _refs((node or {}).get("conformsTo")):
            version = RO_CRATE.match(ref)
            if version:
                found.crate_version = version.group(1)
            elif found.profile is None:
                found.profile, found.profile_declared_on = ref, where
    if found.crate_version == "unknown":
        for ref in found.context:
            version = RO_CRATE.match(ref)
            if version:
                found.crate_version = version.group(1)

    # Which way does this crate say "came from"? Reported because it decides
    # whether `ask` will find anything: a crate with none of these is a bag of
    # entities, not a provenance graph, and that is worth knowing on arrival.
    props = {key for node in index.values() for key in node}
    if any(key.startswith("prov:") for key in props):
        found.provenance.append("PROV properties")
    if props & {"isBasedOn", "isPartOf"}:
        found.provenance.append("schema.org isBasedOn/isPartOf")
    if found.actions and props & {"object", "result"}:
        found.provenance.append("CreateAction object/result")

    # Every @id pointed at must exist. The store refuses to *add* a dangling
    # reference; one that arrived with an adopted crate is not refused, because
    # refusing would just mean refusing the crate - but it is reported, since a
    # hole in the graph is silent otherwise: each entity still validates.
    for node in index.values():
        for key, value in node.items():
            if key in ("@id", "@type", "@context"):
                continue
            for ref in _refs(value):
                if ref not in index and not ref.startswith(("http://", "https://")):
                    found.uninterpreted.append(
                        f"dangling reference: {node['@id']}.{key} -> {ref}")

    # Alignment is run for the report and the result is thrown away. Storing the
    # aligned crate would rewrite somebody else's keys on adoption, which is the
    # one thing this module must not do; `unaligned` is the honest half of it:
    # the keys no vocabulary file has a decision for.
    _, alignment = align_crate(json.loads(json.dumps(crate)))
    found.unaligned = alignment["unaligned"]
    return found, root_id


def _load(crate: dict | str | Path) -> tuple[dict, str]:
    """A dict, a path to the metadata file, or a path to the crate directory.

    The contract says `dict | str`; a `Path` is accepted here too, because a
    caller who already has one should not have to stringify it to be understood.
    """
    if isinstance(crate, dict):
        # Copied: the caller keeps their dict, and a later `record` must not
        # reach back into an object somebody else still holds a reference to.
        return json.loads(json.dumps(crate)), "<dict handed over in memory>"
    path = Path(crate).expanduser().resolve()
    if path.is_dir():
        path = path / CRATE_FILE
    if not path.exists():
        raise AdoptionRefused(f"no crate at {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as broken:
        raise AdoptionRefused(f"{path} is not JSON: {broken}") from broken
    if not isinstance(data, dict):
        raise AdoptionRefused(f"{path} is JSON but not a crate (got {type(data).__name__})")
    return data, str(path)


# --------------------------------------------------------------------------- #
#  The Memory
# --------------------------------------------------------------------------- #
class Memory:
    """Implements `architect.contract.Memory`.

    One crate, held by a `CrateStore` in this run's own directory, whether it
    was created here or adopted. Read-only against the source: nothing is ever
    written back to the file an adopted crate came from.
    """

    def __init__(self, run_id: str, root: Path | str | None = None):
        self.run_id = run_id
        self.store = CrateStore(run_id, Path(root) if root else None)
        self.history: list[Addition] = []
        self.adoption: Adoption | None = None
        self._baseline: str | None = None   # checksum once adoption was recorded

    # ---- 1. starting from somebody else's crate ---------------------------
    def adopt(self, crate: dict | str) -> Adoption:
        """Take an existing crate as the starting point, and say what arrived.

        The contract annotates this `-> None`. It returns the report anyway: a
        caller that ignores the value gets exactly the contract's behaviour,
        and a caller that does not is the reason the method exists. Adopting
        somebody's data and saying nothing about it is how a wrong assumption
        travels - by the time it is noticed, it is in the graph.
        """
        if self.adoption is not None:
            raise AdoptionRefused(
                f"{self.run_id} already adopted {self.adoption.source}. One "
                f"memory holds one crate; adopting again would discard it.")
        if self.history:
            raise AdoptionRefused(
                f"{self.run_id} has already recorded {len(self.history)} "
                f"addition(s). Adopt before recording, or start a new memory: "
                f"adopting now would drop what this run produced.")
        if self.store.path.exists():
            # The store opened a crate that was already on disk. Replacing it
            # with an adopted one is the overwrite the store exists to refuse.
            raise AdoptionRefused(
                f"{self.store.path} already holds a crate for this run. Use a "
                f"fresh run id rather than adopting over it.")

        data, source = _load(crate)
        found, root_id = _survey(data, source)
        if found.entities == 0:
            raise AdoptionRefused(f"{source}: no addressable entities "
                                  f"(@graph has {found.nodes} nodes). "
                                  f"Nothing to continue from.")

        # The store addresses the root dataset as `./`, which is what RO-Crate
        # 1.1 and 1.3 require of a crate stored as a directory. A crate rooted
        # at anything else is still adopted, but the adoption goes in as a plain
        # entity rather than through `action=`, which would reach for `./` and
        # fail - and the report says so first, because an adoption that is not
        # reachable from the root is harder to find later.
        attachable = root_id == "./"
        if not attachable:
            found.uninterpreted.append(
                f"root is {root_id or 'absent'}, not './': the adoption is "
                f"recorded in the graph but not listed under the root's mentions")

        before = self.store.crate
        self.store.crate = data          # it *is* the store's crate from here
        record, parts = self._adoption_record(found, root_id)
        addition = self.store.add("adopt", parts if attachable else [*parts, record],
                                  action=record if attachable else None)
        if not addition.ok:
            self.store.crate = before    # as if adopt had never been called
            raise AdoptionRefused(
                f"{source}: the adoption record was refused "
                f"({addition.summary()}). The crate was not adopted.")

        self.history.append(addition)
        self.adoption = found
        self._baseline = self.store.checksum()
        return found

    def _adoption_record(self, found: Adoption, root_id: str | None
                         ) -> tuple[dict, list[dict]]:
        """The adoption, written into the crate as a CreateAction.

        In the crate rather than in a side file, because a side file is the
        thing that gets lost. What it must survive to say: this crate came from
        somewhere else, on this date, and this is what it hashed to then - so
        anybody holding two copies can tell which one has moved.
        """
        taken = {e["@id"] for e in self.store.crate["@graph"]
                 if isinstance(e, dict) and isinstance(e.get("@id"), str)}
        n = 1
        while f"#adoption/{n}" in taken:
            n += 1
        rid, tool = f"#adoption/{n}", "#architect/memory"

        values = [("adopted_from", found.source), ("checksum_at_adoption", found.checksum),
                  ("entities_at_adoption", found.entities),
                  ("dialect_as_read", found.dialect()),
                  ("could_not_interpret", len(found.uninterpreted))]
        properties = [{"@id": f"{rid}/{slug}", "@type": "PropertyValue",
                       "name": slug, "value": value}
                      for slug, value in values]
        parts = [{"@id": tool, "@type": "SoftwareApplication",
                  "name": "architect.memory",
                  "description": "The Architect's memory: one crate that grows, "
                                 "created here or adopted."}] + properties
        record = {"@id": rid, "@type": "CreateAction",
                  "name": "crate adopted by the Architect",
                  "endTime": found.at, "actionStatus": "CompletedActionStatus",
                  "instrument": {"@id": tool},
                  "additionalProperty": [{"@id": p["@id"]} for p in properties]}
        if root_id:
            record["object"] = {"@id": root_id}
        return record, parts

    # ---- 2. adding to it ---------------------------------------------------
    def record(self, phase: str, entities: list[dict],
               action: dict | None = None) -> Addition:
        """One phase's entities and the action that made them.

        Straight to the store, which is where the three refusals live. The
        return value is the store's own report, so a caller can see that the
        addition was refused - and an adopted entity is defended by the same
        code as one this system wrote, because there is only the one path.
        """
        addition = self.store.add(phase, entities, action=action)
        self.history.append(addition)
        return addition

    # ---- 3. handing it on --------------------------------------------------
    def snapshot(self) -> dict:
        """The crate as it stands, ready for a phase agent or for disk.

        A deep copy. A phase agent is handed this to read, and agents edit what
        they are handed; if that edit landed in the live crate it would bypass
        every refusal in the store, which is the only thing keeping the record
        honest. The crate on disk is kept current by the store itself, in
        `self.store.path`, with the graph beside it in `self.store.graph_path`.
        """
        return json.loads(json.dumps(self.store.crate))

    def write(self, path: str | Path) -> Path:
        """A copy of the crate somewhere else, for export. Never the source."""
        path = Path(path)
        if self.adoption and str(path.resolve()) == self.adoption.source:
            raise AdoptionRefused(f"{path} is where this crate was adopted from. "
                                  f"An adopted crate is not written back.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.store.crate, indent=1) + "\n")
        return path

    # ---- 4. asking it ------------------------------------------------------
    def ask(self, entity: str) -> list[dict]:
        """Walk back from one thing to where it came from, nearest first.

        `kg.provenance_of` does the walking, in both dialects our two real
        crates use. Here the only addition is to refuse an id that is not in
        the crate: an unknown id and an entity with no recorded origin would
        both come back as an empty list, and those are very different answers.
        """
        if entity not in self.store.index:
            raise KeyError(f"{entity} is not in this crate "
                           f"({len(self.store.index)} entities). Nothing to "
                           f"walk back from; check the @id.")
        return provenance_of(self.store.crate, entity)

    def produced(self) -> list[str]:
        """Ids some CreateAction claims as a result - the things with a maker.

        The useful starting points for `ask`, and the honest way to pick an
        entity out of a crate nobody here wrote.
        """
        out: list[str] = []
        for node in self.store.crate.get("@graph", []):
            if isinstance(node, dict) and "CreateAction" in _types(node):
                out.extend(ref for ref in _refs(node.get("result")) if ref not in out)
        return out

    # ---- 5. has it moved since it was adopted? -----------------------------
    def changed_since_adoption(self) -> bool:
        """True once anything has been added after the adoption was recorded.

        Measured from the checksum taken *after* the adoption record went in,
        not from the one in the record: the record itself changes the crate, so
        comparing against it would report drift for every adopted crate always,
        which is a warning nobody reads twice.
        """
        return bool(self._baseline) and self.store.checksum() != self._baseline

    def __len__(self) -> int:
        return len(self.store.crate.get("@graph", []))

    def __repr__(self) -> str:
        origin = self.adoption.source if self.adoption else "created here"
        return f"<Memory {self.run_id}: {len(self)} nodes, {origin}>"


# --------------------------------------------------------------------------- #
#  Run it: a fresh crate, then the two real ones if they are on this machine
# --------------------------------------------------------------------------- #
REAL_CRATES = [
    Path("/Users/marcoanteghini/Research/dbtlhub/bioprospecting/exampleROcrates/"
         "design-to-build-simple/ro-crate-metadata.json"),
    Path("/Users/marcoanteghini/Research/dbtlhub/biomanufacturing/examples/"
         "ro-crate-metadata.json"),
]


def _demo() -> None:
    import hashlib
    import tempfile

    runs = Path(tempfile.mkdtemp(prefix="architect-memory-"))
    print(f"writing to {runs}\n")

    print("=== 1. a crate created here ===")
    fresh = Memory("demo-fresh", root=runs)
    first = fresh.record(
        "design",
        [{"@id": "#protein/ENR-001", "@type": "BioChemEntity",
          "name": "candidate esterase", "description": "SIMULATED"}],
        action={"@id": "#action/panel-selection", "name": "panel selection",
                "result": [{"@id": "#protein/ENR-001"}]})
    print(f"record design: {first.summary()}  ->  {fresh!r}")
    clash = fresh.record("build", [{"@id": "#protein/ENR-001", "name": "renamed"}])
    print(f"renaming it from Build: {clash.summary()} {clash.conflicts} "
          f"(refused, crate unchanged)")
    print(f"provenance of #protein/ENR-001: "
          f"{[step['id'] for step in fresh.ask('#protein/ENR-001')]}\n")

    for n, path in enumerate(REAL_CRATES, start=2):
        print(f"=== {n}. {path.parent.name}/{path.name} ===")
        if not path.exists():
            print("not on this machine, skipped\n")
            continue
        before = hashlib.sha256(path.read_bytes()).hexdigest()

        memory = Memory(f"demo-adopted-{n}", root=runs)
        print(memory.adopt(str(path)).report())

        # The claim that matters: an adopted value is defended like our own.
        made = memory.produced()
        target = next((ref for ref in made if len(memory.ask(ref)) > 1), made[0])
        chain = memory.ask(target)
        print(f"  ask({target}) -> {len(chain)} steps")
        for step in chain[:6]:
            print(f"      {step['id']}  [{step['type']}]  {step['name'][:48]}")
        if len(chain) > 6:
            print(f"      ... and {len(chain) - 6} more")
        refused = memory.record("build", [{"@id": target, "name": "renamed by Build"}])
        print(f"  renaming an adopted entity: {refused.summary()} "
              f"{refused.conflicts} (refused)")
        print(f"  source file untouched: "
              f"{hashlib.sha256(path.read_bytes()).hexdigest() == before}")
        print(f"  our copy: {memory.store.path}")
        print(f"  graph:    {memory.store.graph_path}\n")


if __name__ == "__main__":
    _demo()
