---
layout: default
title: Software
standfirst: The components developed by the project, what each one does, and where its source and documentation are held.
---

All components are held in the
[project repository]({{ site.repository_url }}) and are open source.

## sentinel

The agent framework. A sentinel agent stands at one phase transition of the
cycle, reads what the upstream phase produced, and determines whether the
downstream phase can accept it. It is able to refuse.

The framework is independent of any particular use case. What each use case
requires is held in a profile, so that two use cases may disagree about what
makes a handover incomplete without either of them modifying the framework.

[Source and documentation]({{ site.repository_url }}/tree/main/sentinel)

## sentinel-oo

A deployable service built on the same principle. The generic service is
combined with a contract file that tailors it to one handover, and is
deployed as a web service. It evaluates a handover against its contract and
returns the handover package with the outcome recorded inside it.

The service is also addressable by software agents through a tool interface,
so that a coordinating agent may request a check and receive the outcome and
the findings without receiving the package itself, which is frequently too
large to be useful to an agent directly.

[Source and documentation]({{ site.repository_url }}/tree/main/sentinel-oo)

## The Sentinel Contract Wizard

A notebook that drafts a contract. It is given a handover package and a
description, written in ordinary English under six headings, of what the
receiving process requires. It produces a draft contract, a list of the
questions it was unable to resolve without a decision from a person, and the
result of three checks on the draft.

The three checks establish, in order, whether the draft is well formed;
whether each of its requirements is capable of applying to anything in the
package, since a requirement that matches nothing passes silently; and
whether the draft rejects the package it was drafted from, which would
indicate that it is too strict.

The drafting is performed by a language model running on the machine
executing the notebook. The model proposes requirements and is never the
component that decides: every draft is checked, every ambiguity is returned
as a question, and the draft is corrected by the person before it is used.

[Run it in a browser](https://colab.research.google.com/github/dbtl-synbio/dbtlhub/blob/main/contract-wizard/sentinel_contract_wizard.ipynb)
&middot;
[Source and documentation]({{ site.repository_url }}/tree/main/contract-wizard)

## DBTL Tool Extractor

A pipeline that extracts and classifies the tools registered in
[bio.tools](https://bio.tools), organising them according to their role in
the cycle and recording the data types and file formats each accepts and
produces. Its output is a directory for researchers building or auditing
workflows, with particular attention to which tools can be connected to
which others.

[Source and documentation]({{ site.repository_url }})
