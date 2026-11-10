#!/usr/bin/env python3
"""Export our Handover 1 work into the folder layout Anil pushed to dbtlhub.

    python3 scripts/export_for_dbtlhub.py

Writes `export/bioprospecting/` with the same names as `dbtl-synbio/dbtlhub`:

    agents/handover1_construct_spec/      the checking agent
    exampleROcrates/handover1_construct_spec/
        good/ro-crate-metadata.json       satisfies the contract
        broken/ro-crate-metadata.json     fails it, on purpose, in three ways

That is exactly what his exampleROcrates/README.md asks each handover to
provide: "one crate that satisfies its contract and one deliberately broken
crate, so that the checking agents have something to pass and something to fail
against". Ours already exist - this just gives them his names.

Nothing is pushed anywhere. The folder is a thing to attach, zip, or open a pull
request from, whichever the room prefers.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.agents.base import Task                      # noqa: E402
from framework.agents.sentinel_d2b import DesignToBuildAgent    # noqa: E402
from framework.agents.phase_design import DesignAgent        # noqa: E402
from framework.validator import load_contract, validate      # noqa: E402

OUT = ROOT / "export" / "bioprospecting"
SLOT = "handover1_construct_spec"
FAULTS = {"missing_geo", "orphan_fasta", "unaligned_key"}


def build(run_id: str, faults=None):
    design = DesignAgent().handle(Task(goal="panel", inputs={"n": 6, "faults": faults}))
    agent = DesignToBuildAgent(profile="bioprospecting", lab="newcastle")
    result = agent.handle(Task(
        goal="hand over to Build",
        inputs={"crate": design.outputs["crate"], "items": design.outputs["items"],
                "run_id": run_id},
        max_repairs=2))
    return agent, result


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)

    crates = OUT / "exampleROcrates" / SLOT
    report_lines = []

    for label, faults in (("good", None), ("broken", FAULTS)):
        agent, result = build(f"export-{label}", faults)
        package = result.outputs["package"]
        d = crates / label
        d.mkdir(parents=True, exist_ok=True)
        (d / "ro-crate-metadata.json").write_text(
            json.dumps(package["crate"], indent=1) + "\n")
        # The order and the bindings are the contract-level view of the same
        # handover; without them the crate is a graph nobody can join to a plate.
        (d / "handover.json").write_text(json.dumps(
            {k: v for k, v in package.items() if k != "crate"}, indent=1) + "\n")

        report = validate(package, load_contract("design_to_build",
                                                 profile="bioprospecting"))
        verdict = "PASSES the contract" if report.ok else \
                  f"FAILS the contract, {len(report.errors)} error(s)"
        report_lines.append(f"### `{label}/` — {verdict}\n")
        if not report.ok:
            report_lines.append("```")
            report_lines.extend(f"{e.code:<26} {e.message}" for e in report.errors)
            report_lines.append("```\n")
        print(f"{label:<7} {verdict}")

    (crates / "README.md").write_text(README_CRATES.format(
        results="\n".join(report_lines)))

    agents_dir = OUT / "agents" / SLOT
    agents_dir.mkdir(parents=True, exist_ok=True)
    for src in ("framework/agents/sentinel_base.py", "framework/agents/sentinel_d2b.py",
                "framework/agents/crate_to_graph.py", "framework/validator.py",
                "framework/kg.py", "framework/vocab.py", "framework/llm.py",
                "framework/contracts/design_to_build.schema.json",
                "framework/contracts/profiles/bioprospecting.json",
                "framework/contracts/shapes/design_to_build.shacl.ttl"):
        dst = agents_dir / Path(src).name
        dst.write_text((ROOT / src).read_text())
    (agents_dir / "README.md").write_text(README_AGENT)

    print(f"\nwrote {OUT}")
    print("nothing was pushed; attach it, zip it, or open a pull request from it")


README_CRATES = """# Handover 1 — construct specification

Two example crates for the Design → Build handover, as
`exampleROcrates/README.md` asks: one that satisfies the contract and one
deliberately broken, so a checking agent has something to pass and something to
fail against.

Each folder holds:

- `ro-crate-metadata.json` — the crate, with local keys already aligned to terms
  (`dwc:`, `envo:`, `mixs:`, `prov:`, `qudt:`). Alignment runs **before**
  checking: validating a crate full of invented keys would pass on structure and
  be useless in practice.
- `handover.json` — the contract-level view: the order that goes to the synthesis
  vendor, and the bindings that join each order line to the crate entity it was
  projected from. Without the bindings the two documents describe the same thing
  with no way to join them.

## What the broken crate gets wrong

| fault | what happened in the lab |
|---|---|
| `missing_geo` | the field form came back without coordinates |
| `orphan_fasta` | a sequence appears with no link to what produced it |
| `unaligned_key` | a technician wrote `box_temp_c` for the freezer temperature |

## Result of checking both

{results}
Reproduce with `python3 demo_d2b.py` in the source repo.
"""

README_AGENT = """# Handover 1 — the checking agent

A checking agent for the Design → Build handover, in the sense
`agents/README.md` means it: it reads the RO-Crate produced at the end of
Design and decides whether Build can accept it.

It checks **shape** and **semantics** separately, because they fail differently.

## Shape

`design_to_build.schema.json` (JSON Schema) over the contract-level view: the
order going to the vendor, the crate reference, the bindings between them. A
document, checked as a document.

## Semantics

Three things a JSON Schema cannot express, so they live in the contract's
`x-dbtl-checks` and in `validator.py`:

| check | what it catches |
|---|---|
| `provenance_chain` | a FASTA whose derivation stops in mid-air — no path back to a physical sample |
| `required_provenance` | context that cannot be recovered later: coordinates, collection date, storage temperature |
| `alignment.unaligned` | a key nobody has mapped to a term, i.e. a note rather than metadata |

`design_to_build.shacl.ttl` states the same graph rules as SHACL, for when the
crates go into a store (`pyoxigraph` + `pyshacl`). Written, not yet executed.

## The vocabulary gate

`crate_to_graph.py` is the part that does the work a parser cannot. An RO-Crate
is JSON-LD, so the graph is `rdflib.Graph().parse(...)` — one line. The agent
exists to align the lab's invented keys onto terms that resolve, to fold a bare
value and unit into the measurement shape every handover shares, and only then
to let the crate be checked.

A term proposed by a model is **never applied**: it is reported, the key stays
unaligned, and the handover still fails until a human confirms it into
`vocab.py`. That ordering is what keeps a model from quietly inventing an
ontology.

## Reusable across handovers

`sentinel_base.SentinelAgent` does translate → validate → repair → escalate once,
for every handover. A new checking agent is a subclass with one method; the
Build → Test one is a subclass with no logic in it at all.

## Running it

Zero dependencies, no API key, no network:

    python3 demo_d2b.py

## Open

- `dbtl:` is not minted yet. Until `w3id.org/dbtlhub` resolves, the identifiers
  here are local and two teams' graphs cannot be merged.
- Six terms are marked `proposed` in `vocab.py` and need a human who knows ENVO
  and OBI to confirm or replace them.
- The chain is simulated. The shape of the failures is not.
"""


if __name__ == "__main__":
    main()
