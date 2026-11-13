---
layout: default
title: Interoperability contracts
standfirst: What a contract states, what it can demand of a handover, and what happens when a handover fails to satisfy it.
---

A contract is the written statement of what one phase of the cycle must
transfer to the next. It is a file, held under version control alongside the
code of the processes it governs, so that a change to what a phase requires
is a change that can be inspected, reviewed and dated.

## The four phase transitions

The cycle has four boundaries, and each has its own contract.

| Transition | What is transferred |
|---|---|
| **Design to Build** | Construct specifications: the sequences to be synthesised, the host they are intended for, and the physical arrangement in which they are to be built |
| **Build to Test** | Assembly outputs: what was actually built, the evidence that it was built correctly, and where each construct physically is |
| **Test to Learn** | Phenotypic screening data: the measurements obtained, the conditions under which they were obtained, and the quality control outcomes that qualify them |
| **Learn to Design** | Model predictions: what was inferred, from which data, and with what confidence |

Each contract is stated independently of the others, because the phases are
operated by different teams and change at different rates.

## What a contract states

A contract names the entity types that must be present in a handover, and
for each of them the properties and recorded values that must accompany it.
Four points of its design are deliberate.

**Every requirement carries its justification.** A requirement states what
the receiving process cannot do if it is not satisfied. A requirement for
which no such statement can be made is a preference rather than a
requirement, and preferences accumulate until a specification becomes too
burdensome to apply.

**Presence and soundness are stated separately.** That a reference is
recorded, and that it resolves to something that exists, are two
requirements rather than one. Combining them would make each of them
impossible to state on its own.

**Each requirement declares its severity.** A failure either prevents the
transfer or is recorded as a warning. There is no intermediate outcome,
because an intermediate outcome gives the receiving process nothing it can
act upon.

**A contract declares the entity types it applies to.** A handover that does
not contain them is rejected before any individual requirement is evaluated.
Without this, a requirement naming an entity type absent from the handover
matches nothing, raises nothing, and passes silently, with the result that a
handover which was never meaningfully examined is reported as acceptable.

## The outcome of a check

A check returns one of three outcomes.

| Outcome | Meaning |
|---|---|
| **Accepted** | Every requirement was satisfied. The receiving process may proceed |
| **Accepted with flags** | No requirement that prevents transfer was violated, but something was recorded that the receiving process should be aware of |
| **Refused** | At least one requirement that prevents transfer was violated. The handover does not proceed |

In all three cases the handover package is returned, with the outcome
recorded inside it as an entity of the same type the package already uses
for its processing steps, so that no additional vocabulary is required of a
reader. The record states the outcome, each individual finding, the name and
version of the contract applied, and a checksum of the package as received.

A refused handover is recorded in the same detail as an accepted one, and is
returned to the process that produced it, so that the grounds for refusal
are available to whoever must act on them.

## Relationship to RO-Crate validation

Conformance to the RO-Crate specification is established separately, using
the existing `rocrate-validator` tool. The two questions are different: a
validator establishes whether a package is a well formed RO-Crate, and a
contract establishes whether a given package contains what the next process
requires. Both are applied.

## Where the contracts are

Contract files for the use cases are held in the project repository, within
the folder for each use case. The
[Software]({{ '/software.html' | relative_url }}) page describes the service
that applies them and the tool that assists in drafting them.
