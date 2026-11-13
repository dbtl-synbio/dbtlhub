---
layout: default
title: Acknowledgements
standfirst: The funding that supports this work, the standards and software it is built upon, and the institutions that contribute to it.
---

## Funding

This work is supported by ELIXIR, the European research infrastructure for
life science data.

<ul class="funder-logos">
  <li>
    <a href="https://elixir-europe.org/">
      <img src="{{ '/elixir-logo.png' | relative_url }}" alt="ELIXIR">
    </a>
  </li>
</ul>

## Standards this work is built upon

### RO-Crate

Handovers between the phases of the cycle are packaged as
[RO-Crate](https://www.researchobject.org/ro-crate/), the community standard
for describing research data together with its provenance. The project uses
RO-Crate 1.3 and the Process Run Crate profile, version 0.6.

Using an established standard rather than defining a new package format
means that a handover remains readable by any tool that understands
RO-Crate, and that the provenance recorded within it is expressed in a
vocabulary others already use.

Other projects working with RO-Crate are listed among the
[RO-Crate use cases](https://www.researchobject.org/ro-crate/use_cases).

<ul class="funder-logos standards">
  <li>
    <a href="https://www.researchobject.org/ro-crate/">
      <img src="{{ '/rocrate-logo.png' | relative_url }}" alt="RO-Crate">
    </a>
  </li>
</ul>

### rocrate-validator

Conformance of a package to the RO-Crate specification is established with
the existing `rocrate-validator` tool rather than by anything written here.
The project deliberately does not duplicate it: a validator establishes
whether a package is well formed, and a contract establishes whether a given
package contains what the next process requires.

## Software this work is built upon

The contract drafting tool runs an open weight language model locally,
through [Ollama](https://ollama.com/), so that a handover package supplied
to it is not transmitted to any third party service. The model used in
testing is Qwen 2.5, released by Alibaba under the Apache 2.0 licence.

## Contributing institutions

| Institution | Country |
|---|---|
| Centre of Biological Engineering, University of Minho, Braga | Portugal |
| LABBELS Associate Laboratory, Braga and Guimarães | Portugal |
| CSIC | Spain |
| Newcastle University, and Prozomix Ltd, Newcastle | United Kingdom |
| Wageningen University and Research, Wageningen | Netherlands |

The project is described in more detail, with the people leading each part,
on the [project page]({{ '/project.html' | relative_url }}).
