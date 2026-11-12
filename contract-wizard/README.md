# The Agent Contract Wizard

A tool that writes an interoperability contract for a handover between two
phases of a Design, Build, Test, Learn cycle, from two things the person
supplies: the handover itself, as an RO-Crate, and a description of what
their phase needs, written in ordinary English.

It exists because writing a contract by hand means learning the contract
language first. This turns that round. The person writes English under six
headings, a language model drafts the contract, three checks say which parts
of the draft can be trusted, and the person corrects it.

| File | What it is |
|---|---|
| `agent_contract_wizard.ipynb` | The notebook, run on Google Colab |
| `build_agent_contract_wizard.py` | The script that writes that notebook. The notebook is generated, so change this and run it rather than editing the notebook by hand |

## What it asks for

**An RO-Crate.** A packaged folder of data with a metadata file describing
everything inside it. Three routes: an example from this repository, an
upload from the person's own computer, or a metadata file pasted in as text.

**A description of what the receiving phase needs**, under six headings.
Each heading supplies one part of a requirement:

| Heading | What it decides |
|---|---|
| 1. Which handover is this? | The contract's name and description |
| 2. What does the receiving phase do with it? | Whether each rule is justifiable at all |
| 3. What must be present? | Which rules say `be recorded` |
| 4. What must be true of the values? | Which rules use a range, a list of permitted values, or uniqueness |
| 5. What is worth a warning but not a refusal? | Which rules are `flag` rather than `refuse` |
| 6. What could be recovered rather than refused? | Which rules a language model may later help with |

Headings 1 and 2 produce no rules of their own. They are sent as context
with every request, so the drafting makes four requests rather than six.

## What it gives back

A contract as a YAML file, a list of questions the model wants answered, and
the result of three checks on the draft.

| Check | The question it answers |
|---|---|
| 1 | Does the contract parse? |
| 2 | Can every rule ever fire against this crate? |
| 3 | Does it refuse the crate it was drafted from? |

**Check 2 is the one nobody thinks to do.** A rule naming a type the crate
does not contain matches nothing and passes in silence, and silence reads as
approval. A contract made entirely of such rules reports `ACCEPTED` on every
crate forever while appearing to work, which is worse than having no
contract at all.

## How the model is held to the language

The model's answer is constrained by a JSON schema while it is generating,
through Ollama's structured output support, rather than checked afterwards.
Three things follow from that:

- It cannot use a word outside the 5 permitted demands or the 2 permitted
  severities.
- It cannot name a type or a value that is not in the crate, because those
  lists are read out of the crate first and written into the schema.
- The permitted demands and severities are imported from
  `sentinel_oo.contract`, which is the code that decides whether a contract
  is valid, rather than copied. A copy would disagree with it the day
  somebody adds a sixth demand.

Three decisions are taken away from the model entirely: the version number,
the list of types the contract is for, which is worked out from the rules,
and whether a rule is `repairable`, which permits a model to propose a value
and is a decision for the person reading the draft.

## What was measured, on 12 November 2026

Against `qwen2.5:14b`, which has 14 billion parameters, running on a laptop
with a graphics card, on the bioprospecting Design to Build example crate of
109 entities.

| What was tried | Result |
|---|---|
| Asked for YAML in free text | Invented a demand that does not exist in the language, and put a field name into the severity field. Needed 2 correction rounds to parse, then falsely refused a sound crate 9 times |
| The same model, answer constrained by a schema | Parsed at the first attempt, no rules that could never fire, 4 false refusals |
| Asked for the whole contract in one request | 2 requirements from six headings |
| Asked heading by heading | 17 requirements from the same crate and the same words |
| The whole notebook, end to end | 10 requirements in 55 seconds, 8 questions, parsed first time, accepted the sound crate with 3 flags, refused a deliberately broken one, and reported 1 rule of the 10 that could never fire |

`qwen2.5-coder:14b` was also tried and never produced a contract that
parsed, failing the same way 3 times in a row.

## Known faults, measured rather than guessed

**A type that covers several different things.** The example crate types the
sediment, the DNA extracted from it, and the sequencing library all as
`Sample`. A rule applies to every entity of the type it names, with no
exceptions available, so a rule meant for one of them catches all three. The
crate description now warns about this before any rule is written, and the
model asks about it instead of guessing. It cannot be fixed in the contract:
it is fixed by giving the field material a type of its own in the crate.

**Coverage, not correctness, is now the weak point.** Every constraint that
stops the model being wrong also makes it write less. The three checks find
a wrong contract and say nothing about a thin one, which is why the person
correcting the draft is told to look for what is missing.

## What is tested and what is not

**Run end to end on a laptop on 12 November 2026**: every cell, against a
real model, with the example crate.

**Not tested, because it needs Colab**: the clone and install, the Ollama
install, the file picker, the editing box, and the download.

## Still to do

- The code lives in the notebook's cells. It belongs in a Python package
  with tests, and the notebook should be a front end to it.
- `qwen3.5:9b`, two generations newer and smaller at approximately 6.6
  gigabytes, has not been measured on this task. The notebook has a
  commented line that switches to it.
