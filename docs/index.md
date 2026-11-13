Development in synthetic biology is organised as a **Design, Build, Test,
Learn** cycle. A construct is designed, built, characterised
experimentally, and the results obtained inform the next design. The four
processes are typically carried out by different teams, at different
institutions, using different software.

**Interoperability problems arise principally at the boundaries between
those processes rather than within them.** A Build process may accept a
design that omits a parameter it requires and commission gene synthesis on
that basis, the omission becoming apparent only when experimental results
are returned several weeks later. In most such cases the information was
present somewhere in the project record, but nothing was in a position to
check it at the point of transfer.

DBTLHub addresses that boundary. Work is transferred from one process to
the next as an **RO-Crate**, a package holding the data together with the
steps and parameters that produced it. What the receiving process requires
before it will accept a handover is written down as a **contract**, and a
service checks the crate against that contract and records the outcome
inside the crate itself.

## What is in this repository

| Component | What it is |
|---|---|
| [`sentinel`](https://github.com/dbtl-synbio/dbtlhub/tree/main/sentinel) | The agent framework. A sentinel agent stands at one phase transition, reads what the upstream phase produced, and decides whether the downstream phase can accept it. What each use case requires lives in a profile rather than in the framework |
| [`sentinel-oo`](https://github.com/dbtl-synbio/dbtlhub/tree/main/sentinel-oo) | A deployable service built on the same idea. It is combined with a contract file that tailors it to one handover, and runs as a web service or as a tool interface for agents |
| [`contract-wizard`](https://github.com/dbtl-synbio/dbtlhub/tree/main/contract-wizard) | A notebook that drafts a contract from a crate and a description of what the receiving process needs, written in ordinary English |
| [`bioprospecting`](https://github.com/dbtl-synbio/dbtlhub/tree/main/bioprospecting), [`biomanufacturing`](https://github.com/dbtl-synbio/dbtlhub/tree/main/biomanufacturing), [`directed_evolution`](https://github.com/dbtl-synbio/dbtlhub/tree/main/directed_evolution) | Three use cases, each with its own handovers, example crates and agents |

## Try it without installing anything

The **Sentinel Contract Wizard** runs in a browser on a free Google Colab
machine. Give it an RO-Crate and a description of what your process needs,
and it drafts a contract, lists the questions it could not answer itself,
and checks the draft three ways before you rely on it.

[Open the Sentinel Contract Wizard](https://colab.research.google.com/github/dbtl-synbio/dbtlhub/blob/main/contract-wizard/sentinel_contract_wizard.ipynb)

Nothing is installed on your own computer, no account or key is needed, and
the language model it uses runs on the Colab machine, so the crate does not
leave it.

## How a contract is checked

A contract names the entity types that must be present in a crate, the
values that must be recorded for them, and whether a failure stops the
handover or is recorded as a warning. Each requirement carries the reason it
exists, written for whoever has to act on it.

The checking service returns the crate with the outcome written inside it,
as an action entity of the same type the crate already uses for its
processing steps. The record gives the verdict, each finding, the name and
version of the contract applied, and a checksum of the crate as received. A
rejected handover is recorded in the same detail as an accepted one, so the
crate carries its own history of every check performed upon it.

Conformance to the RO-Crate specification is established separately, with
the existing `rocrate-validator` tool. The two questions are different: one
asks whether a crate is well formed, the other whether it contains what the
next process needs.

## Where to start reading

Each component has its own README. For the contract language and how a
handover is checked, start with
[`sentinel-oo`](https://github.com/dbtl-synbio/dbtlhub/tree/main/sentinel-oo).
For the agent framework and the profiles that tailor it, start with
[`sentinel`](https://github.com/dbtl-synbio/dbtlhub/tree/main/sentinel).
