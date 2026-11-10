Stuff to be resolved

* What does a contract look like?
* How do we represent the specification, metadata and function on the downstream phase in the cycle (we can think of it as a workflow)

  **Answer, 10 November 2026.** A workflow gets described at four levels.
  The first three are covered by existing standards. The fourth is not.

  | Level | Question | Standards that cover it |
  |---|---|---|
  | Function | What is this for? | EDAM operation terms, bio.tools, SBOL activity types. Labels only. |
  | Interface | What goes in and out? | CWL and Galaxy typed ports, SBOL, SBML, EnzymeML |
  | Execution | How do you run it? | CWL, Nextflow, Snakemake, Galaxy, LabOP |
  | Provenance | What happened on a run? | W3C PROV, Workflow Run RO-Crate |

  Function is the weak one. "Sequence alignment" names the kind of
  operation. It does not say what the input must satisfy first, or what
  the output is guaranteed to satisfy afterwards. Those two statements
  are called preconditions and postconditions, and almost nobody writes
  them for bioinformatics workflows.

  **Synthetic biology specifically.** Galaxy-SynBioCAD (Nature
  Communications, 2022) chains design to build as Galaxy workflows and
  passes SBOL and SBML between tools; the contract there is a file format.
  LabOP represents lab protocols formally in RDF on top of SBOL 3.
  Cello compiles a circuit's intended logic from Verilog, which is the
  one case of a formal function statement, though of the construct
  rather than of the workflow. The biofoundry abstraction hierarchy
  (Nature Communications, 2025) gives shared vocabulary at four levels:
  project, service, workflow, unit operation.

  **The gap, and a candidate answer.** Nobody has written "given input
  satisfying X, this phase produces output satisfying Y, and a machine
  can check both". That statement is what a contract could be. One way
  to build it from existing parts: an RO-Crate carries the data across
  the handover, SHACL shapes hold the preconditions and postconditions
  as checkable rules, and the agent checks those rules, falling back on
  judgement only for what cannot be written as a rule.

  Worth looking at from outside synthetic biology: APE, the Automated
  Pipeline Explorer, composes workflows by SAT solving over EDAM-typed
  tools. It does by logic what the group wants its agents to do. Its
  limit is that EDAM types are coarse: a FASTA file is a FASTA file
  whether or not it holds ene-reductases.

* Should we call these agents that sit at the interface between phases "Sentinel agents"?


