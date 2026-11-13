# DBTLHub Interoperability Contracts — integrated technical report

**Project:** ELIXIR BioHackathon Europe 2026, Project 25, "DBTLHub Interoperability Contracts", 9–13 November 2026, Barcelona.
**Repository audited:** `/Users/marcoanteghini/Research/dbtlhub` (clone of `dbtl-synbio/dbtlhub`), branch `main`, HEAD `ec80217` *"Four audits, and the defects they found"*.
**Reader:** Marco Anteghini (LifeGlimmer), contributor of `sentinel/`, briefing the other teams.
**Sources:** four auditor briefings (bioprospecting, directed evolution, biomanufacturing, sentinel/templates) plus every command re-run against HEAD on 2026-11-10. The repository was not modified; `git status --short` at the end is identical to the start.

A note on the `templates.md` briefing: it was written against HEAD `a3d7765`, before two commits of fixes (`cd07cf2`, `ec80217`). Every defect it reports has been re-checked by running the code. §8 marks each one fixed or open, with the commit.

---

## 1. What this project is

Three European groups run Design–Build–Test–Learn cycles on different science: mining metagenomes for industrial enzymes, evolving a protein with a language model in the loop, and engineering *E. coli* to make a flavanone. All three automate the cycle. All three hit the same wall at the four points where one phase hands its work to the next.

The wall is not file formats. It is that a file can be perfectly well formed and still useless to whoever receives it. The bioprospecting use case states the case in `bioprospecting/questions.md`, in an answer dated 10 November 2026, and it is the clearest statement of the problem anywhere in the repository (Anil Wipat, verbatim):

> "Take the Test to Learn handover. Test hands Learn a table of enzyme activity measurements. A format check says: valid table, right columns, numbers are numbers. It passes. What the format check does not say is whether the negative controls behaved as expected, whether each variant was measured 3 times or only 1 time, whether anything was measured above the top of the instrument's range, or whether plate positions were randomised. Learn needs all of those to be true or the model it fits will be wrong. The format check passes either way. **That is the hole.**"

The same document sets out why the existing standards do not close it. To describe a workflow you have to write down four separate things, and only the fourth is missing:

| # | What you write down | Example, for a metagenome mining workflow | Solved by |
|---|---|---|---|
| 1 | What it is for | Find enzyme candidates in a metagenome | Nothing. You only get a label. |
| 2 | What goes in and comes out | A FASTA file in, a table of ranked candidates out | SBOL, SBML, EnzymeML, CWL, Galaxy typed ports |
| 3 | How to run it | These programs, in this order, with these settings | CWL, Nextflow, Snakemake, Galaxy, LabOP |
| 4 | What happened on a run | On this date, this input file produced this output file | W3C PROV, Workflow Run RO-Crate |

> "**Why a label is not enough for item 1.** Tagging a step 'sequence alignment' says what kind of thing it is. It says nothing about whether the data is any good."

And then the definition the whole project rests on:

> "**So a contract is this.** A written statement that before a phase runs, these things must be true of its input, and after it runs, these things are guaranteed to be true of its output. The formal names for the two halves are **preconditions and postconditions**. Nobody in synthetic biology has written these down for the DBTL handovers."

The prior art is credited and bounded in the same place. Galaxy-SynBioCAD (*Nature Communications*, 2022) chains design tools into build tools and passes standard files between them — items 2 and 3, not item 1. LabOP formalises lab protocols so a robot can run them — Build and Test. The biofoundry abstraction hierarchy (*Nature Communications*, 2025) gives shared vocabulary at four levels: project, service, workflow, unit operation. APE (Automated Pipeline Explorer), from bioinformatics rather than synthetic biology, assembles workflows by logic, checking that one tool's output can feed the next tool's input — the closest thing to what the group wants, and:

> "Its weakness is that it only knows file types, so it cannot tell a FASTA file of ene-reductases from any other FASTA file."

The proposed construction, also verbatim: an RO-Crate is a folder with a description of its own contents attached, so use it to carry the data across the handover; SHACL is a language for writing rules that data must satisfy, so use it to write the preconditions and postconditions; the agent runs those rules at the handover. "Whatever can be written as a rule gets checked mechanically, and whatever cannot gets the agent's judgement instead."

That is the project. Three use cases design the agents; `sentinel/` is one implementation of the contracts, the agents and the templates for writing more.

---

## 2. The repository, file by file

116 tracked files. The repository began in May 2026 as a bio.tools scraper and acquired the BioHackathon material on a single day: **every DBTL commit is dated 2026-11-10**.

### 2.1 Root

| File | Contributor | Last touched | What it is |
|---|---|---|---|
| `README.md` | José Campos | 2026-10-22 | Documents the **DBTL Tool Extractor** only — the bio.tools scraper. It says nothing about contracts, agents or the BioHackathon. |
| `DBTL_biotools_extractor.py` | josedrcampos | 2026-06-05 | 12.8 kB. Downloads ~33,000 bio.tools entries, classifies each into DBTL phases by EDAM topic, resolves country via ROR. |
| `bio_tools_dbtl.csv` | josedrcampos | 2026-05-22 | 5.4 MB output of the above. |
| `Biotools DBTL.xlsx` | josedrcampos | 2026-05-22 | 3.9 MB multi-sheet Excel report. |
| `ror_cache.json` | josedrcampos | 2026-05-22 | 546 kB ROR API cache. |
| `LICENSE` | Pablo Carbonell | 2026-05-13 | Initial commit (`cf14b9e`). |
| `.gitignore` | Neil Wipat | 2026-11-10 | Added at `4bb7f7a` to ignore Office lock files, later `.DS_Store`. |
| `DBTL_interface_agents_RO-Crates.png` | — | 2026-11-10 | **Untracked.** 1,833,143 B, 3600×2904. In no commit, referenced by no file. Its aspect ratio (1.240) matches the rendered `directed_evolution/DBTL_interface_agents_RO-Crates.svg`, so it is a loose raster export of the DE diagram. |

### 2.2 `bioprospecting/` — Anil (Neil) Wipat, Newcastle University

18 tracked files, 9 commits, all on 2026-11-10 between 10:16 and 16:23 CET.

| Path | Size | What it is |
|---|---|---|
| `README.md` | 365 B | Scope and lead. |
| `questions.md` | 3,474 B | Three questions; the second carries the contract answer quoted in §1. |
| `agents/README.md` | — | One paragraph defining a checking agent. Nothing else in `agents/`. |
| `docs/README.md` | 272 B | One paragraph. |
| `docs/01_what_is_rocrate.png` | 311,592 B | RO-Crate explained. |
| `docs/02_what_is_process_run_crate-2.png` | 292,087 B | Process Run Crate and the three-profile stack. |
| `docs/04_design_data_concept.png` | 136,865 B | "96 protein sequences → 96 construct designs → one 96-well plate layout". |
| `docs/05_plate_contract.png` | 229,965 B | Intended layout vs delivered plate vs the difference. |
| `docs/06_design_handover_crate.png` | 490,249 B | **The Design handover specification**, with MUST/SHOULD/MAY. |
| `docs/07_crate_graph.png` | 362,563 B | The example crate, drawn. |
| `docs/bioprospecting.pptx` | 4,811,595 B | 6 slides, 5 content images, slide text essentially empty. |
| `exampleROcrates/README.md` | 429 B | Promises one valid and one broken crate per handover. |
| `exampleROcrates/07_crate_graph.png` | 362,563 B | Byte-identical duplicate of the `docs/` copy (md5 `b92b62fc0193e4467942a2642dbf8cbb`). |
| `exampleROcrates/design-to-build-simple/README.md` | 9,212 B | The substantive document of the folder. |
| `.../ro-crate-metadata.json` | 42,324 B | 105 `@graph` entries. |
| `.../constructs.json` | 5,432 B | 4 constructs, labelled SIMULATED. |
| `.../panel.faa` | 1,685 B | 4 FASTA records, each header marked SIMULATED. |
| `.../plate-layout.csv` | 170 B | 4 rows, PLATE-AB-12-01. |

There is no `03_*.png`; the numbering skips 3. One discrepancy with the briefing: it reports "19 tracked files"; `git ls-files bioprospecting | wc -l` returns **18**, which matches its own table. 18 is correct.

The 9 commits: `bd09e44` 10:16 folder and README; `c595eb6` 10:26 docs/agents/exampleROcrates; `4bb7f7a` 10:27 remove Office lock file; `a6fce04` 11:08 open questions and two slides; `e1ef026` 12:47 the contract answer and the plate slide; `e238663` 13:08 example crates with full provenance; `1a44866` 13:14 **revert of the previous commit**; `0d98bbb` 14:40 the simple crate and its graph; `564ca71` 16:23 sharpen the answer, add diagrams 06 and 07.

Two commits matter beyond their diffs. `e238663` added 18 files and 6,046 lines: a 593-line crate generator plus a valid crate and **three deliberately broken ones** (`dangling-reference`, `missing-conformsto`, `missing-gene-calling-mode`) and a 203-line README. `1a44866` reverted all of it six minutes later. The broken crates have not come back.

### 2.3 `directed_evolution/` — BrunoAGSa, Pablo Carbonell

4 tracked files. No `agents/`, no `docs/`, no example crates, no questions file.

