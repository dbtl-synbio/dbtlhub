# Design to Build: example RO-Crates

Example crates for the first handover of the bioprospecting DBTL cycle, the
point at which the Design phase hands its output to the Build phase. They
exist so that an interface agent has something concrete to read, something to
accept, and something to reject.

## Everything here is simulated

No real sequences, samples, accessions or measurements appear in these
crates. The amino acid and DNA sequences are randomly generated from a fixed
seed. Every identifier under `https://example.org/bioprospecting` is a
placeholder and resolves to nothing. The crate's own `description` says so as
well, so an agent reading it cannot mistake it for real data.

## What is in the box

```
valid/
  ro-crate-metadata.json   40,446 bytes, 105 entries in the @graph
  panel.faa                the selected protein sequences, in FASTA
  constructs.json          the construct designs
  plate-layout.csv         the intended plate layout
invalid/
  missing-conformsto/      breaks a profile requirement
  dangling-reference/      names a file that is not there
  missing-gene-calling-mode/  valid, but breaks the contract
make_crate.py              regenerates all four
```

The valid crate's `@graph` holds 11 `CreateAction` entries, one per step,
9 `SoftwareApplication` entries for the things that performed them, 9 `File`
entries, 4 `BioChemEntity` entries for the proteins, and 58 `PropertyValue`
entries carrying the named parameters and measurements.

Four proteins and four constructs are written out in full. A real handover
carries 96 of each, which is one 96-well plate. Four is enough to write an
agent against and short enough to read.

## The provenance chain

The crate records the whole Design phase, not just the last step. Reading
backwards from a protein in the panel:

```
panel.faa
  <- #act-panel-selection      from clusters.tsv, with a panel size
  <- #act-clustering           from proteins.faa, with an identity threshold
  <- #act-annotation           from proteins.faa, with a database release
  <- #act-gene-calling         from contigs.fasta, with a gene calling mode
  <- #act-assembly             from the reads, with a minimum contig length
  <- #act-read-qc              from the reads
  <- #act-sequencing           from the library, Novogene shotgun service
  <- #act-library-prep         from the DNA extract
  <- #act-dna-extraction       from the sample, with a kit and concentration
  <- #act-sampling             from the study
```

The two ends are the point. The chain begins at a physical sample taken from
the ground on a stated date at a stated place, and ends at a DNA sequence
about to be ordered from a vendor.

### How to walk it

There is no property that points from a thing to the action that made it.
RO-Crate has no `resultOf`. The traversal is therefore a reverse lookup:

> to find what produced entity X, scan `@graph` for the `CreateAction`
> whose `result` contains X. To go back another step, take that action's
> `object` and repeat.

That is the single piece of graph traversal an agent needs, and it is the
same mechanism all the way down.

## Tying a sequence back to the study and the sample

The crate follows the hierarchy every sequence archive already uses:

| Level | Entity in this crate | In a real crate |
|---|---|---|
| Study | `.../study/STUDY-001` | an ENA study or NCBI BioProject accession |
| Sample | `.../sample/SAMPLE-AB-12` | a BioSample accession |
| Experiment | `.../library/LIB-AB-12` | the library record |
| Run | `.../reads/` | the sequencing run accession |

The sample's own fields use **MIxS** names, the Minimum Information about any
Sequence standard, so `collection_date`, `geo_loc_name`, `env_medium`,
`depth`, `temp` and `ph` are not invented here. That matters: for the sample,
the agreed vocabulary already exists and the contract only has to require it.

The reads are one `Collection` with two `File` parts and a `mainEntity`,
because paired-end reads are a single digital object stored in two files.

## The parameters that change what a sequence means

Nine parameters are carried as `PropertyValue` entries inside the `object` of
the action that used them, rather than buried in free text. Each has a `name`,
a `value`, and where it is a number, a `unitText` saying what the number
counts.

| Parameter | Value in this example | Why Build needs it |
|---|---|---|
| sequencing platform | Illumina NovaSeq X Plus | sets read length and error profile |
| read layout | paired end | affects assembly contiguity |
| read length | 150 base pairs | affects assembly contiguity |
| sequencing yield | 61.4 gigabases | affects coverage, so affects contiguity |
| minimum contig length | 500 base pairs | short contigs truncate genes |
| assembly N50 | 3,140 base pairs | the contig length at which half the assembly sits in contigs this long or longer |
| **gene calling mode** | **open ends** | **open ends permits a prediction running off the end of a contig, so a sequence may be a truncated fragment** |
| annotation database release | 2026-02 | an annotation means nothing without the database version |
| sequence identity threshold | 0.90, a fraction of identical residues from 0 to 1 | sets how much diversity the panel actually spans |

