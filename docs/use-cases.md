---
layout: default
title: Use cases
standfirst: Three fields of application, each with its own handovers, example packages and agents, used to establish that the specifications hold outside the case they were drawn from.
---

A specification derived from a single workflow tends to encode the
particulars of that workflow. The project therefore develops three use cases
in parallel. Each has its own handovers and its own example packages, and
what each requires is held in its own profile rather than in the shared
framework, so that two use cases may disagree about what makes a handover
incomplete without either modifying the other.

## Bioprospecting

Searching genomes and metagenomes for enzymes of industrial potential, and
taking the candidates found through a Design, Build, Test, Learn cycle.

The use case documents the practical steps of such a cycle and identifies
where the four handovers fall between them. It provides contract files, and
example packages for each handover: one that satisfies its contract, and
several which violate it in a single respect each, so that a checking
service has something to accept and something to refuse.

Lead: Anil Wipat, Newcastle University.

[Materials]({{ site.repository_url }}/tree/main/bioprospecting)

## Biomanufacturing

A worked example grounded in an established automated pipeline: the
SYNBIOCHEM production of (2S)-pinocembrin in *Escherichia coli*, published
by Carbonell and colleagues in Communications Biology in 2018. The published
pipeline is annotated with four proposed interface agents on the phase
transitions, together with a coordination layer above them.

[Materials]({{ site.repository_url }}/tree/main/biomanufacturing)

## Directed evolution

An examination of how agents at the four interfaces might coordinate a
directed evolution campaign. The agents do not replace the biological
experiments or the prediction models; they validate information, manage the
handovers, detect problems and preserve traceability between phases.

The case study is the work of Zhang and colleagues, published in Nature
Communications in 2025, in which a transfer RNA synthetase was evolved over
four cycles in 10 days, testing 96 variants in each cycle and reporting
activity improved by a factor of up to 2.4.

[Materials]({{ site.repository_url }}/tree/main/directed_evolution)