| File | Size | Contributor | Commit |
|---|---|---|---|
| `README.md` | 2,873 B | BrunoAGSa | `4321f3e` "[ADD] Directed evolution case study", merged to `main` via `fad41f8` (PR #1, merged by José Campos) |
| `dbtl_interface_agents.svg` | 24,771 B | BrunoAGSa | `4321f3e` — diagram **v1** |
| `original.png` | 1,852,097 B, 1536×1024 | BrunoAGSa | `4321f3e` — referenced by nothing |
| `DBTL_interface_agents_RO-Crates.svg` | 336,080 B | Pablo Carbonell | `9912375` "DE DBTL interface agents with RO-Crates" — diagram **v2** |

The README embeds only v1. The later, more advanced RO-Crate diagram is linked from nothing.

### 2.4 `biomanufacturing/` — Pablo Carbonell (diagrams), José Campos / josedrcampos (folder, README, deck)

7 tracked files. No code, no crate, no schema, no contract; `agents/` holds only `.gitkeep`.

| Path | Contributor | Commit | What it is |
|---|---|---|---|
| `README.md` | josedrcampos | `315428e` (added empty), filled by `4f96ecc` | One sentence, no DOI. |
| `dbtl_agents_biomanufacturing.svg` + `.png` | Pablo Carbonell | `21a16a3` | Agents-only diagram; the PNG is the same drawing with identical text, no content difference. |
| `dbtl_agents_rocrates_biomanufacturing.svg` | Pablo Carbonell | `4cb39db` | Crate diagram **v1**, case-specific. |
| `DBTL_biomanufacturing_RO-Crates.svg` | Pablo Carbonell | `c3e8b49` | Crate diagram **v2**, generic. Added alongside v1, not replacing it. |
| `agents/.gitkeep` | josedrcampos | `dd150b4` | Empty. |
| `docs/BH DBTLHub Biomanfacturing case Workflows.pptx` | josedrcampos | `1b5b88e` | 9 slides, committed once, never revised, not referenced by the README. |

### 2.5 `sentinel/` — Marco Anteghini, LifeGlimmer

80 tracked files; 45 Python files outside `__pycache__`, **6,683 Python lines** (`wc -l`, measured at HEAD).

| Folder | Contents |
|---|---|
| (top) | `demo.py`, `demo_cycle.py`, `demo_d2b.py`, `demo_l2d.py`, `README.md` (202 lines), `requirements.txt`, `.gitignore` (`__pycache__/`, `*.pyc`, `runs/`, `~$*`, `.DS_Store`) |
| `framework/` | `validator.py` 737 lines, `kg.py` 372, `engines.py` 339, `crate_store.py` 221, `llm.py` 173, `vocab.py` 149, `ledger.py` 52; `README.md` 129 lines; `DESIGN_TO_BUILD.md` 169 lines |
| `framework/agents/` | `base.py` 53, `sentinel_base.py` 133, `phase_base.py` 111, `coordinator.py` 88, `crate_to_graph.py` 117; four sentinels (`sentinel_d2b` 156, `sentinel_b2t` 30, `sentinel_t2l` 31, `sentinel_l2d` 47); four crate-writing phase agents (`phase_design_crate` 105, `phase_build_crate` 136, `phase_test_crate` 129, `phase_learn_crate` 160); three legacy phase agents (`phase_design` 35, `phase_build` 72, `phase_test` 67) |
| `framework/contracts/` | `design_to_build.schema.json` 450 lines, `build_to_test.schema.json` 396, `test_to_learn.schema.json` 305, `learn_to_design.schema.json` 394; `profiles/bioprospecting.json` 184, `profiles/biomanufacturing.json` 111; `shapes/design_to_build.shacl.ttl` 162 |
| `framework/vocabulary/` | `core.json` 202 lines; `labs/newcastle.json` 22; `labs/lifeglimmer.json` 17 |
| `scripts/` | `prove_engine.py` 222 lines, `check_crate.py` 221, `trace.py` 209, `export_for_dbtlhub.py` 197, `ask.py` (168 before the fix, larger now), `show_agents.py` 154, `new_handover.py` 140 |
| `template/` | `TAKE_A_HANDOVER.md` 302 lines, `handover_contract.schema.json` 237, `handover_agent.py` 126, `phase_agent.py` 124, `README.md` 122 |
| `usecases/bioprospecting/` | `sampling.py` 209, `prc_crate.py` 215, `instruments.py` 117, `learning.py` 112 — all simulated science |
| `tests/` | `test_framework.py` (15 tests), `fixtures/b2t_double_booked.json`, `fixtures/b2t_missing_unit.json` — **new at `ec80217`** |
| `examples/design-to-build/` | `README.md` + three crate folders, each the published bioprospecting crate with exactly one injected fault (`ro-crate-metadata.json` ≈ 1283–1298 lines each, plus the three data files) |
| `docs/` | `walkthrough.html` (611 lines), `sentinel_agents.pptx` (57,759 B), and a 165-byte `~$sentinel_agents.pptx` lock file (gitignored) |

`sentinel/` commits in order: `5eaa7af` (template, Handover 1, contracts) → `7c6fbf7` (bring your own model) → `6a45cf0` (Handover 4) → `620861d` (H1 on this repository's own crate) → `668a744` (two severities) → `5a2f75c` (read what the use case published) → `e482417`, `ad66d37`, `0cdad4e`, `681c912`, `ef7388c`, `41e8b5d` (graph, deck, walkthrough) → `8f06e13` (limits) → `5c61c36` (demo_l2d) → `dea5cc1` (one crate per run, sentinel as submodule) → `271a81f` (all four phases write the one crate) → `a3d7765` (close the T→L hole) → `cd07cf2` (biomanufacturing profile corrected) → `ec80217` (the audit fixes and the tests).

---

## 3. The three use cases

### 3.1 Bioprospecting — Anil (Neil) Wipat, Newcastle

**The science.** `bioprospecting/README.md`, verbatim: *"Bioprospecting here means searching genomes and metagenomes for enzymes with industrial potential, and taking the candidates found through a Design, Build, Test, Learn cycle."* The worked example is **ene-reductases from hot-spring sediment** — crate root name "Design to Build handover, ene-reductase panel AB-12", study "Bioprospecting for ene-reductases in hot spring sediment", `geo_loc_name` "Iceland: Hveragerdi". No published paper is cited; the science is the group's own, and everything in the crate is labelled SIMULATED in-band.

**DBTL stages, tools and instruments.** The wet-lab pipeline on slide 2 ("Metagenomic Enzyme Characterisation Use Case", under a running header "Development of an AI-Native Open Data Lakehouse for Automated Synthetic Biology"): Synthesised DNA plate → Rehydration → Dilution and Rearray → PCR → DNA Quantification → DNA Normalisation → PURExpress Protein Synthesis → Biotransformation → Enzyme Assay. Named vendors and instruments legible on that slide: **Twist Bioscience** (DNA synthesis), **Labcyte Echo 550** acoustic liquid handler, **BMG LABTECH CLARIOstar Plus** plate reader, two unlabelled enclosed benchtop liquid handlers.

Slide 4 names the simulated instrument set, one agent each:

| Instrument | Role | Emits |
|---|---|---|
| Opentrons OT-2 | liquid handling | worklists, run logs |
| Agilent TapeStation 4200 | PCR product check | size in bp, ng/µL, pass or fail |
| BMG CLARIOstar Plus | plate reader | absorbance at 510 nm |

with the captions *"Agents replay real recorded runs, packaged as RO-Crate"* and *"Faults injected on purpose, to prove the check catches them"*.

The dry-lab Design chain is 11 steps, physical through computational: collect environmental sample (sterile sediment corer) → extract metagenomic DNA (DNeasy PowerSoil Pro Kit, cat 47016) → prepare shotgun library (Novogene) → sequence (Novogene, Illumina NovaSeq X Plus) → trim and quality filter (read trimmer v0.39) → assemble (metagenome assembler v1.4.2) → predict protein coding genes (gene caller v2.6.3) → annotate (domain scanner v5.72) → cluster (clustering tool v2.0) → select the panel (panel designer v0.9) → specify constructs (codon optimiser v2.1). Scale figures stated in the crate and on diagram 07: **47,812 contigs; 1,612,043 predicted proteins; 96 selected sequences; 61.4 gigabases yield; assembly N50 3,140 bp.**

**The four handovers, as this use case names them** (slide 3, a 14-step DESIGN/BUILD/TEST/LEARN map):

| # | Name on the diagram | Between |
|---|---|---|
| Handover 1 | **Construct specification** | Design → Build |
| Handover 2 | **Assembly outputs and QC results** | Build → Test |
| Handover 3 | **Screening results** | Test → Learn |
| Handover 4 | **Model predictions and recommendations** | Learn → Design (dashed return arrow) |

The 14 steps: DESIGN 1 search metagenome for enzyme candidates, 2 filter on predicted structure and solubility, 3 select a diverse panel, 4 prepare DNA designs for synthesis; BUILD 5 synthesise DNA (vendor), 6 rehydrate and amplify DNA (PCR), 7 check PCR products, 8 make protein (cell-free or fermentation); TEST 9 run enzyme reactions with substrates, 10 measure on plate reader, 11 call hits (statistics); LEARN 12 record results against each candidate, 13 compare hits with sequence and structure, 14 recommend what to test next (drawn **dashed**, unlike 1–13). Slide 4 draws a "✓ contract" gate on Handover 2 and Handover 3.

`agents/README.md`, verbatim: *"Checking agents, one per handover. An agent reads the RO-Crate produced at the end of one phase and decides whether the receiving phase can accept it. It checks the shape of the data, meaning whether the required fields are present, and the semantics, meaning whether those fields mean what the receiving phase expects them to mean."* The name "Sentinel agents" appears in this folder only as an open question.

**The diagrams and what they specify.** `06_design_handover_crate.png` is the most precise specification in the whole repository — "The end-of-Design crate, at Process Run Crate level", subtitled *"every box below is one entry in the same `@graph`. The profile defines the provenance on the left. The entities on the right are ours to define."* Crate header: `@type: Dataset`; `conformsTo {"@id": "https://w3id.org/ro/wfrun/process/0.6"}` **MUST**; every `instrument` a `SoftwareApplication` with `name`, `url` and `version`, all **SHOULD**.

Left column, "What ran" — listed under the root's `mentions` (SHOULD), one `CreateAction` per tool execution, and *"An action's `result` is the next action's `object`, by convention only. The profile guarantees no chain."* Six steps are drawn with instrument MUST, result SHOULD, object MAY:

| Step | `instrument` (MUST) | `result` (SHOULD) | `object` (MAY) |
|---|---|---|---|
| Assemble | assembler v1.4.2 | `contigs.fasta` | — |
| Call genes | gene caller v2.6.3 | `proteins.faa` | `PropertyValue` "gene calling mode" = "open ends" |
| Annotate | domain scanner v5.72 | `annotations.tsv` | `CreativeWork` "reference domain database" version "2026-02" |
| Cluster | clustering tool v2.0 | `clusters.tsv` | `PropertyValue` "sequence identity threshold" = "0.90" |
| Select panel | panel designer v0.9 | `panel.faa` | `PropertyValue` "panel size" = "96"; plus `agent` and `endTime` (SHOULD) |
| Specify constructs | codon optimiser v2.1 | `constructs.gb` | — |

Right column, "What is handed over" — *"Process Run Crate defines none of these entities or fields. This is the part our interoperability contract has to specify."*

| Entity | Cardinality | Required content |
|---|---|---|
| Plate | the physical layout | `identifier`; `format: 96 wells`; well → construct map |
| Protein | one per candidate, 96 in all | database identifier; amino acid sequence, inline or pointed to; predicted, or experimentally confirmed; group identifier and group size; distance to group centre (1 minus fractional identity) |
| Construct | one per item to synthesise, 96 in all | `identifier`; codon-optimised DNA sequence; promoter and terminator parts, and forbidden restriction sites; plate and well position; `isBasedOn` → the Protein |

Footer packaging rules: in the crate, `panel.faa` and `constructs.gb`; held elsewhere and referenced by URL, `contigs.fasta`, `proteins.faa`, `annotations.tsv`, `clusters.tsv`. Paired-end reads SHOULD be one `Collection` with `hasPart` and a `mainEntity`; a renamed file SHOULD keep its original name in `alternateName`; and **"Core RO-Crate has no checksum property."**

`05_plate_contract.png` states the rule that needs no string matching: *"Design states the intended layout. Build records what arrived. The agent computes the difference. Both are keyed by well position, never by sequence name, so there is no string match to get wrong. Nobody has to notice the failures. They fall out of the two records."* Its three panels are the intended layout ("96 wells, every one spoken for"), the delivered plate ("from the vendor's plate map, after synthesis") and the difference ("5 wells. The sequences that failed synthesis"). The crate enforces the separation in prose: `#plate-AB-12-01` says *"What Design asked the synthesis vendor for. It is NOT a record of the plate that arrives."*

`01_what_is_rocrate.png` establishes that `ro-crate-metadata.json` is required and data files optional; that each entry's `@id` is the path of the thing it describes; that an Attached package has relative `@id`s so the file must be present, while a Detached package (1.2 onward) has no directory and every data entity carries an absolute web address; that the file was named `.jsonld` up to RO-Crate 1.0; and that **core RO-Crate defines no checksum property**.

`02_what_is_process_run_crate-2.png` gives the profile stack — *"Three profiles. Each includes the rules of the one before it, and a crate lists every profile it follows in `conformsTo`"*:

| Profile | URI | What it adds |
|---|---|---|
| Process Run Crate | `ro/wfrun/process/0.6` | tools that ran. No workflow file. |
| Workflow Run Crate | `ro/wfrun/workflow/0.6` | adds the workflow as `mainEntity`, plus an action for the whole run |
| Provenance Run Crate | `ro/wfrun/provenance/0.6` | adds the steps inside that run |

**This use case sits at the first level only.** The same diagram notes that an action is not a file, so its identifier begins with `#`, and that *"The version is part of the URI."*

**The example crate.** `exampleROcrates/design-to-build-simple/` *is* the crate (its README says so in bold), and it covers **Handover 1 only**. `@context` is a two-element array (`ro/crate/1.3/context` plus `ro/terms/workflow-run/context`). **105 entries in `@graph`**:

| Count | `@type` |
|---|---|
| 54 | `PropertyValue` |
| 11 | `File` |
| 11 | `CreateAction` |
| 10 | `SoftwareApplication` |
| 6 | `CreativeWork` (descriptor, the plate, 4 constructs) |
| 4 | `BioChemEntity` (the proteins) |
| 3 | `["Sample","CreativeWork"]` (sample, DNA extract, library) |
| 2 | `Collection` (raw reads, trimmed reads) |
| 1 each | `Dataset` (root), `["CreativeWork","Profile"]`, `ResearchProject`, `Person` |

Of the 11 `File` entries, 3 are relative paths inside the crate and 8 are absolute `https://example.org/...` URLs. The root's `hasPart` lists 9 entries; its `mentions` lists **20** (11 actions, 4 proteins, 4 constructs, 1 plate). `conformsTo` is declared in two places for two different things: on the metadata descriptor, `https://w3id.org/ro/crate/1.3` (the RO-Crate version); on the root data entity, `https://w3id.org/ro/wfrun/process/0.6` (the profile), which is also materialised as its own graph entry.

Provenance is **reverse lookup over `CreateAction`**, stated in the README verbatim: *"There is no property that points from a thing to the action that made it. RO-Crate has no `resultOf`. The traversal is a reverse lookup: to find what produced entity X, scan `@graph` for the `CreateAction` whose `result` contains X. To go back another step, take that action's `object` and repeat."* It adds: *"The trimmed reads are a separate entity from the raw reads precisely so that this walk terminates instead of looping."* All 11 actions carry `instrument`, `object`, `result`, `agent`, `endTime` and `actionStatus`; chaining is by convention only, with no explicit link property. Derivation between non-file entities uses `isBasedOn` (8 uses), containment uses `isPartOf` (7), and entity-level metadata uses `additionalProperty` → `PropertyValue` (12 entities).

Ten run parameters ride on the actions as `PropertyValue`s, with `unitText` on every numeric one: sequencing platform (Illumina NovaSeq X Plus), read layout (paired end), read length (150 bp), sequencing yield (61.4 Gb), minimum contig length (500 bp), assembly N50 (3,140 bp), **gene calling mode (open ends)**, annotation reference database release (2026-02), sequence identity threshold (0.90), panel size (96 sequences). The one that matters most: *"open ends permits a prediction running off the end of a contig, so a sequence may be a truncated fragment"* — and *"Gene calling mode matters most, and it is why the chain has to reach further back than the preceding step. Knowing the mode alone does not tell you the fragment risk. You also need to know whether the contigs were short, which depends on the assembly, which depends on the coverage, which depends on the sequencing run."* **ENR-003 is marked `right partial`**; the other three are `complete`.

MIxS field names are used verbatim on the sample (`collection_date` 2026-03-02, `geo_loc_name` Iceland: Hveragerdi, `env_medium` hot spring sediment, `depth` 0.15 m, `temp` 68.4 °C, `ph` 6.8) — *"For the sample, the agreed vocabulary already exists and a contract only has to require it."*

The crate declares four known problems itself: a human step has nothing to put in `instrument` (the ranking tool is named as instrument and the person as agent, *"a reasonable reading but not a settled one"*); physical things (corer, extraction kit, sequencing service) are recorded as `SoftwareApplication` with a catalogue number standing in for `version` — *"This is the clearest gap the bioprospecting use case exposes"*; `version` vs `softwareVersion` (11 and 10 uses respectively, both set); and *"One crate describes one Design run"* — a panel assembled from two runs with different gene calling modes cannot be described in this shape.

Validation as reported: passes `rocrate-validator` 0.13.1 against **RO-Crate 1.3** with `--skip-availability-check`. With availability checks on it fails because `example.org` placeholders do not resolve — *"a property of the simulated data, not a fault in the crate."* The profile check fails because the validator implements Process Run Crate 0.5 (assuming RO-Crate 1.1) and the crate targets 0.6 — *"Do not 'fix' the crate to satisfy the older checker."* Three hand checks pass, *"because no validator makes them"*: nothing unreachable from the root, no reference to a missing entry, no action consuming what it produces — *"they are cheap to write and they caught real faults in a file that had already passed validation."*

**What it requires of a shared framework** — the seven checks, quoted from the crate README: (1) does it parse, and is it valid RO-Crate; (2) does the root declare `conformsTo` the profile; (3) does every referenced `@id` resolve, and does every relative `@id` correspond to a file present; (4) can every entity be reached from the root, and does no action consume what it produces; (5) is there an unbroken chain of `CreateAction` entries from the handed-over files back to the sample; (6) are the required parameters present, with the agreed `name` strings and a `unitText` on every numeric one; (7) do the values mean what Build expects. Then:

> "Checks 1 to 5 are generic and structural, and a crate can fail them while passing every schema check there is. Checks 6 and 7 are the contract, and they are the part nobody has written down yet."

Check 7 is explicitly not pass/fail: *"Gene calling mode set to open ends is not an error, but it is a flag that Build must act on."* Plus a vocabulary for laboratory equipment that `SoftwareApplication` is standing in for; the equipment-simulator unit from slide 5 (a Request in; Agent, what it is, what is in each well, and a fault switch inside; a Result file and Provenance out); and, from `exampleROcrates/README.md`, *"at least one crate that satisfies its contract and one deliberately broken crate"* per handover.

### 3.2 Directed evolution — BrunoAGSa, Pablo Carbonell

**The science and its citation.** `directed_evolution/README.md`, line 7, verbatim:

> **Case study:** Zhang et al. (2025), *Nature Communications*, [Integrating protein language models and automatic biofoundry for enhanced protein evolution](https://www.nature.com/articles/s41467-025-56751-8). The study evolved a tRNA synthetase over **four DBTL rounds in 10 days**, testing **96 variants per round** and reporting **up to 2.4× improved activity**.

The References section adds the code link, `https://github.com/HICAI-ZJU/PLMeAE`. Both diagrams name the target specifically: **pCNF-RS**. The README does not state the organism, the 2.4× baseline, or what activity is measured against; the diagram's Test stage names **sfGFP fluorescence** as readout, so the assay is implied but never stated in prose.

**DBTL stages, tools, instruments** (README table, verbatim):

| Stage | Techniques, software, equipment | Output |
|---|---|---|
| Design | ESM-2 protein language model, zero-shot mutation ranking, Python/PyTorch | Candidate enzyme variants |
| Build | Site-directed mutagenesis (PCR, DpnI), bacterial transformation, automated liquid handling (Tecan EVO/Echo/Fluent) | Constructed and tracked variant library |
| Test | Cell cultivation, fluorescence/OD600 assays, CLARIOstar plate reader, Cytomat incubators, Sanger sequence verification | Experimental measurements and QC records |
| Learn | ESM-2 sequence representations, multilayer perceptron, supervised fitness prediction, PyTorch | Updated model and next-round predictions |

Immediately after the table, the provenance boundary, verbatim: *"Equipment and methods above refer to the **published experimental workflow**; allocation to interfaces below is **our proposal**."* Both diagrams repeat it in their footers — v1 *"Proposed architecture · not implemented in the original study"*, v2 *"Experimental tools from Zhang et al. (2025) ● Interface agents and RO-Crates are the proposed theoretical architecture, not used in the original experiment."*

**Three tool lists exist and none is authoritative.** v2 **adds** "ML-guided variant selection" (Design), "Python primer design" (Build) and "Momentum DataMiner (data acquisition/processing)" (Test); v2 **drops** "ITC sampling" and the explicit "Python · PyTorch" from Design, "Transformation · colony picking" from Build, "sfGFP fluorescence" and "assay QC" from Test, and "PyTorch training" and "variant ranking" from Learn. None of the three additions is in the README table.

**The four handovers, as this use case names them** (README table):

| Interface | Agent responsibilities | Handoff |
|---|---|---|
| Design → Build | Validate selected sequences, check feasibility and primer requirements | Variant list, design specifications, build plan |
| Build → Test | Verify sample identity, sequence confirmation, construction quality and assay readiness | Sample/plate maps, verified constructs, QC status |
| Test → Learn | Normalize and curate measurements; check controls, replicates, outliers and missing data | Validated fitness dataset and metadata |
| Learn → Design | Interpret model results and uncertainty; prioritize mutations and next-round constraints | Updated design objectives and candidate priorities |

**The diagrams and what they specify.** v1 (`dbtl_interface_agents.svg`) carries a badge *"4 transition agents · 1 coordination layer"*, a key (*"Solid arrows: DBTL flow through interface agents · Dashed lines: coordination and oversight"*), and names handoffs as untyped prose payloads: "variant list + build plan", "verified samples + QC", "QC-approved fitness data", "new design specification". Its Coordinator has four bullets: Data provenance / Handoff validation / Exception handling / Human approval gates.

v2 (`DBTL_interface_agents_RO-Crates.svg`) replaces every payload with a named RO-Crate object and adds the structural heart of the revision: **every agent gains the identical bullet "Reads all four RO-Crates and packages the \<next\> RO-Crate."** Each handoff is then itemised — the Build RO-Crate carries "Validated variant list", "Primer sequences", "Plate map & build plan"; the Test RO-Crate "Verified library (IDs + sequences)", "Expression & assay setup", "QC status (pass/fail)"; the Learn RO-Crate "Cleaned, normalised activity data", "QC report (controls, outliers)", "Metadata (conditions, replicates)"; the Design RO-Crate "Design constraints", "Prioritised mutation sites", "Next library specifications (e.g., 96 variants)".

v2's store: a central dashed panel, **"Shared RO-Crate store"**, strap-lined *"All stages and agents read all four crates"*. **Four crates, one per DBTL stage.** Writes are strictly one-to-one — each stage box carries "Writes Design RO-Crate", "Writes Build RO-Crate", and so on. Reads are all-to-all — each stage box also carries a "Reads D B T L" chip strip with its own letter highlighted.

| Crate | Seed | Adds |
|---|---|---|
| Design | objective, library size | ranked variants, rationale |
| Build | available build equipment | primers, plate map, build log |
| Test | available assay equipment | raw reads, QC flags, run log |
| Learn | model and compute limits | trained model, predictions |

The numbered protocol, quoted in full: **0 Seed** *"Before round 1, the researcher seeds the crates with constraints, e.g., available equipment."* **1 Package** *"Each interface agent packages the next stage's crate with validated inputs."* **2 Record** *"Each stage adds its outputs and provenance to its own crate."* **3 Share** *"All stages and agents read all four crates, so Design can respect Build and Test limits."*

That last clause is the architectural claim: constraints must flow **backwards**, not just forwards around the cycle. The Coordinator in v2 is a hexagon — *"Tracks decisions, provenance, exceptions and human approvals; curates the RO-Crate store"* — gaining crate curation and losing "Handoff validation" as an explicit line, which moves into the agents. The human researcher is promoted from invisible to a first-class box with an arrow into the D→B agent: *"Sets the objective, seeds the RO-Crates with constraints and approves rounds."* The legend grows from 2 items plus an arrow key to 8 items covering every node and edge type.

One-sentence summary of the change: v1 models the cycle as four agents passing messages forward around a ring; v2 replaces the messages with four persistent, globally-readable crates that accumulate provenance, are seeded with physical constraints before round 1, and are read by everyone — turning the handover from a transient payload into a durable, addressable artefact.

**What it requires of a shared framework.** The contract unit must be an RO-Crate, not a message. Four per-stage profiles, not one schema. A seed/adds distinction a contract can assert separately. Constraints as machine-readable content, so "checks feasibility against equipment limits" can be mechanical — which implies a vocabulary for equipment and capacity, not free text. Backwards readability, cross-stage and cross-round, with crate addressing and versioning. Round identity (four rounds, 96 variants each, and which crate belongs to which round). Provenance accumulation as mandatory, not optional. A QC verdict concept a gate can act on. Sample and plate identity as a joinable key that survives the crate boundary. An exception path plus a blocking human approval — at least two outcomes beyond pass/fail. **Packaging as a role distinct from writing** — a framework modelling only "producer writes, consumer validates" is one role short. A store maintained independently of the agents. Lab-automation vocabulary (Tecan EVO/Echo/Fluent, CLARIOstar, Cytomat, Momentum DataMiner, Sanger, OD600, sfGFP). And a model artefact plus an uncertainty quantity, not just tabular results.

### 3.3 Biomanufacturing — José Campos / josedrcampos, Pablo Carbonell

**The science and its citation.** The README, verbatim and complete, is one sentence:

> Worked example grounding the DBTL interoperability discussion: the SYNBIOCHEM automated pipeline for (2S)-pinocembrin in *E. coli* (Carbonell et al., Communications Biology 2018, Fig. 1), annotated with four proposed interface agents on the stage transitions plus a coordination layer.

Target compound **(2S)-pinocembrin**, a flavanone; chassis ***E. coli***. No DOI anywhere in the folder. Both the agents diagram and Fig. 1 end the loop at a decision "Optimised" → **"process development and scaleup"**; the agents diagram labels that green box *"Optimised → process development · Chassis and media screening, genome integration, scale-up"*.

**DBTL stages, tools, instruments.** The agents diagram gives short lists; crate diagram v1 gives the detailed ones:

| Stage | Crate diagram v1 |
|---|---|
| Design — "Select pathway, enzymes and parts library" | RetroPath retrosynthesis; Selenzyme enzyme selection; PartsGenie RBS + codon design; **SBC-DoE orthogonal arrays and Latin square (R planor, DoE.base)**; DominoGenie worklists; **ICE / SBOL** |
| Build — "Assemble and verify pathway plasmids" | Commercial DNA synthesis of parts; PCR part prep (5'-P primers, DpnI); ligase cycling reaction (LCR) assembly; **Hamilton STAR** worklist-driven liquid handling; **QIAprep 96**, digest + CE, Sanger |
| Test — "Cultivate strains and quantify titers" | Chassis transformation, colony picking; 96-deep-well growth, IPTG induction; automated methanol/water extraction; **Acquity UPLC – Xevo TQ-S (QqQ), MRM quantification**; ProteoWizard mzXML + R peak scripts |
| Learn — "Infer design rules from titer data" | Standard least squares (**JMP**); F-test p-values per design factor; copy number, promoter and gene-order effects; statistical machine learning models; design rules for the next library |

The deck adds two tools the diagrams never mention: **DNABot** (Build, slide 7) and **OptBioDes (Galaxy SynBioCAD)** (Design/DoE, slide 4).

**The four handovers, as this use case names them** (agents diagram, verbatim):

| Agent | Bullets | HANDOFF |
|---|---|---|
| D→B Design-to-Build | Expand DoE library into part lists / Flag risky junctions · bridging oligos / **Register parts in ICE · emit worklists** | construct library + LCR recipes |
| B→T Build-to-Test | Reconcile verified vs failed constructs / Map plasmid IDs to wells and runs / Release only sequence-perfect clones | verified strains + plate map |
| T→L Test-to-Learn | Gate peaks by LOD / LOQ and calibration / Normalize titers across replicate clones / Join titers to design factor table | curated titer-design dataset |
| L→D Learn-to-Design | Rank factor effects and uncertainty / Turn effects into library constraints / Decide DoE vs full-factorial next round | focused library specification |

Coordinator, "cross-stage oversight", four bullets: *"FAIR provenance (ICE / SBOL)"*, *"Handoff validation"*, *"Exception handling · failed builds"*, *"Human approval gates"*. Drawn in the centre with dashed links to all four agents — oversight, not data flow.

**The diagrams, and the two-versions problem.** Crate diagrams v1 and v2 have identical structure (four stages, four agents, a shared store of four crates, a Coordinator hexagon, an 8-item legend, a 0–3 protocol, a human researcher box) and v2 was added without deleting v1. Every change is de-specialisation from pinocembrin to a generic microbial workflow — and the cost is exactly the detail a contract needs:

| Lost in v2 | What v1 had |
|---|---|
| Identifier standards | ICE / SBOL, in the Design tool list and in the D→B handoff payload |
| Named instruments | Hamilton STAR, QIAprep 96, Acquity UPLC – Xevo TQ-S, ProteoWizard, JMP, R planor/DoE.base |
| Measurement gating language | "Validates MRM peaks against calibration curves, **LOD / LOQ limits and blanks**" |
| Units | "Curated titer table (**mg/L**)", OD600 |
| Concrete design constraints | "Design constraints (**ColE1, CHI first, PAL at the 3' end**)" |
| Library size | "Next library spec (**36 constructs**)" → "e.g., full-factorial" |
| The scale-up gate | Coordinator "**gates scale-up**" |
| The DoE decision | L→D "**Chooses DoE or full factorial and the next library size**" |

Seeds also shift towards equipment in v2 (Build seed becomes "robots, vendors, plate formats"; Test "assay equipment and limits"; Learn "model and compute limits"), and the D→B agent's job becomes *"Checks designs and assembly feasibility against equipment limits"*.

**The deck specifies a different architecture from the diagrams.** `docs/BH DBTLHub Biomanfacturing case Workflows.pptx` is an earlier hand-drawn "where do the interfaces go" sketch, never revised since the diagrams landed and not referenced by the README. Slide 3 carries the complaint that motivates the project, verbatim:

> "Issues: Findable code / Tools non-usable without modification / Requirements of external databases (reaction rules, genes, genetic parts) would be nice to allow user-selection / **Common input-output to allow swappable code**"

Slide 4 is the richest and the most contradictory. It attaches **an RO-Crate to each individual tool step inside Design** — "Pathway / RetroPath" has an RO-Crate label below it, so do "Enzyme / Selenzyme" and "DoE / OptBioDes (Galaxy SynBioCAD)", and the fourth box reads **"DNA parts / RO-Crate?"**, with the question mark inside the box. It also places an **"AI AGENTS"** box *inside* Design, with one arrow into the ranking/pathway-selection region and one into the DoE region, and carries the deck's only speaker note: *"Ranking made by Agent / Formula"*. And it carries the only objectives and constraints stated anywhere in the use case: a "Bioprocess context" box reading *"Equipment / **Objectives:** Titer, Rate, Yield / **Constraints** Budget / …"*. Neither SVG carries any of this. Top-right of the same slide is a leftover title from another use case: *"Study case 3: Directed evolution workflow"*.

Slides 5 and 6, "Agent-based Design-Build Interface", frame the handover as DESIGN/Output → BUILD/Input. Slide 5: *{list of sequences + RO-Crate provenance info + Context info} → {Synthesis Protocol}*. Slide 6 adds an **AGENT** box in the centre and **three labelled inputs down the left edge, each with its own arrow into the agent**: **TOOLS** (level with "List of sequences"), **WORKFLOW** (level with "RO-Crate provenance info"), **PROMPT** (level with "Context info"). The output is *"How to: Experimental planning / Synthesize the DNA parts / Assembly the pathways / which protocol / which equipments"*. Bottom right is a screenshot of an actual LLM answer — a numbered "4. Library construction workflow" with Level 0/1/2 Golden Gate assembly and yeast transformation — which is **Golden Gate into yeast with TyrH**, not LCR into *E. coli* for pinocembrin.

Slide 7 is Build ("Assembly protocol → DNA synthesis → Pathway assembly → Sequence verification", annotated *"Tool: DNABot,"* with a trailing comma). Slide 8 is Test, split into **Discrete (samples)** and **Continuous (online, realtime data)**, with a Cell-free box feeding Biosensor design / Screening / Pathway regulation, and a floating note *"\*Could swap these around"*. Slide 9 is Learn, with the question list: *"How to improve TRY / What are the next experiments? / Which pathways should be built? / Chassis optimisation / suitability / Scaling-up / Check if models should be re-parameterised / Decision support: Which changes in the experimental protocol?"*

**The provenance mechanism that is not RO-Crate.** ICE / SBOL. The agents diagram makes it the Coordinator's first responsibility (*"FAIR provenance (ICE / SBOL)"*) and the D→B agent's third bullet (*"Register parts in ICE · emit worklists"*); crate diagram v1 lists it among Design's tools and in the D→B handoff payload. ICE is the JBEI Inventory of Composable Elements part registry; SBOL is the Synthetic Biology Open Language. Here they carry part and plasmid identity and provenance, with RO-Crate as run-level packaging around them. Secondary, in the deck: **git** (logo) and a **"Package manager (pypi, conda)"** box for the code side of reproducibility — in boxes parked below the slide edge.

**What it requires of a shared framework.** Cross-stage reads so Design can respect Build and Test limits. A constraint/limit object, not only a result object, surviving a full cycle. Round-0 human seeding and human approval gates between rounds. Per-stage write isolation with shared read — a four-writer, shared-read store with per-stage ownership. Carryable identifier standards: the B→T agent's job *is* identifier continuity (plasmid IDs → barcodes → well positions → sample IDs). Measurement **validity**, not just values: LOD/LOQ gating, calibration curves, blanks, replicate normalisation, mg/L, pass/fail — *"The T→L contract must be able to reject an in-range-looking peak."* Failure reporting, not only successes. A join from a measurement back to its DoE factor levels. Nesting or aggregation of crates, if the deck's per-tool crates are real. An agent input surface of TOOLS + WORKFLOW + PROMPT + RO-Crate provenance + context, with the agent's experimental plan as a first-class handover artefact. And code and environment provenance alongside data provenance.

### 3.4 Comparison across the three

| | Bioprospecting | Directed evolution | Biomanufacturing |
|---|---|---|---|
| Owner | Anil (Neil) Wipat, Newcastle | BrunoAGSa; Pablo Carbonell | José Campos / josedrcampos; Pablo Carbonell |
| Science | Ene-reductases from hot-spring sediment (own, simulated) | pCNF-RS tRNA synthetase | (2S)-pinocembrin in *E. coli* |
| Citation | none — the use case's own pipeline | Zhang et al. 2025, *Nat Commun*, s41467-025-56751-8 | Carbonell et al. 2018, *Communications Biology*, Fig. 1 (no DOI) |
| **Provenance mechanism** | RO-Crate + **Process Run Crate 0.6**, reverse lookup over `CreateAction`; MIxS on the sample; **SHACL proposed** for the rules | RO-Crate, unversioned, no profile, no vocabulary, no PID scheme named | RO-Crate **plus ICE / SBOL** for part and plasmid identity (v1 only); git + pypi/conda for code |
| **Crate granularity** | **one crate per Design run** ("One crate describes one Design run") | **one crate per DBTL stage**, four in a shared store | **one per stage** in both SVGs; **one per tool step** on deck slide 4, with "DNA parts / RO-Crate?" unresolved |
| What their agents do | Check shape and semantics; refuse; compute the intended-vs-delivered plate difference; flag rather than fail on `open ends` | Validate, curate, translate, **read all four crates and package the next one** | Validate, reconcile verified vs failed, gate peaks by LOD/LOQ, join titres to factors, **read all crates and package the next** |
| Coordinator | not named | "Tracks decisions, provenance, exceptions and human approvals; curates the RO-Crate store" | "FAIR provenance (ICE / SBOL)", handoff validation, exception handling, human approval gates; v1 also "gates scale-up" |
| Human role | `#operator`, a bare `Person` with a name | first-class box: sets objective, seeds crates, approves rounds | first-class box: sets target compound, seeds chassis/media/platform limits, approves rounds |
| MUST/SHOULD/MAY | yes, on diagram 06 — but only on the profile-derived left column | none | none |
| **Implemented** | a real 105-entry crate with 4 data files, validator-checked | **nothing** | **nothing** |
| **Drawn only** | Handovers 2, 3 and 4; the broken crates; all SHACL | everything | everything |
| Units stated | `unitText` on all 10 numeric parameters; °C, m, bp, Gb | OD600 (implicit) | mg/L, OD600 (v1 only) |
| Links to `sentinel/` | none | none | none |

---

## 4. The convergence, and the three disagreements

### 4.1 What all three found independently

Three teams, three sciences, no shared design document, and the same architecture: **four interface agents, one per DBTL handover, plus a coordinator.**

| | Bioprospecting | Directed evolution | Biomanufacturing |
|---|---|---|---|
| Four agents at the four handovers | "Checking agents, one per handover" | "4 transition agents · 1 coordination layer" | "4 transition agents · 1 coordination layer" |
| A coordination layer | not named | Coordinator hexagon | Coordinator, "cross-stage oversight" |
| RO-Crate as the carrier | yes, specified in detail | yes, named per stage | yes, plus ICE/SBOL |
| A gate that can refuse | "decides whether the receiving phase can accept it" | "packages … with validated inputs" | "Release only sequence-perfect clones" |
| A human approval point | — | "approves rounds" | "Human approval gates" |

Two of the three use the identical phrasing "4 transition agents · 1 coordination layer", because Pablo Carbonell drew both. Bioprospecting arrived at the same count independently, and `sentinel/` implements exactly four sentinels and one coordinator. The convergence is the project's strongest result: the interface is where the problem lives, and everybody found it in the same place.

### 4.2 Disagreement 1 — the provenance mechanism

| Position | Held by | Evidence |
|---|---|---|
| **RO-Crate + Process Run Crate 0.6**, with the version in the URI, provenance read by reverse lookup over `CreateAction`, and the rules written in **SHACL** | Bioprospecting (Wipat) | `docs/06_*.png` makes `conformsTo https://w3id.org/ro/wfrun/process/0.6` a **MUST**; `02_*.png` states *"The version is part of the URI"*; the crate declares the profile on the root data entity and materialises it as a graph entry; `questions.md` proposes SHACL once |
| **RO-Crate, profile unspecified**; the crate is simply "the Build RO-Crate" | Directed evolution (Carbonell, v2) | An 8-item legend naming "RO-Crate per stage"; no profile URI, no metadata standard, no vocabulary, no identifier scheme anywhere in the folder |
| **RO-Crate as run-level packaging around ICE / SBOL** carrying part and plasmid identity | Biomanufacturing (v1) | Coordinator bullet *"FAIR provenance (ICE / SBOL)"*; D→B bullet *"Register parts in ICE · emit worklists"*; D→B handoff item *"ICE / SBOL part and plasmid IDs"*; ICE/SBOL also in the Design tool list |

**Checked.** I confirmed by grep that crate diagram **v2 of biomanufacturing deletes every ICE/SBOL mention**, replacing the handoff item with the neutral "Part and plasmid designs (IDs)" — so that use case's own newer diagram has no identifier standard at all, and v1 is the only place the standard exists. I also confirmed that **no `.ttl` or SHACL file exists under `bioprospecting/`**: SHACL is named exactly once, in `questions.md`, and never instantiated there. `sentinel/` has one SHACL file (162 lines) and never runs it.

What hangs on this: whether a contract can be a graph shape at all. Bioprospecting's position makes the contract a SHACL shape over a profiled crate; biomanufacturing's position makes crate provenance secondary to a part registry; directed evolution's position leaves the contract with nothing to bind to.

### 4.3 Disagreement 2 — crate granularity

| Position | Held by | Evidence |
|---|---|---|
| **One crate per run** (the whole DBTL cycle writes one crate, grown by the phases) | `sentinel/` | `crate_store.py` — *"One crate per run, that grows"*; `demo_cycle.py` grows one crate from 2 to 55 entities across all four phases |
| **One crate per phase/stage**, four in a shared store | Directed evolution v2; biomanufacturing both SVGs | Legend on both diagram sets: *"RO-Crate per stage (one crate for each DBTL stage)"*; stage badges "Writes Design RO-Crate" etc. |
| **One crate per Design run** (one phase, one run) | Bioprospecting | Crate README known problem 4: *"One crate describes one Design run"*; Open question 1 on `docs/06_*.png`: *"every parameter above describes the whole run, not one sequence, so one crate holds exactly one Design run. A panel assembled from two runs with different gene calling modes cannot be described this way."* |
| **One crate per tool step** | Biomanufacturing deck, slide 4 | RetroPath, Selenzyme and OptBioDes each carry an "RO-Crate" label; the DNA-parts box reads **"DNA parts / RO-Crate?"** |

**Checked.** This is a four-way split, not a three-way one, and the fourth position contradicts the same use case's own diagrams: the biomanufacturing SVGs say four crates per cycle, the biomanufacturing deck says one per tool step inside a single stage, and nothing in the folder reconciles them. I confirmed the briefing's reading against both SVGs and the deck's slide-4 geometry.

What hangs on this: whether the provenance chain is one traversal or a join across files. `sentinel/`'s `demo_cycle.py` makes the claim explicit — *"the whole cycle is one traversal, with no backlink to follow and no second file to open"* — and printed a 32-node chain to prove it. Under a four-crate model that same chain crosses three crate boundaries and needs a join key per boundary. Under a per-tool-step model it needs crate nesting or aggregation, which no profile on the table defines.

### 4.4 Disagreement 3 — crate lifetime across rounds

| Position | Held by | Evidence |
|---|---|---|
| **Undefined** — and the two clues point opposite ways | Directed evolution; biomanufacturing | *"Round 0: the researcher seeds each crate with constraints **before the first cycle**"* suggests seeding happens once and the four crates persist; *"Each stage adds its outputs and provenance to its own crate"* suggests growth. Four rounds in 10 days are run, and nothing says whether there are 4 crates in total or 4 per round (16). Neither diagram defines a round boundary, a version, or whether round-2 Design reads round-1 or round-2 Build. |
| **One crate per run, and a run is one cycle**; what crosses rounds is `reads` + `limits` with a checksum | `sentinel/` | `TAKE_A_HANDOVER.md` §4a: *"a limit is this run's equipment and this round's budget, and it changes between rounds. Putting it in the profile would freeze it"*, and record the `checksum` of what you read, because *"a shared crate grows between rounds."* |
| **One crate, one Design run** — explicitly cannot span two runs | Bioprospecting | Known problem 4 and Open question 1, above |

**Checked.** The directed-evolution briefing flags this as its gap (g) and the biomanufacturing folder has the same silence. I confirmed that `sentinel/` is the only place where cross-round addressing has a mechanism: the envelope's `reads` array (`crate`, `role` ∈ {constraints, context, upstream}, `checksum`) and `limits` array (`quantity`, `value`, `unit`, `from`, `stated_by`). That is a design decision taken unilaterally by the framework, not a group agreement.

What hangs on this: whether a crate is an immutable record of one run or a mutable shared workspace. If crates persist and grow across rounds, every checksum in every contract is a moving target and `reads` must carry a version; if a crate is one run, the four-crate shared store has to be re-seeded every round and the "Design can respect Build limits" guarantee only holds within a round.

---

## 5. The shared framework (`sentinel/`)

### 5.1 The two agent kinds

The framework's own statement of the split, from `template/TAKE_A_HANDOVER.md`:

| | **phase agent** | **sentinel agent** |
|---|---|---|
| sits | inside a phase | between two phases |
| does | the work | the check |
| may | choose, rank, optimise, call a model | refuse |
| writes | its part of the run's crate | nothing |

The ordering matters and is stated twice in the code (`phase_base.py` lines 11–15): *"The sentinel is a **submodule** here, not a superclass… the phase agent is in charge, and the check is something it submits to rather than something that wraps it."*

Both derive from one ABC (`framework/agents/base.py`, 53 lines): class attributes `name`, `phase`, `consumes`, `produces`; a concrete `capabilities()`; one abstract `handle(task) -> Result`. `Task` carries `goal`, `inputs`, `contract`, `max_repairs=2` (*"bounded, or two agents ping-pong for hours"*). `Result` carries `status` ∈ {`ok`, `escalated`, `failed`}, `outputs`, `evidence`, `errors`, `engine` (*"which model ran, or `none`"*), `notes`.

**`PhaseAgent.handle()`** (52 lines, never overridden) does, in order: read `run_id` from the task; open the run's `CrateStore`; record `before = len(store)`; call `self.produce(...)`; `store.add(phase, entities, action, files)`; emit the trace line `"<phase>: wrote into the run crate - N new (before -> after entities)"`; **if the crate refused the addition, return `escalated`** — with the comment that this is not a contract failure, *"a later phase tried to change something an earlier one recorded. That is a disagreement about what happened, and no contract can settle it"*; then call `self.package(...)` and, if there is one and a sentinel exists, **submit** it, returning the sentinel's status, engine and errors as its own. *"The phase agent gets no special treatment for having written the crate itself."* A subclass supplies `name`, `phase`, `produce()`, optionally `consumes`/`produces`, `sentinel_class` and `package()`, and must never write `handle()`. `produce()`'s docstring: *"This is the only place the science lives. Everything else in this class is bookkeeping that should look the same in every phase."*

**`SentinelAgent.handle()`** (74 lines, never overridden) does four steps in order — **translate → validate → repair → escalate**. `translate()` defaults to returning the package the upstream phase already emitted. `validate(package, self.contract)` produces a report; the trace line names the contract `$id`, the profile, and PASS or FAIL with error and flag counts. The repair loop runs `while not report.ok and attempt < task.max_repairs`; a flag is never a repair candidate (*"A flag is not a defect to be patched away - it is something true about the data that the next phase has to be told"*); the engine sees only the non-blocking errors; any patch whose path is outside `allowed = {e.path for e in fixable}` is refused; and *"The validator is the authority: re-check, never trust the patch."* If nothing is fixable: *"repair N: every remaining error needs a decision, not a patch."* A subclass supplies `name` and `contract_name`, optionally `never_autofix` and `translate()`.

How little that costs, measured by AST over class bodies:

| agent | file lines | class body | methods | verdict |
|---|---:|---:|---|---|
| `BuildToTestAgent` | 30 | **4** | none | 3 declarations + the class line |
| `TestToLearnAgent` | 31 | **4** | none | 3 declarations |
| `LearnToDesignAgent` | 47 | **4** | none | 3 declarations |
| `DesignToBuildAgent` | 156 | 80 | `__init__` (4), `translate` (53), `provider_view` (16) | the one exception |
| `HandoverAgent` (template) | 126 | 50 | `translate` (25) | scaffold |

Three of four sentinels are literally three declarations:

```python
class BuildToTestAgent(SentinelAgent):
    name = "sentinel_b2t"
    contract_name = "build_to_test"
    never_autofix = NEVER_AUTOFIX
```

`sentinel_d2b.py` is long because its `translate()` projects a vendor order out of the crate and keeps the two joined; its docstring: *"Almost nothing here is auto-fixable, and that is a finding rather than a limitation."*

Phase agents cost more, because the science is theirs: `DesignPhaseAgent` 73 class-body lines (`produce` 38, `package` 28), `BuildPhaseAgent` 109 (`produce` 50, `package` 33, `_design_entities` 16), `TestPhaseAgent` 101 (`produce` 70, `package` 23), `LearnPhaseAgent` 130 (`produce` 87, `package` 35). Shared machinery nobody reimplements: `sentinel_base.handle` 74 lines, `phase_base.handle` 52, `validator.py` 737.

### 5.2 The one-crate-per-run model, and the crate as a third refuser

`framework/crate_store.py` (221 lines) holds one crate per run and grows it. Its docstring: *"An entity may be extended by a later phase… but a value already written is never silently replaced… because overwriting a recorded value is how a laboratory record quietly becomes wrong."*

An `Addition` reports `added`, `extended`, `conflicts`, `collisions`, `dangling`; `ok` is none of the last three. Since `ec80217` the addition is **atomic** — assembled on a copy and committed only if accepted — and a **collision** (one `@id` written twice for two different things inside one addition) is diagnosed separately from a **conflict** (a later phase changing what an earlier one recorded), because, in the code's words, *"merging them would hide the collision instead of reporting it."*

So there are three classes of refusal, owned by three different things: the **contract** refuses a package; the **crate** refuses an addition; the **vocabulary** refuses an unmapped key.

Real output, `python3 demo_cycle.py` at HEAD:

```
[phase_design] -> OK   design: wrote into the run crate - 28 new (2 -> 31 entities)
      validate against dbtl:design_to_build/0.1.0 [profile bioprospecting] -> PASS
[phase_build]  -> OK   build: 9 new (31 -> 41)   dbtl:build_to_test/0.2.0   -> PASS
[phase_test]   -> OK   test:  7 new (41 -> 49)   dbtl:test_to_learn/0.1.0   -> PASS
[phase_learn]  -> OK   learn: 5 new (49 -> 55)   dbtl:learn_to_design/0.1.0 -> PASS
  55 entities, 441 triples
      32 nodes, from what to make next back to the ground it came out of.

  A later phase tries to change a coordinate Design recorded:
      0 new, 1 CONFLICT  ->  ['#site/NS-01.dwc:decimalLatitude']
      nothing written; the crate still says 53.4712
  A later phase writes a reference to something not in the crate:
      1 new, 1 DANGLING  ->  ['#reading/R1.prov:wasDerivedFrom -> #sample/NOPE']
      nothing written; a join to nothing is not a forward reference
```

(The briefing recorded 462 triples here; at HEAD `run.nt` holds **441**, because the handover spine moved to its own file — see §8, defect F3. `ask.py` now reports `run.nt, handovers.nt - 543 triples, 76 subjects` for the same run.)

The framework's own commentary on the two refusals: *"No contract can settle two phases disagreeing about what happened, or notice a reference that points at nothing. They belong to the crate, and they only exist at all because the crate is shared."*

### 5.3 The contract / profile split

`load_contract(name, profile)` (`validator.py:102`) loads the contract JSON, then `_bind()` walks the whole document replacing each `{"x-pattern": "<key>"}` with `{"pattern": <the profile's regex>}` in place, and attaches the whole profile as `contract["x-dbtl-profile"]`, which is how every `from_profile` lookup in the ten check handlers resolves. The comment: *"The generic contract says 'this field is an identifier'; the profile says what an identifier looks like in this use case. Without a profile the structure is still checked, the formats simply are not."*

`demo.py` §3 proves it operationally. One hand-written biomanufacturing package, two profiles, verbatim output from my run at HEAD:

```
   [sentinel_b2t / biomanufacturing] -> PASS

   [sentinel_b2t / bioprospecting]   -> FAIL
     design_ref.items[0].design_item_id  bad_format  'PATH-001' does not match ^(CAND|CON|ENR)-[0-9]{3}$
     design_ref.items[0].accession       bad_format  'MetaNetX:MNXR104919' does not match ^(MGYP|UniProt|NCBI):[A-Za-z0-9_.]+$
     samples[0].sample_id                bad_format  'BM1-R1' does not match ^BP[0-9]+-[A-H][0-9]{2}$
     samples[0].design_item_id           bad_format  'PATH-001' does not match ^(CAND|CON|ENR)-[0-9]{3}$
     samples[0].location.container_id    bad_format  'REACTOR-1' does not match ^PLATE-[0-9]+$
     samples[0].location.position        bad_format  'R1' does not match ^[A-H][0-9]{1,2}$
     samples[0].qc.measurements          missing_quantity  'fragment_size': the profile requires this measurement
     samples[0].qc.measurements          missing_quantity  'dna_concentration': the profile requires this measurement
```

Eight errors: six `bad_format`, two `missing_quantity`. Same contract, same structure, different profile.

Where the two profiles differ. Identifier patterns:

| key | bioprospecting | biomanufacturing |
|---|---|---|
| `design_item_id` | `^(CAND\|CON\|ENR)-[0-9]{3}$` | `^(PATH\|CONS)-[0-9]{3}$` |
| `accession` | `^(MGYP\|UniProt\|NCBI):[A-Za-z0-9_.]+$` | `^(MetaNetX\|MNXR\|MNXM\|UniProt\|SBOL\|Rhea):[A-Za-z0-9_.:]+$` |
| `sample_id` | `^BP[0-9]+-[A-H][0-9]{2}$` | `^BM[0-9]+-[A-Z0-9]{2,4}$` |
| `container_id` | `^PLATE-[0-9]+$` | `^(FLASK\|REACTOR\|PLATE)-[0-9]+$` |
| `position` | `^[A-H][0-9]{1,2}$` | `^([A-H][0-9]{1,2}\|R[0-9]+\|single)$` |
| `order_item_id`, `recommendation_id` | `^ORD-[0-9]{3}$`, `^REC-[0-9]{3}$` | identical |

Bioprospecting also carries `_note_design_item_id`, an honest note that three spellings (`CAND-`, `CON-`, `ENR-`) are in use and *"Agreeing one is a group decision, not an agent's."*

Required measurements, **as corrected at `cd07cf2`** (read from the file at HEAD):

| handover | bioprospecting | biomanufacturing (HEAD) |
|---|---|---|
| `build_to_test` | `fragment_size` (bp, TapeStation 4200); `dna_concentration` (ng/uL, TapeStation 4200) | `sequence_verified` (dimensionless, Sanger verification of the assembled plasmid); `biomass` (**OD600**, 96-deep-well growth, plate reader) |
| `test_to_learn` | `blank_corrected_absorbance` (AU, CLARIOstar 510 nm, blank subtracted) | `titre` (**mg/L**, Acquity UPLC – Xevo TQ-S, MRM against a calibration curve, ProteoWizard + R) |
| `learn_to_design` | `predicted_activity` (U/mg) | `predicted_titre` (**mg/L**, *"in the same unit as the measurement that will test it"*) |

No overlap at all between the two columns. The provenance root is the same check with a different far end: bioprospecting walks back to `bioschemas:BioSample` / `Sample` within a `ResearchProject`, following `prov:wasDerivedFrom`, `prov:wasGeneratedBy`, `prov:used`, `isBasedOn`, `isPartOf`, with four required entity types plus a `one_of`, and the Process Run Crate dialect keys (`action_type`, `produces`, `consumes`, `root_within`, `dialects`). Biomanufacturing walks back to `bioschemas:BioChemEntity` with two required types, no dialect keys, and its own note: *"Here a construct does not trace back to a field site but to a registered part and a chassis strain. The chain is as rigid, the far end is a registry entry rather than a freezer."* `required_provenance.test_to_learn` is structurally identical in both: `dbtl:blankCorrected`, `dbtl:replicates`, `dbtl:withinRange` on every `dbtl:Reading`.

### 5.4 The four contracts and every check

| # | file | `$id` | handover name | envelope fields | checks |
|---|---|---|---|---:|---:|
| 1 | `design_to_build.schema.json` | `dbtl:design_to_build/0.1.0` | construct specification | 15 | **11** |
| 2 | `build_to_test.schema.json` | `dbtl:build_to_test/0.2.0` | assembly outputs and QC results | 13 | **5** |
| 3 | `test_to_learn.schema.json` | `dbtl:test_to_learn/0.1.0` | screening results | 12 | **3** |
| 4 | `learn_to_design.schema.json` | `dbtl:learn_to_design/0.1.0` | model predictions and recommendations | 11 | **5** |

All four carry the same `x-handover.source`: *"Anil Wipat, bioprospecting use case slides, dbtl-synbio/dbtlhub, 10 Nov 2026"* — the handover names come straight from that use case's slide 3.

**The shared envelope**, identical in all four: `contract` (const), `contract_version` (const), `profile` (enum: bioprospecting | biomanufacturing), `run_id` (`^[A-Za-z0-9._-]+$`), `produced_at` (`^[0-9]{4}-[0-9]{2}-[0-9]{2}T`), `produced_by` (object requiring `agent`, `tool`, `engine` — *"'engine' records the model used, or 'none' for a deterministic step"*). Plus the two reverse-flow fields: `reads` (array of `{crate (req), role (req: constraints|context|upstream), checksum}` — crates read but not produced) and `limits` (array of `{quantity, value, unit, from}` required plus `stated_by`) — *"the one piece of information in the cycle that travels backwards"*. Plus one mandatory backlink each: `crate_ref` (H1), `design_ref` (H2), `build_ref` (H3), `test_ref` (H4).

**Handover 1** requires `contract, contract_version, profile, run_id, produced_by, produced_at, crate_ref, crate, order, bindings`. `crate_ref` requires `path` (`ro-crate-metadata\.json$`), `conforms_to` (≥1 URL), `root` (const `"./"`), `checksum` (`^sha256:[0-9a-f]{64}$`). `crate` requires `@context` and `@graph` (≥3 items, each requiring `@id` and `@type`). `order` requires `provider`, `format` (`fasta|genbank|sbol`), `container_id`, `items` (≥1, each requiring `order_item_id`, `position`, `design_item_id`, `sequence_type`, `sequence_sha256`). `bindings` requires ≥1 `{design_item_id, crate_entity}`. Optional: `alignment` (whose `unaligned` must be empty), `target_list`, `crate_ref_missing_files` (must be empty), `reads`, `limits`.

All 11 of its checks:

| kind | code | what it catches | blocked by |
|---|---|---|---|
| `unique` | `double_booked_position` | two ordered sequences claim the same well of the order plate | both routes |
| `unique` | `duplicate_order_item` | this design item is ordered twice | `never_autofix` |
| `cross_ref` | `unbound_order_item` | ordered, but nothing says which crate entity it came from | both |
| `cross_ref` | `missing_crate_entity` | the binding points at an entity the crate does not contain | `never_autofix` |
| `provenance_chain` | `broken_provenance_chain` | no path of derivation from this sequence back to a physical sample | both |
| `required_provenance` | `missing_provenance` | the profile requires this property on this kind of entity | `never_autofix` |
| `empty` | `unaligned_key` | no term has been agreed for this key, so nothing can query it | `never_autofix`; the hint names the exact fix |
| `derived` | `checksum_mismatch` | the checksum does not match the crate it is supposed to attest | contract hint |
| `empty` | `missing_file` | the crate names this file and it is not there | contract hint |
| `entity_value` | `flagged_entity` | the crate states something about this entity that Build has to act on | contract hint: *"not auto-fixable, and not a defect in the crate: the crate is telling the truth"* |
| `within_limits` | `exceeds_stated_limit` | more constructs ordered than the receiving phase said it can build | contract hint |

**Handover 2** requires `design_ref` and `samples`. Envelope: `design_ref` (`package` + `items[]` of `{design_item_id, accession}`), `target_list`, `samples` (≥1, each requiring `sample_id`, `design_item_id`, `location{container_id, position}`, `qc{measurements[≥1] of {quantity,value,unit,method}, verdict: pass|fail}`), `provenance[{step, tool, ref}]`, `not_delivered[{design_item_id, reason, reported_by}]`, `reads`, `limits`. Its 5 checks: `double_booked_location` (two samples claim the same physical position), `duplicate_sample_id`, `unknown_design_item` (not in what Design committed to), `missing_quantity` (the profile requires this measurement), and `unaccounted_item` — Design committed to this item and the Build record neither contains it nor reports it as not delivered.

**Handover 3** requires `build_ref` and `results`, and its envelope adds `crate` — *"The run's crate, as it stands when this handover is made. Carried so the checks below can read what Test recorded"* — the field commit `a3d7765` added. Its 3 checks: `duplicate_sample_id`, `missing_quantity`, and **`unusable_reading`**, the "peak area is not flux" check: the profile demands `dbtl:blankCorrected`, `dbtl:replicates` and `dbtl:withinRange` on every `dbtl:Reading` before a model is fitted to it.

**Handover 4** requires `test_ref`, `model` and `recommendations`. `model` requires `name`, `version`, `trained_on[≥1]`, `fitted_at`, with optional `holdout{metric, value, n}`. Each recommendation requires `recommendation_id`, `rank` (≥1), `proposes{kind: variant_of|new_candidate|repeat_with_change, derived_from_design_item, change, sequence}`, `evidence[≥1]` and `predictions[≥1]` — and each prediction requires `quantity, value, unit, method` **and `uncertainty{value, unit, kind}`**, which is **the one place in the framework where uncertainty is mandatory**. Its 5 checks: `duplicate_recommendation_id`, `duplicate_rank`, `unsupported_recommendation` (cites a result that is not in the data it claims to have learned from), `unknown_design_item` (proposes a variant of something never built and measured this round), `missing_quantity`.

`python3 scripts/show_agents.py` at HEAD:

```
      sentinel       contract         checks  never fixed  state
  H1  sentinel_d2b   design_to_build  11      11        working, custom translate()
  H2  sentinel_b2t   build_to_test    5       5         working, no logic
  H3  sentinel_t2l   test_to_learn    3       3         working, no logic
  H4  sentinel_l2d   learn_to_design  5       5         working, no logic
```

**24 checks, every one non-patchable by at least one of the two routes.**

**Every check kind the validator implements** — `CHECKS` in `framework/validator.py` (lines 717–725) maps exactly ten:

| kind | what it catches |
|---|---|
| `unique` | a tuple of fields repeated across a list; rows where any key field is `None` are skipped (*"a missing field is the schema's business"*); the error path names both indices, e.g. `samples[3],[9].location.container_id+location.position` |
| `cross_ref` | a value absent from an allowed set gathered elsewhere in the same package; supports a plain key, a nested key (`proposes.derived_from_design_item`) and a list member (`evidence[]`) |
| `derived` | a field that must **equal** a value computed from the package. Only `crate_checksum` is in the `DERIVATIONS` table, *"because a contract is data and data must not choose code"*; a mismatch reports both the claimed and the derived prefix |
| `required_quantities` | a measurement the active profile declares mandatory is absent (`missing_quantity`) or present with the wrong unit (`wrong_unit`); silent if the profile declares nothing |
| `provenance_chain` | breadth-first walk from each bound entity back to a `root_type`, following the profile's `follow` properties, the action's `consumes`, **and** a reverse index of actions whose `produces` contains the entity. Reports how many entities were walked and the deepest id. Handles both dialects — PROV forwards, Process Run Crate `CreateAction`/`object`/`result` backwards — and disambiguates the root with `root_within` |
| `required_provenance` | per-entity-type context: no entity of a required type exists at all; a required property on a matching entity is empty; a required measurement under `at` is absent or wrong-unit. Supports `if_present`, `within`, `where` (pick one entity among many by what the crate says, *"never on array position"*), `properties_at`, `one_of` |
| `entity_value` | a referenced entity states a value the receiving phase must act on; per-rule `accept` list; `severity` defaults to `flag` for a disallowed value and `error` for an absent required property. This is the `right partial` case |
| `within_limits` | the package exceeds a limit it itself carries in `limits`; `measure: count` counts rows, otherwise it takes the max of a numeric field; silence is a pass, and the message names the crate via `from` |
| `accounted_for` | the other direction from `cross_ref` — an item the upstream phase committed to that appears in neither the delivered list nor the stated-failure list (*"a row is just absent, and absence has no field to check"*) |
| `empty` | a list that must be empty for the handover to be complete — unmapped vocabulary keys, promised-but-absent files |

Underneath, `validate()` first runs a hand-written JSON Schema subset: `type` (including unions, with `bool` excluded from `number`/`integer`), `required` (treating `None` as absent), `properties`, `items`, `minItems`, `enum`, `const`, `pattern` (via `re.search`), `minimum`, `maximum` — producing `wrong_const`, `not_in_enum`, `wrong_type`, `bad_format`, `out_of_range`, `missing_field`, `too_few_items`. Two severities exist: `error` stops the handover, `flag` does not; `Report.ok` is `not self.blocking`.

### 5.5 The vocabulary layers

Three layers, and only one is code.

| Layer | File | Role |
|---|---|---|
| Core | `vocabulary/core.json` (202 lines) | the shared, PR-reviewed term list and prefixes |
| Lab | `vocabulary/labs/newcastle.json` (22), `labs/lifeglimmer.json` (17) | local spellings, aliased to core terms |
| Code | `framework/vocab.py` (149 lines) | the resolver and the anti-drift rule |

The anti-drift rule is enforced in code: **a lab file may only alias to a term `core.json` declares, or `VocabularyError`.** `newcastle.json` carries a `review` block explaining that `box_temp_c` is unmapped **on purpose**, so the demo's failure has something real behind it. The `crate_to_graph` agent is the gate: it aligns keys to confirmed terms, records proposals separately, and leaves any unaligned key unaligned — which makes the `empty`/`unaligned_key` check fail the handover.

### 5.6 Where a language model may act, and the constraints on it

`grep -rn 'self\.engine\.'` over `sentinel/` returns 16 hits. **Only two call a model**; the other fourteen read `self.engine.name` to write it into a ledger entry or a `Result`. The entire surface a model can touch is two methods on one class: `Engine.propose_patches` (`llm.py:31`) and `Engine.propose_terms` (`llm.py:34`), called from `sentinel_base.py:84` and `crate_to_graph.py:74`.

| # | Constraint | Where, and what it says |
|---|---|---|
| 1 | The engine is never asked about a blocking error | `sentinel_base.py:71` — `fixable = [e for e in report.blocking if not self.is_blocking(e)]`; `BLOCKING_PREFIX = "not auto-fixable"` gives two independent routes, one in Python (`never_autofix`), one in reviewable contract prose (`fix_hint`) |
| 2 | Flags are never repair candidates | the filter starts from `report.blocking` |
| 3 | A patch may only land where the validator pointed | `sentinel_base.py:91–94`. The code's reason: *"a model could 'fix' a double-booked well by renaming it - and the re-validation would pass, because renaming genuinely does make the key unique. It would also have fabricated a lab record. The rule has to be a constraint here, not a comment in the contract."* |
| 4 | The validator re-checks; the engine is never its own authority | `sentinel_base.py:100–101` |
| 5 | A fabricated value that satisfies "the field is present" is still caught | the `derived` kind: *"A missing checksum is a fixable error, so some engine will supply one - and an engine that is wrong, or hostile, can supply a plausible string that satisfies 'present' while the crate's integrity claim becomes a lie. The claim has to be checked, not the field."* |
| 6 | A contract may not name code to run | `DERIVATIONS = {"crate_checksum": _derive_crate_checksum}` — *"It cannot name a function to import, because a contract is data and data must not choose code."* |
| 7 | The repair loop is bounded | `max_repairs: int = 2` on `Task` |
| 8 | Term proposals are reported, never applied | `crate_to_graph.py` — *"A proposed term goes into the result for review and the key stays unaligned, so the handover still fails. That ordering is the difference between a model helping and a model quietly inventing an ontology."* |
| 9 | A model may rename, not coin | `engines.py:144–148` — a term not in `vocab.terms` comes back `"confidence": "rejected"`; `propose_terms` also discards any key the engine invented, and `propose_patches` discards any item without a `path` and truncates `reason` to 300 characters |
| 10 | No key is read anywhere | *"The CLIs use whatever login or API key you already have in your own environment… The key never enters a contract, a crate, a package or the ledger - only the engine's `name` does."* Presets: `claude -p`, `codex exec --skip-git-repo-check`, `ollama run qwen2.5-coder:3b`; failures raise `EngineError` (not on PATH, 300 s timeout, non-zero exit, no JSON) |
| 11 | The prompts make refusal an easy, named option | *"Short on purpose: the constraints are enforced in code, not asked for politely."* `PATCH_RULES`: *"Returning an empty list is a correct and expected answer, and renaming something to make an error go away is the worst possible answer."* `TERM_RULES`: *"Your answer is a SUGGESTION FOR A HUMAN… the handover stays failed until somebody confirms it."* |
| 12 | The default is no model | `Engine.name = "none"`; both agent constructors do `self.engine = engine or RulesEngine()`. `RulesEngine` fixes exactly two derivable things: a `.unit` the profile already states, and `crate_ref.checksum` recomputed from the inlined crate |

Proof, from `python3 scripts/prove_engine.py` at HEAD:

```
PART 1  -  no model at all
    UNALIGNED 'box_temp_c': engine 'rules' has no suggestion
  handover: ESCALATED, 5 error(s)

PART 3  -  the guard, with no model needed
    hostile engine saw 1 fixable path(s) and proposed 3 patch(es)
  REFUSED order.items[0].position - the validator did not report that path as fixable
  REFUSED crate.@graph[#site/NS-01].dwc:decimalLatitude - the validator did not report that path as fixable
  LET THROUGH crate_ref.checksum <- 'sha256:000000000000000000000000000000000000000000
  handover: ESCALATED, 6 error(s)

WHAT THIS PROVED
  · the handover can be checked with no model at all (part 1)
  · a model cannot write where the validator did not point, and cannot coin a vocabulary term (part 3)
```

Three hostile patches: two refused at the path gate, one let through and then caught by the `derived` check on re-validation. `engines.py`'s header claim — *"So the worst a bad model can do here is waste a turn"* — is accurate for the two call sites that exist.

### 5.7 The limits mechanism that flows backwards

`limits` is the one field whose information travels against the cycle, and it answers protocol step 3 of both diagram sets — *"so Design can respect Build and Test limits."* It is deliberately **not** profile material: *"a limit is this run's equipment and this round's budget, and it changes between rounds. Putting it in the profile would freeze it."*

From `python3 demo_l2d.py` at HEAD:

```
    next round orders  36 constructs   ->  accepted
    next round orders  96 constructs   ->  REFUSED  96 constructs against a stated limit of 36 constructs (from #crate/learn)
```

Learn states `library_size = 36 constructs`; 36 is accepted, 96 is refused, and the message names the crate the limit came from.

### 5.8 The graph

`framework/kg.py` (372 lines) lifts a crate into N-Triples through the same vocabulary the agents resolve against. One run's graph is now two files: `runs/<id>/graph/run.nt` (written from the crate by the store, rewritten on every addition) plus `runs/<id>/graph/handovers.nt` (the handover spine, appended by the coordinator — its own file since `ec80217`). `framework/ledger.py` (52 lines) is an append-only JSONL per run, and every step records which engine ran, so *"a big-model-vs-small-model comparison is a query over `runs/*/ledger.jsonl`, not a separate experiment."*

The traversal, from `python3 scripts/ask.py cycle --behind REC-001` at HEAD, reading the files on disk:

```
What is behind REC-001
   0. make a variant of CAND-001                      Recommendation, Entity
   1. plate read of BP1-A01                           Reading, Entity
   2. Fit the model and rank the next round            CreateAction
  ...
  29. DNA extraction                                   Activity, CreateAction
  30. sediment core NS-01 / 0-5 cm                     BioSample, Entity
  31. sediment core collection                         Activity, Event

  reaches the ground: sediment core NS-01 / 0-5 cm
```

32 nodes, from a recommendation about what to make next back to a sediment core. This is the claim the framework puts on its slides, and at HEAD it holds **on disk** as well as in memory.

### 5.9 The two sockets, and the protocol for reaching them

*Added 13 November 2026.*

The Architect reaches everything around it through exactly two callables, fixed in `architect/contract.py` and `architect/architect.py`:

```python
Runner  = Callable[[phase, Architect], PhaseResult]            # does the work
Checker = Callable[[handover, package, Architect], Checked]    # checks it
```

That is why a phase run by a person and a phase run by a program are the same object to it. What those sockets were not is **reachable from outside this process**: to plug an agent in you had to write Python in this repository and import it, which makes the Architect the owner of everybody's code — the opposite of what this project is for.

They now also speak the Model Context Protocol: JSON-RPC 2.0, one object per line, on standard input and output, protocol `2025-06-18`. No port, no daemon, no authentication; the coordinator starts the process, owns it for the run, and ends it. In-process stays the default and stays fastest — the protocol is chosen, per phase or per handover.

| File | What it is |
|---|---|
| `architect/mcp.py` | the client: `Server`, `checker_over_mcp()`, `runner_over_mcp()`, and a `Spec` for `sentinel-oo` and for ourselves |
| `architect/mcp_server.py` | this framework's four sentinels and four phase agents **as** a server |
| `architect/MCP.md` | the picture, the four tools, what is proven and what is not |

`check_handover`, `list_handovers` and `read_contract` are named and shaped as `sentinel-oo` names them, so a coordinator written for his service drives ours without knowing. Where he returns a field we have no equivalent for, we leave it out rather than invent one. **`run_phase` is ours**: nothing outside this project defines a tool for running a phase of a DBTL cycle, so it is published as a proposal rather than dressed up as a standard. A phase agent reached this way works on a **copy** of the crate and only what it *added* comes back — a phase at the end of a pipe must not be able to rewrite the coordinator's record of the run.

**It was proven against somebody else's server.** `python3 architect/mcp.py` drives Anil Wipat's agent interface and returns the same six verdicts `scripts/compare_sentinels.py` gets in process, with nothing of his imported. His `docs/API_MANUAL.md` states that interface is *"Not yet tested against a real Model Context Protocol client"*. On 13 November 2026 it was, by this client, and it answered correctly at the first attempt.

Two faults the seam exposed, both ours:

- **A crate passed by value loses the files it names.** His `hold data` demand asks whether the file an entity stands for exists and is not empty, which is a question about a folder. Writing our in-memory crate into an empty scratch directory and pointing him at it **refused his own `valid` example** for files it could not see. The checker now sends the run's real crate directory, flushed first.
- **Our contracts need more than a crate.** His rules are about entities in a crate; ours are about paths in a package — `order.items`, `bindings`, `produced_by`. Sent a crate alone, every such rule reported that it matched nothing and a sound handover came back REFUSED. The client now reads each server's `tools/list` schema and sends `package` only to a server that declares it. Our own server did not declare it at first, and the schema check is what caught that.

---

## 6. The templates, and how to reproduce everything

### 6.1 What a newcomer runs, in order

Every command below was run at HEAD on 2026-11-10 from `/Users/marcoanteghini/Research/dbtlhub/sentinel`, with Python 3 and **no third-party package, no network and no API key**. All exited 0.

| # | Command | What it prints | What it proves |
|---|---|---|---|
| 1 | `python3 tests/test_framework.py` | `Ran 15 tests in 0.542s` / `OK` | The framework has tests, and three of them encode defects found in this audit so they cannot return quietly |
| 2 | `python3 demo_cycle.py` | one crate 2 → 31 → 41 → 49 → 55 entities, 4/4 handovers PASS, 441 triples, a 32-node traversal, then `1 CONFLICT` and `1 DANGLING` refused | The one-crate-per-run model; three classes of refusal; the chain reaches the ground |
| 3 | `python3 demo.py` | §1 clean: D→B, B→T, T→L all PASS (2 → 43 → 59 → 73 entities). §2 broken: `[sentinel_b2t] -> ESCALATED`, `build: 13 new, 1 COLLISION (43 -> 43 entities)`, `two different things share one @id: #sample/BP1-A04.prov:wasDerivedFrom`, `route stopped: Test is not given a package the validator rejected`. §3: biomanufacturing PASS / bioprospecting FAIL with 8 errors | The clean run is clean; a crate refusal stops the route; the contract/profile split |
| 4 | `python3 demo_d2b.py` | clean: 16 keys aligned to confirmed terms, 8 proposed, 0 unaligned; 226 triples / 29 entities; FAIL 1 → 1 repair (`crate_ref.checksum`) → 0 errors. broken: 14/7, 1 unaligned (`box_temp_c`); 219 triples; FAIL 6 → 1 repair → **5 errors left**, `repair 2: every remaining error needs a decision, not a patch` | Of 6 errors exactly 1 was repairable and 5 needed a human |
| 5 | `python3 demo_l2d.py` | clean OK/PASS (REC-001 rank 1, prediction 4.26 ± 0.54 U/mg, model `esm2-ridge-activity 0.3.1+g4c1a77e`, holdout spearman_rho 0.61); broken ESCALATED with 4 errors (`missing_field` on uncertainty, `duplicate_rank`, `unsupported_recommendation` RES-099, `missing_quantity`), **all 4 needing a human**; limits 36 accepted / 96 REFUSED | Handover 4 closes the cycle, or refuses to; the backwards-flowing limit |
| 6 | `python3 scripts/show_agents.py` | the 4 × (sentinel, contract, checks, never-fixed, state) table | 24 checks, every one blocked by at least one route. The table is built by `importlib`-ing the live classes and reading the contract files, so *"if the table says a check exists, it exists"* |
| 7 | `python3 scripts/show_agents.py --handover 1` | all 9 envelope fields with required/optional, all 11 checks with kind, code and `never auto-fixed`, and `engine  rules  (propose_patches, propose_terms)` | One handover in full, from the contract file |
| 8 | `python3 scripts/check_crate.py --break-all` | `as published ACCEPTED the order can go out +1 flag(s)`; `dangling-reference REFUSED 1 error(s): missing_file`; `missing-conformsto REFUSED … too_few_items`; `missing-gene-calling-mode REFUSED … missing_provenance` | Handover 1 runs on **somebody else's** crate — Anil's published 105-entity crate — and refuses three injected faults. *"Two of those three faults pass every RO-Crate validator there is."* |
| 9 | `python3 scripts/check_crate.py` | 105 entities in `@graph`; `conforms to https://w3id.org/ro/crate/1.3, https://w3id.org/ro/wfrun/process/0.6`; 3 files promised / none missing; 4 constructs / 4 proteins; 570 triples over 105 entities; 0 keys aligned (already term-clean); 4 order lines / 4 bindings; 1 checksum repair; flag `ENR-003: coding sequence completeness is 'right partial', not 'complete'` | Every number the use case's own README quotes, independently recomputed |
| 10 | `python3 scripts/prove_engine.py` | PART 1 ESCALATED 5 errors; PART 3 hostile engine, 3 patches, 2 REFUSED, 1 LET THROUGH then caught, ESCALATED 6 errors | The handover can be checked with no model at all; a model cannot write where the validator did not point, and cannot coin a term |
| 11 | `python3 scripts/ask.py cycle` | `run.nt, handovers.nt - 543 triples, 76 subjects`, then the four handovers with item counts and engines | The graph on disk answers questions about the run |
| 12 | `python3 scripts/ask.py cycle --behind REC-001` | 32 nodes, ending `reaches the ground: sediment core NS-01 / 0-5 cm` | The traversal works **from the artefact**, not only in memory |
| 13 | `python3 scripts/trace.py --list` | 13 runs on disk, with step counts and last package per run | The ledger records every step of every run |
| 14 | `rm -rf runs` | — | `runs/` is gitignored; nothing a demo writes can pollute the repository. `git status --short` is unchanged afterwards |

### 6.2 What they do to take a handover

`template/TAKE_A_HANDOVER.md` (302 lines) is the documented procedure; `sentinel/README.md` calls it *"the thing to read first"*.

| Step | What to do |
|---|---|
| 0 | **Scaffold.** `python3 scripts/new_handover.py <name> --number N --label "…" --from <phase> --to <phase>`. *"Do not copy an existing file by hand. The envelope is identical in every contract, and identical by construction beats identical by discipline: three people copying a file produce three slightly different envelopes within a week."* |
| 1 | **The contract** — `framework/contracts/<name>.schema.json`. Replace `TODO_items`, name the backlink, keep the envelope and the measurement shape exactly as scaffolded, delete the example checks you do not use — *"an unused check is worse than no check, because people stop reading them."* |
| 2 | **The profile entries** — `required_quantities.<your_handover>` in **both** `bioprospecting.json` and `biomanufacturing.json`, plus any `x-pattern` identifiers. *"Do not fork the contract to say it."* |
| 3 | **`never_autofix`** — one line. The test is not "is this hard to fix" but *"would fixing it invent something nobody recorded?"* Or put it in the contract: any check whose `fix_hint` begins `"not auto-fixable"` is blocking without appearing in the Python set, and the one-pager prefers that route *"when the reason is worth reading."* |
| 4 | **`translate()`** — delete it, unless the upstream phase does not already emit the contract's shape. H1 is the stated exception. **4a Limits:** `reads` records a crate consulted but not produced; `limits` holds numbers lifted out of it with `from` naming the crate; record the `checksum` of what you read, because *"a shared crate grows between rounds."* **4b Errors vs flags:** `severity: "flag"` for a package that can be acted on, but not blindly — the forcing case is the `right partial` protein. **4c The backlink:** *"Fill the backlink from where the upstream package was actually stored. Never construct the path"* — `coord.path_of("b2t")` is right, `f"{run_id}/b2t/handover.json"` is *"what we used to do, and it was wrong."* |
| 5 | **The step everyone skips** — *"A deliberately broken package, and a test that it fails for the reason you expect. A check nobody has seen fail is a check nobody trusts."* |

Three prohibitions: do not re-implement the loop; do not let the agent decide a vocabulary term; do not let the agent be its own authority. For a **phase** agent, three more rules: resolve your own vocabulary before writing; look an identifier up, never construct one; add only what you alone know — fill a gap, never change a recorded value.

The scaffolder was proved by the earlier audit: `new_handover.py zzz_to_qqq --number 9 --label "smoke test" --from zzz --to qqq` wrote exactly two files and exited 0. The contract came out with `$id: dbtl:zzz_to_qqq/0.1.0`, the full envelope, `reads`, `limits`, `TODO_items`, the backlink renamed from `TODO_ref` to **`zzz_ref`** and appended to `required`, the three example checks' `from_profile` rewritten to `required_quantities.zzz_to_qqq`, and a `$comment` preserving the instruction not to rename envelope fields. The agent came out with the abbreviation `z2q` derived by `abbreviate()`, the `sys.path` depth corrected from 2 to 3 parents for its new location, `never_autofix = NEVER_AUTOFIX` (an empty set with two commented examples), and a `translate()` with the envelope filled and `"zzz_ref": {},   # TODO the backlink`. The scaffolder refuses to overwrite (`sys.exit(f"{path} already exists — edit it rather than scaffolding over it")`) and validates the name against `[a-z]+_to_[a-z]+`. Both files were deleted afterwards and `git status` returned to clean.

As of `ec80217`, step 5 is no longer only advice. `tests/test_framework.py` is the worked example of it, in four classes:

| class | tests | what they hold down |
|---|---:|---|
| `TestProfilesAndContracts` | 4 | a prediction and the measurement meant to test it share a unit; every check kind the contracts name is implemented; nothing is auto-fixable by accident; both profiles declare the same handovers |
| `TestCrateStore` | 4 | a gap may be filled; a recorded value may not be overwritten; one `@id` for two things is a **collision**; a reference to nothing is refused |
| `TestRepairIsConstrained` | 2 | a patch outside the reported paths is refused (driven by a hostile engine stub that tries to move a sample to well H12); the rules engine invents nothing beyond a `.unit` |
| `TestEndToEnd` | 5 | the demos report the right verdicts; **a clean run has no failing handover**; Handover 1 accepts the published crate; the graph query reaches the ground **on disk**; the chain of packages resolves |

`TestEndToEnd` runs the real scripts and reads what they say, with a helper that asserts no `Traceback` appears in stdout or stderr — *"not what they exit with."* That is the direct answer to defect F1, where the exit code was 0 and the printed line said FAIL.

---

## 7. Verification: what is proven by running something

Three categories, kept strictly apart.

### 7.1 Demonstrated — a command produces the result

| Claim | Command or test |
|---|---|
| All four handovers validate, and escalate as documented | `demo_cycle.py`, `demo_d2b.py`, `demo_l2d.py`, `demo.py` |
| A sentinel agent for a new handover is three declarations | `show_agents.py`; AST measurement of the class bodies |
| The contract/profile split works: one package, two profiles, PASS and 8 errors | `demo.py` §3 |
| Handover 1 accepts the use case's own published 105-entity crate, and refuses three injected faults | `check_crate.py --break-all` |
| Every number in the bioprospecting crate README recomputes | `check_crate.py` |
| The crate refuses a conflicting value and a dangling reference, and the refusal is atomic | `demo_cycle.py`; `TestCrateStore` |
| One `@id` written twice for two things is diagnosed as a collision, and stops the route | `demo.py` §2 |
| A hostile engine cannot write where the validator did not point, and a fabricated checksum is caught on re-validation | `prove_engine.py` PART 3; `TestRepairIsConstrained` |
| A model may rename but not coin a vocabulary term | `engines.py:144` plus `prove_engine.py` |
| The repair loop is bounded and says so | `demo_d2b.py`: `repair 2: every remaining error needs a decision, not a patch` |
| Of 6 D→B errors exactly 1 is repairable and 5 need a human; all 4 L→D errors need a human | `demo_d2b.py`, `demo_l2d.py` |
| The backwards-flowing limit refuses 96 against a stated 36 and names the crate | `demo_l2d.py` |
| The provenance chain reaches a physical sample **from the files on disk**, 32 nodes | `ask.py cycle --behind REC-001`; `TestEndToEnd` |
| The framework runs with no network, no API key and no third-party package | every command above |
| The scaffolder produces a correct envelope and refuses to overwrite | `new_handover.py` |
| 61 tests pass, on Python 3.12 and on 3.9 with no PyYAML installed | `tests/test_framework.py` (15 when this report was first written) |
| The Architect drives **somebody else's sentinel** over the Model Context Protocol, and gets the same six verdicts as the in-process comparison | `architect/mcp.py`; `TestTheUniformSocket` |
| A handover checked by a sentinel in another process, with its act landing in the crate that grows | `TestTheUniformSocket.test_the_architect_accepts_a_sentinel_at_the_end_of_a_pipe` |
| A phase of the cycle run by another process, and a phase with no server falling back in-process | `architect/mcp_server.py --self-test`; `TestTheUniformSocket` |
| A contract drafted by the contract wizard runs here unchanged, and a sixth demand is refused by name rather than ignored | `TestAContractTheWizardWrote` |
| Which requirements of a contract **could not fire** against a crate — 0 of 20 for `design_to_build/0.11.0` on all six example crates | `scripts/compare_sentinels.py`; `oo_contract.silent()` |

### 7.2 Written but never executed

| Artefact | Size | Status |
|---|---:|---|
| `framework/contracts/shapes/design_to_build.shacl.ttl` | 162 lines | SHACL equivalents of the graph checks. Its own header: *"Run it, once the dependency is acceptable: pip install pyshacl rdflib."* I grepped the whole repository — `pyshacl` appears in `requirements.txt`, `README.md`, `framework/README.md`, a `validator.py` comment, a `kg.py` comment, `DESIGN_TO_BUILD.md`, `export_for_dbtlhub.py` and the shape file itself. **Nothing invokes it.** |
| `DESIGN_TO_BUILD.md`'s "The stack" table | — | Names `ro-crate-py`, `rdflib`, `pyoxigraph`, `pyshacl`. **None is used by any code on disk.** What runs is a hand-written JSON Schema subset, a hand-written N-Triples writer and a hand-written N-Triples reader. |
| `scripts/export_for_dbtlhub.py` | 197 lines | Exercised by no demo and no test, and not run in either audit. |
| `scripts/trace.py` per-run walk | — | Only `--list` was run. The backlink-resolution walk that `TAKE_A_HANDOVER.md` §4c points at was not exercised. |
| `prove_engine.py` PART 2 | — | Silently absent without `--engine`. No "PART 2 skipped" header; only a dim summary line, `no model tried - pass --engine claude\|codex\|ollama`. |
| H2's `unknown_design_item` and `unaccounted_item` | — | **New finding at HEAD.** Since `ec80217`, `demo.py`'s broken run is stopped by the crate store's COLLISION before the B→T contract is reached, so these two checks are no longer demonstrated by any run. I validated both test fixtures directly: `b2t_double_booked.json` yields `double_booked_location` + `duplicate_sample_id`; `b2t_missing_unit.json` yields two `missing_field`. Neither fixture produces the other two codes. |
| `entity_value` / `flagged_entity` under `profile=biomanufacturing` | — | The check is in the shared contract, but only `bioprospecting.json` declares `accepted_values.design_to_build`, so under the other profile `_check_entity_value` returns at its first line. A silent no-op. |
| `within_limits` when no limit is stated | — | `_check_within_limits` comments that a contract may insist via `required_limits`, but **no contract on disk has a `required_limits` key**, so silence *is* currently a pass. The backwards-flowing limit is enforced only when the producing phase volunteers it. |

### 7.3 Claimed in prose, not reproducible here

| Claim | Why it is not verifiable |
|---|---|
| The four-row model comparison in `README.md` and `TAKE_A_HANDOVER.md`, presented as *"Measured, same code, same broken crate"* (`claude -p` → `dbtl:storageTemperature`; `codex exec` → the same; `ollama` 3B → `envo:temperature` **rejected**) | No recorded ledger, no fixture, no transcript. The *mechanism* is verifiable by reading `engines.py:144`; the *measurement* needs three CLIs installed and logged in. |
| `rocrate-validator` 0.13.1 passes the bioprospecting crate against RO-Crate 1.3 | Reported in that use case's README; not re-run in either audit. |
| Every number in every demo — `4.26 ± 0.54 U/mg`, `spearman_rho 0.61`, every plate reading, 47,812 contigs, 61.4 Gb, N50 3,140 bp | **Simulated by construction.** `usecases/bioprospecting/*` generates them; the files say so plainly, but a reader of demo output could miss it. |
| `docs/walkthrough.html` (611 lines) and `docs/sentinel_agents.pptx` | Prose; not cross-checked line by line in either audit. |
| Every directed-evolution and biomanufacturing architectural claim | Both folders are diagrams and prose only, and both say so: *"Interface agents and RO-Crates are the proposed theoretical architecture, not used in the original experiment."* |
| The bioprospecting plate-difference rule (intended vs delivered) | Specified on a diagram and stated in the crate's prose. No Build record of a delivered plate exists anywhere, so the difference has never been computed. |

### 7.4 Scale

Every entity count in the bioprospecting crate is **4** where the stated real handover is **96**; the crate's own `File` descriptions name the intended scale ("96 selected protein sequences, a count"). Nothing has been run at 96, and nothing has been run on a panel assembled from two Design runs, which is the limitation the crate itself declares.

---

## 8. Defects found by this audit

### 8.1 Framework defects, found and fixed

| # | Defect | What was wrong | Fixed in |
|---|---|---|---|
| F1 | **`demo.py`'s "clean" run ended in a failed handover, and the script still exited 0** | The `test_to_learn` `required_provenance` check added at `a3d7765` had nothing to read, because the legacy `phase_test.py` emitted a T→L package with no crate. Section 1 printed `[sentinel_t2l] -> FAIL … unusable_reading: no entity of type 'dbtl:Reading' anywhere in the crate` while the closing summary said `escalated none`. HEAD had closed the hole for the crate-based path and broken the demo the README offers as the entry point; the regression check that was supposed to catch it passed. | `ec80217`. `demo.py` now drives the crate-writing family only; its clean run is three PASSes (2 → 43 → 59 → 73 entities), and `TestEndToEnd.test_a_clean_run_has_no_failing_handover` holds it down. Verified by running both. |
| F2 | **`scripts/ask.py` could not walk the chain the framework puts on its slides** | It built predicate IRIs by gluing strings onto a base, looking for `<base>restsOn` while the graph held `<base>terms/restsOn`. On the same `cycle` run where `demo_cycle.py` had just printed a 32-node chain to the ground, `ask.py --behind REC-001` reported `does not reach a physical sample — Walked 2 node(s) and found no sample`. Its hand-rolled N-Triples parser also required a line to start with `<`, so it dropped every blank-node subject — losing exactly the `quantity+value+unit+method` shape the framework insists on (the four triples `qudt:quantityKind "storage_temperature"`, `schema:value "-80.0"`, `qudt:unit "degC"`, `schema:instrument "freezer log"`), and under-reporting 462 file lines as 458 triples. | `ec80217`. It now expands predicates through the same vocabulary the lifter uses and keeps blank-node subjects. Verified: `ask.py cycle --behind REC-001` prints 32 nodes and `reaches the ground: sediment core NS-01 / 0-5 cm`; `TestEndToEnd.test_graph_query_reaches_the_ground_on_disk` holds it down. |
| F3 | **Two writers, one file: the handover spine was silently clobbered** | The coordinator appended the lifted handover packages to `runs/<id>/graph/run.nt`, which the crate store rewrites from the crate on every addition. The spine was written and then overwritten, and the loser was invisible. | `ec80217`. The spine has its own file, `graph/handovers.nt`, with the reason in a comment. Verified: `ask.py` now reports `run.nt, handovers.nt - 543 triples, 76 subjects`, and `run.nt` alone is 441 — which is why the triple count in §5.2 differs from the briefing's 462. |
| F4 | **The crate store mutated on refusal** | It refused a bad addition correctly and left the bad entity in the in-memory graph anyway, so the next caller saw a crate the store had declined to write. | `ec80217`. `CrateStore.add` is now atomic — assembled on a copy, committed only if accepted, *"so a refusal leaves the crate exactly as it was - in memory as well as on disk."* Caught and held down by `TestCrateStore`. |
| F5 | **The Build phase crashed on an unknown identifier** | `phase_build_crate.py` did `made[row["design_item_id"]]`, so a tube relabelled by hand with an ID Design never made raised `KeyError` instead of letting the contract refuse the package. | `ec80217`. It now writes the sample with no origin — *"Do NOT invent a join: write the sample without an origin and let the contract refuse the package… A fabricated `@id` would pass the crate store and lose the error"* — and the action's `object` list filters to known items. Relatedly, one identifier written twice for two different things is now diagnosed as a **collision**, not as one phase overwriting another. |
| F6 | **`requirements.txt` was an unrelated `pip freeze`** | 29 lines of `matplotlib`, `scikit-learn`, `leidenalg`, `python-igraph`, `pyarrow`, `pandas`, `networkx` — left over from another project in the same folder, naming nothing the framework uses and none of the four libraries its own documentation names. | `ec80217`. It now states there are no dependencies (true: zero third-party imports) and lists `rdflib`, `pyoxigraph`, `pyshacl`, `ro-crate-py` as optional, each with what it would be for, and *"None of those is imported anywhere."* Verified by reading the file. |
| F7 | **`framework/README.md` contradicted the code** | Its status table called the L→D contract and the Learn phase agent "not written", when `learn_to_design.schema.json` (394 lines, 5 checks) and `phase_learn_crate.py` (160 lines) both run. | `ec80217` — **partially**; both rows now read "working", but two others are still stale (see D1). |
| F8 | **No tests of any kind** | No `tests/`, no `pytest`, no assertion anywhere in 6,360 Python lines. The framework's own step 5 — *"A check nobody has seen fail is a check nobody trusts"* — was the step it had not taken. | `ec80217`. `tests/test_framework.py`, **15 tests, no dependencies**: `Ran 15 tests in 0.542s / OK`. Three of them encode defects from this round (F1, F2, F4) so they cannot come back quietly. |
| F9 | **The biomanufacturing profile described a case that was not theirs** | It required titre in **mg/gDW** by MZmine/OpenMS with nanopore verification. The published pipeline — SYNBIOCHEM, (2S)-pinocembrin in *E. coli*, Carbonell et al. 2018 — reports **mg/L** from an Acquity UPLC and a Xevo TQ-S by MRM against a calibration curve, with Sanger verification and Hamilton STAR assembly. The audit's words: *"We had written our own case and put their name on it."* Worse, `predicted_titre` was in **g/L** while `titre` was in mg/L, so a prediction and the measurement meant to test it were in different units **inside one profile** — the exact mistake this framework exists to refuse. | `cd07cf2`. Verified by reading the file at HEAD: `titre` mg/L, `predicted_titre` mg/L, `biomass` OD600, instruments corrected to Hamilton STAR / QIAprep 96 + CE + Sanger / Acquity UPLC – Xevo TQ-S. The argument for per-gDW normalisation is preserved as a `review` note for the use case owner to settle. `TestProfilesAndContracts.test_profile_units_are_coherent` holds the unit coherence down. |

### 8.2 Framework defects still open

| # | Defect | Evidence at HEAD |
|---|---|---|
| D1 | **`framework/README.md` is still partly stale.** Line 99: `T→L contract \\| working, validated directly — no sentinel agent yet` — but `sentinel_t2l.py` exists and ran in every demo. Line 102: `Model engine \\| … only RulesEngine implemented` — but `engines.py` has `CommandEngine` with three presets. The "suggested order" paragraph still proposes writing the T→L sentinel as the next step. | Read at HEAD. |
| D2 | **`README.md`'s "Known gaps" has a bullet duplicated verbatim and a bullet whose three clauses are all false.** The duplicate is *"H2 and H3 packages are JSON, not RO-Crates"*, appearing twice. The false bullet claims nobody has run this on a real crate, that Anil's crates use `CreateAction`/`object`/`result` *"so the provenance traversal does not yet walk them"*, and that *"the mechanism is hardcoded where it should be declared in the profile"*. All three are contradicted by `check_crate.py` (which ACCEPTS that crate), by `_reverse_actions`/`predecessors` in `validator.py`, and by the dialect keys declared in `profiles/bioprospecting.json`. The same README elsewhere describes the `check_crate.py` run in detail, so the document argues with itself. | `sed -n '/Known gaps/,/^## /p' README.md`. |
| D3 | **`README.md` names a profile that does not exist.** Line 8: *"`bioprospecting` and `directed_evolution` can disagree about what a handover is incomplete without…"*. `contracts/profiles/` holds `bioprospecting.json` and `biomanufacturing.json`, and `show_agents.py --profile` accepts only those two. `demo_l2d.py:102` also narrates the directed-evolution architecture, and no directed-evolution artefact exists in `sentinel/`. | `grep -n directed_evolution README.md demo_l2d.py`. |
| D4 | **Two phase-agent families still coexist, and three callers still use the old one.** `demo.py` was converted at `ec80217`, but `demo_d2b.py:29`, `scripts/prove_engine.py:33` and `scripts/export_for_dbtlhub.py:33` still `from framework.agents.phase_design import DesignAgent`, which subclasses `Agent` directly, implements its own `handle()`, and bypasses the crate write and the conflict/dangling refusal. `phase_design.py` (35 lines), `phase_build.py` (72) and `phase_test.py` (67) are still on disk with no deprecation marker. The commit message's *"There is one family now"* is true of `demo.py` only, and keeping two families alive is what caused F1. | `grep -rn "phase_design import"`; `ls framework/agents/`. |
| D5 | **H2's `unknown_design_item` and `unaccounted_item` are now demonstrated by nothing.** The crate store's COLLISION stops `demo.py`'s broken run before the B→T contract is reached, and neither test fixture produces those codes (verified by validating both fixtures directly). A side effect of F5's otherwise correct fix: the earlier run showed 7 b2t errors including `unknown_design_item 'CAND-999'` and two `unaccounted_item`s; HEAD shows the collision instead. | My own run of `demo.py`; direct validation of both fixtures. |
| D6 | **`entity_value` / `flagged_entity` is live in one profile only**, and `within_limits` is a silent pass whenever the package carries no matching `limits` entry, because no contract declares `required_limits`. | §7.2. |
| D7 | **Pattern matching uses `re.search`, not `re.fullmatch`** (`validator.py:161`). Every profile pattern is anchored `^…$`, so no defect is observable today, but an unanchored pattern added later would match a substring and pass. The anchoring convention is undocumented and unenforced. | Read at HEAD. |
| D8 | **`prove_engine.py` PART 2 vanishes without a header** when no `--engine` is given; only a dim summary line records that no model was tried. | My own run. |
| D9 | **`show_agents.py --handover 1` marks `checksum_mismatch` "never auto-fixed" while the demos patch `crate_ref.checksum`.** Both statements are true — the `derived` check is never patched; `missing_field` on the same path is the one repair `RulesEngine` performs — but the column name is doing more work than it can carry, and a reader of the red table would reasonably conclude the checksum is untouchable, then watch `demo_d2b.py` fill it in. | Previous audit; the column logic is unchanged at HEAD. |
| D10 | **`dbtl:` is not minted** at `https://w3id.org/dbtlhub/`, so every IRI the framework writes is unresolvable and two teams' graphs cannot be merged. The framework states this itself, first in its own suggested order. | `README.md` "Known gaps". |
| D11 | **Referential integrity is partial for crates read from disk.** Relative `@id`s typed `File` are checked against the folder; not every `@id` referenced anywhere in `@graph`. `CrateStore` does check this for crates it writes itself (the DANGLING demo), so the gap is specifically for foreign crates — which is exactly check 3 of the bioprospecting list. | `README.md`; `demo_cycle.py`. |
| D12 | **Two crate dialects are supported.** `profiles/bioprospecting.json` calls this *"a finding to settle as a group, not a feature"*; `README.md` calls it *"a tax that compounds with every handover."* | Read at HEAD. |
| D13 | **Three identifier spellings in one regex**: `^(CAND\|CON\|ENR)-[0-9]{3}$`, with the profile's own note that *"Agreeing one is a group decision, not an agent's."* | Read at HEAD. |
| D14 | **Housekeeping.** A 165-byte `docs/~$sentinel_agents.pptx` lock file sits in the tree (gitignored, so harmless but untidy). The four `break-*` ledger runs record a step with `last package: none`, so `trace.py --list` shows rows it can say nothing about. | My own run of `trace.py --list`. |

### 8.3 Use case defects — bioprospecting

| # | Defect |
|---|---|
| B1 | **A dangling pointer, and the promised broken crates do not exist.** `exampleROcrates/README.md` requires *"at least one crate that satisfies its contract and one deliberately broken crate"* per handover; none is present. `design-to-build-simple/README.md` points at `../design-to-build/` — *"holds the generator that produces this crate, plus three crates that are deliberately broken"* — **a directory that is not on disk**. It was added in `e238663` and reverted in `1a44866` six minutes later. Whether the revert was deliberate cannot be determined from the repository. `sentinel/examples/design-to-build/` now holds equivalent broken crates, generated by `check_crate.py --write-broken`, but nothing in `bioprospecting/` says so. |
| B2 | **The spec diagram and the implemented crate disagree in six places, none flagged as a known divergence.** `06_design_handover_crate.png` says the construct file is `constructs.gb` (GenBank); the crate ships `constructs.json`. The diagram requires each Construct to carry *"promoter and terminator parts, and forbidden restriction sites"* — **absent from the crate**. It requires each Protein to carry *"predicted, or experimentally confirmed"* and *"group size (number of sequences)"* — **both absent**; the crate has cluster identifier and distance only. It names the annotation-database entity as a `CreativeWork` named "reference domain database"; the crate uses a `PropertyValue` named "annotation reference database release". It attaches `endTime "2026-03-14T09:21:00Z"` to "Select panel"; in the crate that timestamp belongs to `#act-gene-calling` and panel selection is `2026-03-16T10:12:00Z`. And it draws 6 actions where the crate has 11 (sampling, DNA extraction, library prep, sequencing and read QC are not shown). |
| B3 | **Only Handover 1 has any artifact.** Handovers 2, 3 and 4 are named on one slide and have no crate, no contract text and no field list. The Test→Learn example that motivates the whole contract argument — negative controls, replicate count, instrument range, plate randomisation — is written down **nowhere** as requirements. (`sentinel/contracts/test_to_learn.schema.json` encodes three of the four as `dbtl:blankCorrected`, `dbtl:replicates`, `dbtl:withinRange`; **plate randomisation is still required by nothing**.) |
| B4 | **No SHACL exists in the folder.** Proposed once in `questions.md`, never instantiated: no shapes file, no rule, no machine-readable form of any check. |
| B5 | **No agent code.** `agents/` contains an 8-line README and nothing else. |
| B6 | **MUST/SHOULD/MAY appear on one diagram only**, and only on the Process-Run-Crate-derived left column plus the `conformsTo` line. **The right-hand column — Plate, Protein, Construct, the part the contract is said to be — carries no obligation markers at all.** |
| B7 | **No authoritative list of the agreed `name` strings exists**, although check 6 requires them. The crate README's table says "annotation database release"; the JSON says "annotation reference database release". |
| B8 | **The `.pptx` and the `docs/*.png` set are not in sync.** Two slides exist only in the deck (the instrument montage and the four-handover map); `05`, `06` and `07` are not in the deck; the numbering gap at `03` is unexplained; `07_crate_graph.png` is duplicated byte-for-byte in two directories; slides 2–6 are flat images, so none of their content is searchable or diffable, and text extraction yields only the title slide. |
| B9 | **Equipment-as-software has no proposed fix.** The crate calls it *"the clearest gap the bioprospecting use case exposes"*, proposes no vocabulary or extension, and ships the workaround (catalogue number as `version`) in the data. The corer's own `description` says so: *"A hand corer. It is not software and it has no version; the value 1 is there only because RO-Crate requires one."* |
| B10 | **`#operator` is a bare `Person` with only a name** ("Simulated operator") — no resolvable `@id`, no ORCID, no affiliation. Whether a contract should require an identifiable agent is not stated. |
| B11 | **No checksums.** The folder twice notes that core RO-Crate has no checksum property and never says what the contract should require instead. (`sentinel/` requires `sha256:` on `crate_ref` and verifies it by derivation — a unilateral decision.) |
| B12 | **Scale is asserted, not demonstrated.** Every entity count is 4 where the stated handover is 96, and the one-crate-one-run limitation is acknowledged and not addressed. |
| B13 | **"Sentinel agents" is an open naming question here, not an adopted term**, and nothing in `bioprospecting/` references `sentinel/`, its contracts, or any shared framework by name. |

### 8.4 Use case defects — directed evolution

| # | Defect |
|---|---|
| E1 | **Nothing is implemented.** No `agents/`, no `docs/`, no example crates, no questions file — unlike the other two folders. One README and two diagrams. |
| E2 | **The README is out of date relative to the later diagram.** It embeds v1 only, and **RO-Crates are never mentioned anywhere in the README text.** A reader of the README alone would not know the RO-Crate architecture exists. |
| E3 | **The root `DBTL_interface_agents_RO-Crates.png` is untracked and unexplained** — in no commit, referenced by no file, sitting at the repository root rather than in the use-case folder. Its relationship to the SVG is inferred from aspect ratio only (1.240 for both). The briefing also corrects the original task brief here: there is **no** `DBTL_interface_agents_RO-Crates.svg` at the root, and the PNG is **not** a copy of `directed_evolution/original.png` (md5 `59d482bf…` vs `4edb4e34…`). |
| E4 | **`original.png` is orphaned** — 1.8 MB, committed, referenced by nothing, no caption, purpose undocumented. |
| E5 | **Three inconsistent tool lists** (README, v1, v2), with nothing stating which is authoritative. "ITC sampling" is v1-only; "Momentum DataMiner" and "ML-guided variant selection" are v2-only; none of the three appears in the README table. |
| E6 | **The write/package boundary is ambiguous.** The legend says *"Stage writes its own crate"*; the protocol says *"Each interface agent packages the next stage's crate with validated inputs"*, and each agent says it packages the next crate. Whether the agent or the stage is the writer of record — and whether "package" implies a write — is unresolved. This matters directly to any contract that must identify a responsible producer. |
| E7 | **"Validated inputs" is undefined.** Protocol step 1 says agents package the next crate "with validated inputs", and no validation rule, schema, threshold or failure mode is given anywhere. This is the exact point at which a contract plugs in, and the vaguest sentence in the artefact. |
| E8 | **No failure behaviour.** Nothing says what happens when validation fails, when QC status is "fail", when an exception is raised, or when a human declines to approve a round. There is no reject/retry/escalate path in either diagram. |
| E9 | **Human approval is unlocated.** The Coordinator has "human approvals" and the researcher "approves rounds", but no diagram places the gate at a specific handover, and "key decision points" are not enumerated. |
| E10 | **No identifiers, formats or vocabularies.** No file format, no ontology, no persistent-identifier scheme, no RO-Crate profile, no metadata standard. *"Metadata (conditions, replicates)"* is as specific as it gets. |
| E11 | **Unreconciled diagram versions, and unqualified numbers.** v1 and v2 differ on 16 dimensions with nothing stating that v2 supersedes v1. The "2.4× improved activity" figure has no baseline, no assay definition and no statement of which round achieved it. "96 variants" is marked "e.g." in v2 although it is a hard reported figure in the paper, leaving open whether library size is a constraint or an agent-chosen parameter. |
| E12 | **Both diagrams are SVG-with-embedded-raster.** The v2 SVG is 336 kB carrying a large embedded base64 payload (a C2PA/Content-Credentials manifest and embedded images), so changes to it cannot be reviewed as text in a pull request. |
| E13 | **No link to `sentinel/`**, and the vocabulary used here ("packages", "crate store", "Coordinator") is this use case's own; alignment with the shared framework's terms is untested. |

### 8.5 Use case defects — biomanufacturing

| # | Defect |
|---|---|
| M1 | **Nothing is implemented.** `agents/` is a `.gitkeep`. Both crate diagrams state plainly: *"Interface agents and RO-Crates are the proposed architecture, not used in the original study"* (v2: *"proposed theoretical architecture … original pipeline"*). |
| M2 | **Two crate diagrams coexist with no statement of which is authoritative.** v2's commit message says "new version", v1 was not deleted, and v1 is the only version carrying ICE/SBOL, the named instruments, LOD/LOQ gating, the concrete design constraints and the library size — exactly what a contract needs to be testable. |
| M3 | **Crate granularity is contradictory within the folder.** The SVGs: one crate per stage, four total. Deck slide 4: an RO-Crate per tool step inside Design, with "DNA parts / RO-Crate?" undecided. The two models are never reconciled. |
| M4 | **Agent placement is contradictory.** The SVGs put agents only on the four stage boundaries; slide 4 puts an "AI AGENTS" box *inside* Design feeding the ranking and DoE steps, with the note "Ranking made by Agent / Formula". |
| M5 | **The deck is labelled with the wrong use case.** Slide 4 carries the title *"Study case 3: Directed evolution workflow"* inside the biomanufacturing deck. |
| M6 | **The agent exemplar is from different biology.** The LLM-answer screenshot on slide 6 is a **Golden Gate / yeast / TyrH** library-construction protocol; the use case is LCR / *E. coli* / pinocembrin. |
| M7 | **Scope mismatch between deck and diagrams.** The deck's Test slide covers continuous/online data, omics, cell-free systems and biosensors; its Learn slide covers model re-parameterisation and scale-up questions. The SVGs reduce Test to LC-MS titre and Learn to factor analysis. The deck has never been updated since the diagrams landed. |
| M8 | **Objectives and constraints are named but neither quantified nor located.** "Titer, Rate, Yield" and "Budget, …" exist only on slide 4; no SVG, README or crate seed mentions an objective function or a budget, and the ellipsis is never filled in. |
| M9 | **"Gates scale-up" lost.** v1 made the Coordinator gate the exit to process development; v2 drops it, so in the current "new version" nothing decides when the cycle ends — even though both Fig. 1 and the agents diagram draw the exit to scale-up. |
| M10 | **Off-canvas content.** The git / package-manager / empty-box annotation row on slide 2 sits at y = 5.41–6.08 in on a 5.625 in-tall slide, below the edge; the footnote panels on slides 3–4 overrun the right edge. Anyone reading the deck as slides rather than as XML will not see them. The third box in that row is empty — the annotation was never completed. |
| M11 | **No unit, identifier or schema commitments.** The only units anywhere are mg/L (v1 T→L handoff) and OD600; the only identifier systems are ICE/SBOL (v1 only). No regex, no schema, no controlled vocabulary — everything is prose inside diagrams. |
| M12 | **The README cites "Fig. 1" without a DOI**, and the citation appears only as "Carbonell et al., Communications Biology (2018)". |
| M13 | **The WORKFLOW/PROMPT agent input is never specified further.** No prompt text, no workflow format (CWL? Galaxy? Nextflow? — slide 4 names "OptBioDes (Galaxy SynBioCAD)", which hints at Galaxy but never says so), no statement of what "Context info" contains. |
| M14 | **Unfinished enumerations.** *"Tool: DNABot,"* on slide 7 ends in a comma; *"Could swap these around"* on slide 8 leaves the order of data analysis and data integration unresolved. |

---

## 9. Open questions for the group

Each of these is a decision the three teams have to take together. None is `sentinel/`'s to take alone, and `sentinel/` has already taken several unilaterally in order to have something that runs.

| # | Question | Options | What hangs on it |
|---|---|---|---|
| Q1 | **Is a crate one per run, one per phase, or one per tool step?** | (a) one per run, grown by the phases — `sentinel/`'s choice, demonstrated; (b) four per cycle in a shared store — both SVG diagram sets; (c) one per Design run — bioprospecting's constraint; (d) one per tool step, nested — biomanufacturing's deck | Whether the provenance chain is one traversal or a join across three boundaries. The 32-node chain `demo_cycle.py` prints exists only under (a). Under (b) every boundary needs a join key and a version; under (d) a profile for crate nesting must be written, and none of the three profiles on the table defines one. |
| Q2 | **Which profile does a handover crate declare, and at what version?** | (a) Process Run Crate 0.6 on the root data entity — bioprospecting's **MUST**; (b) unspecified — directed evolution; (c) whatever ICE/SBOL needs around it — biomanufacturing v1 | Whether a contract can be a SHACL shape over a profiled crate at all. Also whether to track the current `rocrate-validator` (which implements 0.5 and assumes RO-Crate 1.1) or to stay ahead of it, as bioprospecting explicitly chooses: *"Do not 'fix' the crate to satisfy the older checker."* |
| Q3 | **Do crates persist and grow across rounds, or is a crate one run?** | (a) persist and grow, seeded once at round 0; (b) one per run, with `reads` + `limits` + a checksum carrying what crosses | Every checksum in every contract. Under (a) a checksum is a moving target and `reads` needs a version; under (b) the four-crate store must be re-seeded every round and the "Design respects Build limits" guarantee holds only within a round. |
| Q4 | **Is the writer of record the stage or the agent?** | (a) the stage writes, the agent packages — both diagram legends; (b) the phase agent writes and the sentinel writes nothing — `sentinel/`'s implementation | Who is accountable for a bad record, and whether "package" is a write. A contract has to name a responsible producer; `produced_by` currently requires `agent`, `tool` and `engine`, which answers (b) and not (a). This is directed evolution's gap (f) stated as a decision. |
| Q5 | **Is SHACL the rule language, and who runs it?** | (a) yes — bioprospecting's proposal; (b) the hand-written validator subset that exists and runs; (c) both, with SHACL as the published artefact and code as the executable one | 162 lines of SHACL exist and have never been run. If SHACL is the answer, `pyshacl` becomes a hard dependency and all ten check kinds need SHACL equivalents — several of them (`accounted_for`, `within_limits`, `derived`) are not naturally expressible as shapes. |
| Q6 | **Is `flag` a first-class outcome, or only pass/fail?** | (a) three outcomes: pass, flag, refuse — `sentinel/`'s two severities plus `escalated`; (b) pass/fail with a separate exception channel — the Coordinator bullets in both diagram sets | Whether the `right partial` protein (ENR-003) and `gene calling mode = open ends` block an order or travel with it. Bioprospecting's check 7 says *"not an error, but it is a flag that Build must act on"*, which only (a) can express. |
| Q7 | **Where exactly is the human approval gate?** | (a) at every handover; (b) at the round boundary only ("approves rounds"); (c) only on escalation | Both diagram sets have a human gate and neither places it. `sentinel/` has only one outcome a human must act on — `escalated` — and no explicit approval step. |
| Q8 | **What vocabulary covers laboratory equipment?** | (a) keep `SoftwareApplication` with a catalogue number as `version`, as the bioprospecting crate ships; (b) extend Process Run Crate; (c) adopt an external vocabulary (OBI, ENVO or similar); (d) mint terms under `dbtl:` | The crate calls this *"the clearest gap the bioprospecting use case exposes"*. Until it is settled, a hand sediment corer is software with version 1. |
| Q9 | **Should `dbtl:` be minted at `https://w3id.org/dbtlhub/`?** | (a) yes, by pull request, now; (b) reuse an existing namespace; (c) leave IRIs unresolvable | Blocks merging two teams' graphs. `framework/README.md` lists it first in its suggested order, calling it *"a pull request, and it blocks others."* |
| Q10 | **Which identifier spelling?** `CAND-`, `CON-` or `ENR-`? | pick one | `profiles/bioprospecting.json` carries all three in one regex with its own note: *"Agreeing one is a group decision, not an agent's."* |
| Q11 | **Which crate dialect?** PROV properties, or Process Run Crate `CreateAction`/`object`/`result`? | (a) one; (b) both, as now | `profiles/bioprospecting.json`: *"That there are two is a finding to settle as a group, not a feature."* `sentinel/README.md`: *"a tax that compounds with every handover."* |
| Q12 | **Are H2 and H3 packages RO-Crates or JSON?** | (a) all four handovers are crates — what the use case slides imply; (b) crates where they help, JSON elsewhere — what is implemented | `sentinel/README.md` raises this itself. The contracts do not care; the example packages are inconsistent. |
| Q13 | **Should the agents be called "Sentinel agents"?** | yes / no | `bioprospecting/questions.md`, bullet 3, no answer recorded. `sentinel/` has already adopted the name in code; directed evolution and biomanufacturing both say "interface agents". |
| Q14 | **Is a titre required per volume, per biomass, or both?** | (a) mg/L, as published; (b) mg/gDW, which separates a strain that makes more from one that simply grows more; (c) both | Recorded as a `review` note in `profiles/biomanufacturing.json` at `cd07cf2`, explicitly *"a question for the use case owner, not a decision for whoever edits this file."* |
| Q15 | **What does the contract require instead of a checksum, given that core RO-Crate has no checksum property?** | (a) `sha256:` on the crate reference, verified by derivation — what `sentinel/` does; (b) nothing; (c) an external manifest | Bioprospecting notes the absence twice and proposes nothing. `sentinel/` requires it, and the `derived` check is what caught the hostile engine. |
| Q16 | **Which measurement-validity conditions are mandatory at Test → Learn?** | bioprospecting's prose names four — negative controls, replicate count, within instrument range, plate randomisation; `sentinel/` requires three (`dbtl:blankCorrected`, `dbtl:replicates`, `dbtl:withinRange`); biomanufacturing v1 names LOD/LOQ, calibration curves and blanks | This is the handover the whole project was argued from, and no two sources name the same list. **Plate randomisation is required by nothing.** |
| Q17 | **What is the agent's input surface?** | (a) a package and a contract — `sentinel/`'s `Task`; (b) TOOLS + WORKFLOW + PROMPT + provenance + context — biomanufacturing deck slide 6 | Whether an agent is a validator with an optional model, or an LLM-driven planner that emits an experimental protocol. The two readings produce very different software, and the biomanufacturing deck is the only place the second is drawn. |
| Q18 | **Which diagram is authoritative where two exist?** | biomanufacturing v1 vs v2; directed evolution v1 vs v2; deck vs SVGs | Four unreconciled pairs. v1 in both cases holds the testable detail; v2 in both cases is the newer file. Until this is settled, a contract author does not know which document to encode. |

---

## 10. What is not done

Stated plainly.

1. **Two of the three use cases have no artefact at all.** `directed_evolution/` is a README and two diagrams. `biomanufacturing/` is a one-sentence README, three diagrams and a nine-slide deck that disagrees with the diagrams on crate granularity, agent placement and scope. Neither has code, a crate, a schema, a profile or a contract. Both say so in their own footers.

2. **Only Handover 1 has a real crate anywhere in the repository**, and it covers one phase of one simulated run with 4 entities where the stated handover is 96. Handovers 2, 3 and 4 exist as contracts in `sentinel/` written from one use case's slides, and as names on a diagram.

3. **The broken crates the bioprospecting README promises do not exist in that folder**, and its README points at a reverted directory. The equivalents live in `sentinel/examples/design-to-build/` and nothing in `bioprospecting/` says so.

4. **No SHACL has ever been executed.** 162 lines are written. `pyshacl` is named in eight files and invoked by none.

5. **`dbtl:` is not minted.** Every IRI the framework writes is unresolvable, and two teams' graphs cannot be merged today.

6. **`ro-crate-py`, `rdflib`, `pyoxigraph` and `pyshacl` — the entire documented stack — are used by nothing.** What runs is a hand-written JSON Schema subset, a hand-written N-Triples writer and a hand-written N-Triples reader. That is why the framework needs no install step, and also why F2 was possible.

7. **No model has been run in a way anyone else can repeat.** The engine interface, the path gate, the re-validation and the term-rejection rule are all demonstrated with a hostile stub and with `RulesEngine`. The four-row CLI comparison in the READMEs needs three CLIs installed and logged in, and there is no ledger, fixture or transcript of the run that produced it.

8. **All the science is simulated.** Every number in every demo is generated by `usecases/bioprospecting/*`. The one piece of real third-party data in the loop is Anil's 105-entity crate, whose contents are themselves labelled SIMULATED in-band.

9. **Two phase-agent families still coexist**, and three scripts still drive the old one (D4). That duplication is what let a contract change pass its own demo and break another; it is fixed for `demo.py` and not for `demo_d2b.py`, `prove_engine.py` or `export_for_dbtlhub.py`.

10. **Two H2 checks are now demonstrated by nothing** (D5), and two check behaviours are silent no-ops under one profile or when a limit is not volunteered (D6).

11. **Nothing in any use case folder references `sentinel/`**, and `sentinel/` references a `directed_evolution` profile that does not exist. The shared framework and the three use cases have not yet been introduced to each other in writing.

12. **The plate-difference rule — the cleanest idea in the project — has never been computed**, because no Build record of a delivered plate exists anywhere.

13. **Plate randomisation, the fourth of the four Test→Learn conditions the project was argued from, is required by nothing.**

14. **Scale, multi-run panels, and the per-tool-step crate** are all acknowledged limitations with no work against them.

15. **`runner_over_mcp` has no outside witness.** The checker socket was proven against a server somebody else wrote; the runner socket could not be, because no phase agent anywhere speaks MCP yet. `run_phase` is tested only against our own server, and the containerised form of `sentinel-oo` (`docker run -i --rm sentinel-oo:dev --agent-interface`) is one `Spec` with a different argv that has not been run here — the image is not built on this machine. *(Added 13 November 2026.)*

16. **The interface is single-user.** Sessions are per browser and runs are per session, but the run id comes from the form and the worked example gives every browser the same one, there is no lock on a crate two sessions may share, and an API key pasted into the setup screen goes into the **process** environment, so it is used by everyone on that server. Measured, not inferred: two concurrent sessions wrote into one crate, and one was refused over a sample left by the other's earlier run. One server per person, sharing crates rather than a GUI, is the shape this framework is actually for. *(Added 13 November 2026.)*

---

*Compiled 2026-11-10 from four auditor briefings plus every command re-run against HEAD `ec80217`. The repository was read and executed, never modified: `git status --short` at the end lists the same three untracked files as at the start, and `sentinel/runs/` (gitignored) was removed after use.*
