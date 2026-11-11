# Bioprospecting use case

Work on the bioprospecting use case for ELIXIR BioHackathon Europe 2026,
Project 25, DBTLHub Interoperability Contracts.

Bioprospecting here means searching genomes and metagenomes for enzymes with
industrial potential, and taking the candidates found through a Design, Build,
Test, Learn cycle.

Lead: Anil Wipat, Newcastle University.

## What is in this folder

| Folder or file | What it holds |
|---|---|
| `USE_CASE_STEPS.md` | The 14 practical steps of a bioprospecting Design, Build, Test, Learn cycle, and where the four handovers sit between them |
| `contracts/` | The handover contracts for this use case, written as files. `design_to_build.yaml` is complete enough to run; `build_to_test.yaml` says what it is for and checks packaging only |
| `exampleROcrates/` | Example crates for each handover: one that satisfies its contract and several broken one way each, so a checking service has something to pass and something to fail |
| `deployment/` | How this use case's own instance of sentinel-oo is deployed: its `compose.yaml` and what it mounts |
| `demonstration/` | A walkthrough of the Design to Build handover end to end, and a simulated version of the step that receives it |
| `agents/` | Agent work for this use case |
| `docs/` | Slides and diagrams |

The service these contracts are written for is `sentinel-oo`, at the top
level of this repository. It is generic: tailoring it to this use case means
writing the contracts in `contracts/` and nothing else.

## On the data

The worked example is based on work from Anil Wipat's laboratory at
Newcastle University. The sequences in these example crates are simulated,
and every one says so in its own description line. What is kept from the
real cycle is its structure, the quality thresholds, the failure modes and
the attrition numbers, because those are what the contracts have to carry.

