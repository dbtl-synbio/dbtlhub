---
layout: default
---

Development in engineering biology is organised as a **Design, Build, Test,
Learn** cycle. A construct is designed, built, characterised
experimentally, and the results obtained inform the next design. The four
processes are typically carried out by different teams, frequently at
different institutions, and using different software.

**Tools for design, build, test and learn excel within their domains, but
the exchange of outputs, metadata, provenance and quality information
between phases is inconsistent, often manual, and poorly standardised.**
This creates unnecessary friction for researchers attempting to connect
existing resources into coherent workflows. A receiving process may accept
work that omits a parameter it requires, and the omission can remain
undetected until experimental results are returned several weeks later.

DBTLHub addresses that boundary. The transition between one phase and the
next is treated as a first class object with a formal specification, rather
than as an afterthought in which each tool emits an ad hoc output that the
next user must parse by hand.

## The approach, in three parts

**Work is transferred as an RO-Crate.** Each process passes its output to
the next as a package holding the data together with the processing steps
and parameters that produced it, so that the receiving process obtains both
the work and its provenance at once.

**What the receiving process requires is written down as a contract.** A
contract names the entities that must be present, the values that must be
recorded for them, and whether a failure prevents the transfer or is
recorded as a warning. Each requirement states the consequence of its
omission, in terms of what the receiving process cannot then do.

**A service checks the handover and records the outcome inside the crate.**
The crate is returned with the verdict, the findings and the version of the
contract applied written into it, so that it carries its own record of
every check performed upon it.

## Where to go next

| If you want to | Go to |
|---|---|
| Understand the project, its partners and its scope | [The project]({{ '/project.html' | relative_url }}) |
| Read what a contract specifies at each of the four phase transitions | [Interoperability contracts]({{ '/contracts.html' | relative_url }}) |
| See what has been built, and where the code is | [Software]({{ '/software.html' | relative_url }}) |
| Read how the work applies in a particular field | [Use cases]({{ '/use-cases.html' | relative_url }}) |
| Try it in a browser, without installing anything | [Get started]({{ '/get-started.html' | relative_url }}) |
