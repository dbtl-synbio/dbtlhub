"""The crate -> knowledge graph agent.

What it is NOT: a graph builder. An RO-Crate is JSON-LD, so the graph is one
parse call away (see framework/kg.py). Writing an agent to do that would be
writing an agent to call rdflib.

What it IS: the vocabulary gate. Three jobs, in order.

    1. align      every local key the lab invented is mapped to a term that
                  resolves, or the handover fails. `freezer_temp: -80` is not
                  metadata, it is a note; `dbtl:storageTemperature` is metadata.
    2. normalise  a bare value with a `unit` beside it becomes the same
                  measurement shape the other three contracts use, so one query
                  spans the whole cycle.
    3. lift       serialise the aligned crate to triples and write them out, so
                  the graph is a file a partner can load without our code.

This is the one place in the framework where a model earns its keep. Everything
else - validation, the provenance walk, the order projection - is deterministic
and should stay that way. Mapping an unknown key onto the right term out of
ENVO, MIxS, OBI, EDAM, PROV-O and Darwin Core is genuinely hard, genuinely
useful, and genuinely checkable afterwards by a human who reads one line.

The proposal is never applied. A proposed term goes into the result for review
and the key stays unaligned, so the handover still fails. That ordering is the
difference between a model helping and a model quietly inventing an ontology.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.base import Agent, Result, Task                  # noqa: E402
from framework.kg import align_crate, lift, write_graph                # noqa: E402
from framework.vocab import load_vocabulary                            # noqa: E402
from framework.ledger import RUNS                                      # noqa: E402
from framework.llm import Engine, RulesEngine                          # noqa: E402


class CrateToGraphAgent(Agent):
    name = "crate_to_graph"
    phase = None
    consumes = ["ro-crate"]
    produces = ["rdf-graph", "aligned-crate"]

    def __init__(self, engine: Engine | None = None, lab: str | None = None):
        self.engine = engine or RulesEngine()
        # Which site's spellings to accept on top of the shared vocabulary. A
        # crate from Newcastle and one from us use different words for the same
        # freezer; both are right locally, and both must end up at the same term.
        self.lab = lab
        self.vocab = load_vocabulary(lab) if lab else load_vocabulary()

    def handle(self, task: Task) -> Result:
        crate = task.inputs["crate"]
        run_id = task.inputs.get("run_id", "adhoc")
        trace: list[str] = []

        # 1 + 2 - alignment and normalisation
        aligned, report = align_crate(crate, self.vocab)
        trace.append(f"vocabulary: {' + '.join(report['vocabulary'])}")
        trace.append(f"aligned {len(report['confirmed'])} key(s) to confirmed terms, "
                     f"{len(report['proposed'])} to proposed terms")
        if report["proposed"]:
            trace.append("  proposed terms, not yet reviewed by a human: "
                         + ", ".join(report["proposed"][:4])
                         + (" ..." if len(report["proposed"]) > 4 else ""))

        proposals: dict = {}
        if report["unaligned"]:
            proposals = self.engine.propose_terms(report["unaligned"], crate,
                                                  self.vocab)
            for key in report["unaligned"]:
                got = proposals.get(key)
                trace.append(f"  UNALIGNED {key!r}: "
                             + (f"engine suggests {got['term']} ({got['why']})"
                                if got else
                                f"engine '{self.engine.name}' has no suggestion"))

        # 3 - lifting. The aligned crate is written out beside the graph: the
        # contract's crate_ref.path must point at a file that exists, or the
        # handover is making a claim it cannot support - which is the exact
        # failure this framework is built to refuse.
        crate_path = RUNS / run_id / "design" / "ro-crate-metadata.json"
        crate_path.parent.mkdir(parents=True, exist_ok=True)
        crate_path.write_text(json.dumps(aligned, indent=1))

        triples = lift(aligned)
        path = write_graph(triples, RUNS / run_id / "graph" / "design.nt")
        trace.append(f"wrote the aligned crate -> {crate_path}")
        trace.append(f"lifted {len(triples)} triples over "
                     f"{len(aligned['@graph'])} entities -> {path}")

        status = "escalated" if report["unaligned"] else "ok"
        return Result(
            status=status,
            outputs={"crate": aligned, "alignment": report,
                     "graph_path": path, "triples": len(triples),
                     "proposals": proposals},
            evidence=[str(crate_path), path],
            errors=[f"no agreed term for key {k!r}" for k in report["unaligned"]],
            engine=self.engine.name,
            notes=trace + ([
                "ESCALATE: a key nobody has mapped is a key nobody can query.",
                f"  Fix: one reviewed line in vocabulary/labs/{self.lab or '<lab>'}.json "
                f"if it is only this site's spelling,",
                "  or a pull request against vocabulary/core.json if it is a new term. "
                "Not a model deciding at run time.",
            ] if report["unaligned"] else []),
        )
