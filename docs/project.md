---
layout: default
title: The project
standfirst: What DBTLHub sets out to do, who is doing it, and where the work sits within the wider research infrastructure.
---

## Scope

The goal of the project is to define a practical interoperability layer for
the phase transitions of the Design, Build, Test, Learn cycle, by producing
machine readable handover specifications for each of the four transitions:
Design to Build, Build to Test, Test to Learn, and Learn to Design.

Each specification states the minimum artefacts that must be transferred,
such as sequences, assemblies, assay data and models; the metadata that must
accompany them, such as parameters and identifiers; the provenance that must
be recorded, such as tool versions and timestamps; and the quality signals
required, such as quality control metrics and pass or fail outcomes.

The specifications are accompanied by a service that applies them, and by
example adapters demonstrating how the output of an existing tool is
converted into a conforming handover.

## The case for it

Current tools for design, build, test and learn perform well within their
own phases but fail at the boundaries between them. Researchers manually
reformat outputs, and metadata and reproducibility are lost in the process.
The project addresses that friction by defining precisely what data must
travel between phases.

Industrial biotechnology is data rich and tool diverse, yet workflows remain
brittle because phase transitions are poorly specified. Standardised
handovers allow existing resources to be connected into coherent pipelines
without rebuilding the tools themselves.

Workflow standards and metadata specifications already exist, and this
project uses them rather than competing with them. What none of them
provides is a specification of the data contract between the phases of an
engineering biology cycle. General bioinformatics standards target general
pipelines; biofoundries require phase specific contracts.

The technical contribution is therefore the handover specification itself: a
minimal, machine readable statement of what a transfer must contain, which
captures the particular requirements of biotechnology while remaining
adoptable by existing tools through straightforward adapters.

## Partners

| Institution | Country |
|---|---|
| Centre of Biological Engineering, University of Minho, Braga | Portugal |
| LABBELS Associate Laboratory, Braga and Guimarães | Portugal |
| CSIC | Spain |
| Newcastle University, and Prozomix Ltd, Newcastle | United Kingdom |
| Wageningen University and Research, Wageningen | Netherlands |

The collaboration spans the Systems Biology and Microbial Biotechnology
communities, and connects tools experts, workflow engineers and domain
specialists across four countries.

## People

| | Institution |
|---|---|
| **Óscar Dias**, project lead | Centre of Biological Engineering, University of Minho |
| **Vítor Martins dos Santos** | Wageningen University and Research |
| **Anil Wipat** | Newcastle University and Prozomix |
| **Pablo Carbonell** | CSIC |
| **Gizem Buldum** | Newcastle University |

## Context

The project forms part of ELIXIR's Cellular and Molecular Research focus. It
supports reproducible analytics and federated services through standardised
handovers, and builds capacity across ELIXIR Nodes in Portugal, Spain, the
United Kingdom and the Netherlands. It advances FAIR data practice and
workflow interoperability for the Systems Biology and Microbial
Biotechnology communities.

Beyond ELIXIR, the work supports the IBISBA partnership on biofoundry
standards, providing industrial workflows with an explicit data contract
between computational design and laboratory execution. The intention is to
connect the bioinformatics strength of ELIXIR with the biomanufacturing
infrastructure of IBISBA, so that the Design, Build, Test, Learn cycle
becomes practical for engineering biology applications in production rather
than only in principle.

## Engagement with industry

The project engages with industrial biotechnology through the biofoundry
expertise of its partners and through the ELIXIR and IBISBA collaboration on
biomanufacturing standards. Phase transition contracts address bottlenecks
that arise in industrial practice: connecting computational design tools to
laboratory execution, and connecting high throughput screening to model
optimisation.