Gene calling mode is the one that matters most, and it is why the chain has to
reach further back than the preceding step. Knowing the mode alone does not
tell you the fragment risk. You also need to know whether the contigs were
short, which depends on the assembly, which depends on the coverage, which
depends on the sequencing run. Each protein additionally carries its own
`coding sequence completeness`, and one of the four in this example is
deliberately marked `right partial`.

## What validates, and what does not

Checked with `rocrate-validator` version 0.13.1.

| Crate | RO-Crate 1.3 | Process Run Crate | Caught by a validator? |
|---|---|---|---|
| `valid/` | passes | see the note below | n/a |
| `invalid/missing-conformsto/` | passes | fails, no `conformsTo` on the root | yes, by the profile check |
| `invalid/dangling-reference/` | passes | passes | **no** |
| `invalid/missing-gene-calling-mode/` | passes | passes | **no** |

Run with `--skip-availability-check`. With availability checks switched on,
every crate here fails, including the valid one, because the placeholder
addresses under `example.org` do not resolve. That is a property of the
simulated data, not a fault in the crates.

**Two of the three broken crates are not caught by any validator**, which is
the point of including them.

`dangling-reference` adds `sequencing-report.pdf` to the root's `hasPart`
and does not supply the file. We checked: this validator reports the same
six issues for it as for the valid crate, so the missing file is not
isolated. An agent has to make that check itself, which is check 3 below.

**The note.** This crate targets Process Run Crate version 0.6, which aligns
to RO-Crate 1.3 and uses two context URLs. The validator currently implements
version 0.5 of the profile, which assumes RO-Crate 1.1. Rewrite the metadata
descriptor's `conformsTo` to `https://w3id.org/ro/crate/1.1` and the crate
passes the 0.5 check unchanged, which is how we know the structure is right
and the tool is behind. Do not "fix" the crate to satisfy the older checker.

**`missing-gene-calling-mode` is the one to build against.** It passes every
automated check there is and must still be rejected, because the gene calling
mode is absent and Build cannot tell whether the sequences may be truncated.
That is the whole argument for having a contract on top of a profile:
conformance is not sufficiency.

## What an agent should check

1. Does it parse, and is it valid RO-Crate?
2. Does the root declare `conformsTo` the profile?
3. Does every `@id` referenced anywhere resolve to an entry in `@graph`, and
   does every relative `@id` correspond to a file that is present?
4. Is there an unbroken chain of `CreateAction` entries from the handed-over
   files back to the sample?
5. Are the required parameters present, with the agreed `name` strings and a
   `unitText` on every numeric one?
6. Do the values mean what Build expects? Gene calling mode set to open ends
   is not an error, but it is a flag that Build must act on.

Checks 1 to 3 are generic. Check 4 is structural. Checks 5 and 6 are the
contract, and they are the part nobody has written down yet.

## Known problems, which are real and not oversights

**A step done by a person has nothing to put in `instrument`.** Process Run
Crate requires `instrument` on every action. Panel selection is a human
judgement; a tool ranked the candidates but a person chose. Here the ranking
tool is named as the instrument and the person as the agent, which is a
reasonable reading but not a settled one.

**Physical things are being recorded as software.** The DNA extraction kit and
the sequencing service are typed `SoftwareApplication` because that is what
`instrument` expects, and RO-Crate then demands a `version` on them, so the
kit's catalogue number stands in for one. The profile is scoped to
computational tools and has no vocabulary for laboratory equipment. This is
the clearest gap the bioprospecting use case exposes.

**`version` versus `softwareVersion`.** The profile's own worked example uses
`softwareVersion`; RO-Crate 1.3 requires `version`. Both are set here.

**One crate describes one Design run.** Every parameter above belongs to the
run, not to an individual sequence. A panel assembled from two runs with
different gene calling modes cannot be described in this shape.

## Regenerating

```
python3 make_crate.py
```

No dependencies beyond the Python standard library. The random seed is fixed,
so the output is byte for byte reproducible.
