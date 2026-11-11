# Design to Build: an example RO-Crate

This folder **is** the crate. One example of what the Design phase hands to
the Build phase in the bioprospecting DBTL cycle, for an interface agent to
read.

```
ro-crate-metadata.json   42,324 bytes, 105 entries in the @graph
panel.faa                the selected protein sequences, in FASTA
constructs.json          the construct designs
plate-layout.csv         the intended plate layout
```

All four are needed. The metadata names the other three as relative paths, and
in RO-Crate a relative path is a promise that the file is present.

## Everything here is simulated

No real sequences, samples, accessions or measurements. The amino acid and DNA
sequences are randomly generated. Every identifier under
`https://example.org/bioprospecting` is a placeholder and resolves to nothing.
The crate's own `description` says so, so an agent cannot mistake it for real
data.

## What it records

The whole Design phase, not just the last step. Reading backwards from the
panel, which is the traversal an agent actually performs:

```
panel.faa
  <- Select the panel                 from clusters.tsv, with a panel size
  <- Cluster the annotated proteins   from proteins.faa and annotations.tsv
  <- Predict protein coding genes     from contigs.fasta, with a calling mode
  <- Assemble the reads into contigs  from the trimmed reads
  <- Trim and quality filter          from the raw reads
  <- Sequence the library             from the library, Novogene shotgun
  <- Prepare the shotgun library      from the DNA extract
  <- Extract metagenomic DNA          from the sample, with a kit
  <- Collect the environmental sample from the study
```

The two ends are the point. The chain begins at a physical sample taken from
the ground on a stated date at a stated place, and ends at a DNA sequence
about to be ordered from a vendor.

The `@graph` holds 11 `CreateAction` entries, one per step, 10
`SoftwareApplication` entries for the things that performed them, 11 `File`
entries, 2 `Collection` entries for the paired-end reads, 4 `Protein`
entries for the proteins, and 54 `PropertyValue` entries carrying the named
parameters and measurements.

Four proteins and four constructs are written out in full. A real handover
carries 96 of each, which is one 96-well plate.

## How to walk the chain

There is no property that points from a thing to the action that made it.
RO-Crate has no `resultOf`. The traversal is a reverse lookup:

> to find what produced entity X, scan `@graph` for the `CreateAction`
> whose `result` contains X. To go back another step, take that action's
> `object` and repeat.

That is the single piece of graph traversal an agent needs, and it is the same
mechanism all the way down. The trimmed reads are a separate entity from the
raw reads precisely so that this walk terminates instead of looping.

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
`depth`, `temp` and `ph` are not invented here. For the sample, the agreed
vocabulary already exists and a contract only has to require it.

The reads are one `Collection` with two `File` parts and a `mainEntity`,
because paired-end reads are a single digital object stored in two files.

## The parameters that change what a sequence means

Ten parameters are carried as `PropertyValue` entries on the action that used
or produced them, rather than buried in free text. Each has a `name`, a
`value`, and where it is a number, a `unitText` saying what the number counts.
A parameter the action consumed sits in `object`; one it produced sits in
`result`.

| Parameter | Slot | Value here | Why Build needs it |
|---|---|---|---|
| sequencing platform | object | Illumina NovaSeq X Plus | sets read length and error profile |
| read layout | object | paired end | affects assembly contiguity |
| read length | object | 150 base pairs | affects assembly contiguity |
| sequencing yield | result | 61.4 gigabases | affects coverage, so affects contiguity |
| minimum contig length | object | 500 base pairs | short contigs truncate genes |
| assembly N50 | result | 3,140 base pairs | the contig length at which half the assembly sits in contigs this long or longer |
| **gene calling mode** | object | **open ends** | **open ends permits a prediction running off the end of a contig, so a sequence may be a truncated fragment** |
| annotation database release | object | 2026-02 | an annotation means nothing without the database version |
| sequence identity threshold | object | 0.90, a fraction of identical residues from 0 to 1 | sets how much diversity the panel actually spans |
| panel size | object | 96 sequences | what Build is expected to receive |

Gene calling mode matters most, and it is why the chain has to reach further
back than the preceding step. Knowing the mode alone does not tell you the
fragment risk. You also need to know whether the contigs were short, which
depends on the assembly, which depends on the coverage, which depends on the
sequencing run. Each protein additionally carries its own `coding sequence
completeness`, and one of the four here is marked `right partial`.

## What validates

Checked with `rocrate-validator` version 0.13.1, run with
`--skip-availability-check`. The crate passes **RO-Crate 1.3**.

With availability checks switched on it fails, because the placeholder
addresses under `example.org` do not resolve. That is a property of the
simulated data, not a fault in the crate.

**On the profile check.** This crate targets Process Run Crate version 0.6,
which aligns to RO-Crate 1.3 and uses two context URLs. The validator
currently implements version 0.5 of the profile, which assumes RO-Crate 1.1,
so it reports a failure on the metadata descriptor. Rewrite that descriptor's
`conformsTo` to `https://w3id.org/ro/crate/1.1` and the crate passes the 0.5
check unchanged, which is how we know the structure is right and the tool is
behind. Do not "fix" the crate to satisfy the older checker.

**Three further checks were run by hand**, because no validator makes them:
nothing in the graph is unreachable from the root, no reference points at a
missing entry, and no action consumes what it produces. All three pass. They
are cheap to write and they caught real faults in a file that had already
passed validation.

## What an agent should check

1. Does it parse, and is it valid RO-Crate?
2. Does the root declare `conformsTo` the profile?
3. Does every `@id` referenced anywhere resolve to an entry in `@graph`, and
   does every relative `@id` correspond to a file that is present?
4. Can every entity be reached from the root, and does no action consume what
   it produces?
5. Is there an unbroken chain of `CreateAction` entries from the handed-over
   files back to the sample?
6. Are the required parameters present, with the agreed `name` strings and a
   `unitText` on every numeric one?
7. Do the values mean what Build expects? Gene calling mode set to open ends
   is not an error, but it is a flag that Build must act on.

Checks 1 to 5 are generic and structural, and a crate can fail them while
passing every schema check there is. Checks 6 and 7 are the contract, and they
are the part nobody has written down yet.

## Known problems, which are real and not oversights

**A step done by a person has nothing to put in `instrument`.** Process Run
Crate requires `instrument` on every action. Panel selection is a human
judgement; a tool ranked the candidates but a person chose. Here the ranking
tool is named as the instrument and the person as the agent, which is a
reasonable reading but not a settled one.

**Physical things are being recorded as software.** The sediment corer, the
DNA extraction kit and the sequencing service are all typed
`SoftwareApplication` because that is what `instrument` expects, and RO-Crate
then demands a `version` on them, so a catalogue number stands in for one. The
profile is scoped to computational tools and has no vocabulary for laboratory
equipment. This is the clearest gap the bioprospecting use case exposes.

**`version` versus `softwareVersion`.** The profile's own worked example uses
`softwareVersion`; RO-Crate 1.3 requires `version`. Both are set here.

**One crate describes one Design run.** Every parameter above belongs to the
run, not to an individual sequence. A panel assembled from two runs with
different gene calling modes cannot be described in this shape.

## Where the rest is

`../design-to-build/` holds the generator that produces this crate, plus three
crates that are deliberately broken, for testing what an agent rejects. They
are kept separate on purpose so that this example stays simple.
