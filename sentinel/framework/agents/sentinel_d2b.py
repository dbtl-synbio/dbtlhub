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
    for node in crate.get("@graph", []):
        if node.get("@id") == "ro-crate-metadata.json":
            refs = node.get("conformsTo")
            got = [r.get("@id") for r in ([refs] if isinstance(refs, dict) else refs or [])
                   if isinstance(r, dict)]
            return got
    # No descriptor node at all. Returning the default here would invent a
    # claim the crate never made, and the schema is right to refuse an empty
    # list: a reader that does not know the profile cannot interpret the crate.
    return []
