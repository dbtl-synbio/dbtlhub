Stuff to be resolved

* What does a contract look like?
* How do we represent the specification, metadata and function on the downstream phase in the cycle (we can think of it as a workflow)

  **Answer, 10 November 2026.**

  To describe a workflow properly you have to write down four separate
  things. Three of them are solved. The fourth is not, and the fourth is
  what a contract would be.

  | # | What you write down | Example, for a metagenome mining workflow | Solved by |
  |---|---|---|---|
  | 1 | What it is for | Find enzyme candidates in a metagenome | Nothing. You only get a label. |
  | 2 | What goes in and comes out | A FASTA file in, a table of ranked candidates out | SBOL, SBML, EnzymeML, CWL and Galaxy typed ports |
  | 3 | How to run it | These programs, in this order, with these settings | CWL, Nextflow, Snakemake, Galaxy, LabOP |
  | 4 | What happened on a run | On this date, this input file produced this output file | W3C PROV, Workflow Run RO-Crate |

  **Why a label is not enough for item 1.** Tagging a step "sequence
  alignment" says what kind of thing it is. It says nothing about
  whether the data is any good.

  Take the Test to Learn handover. Test hands Learn a table of enzyme
  activity measurements. A format check says: valid table, right
  columns, numbers are numbers. It passes.

  What the format check does not say is whether the negative controls
  behaved as expected, whether each variant was measured 3 times or only
  1 time, whether anything was measured above the top of the
  instrument's range, or whether plate positions were randomised. Learn
  needs all of those to be true or the model it fits will be wrong. The
  format check passes either way. That is the hole.

  **So a contract is this.** A written statement that before a phase
  runs, these things must be true of its input, and after it runs, these
  things are guaranteed to be true of its output. The formal names for
  the two halves are preconditions and postconditions. Nobody in
  synthetic biology has written these down for the DBTL handovers.

  **What already exists.** Galaxy-SynBioCAD (Nature Communications,
  2022) chains design tools into build tools and passes standard files
  between them, which covers items 2 and 3 but not item 1. LabOP writes
  lab protocols down formally so a robot can run them and a record comes
  back, covering Build and Test. The biofoundry abstraction hierarchy
  (Nature Communications, 2025) gives shared vocabulary at four levels:
  project, service, workflow, unit operation.

  From bioinformatics rather than synthetic biology, APE (Automated
  Pipeline Explorer) assembles workflows by logic, checking that one
  tool's output can feed the next tool's input. That is close to what
  the group wants its agents to do. Its weakness is that it only knows
  file types, so it cannot tell a FASTA file of ene-reductases from any
  other FASTA file.

  **A way to build it from parts that exist.** An RO-Crate is a folder
  with a description of its own contents attached: use it to carry the
  data across the handover. SHACL is a language for writing rules that
  data must satisfy: use it to write the preconditions and
  postconditions. The agent runs those rules at the handover. Whatever
  can be written as a rule gets checked mechanically, and whatever
  cannot gets the agent's judgement instead.

* Should we call these agents that sit at the interface between phases "Sentinel agents"?


