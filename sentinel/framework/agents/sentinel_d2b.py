"""The Design -> Build sentinel agent.

The handover with two audiences. The synthesis provider gets a flat list of
sequences and wells - that is all they need, and all we are willing to send. We
keep the crate, which says where every one of those sequences came from, down to
the freezer the sediment core is sitting in.

`translate` therefore does something the other handovers do not: it *projects*.
Projection is where traceability is normally lost, because the order is the thing
everyone needs tomorrow and the crate is the thing someone needs in two years.
So the contract refuses to accept the projection unless the thing projected from
is present, aligned, and connected: every order line must bind to a crate entity
whose chain of derivation reaches a physical sample.

Almost nothing here is auto-fixable, and that is a finding rather than a
limitation. A missing provenance step cannot be guessed without inventing the
origin of a sequence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Task                                 # noqa: E402
from framework.agents.crate_to_graph import CrateToGraphAgent          # noqa: E402
from framework.agents.sentinel_base import SentinelAgent                 # noqa: E402
from framework.ledger import now                                       # noqa: E402
from usecases.bioprospecting.sampling import order_from_crate          # noqa: E402

NEVER_AUTOFIX = {
    "broken_provenance_chain",   # inventing a step would fabricate an origin
    "missing_provenance",        # the context was never recorded; it cannot be recovered
    "unaligned_key",             # a term is a decision, and a human takes it once
    "double_booked_position",    # the provider would synthesise one and drop the other
    "duplicate_order_item",
    "unbound_order_item",
    "missing_crate_entity",
}

CONFORMS_TO = ["https://w3id.org/ro/crate/1.1",
               "https://w3id.org/ro/wfrun/process/0.5"]


class DesignToBuildAgent(SentinelAgent):
    name = "sentinel_d2b"
    contract_name = "design_to_build"
    never_autofix = NEVER_AUTOFIX

    def __init__(self, profile="bioprospecting", engine=None, lab: str | None = None,
                 kg_agent: CrateToGraphAgent | None = None):
        super().__init__(profile=profile, engine=engine)
        self.kg = kg_agent or CrateToGraphAgent(engine=self.engine, lab=lab)

    def translate(self, task: Task) -> tuple[dict, list[str]]:
        # New arrangement: the Design phase agent wrote the run's one crate and
        # packaged the handover itself, so there is nothing to project here and
        # the sentinel's job is only to check. Older callers still hand a crate
        # and a list of items, and that path is unchanged below.
        if task.inputs.get("package") is not None:
            return task.inputs["package"], [
                "package supplied by the phase agent; no projection needed"]

        crate = task.inputs["crate"]
        items = task.inputs["items"]
        run_id = task.inputs.get("run_id", "adhoc")

        # The crate goes through the vocabulary gate before anything is checked.
        # Validating an unaligned crate would be checking a document nobody can
        # query - it would pass on structure and be useless in practice.
        kg = self.kg.handle(Task(goal="lift the design crate to a graph",
                                 inputs={"crate": crate, "run_id": run_id}))
        trace = [f"delegated to {self.kg.name}: {note}" for note in kg.notes]

        aligned = kg.outputs["crate"]
        package = {
            "contract": "design_to_build",
            "contract_version": "0.1.0",
            "profile": self.profile,
            "run_id": run_id,
            "produced_by": {"agent": self.name, "tool": "design pipeline",
                            "engine": self.engine.name},
            "produced_at": now(),
            "crate_ref": {
                "path": f"runs/{run_id}/design/ro-crate-metadata.json",
                "conforms_to": _conforms_to(aligned),
                "root": "./",
                # checksum deliberately left out: it is derivable, so it is the
                # one thing the repair step is allowed to supply.
            },
            # A relative @id in RO-Crate is a promise that the file is there.
            # No profile validator checks it, so the handover does.
            "crate_ref_missing_files": list(task.inputs.get("files_missing") or []),
            "crate": aligned,
            "order": order_from_crate(items, container=task.inputs.get(
                "container", "ORDPLATE-1")),
            "bindings": [{"design_item_id": it["design_item_id"],
                          "crate_entity": it["crate_entity"]} for it in items],
            "alignment": kg.outputs["alignment"],
        }
        if task.inputs.get("target_list"):
            package["target_list"] = task.inputs["target_list"]

        trace.append(f"projected {len(package['order']['items'])} order line(s) from "
                     f"{len(aligned['@graph'])} crate entities; "
                     f"{len(package['bindings'])} binding(s) keep the two joined")
        return package, trace

    def provider_view(self, package: dict) -> dict:
        """Exactly what is sent out, and nothing else.

        Worth having as a method rather than a comment: it makes "what did we
        disclose?" answerable, which is a question with legal weight once the
        material came out of the ground somewhere.
        """
        return {
            "provider": package["order"]["provider"],
            "format": package["order"]["format"],
            "container_id": package["order"]["container_id"],
            "items": [{k: v for k, v in item.items()
                       if k in ("order_item_id", "position", "sequence_type",
                                "length_bp", "sequence_sha256")}
                      for item in package["order"]["items"]],
        }


def _conforms_to(crate: dict) -> list[str]:
    """Every profile the crate claims, from both places RO-Crate puts them.

    The metadata descriptor says which version of RO-Crate the *file* follows.
    The root dataset - the entity the descriptor is `about` - says which
    profile the *content* follows, such as Process Run Crate 0.6. Reading only
    the first gets you "ro/crate/1.3" and silently loses the statement that
    tells a reader how to interpret the crate at all.

    A crate may claim several. Process, Workflow and Provenance Run Crate each
    include the rules of the one before, and a crate lists all it follows.

    No claim anywhere returns an empty list rather than a default: inventing a
    conformance claim the crate never made is the thing this framework exists
    to prevent, and the schema is right to refuse the result.
    """
    index = {e.get("@id"): e for e in crate.get("@graph", []) if isinstance(e, dict)}
    descriptor = index.get("ro-crate-metadata.json", {})
    about = descriptor.get("about")
    root_id = about.get("@id") if isinstance(about, dict) else "./"
    out: list[str] = []
    for node in (descriptor, index.get(root_id, {})):
        refs = node.get("conformsTo")
        refs = [refs] if isinstance(refs, dict) else (refs or [])
        for ref in refs:
            got = ref.get("@id") if isinstance(ref, dict) else ref
            if got and got not in out:
                out.append(got)
    return out
