#!/usr/bin/env python3
"""Generate the Design-to-Build example RO-Crates for the bioprospecting
use case.

Produces one crate that is valid and conforms to Process Run Crate 0.6,
and three that are each broken in exactly one way, so that a checking
agent has something to pass and something to fail.

All data in these crates is SIMULATED. No real sequences, samples or
accessions are used. Run with no arguments from this directory.
"""

import csv
import json
import os
import random
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.3/context"
WFRUN_CONTEXT = "https://w3id.org/ro/terms/workflow-run/context"
RO_CRATE_SPEC = "https://w3id.org/ro/crate/1.3"
PROCESS_RUN_CRATE = "https://w3id.org/ro/wfrun/process/0.6"

# Everything under this prefix is a stand-in for a real archive record.
EX = "https://example.org/bioprospecting"

PANEL_SIZE = 96          # proteins in the real panel, a count
N_SHOWN = 4              # entities written out in full in this example

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"


def simulated_protein(rng, length):
    """An obviously synthetic amino acid sequence. Not a real protein."""
    return "M" + "".join(rng.choice(AMINO_ACIDS) for _ in range(length - 1))


def simulated_dna(rng, length):
    return "".join(rng.choice("ACGT") for _ in range(length))


def well_name(index):
    """A1, A2, ... H12 for a 96-well plate, filled by row."""
    return "%s%d" % ("ABCDEFGH"[index // 12], (index % 12) + 1)


# ---------------------------------------------------------------------
# the entities
# ---------------------------------------------------------------------

def build_graph(rng, include_gene_calling_mode=True,
                include_conformsto=True, dangling_reference=False):
    proteins = []
    constructs = []
    for i in range(N_SHOWN):
        pid = "ENR-%03d" % (i + 1)
        aa = simulated_protein(rng, rng.randint(340, 400))
        proteins.append({
            "id": pid,
            "aa": aa,
            "contig": "contig_%05d" % rng.randint(1, 48000),
            "complete": i != 2,          # one of them is a fragment
            "cluster": "cluster_%03d" % (i + 1),
            "cluster_size": rng.randint(3, 41),
            "distance": round(rng.uniform(0.02, 0.18), 3),
        })
        constructs.append({
            "id": "CON-%03d" % (i + 1),
            "protein": pid,
            "dna": simulated_dna(rng, len(aa) * 3 + 3),
            "well": well_name(i),
        })

    g = []

    # ---- the metadata descriptor ----
    g.append({
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "conformsTo": {"@id": RO_CRATE_SPEC},
        "about": {"@id": "./"},
    })

    # ---- the root ----
    has_part = [
        {"@id": "panel.faa"},
        {"@id": "constructs.json"},
        {"@id": "plate-layout.csv"},
        {"@id": EX + "/reads/"},
        {"@id": EX + "/files/contigs.fasta"},
        {"@id": EX + "/files/proteins.faa"},
        {"@id": EX + "/files/annotations.tsv"},
        {"@id": EX + "/files/clusters.tsv"},
    ]
    if dangling_reference:
        has_part.append({"@id": "sequencing-report.pdf"})

    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": "Design to Build handover, ene-reductase panel AB-12",
        "description": (
            "The output of one Design run for the bioprospecting use case: "
            "a panel of %d candidate proteins, the constructs specified from "
            "them, and the intended plate layout, together with a record of "
            "every step that produced them, back to the environmental sample. "
            "ALL DATA IN THIS CRATE IS SIMULATED. The sequences are randomly "
            "generated and are not real proteins. The accessions are "
            "placeholders under example.org and resolve to nothing."
            % PANEL_SIZE),
        "datePublished": "2026-11-10",
        "license": {"@id": "https://spdx.org/licenses/CC0-1.0"},
        "hasPart": has_part,
        "mentions": [{"@id": a} for a in [
            "#act-sampling", "#act-dna-extraction", "#act-library-prep",
            "#act-sequencing", "#act-read-qc", "#act-assembly",
            "#act-gene-calling", "#act-annotation", "#act-clustering",
            "#act-panel-selection", "#act-construct-design"]],
        "about": [{"@id": EX + "/study/STUDY-001"}],
    }
    if include_conformsto:
        root["conformsTo"] = {"@id": PROCESS_RUN_CRATE}
    g.append(root)

    # RO-Crate 1.3 requires that any value of the root's conformsTo is
    # itself described in the graph as a Profile entity.
    g.append({
        "@id": PROCESS_RUN_CRATE,
        "@type": ["CreativeWork", "Profile"],
        "name": "Process Run Crate",
        "version": "0.6",
    })

    # ---- the study and the sample: where it all traces back to ----
    g.append({
        "@id": EX + "/study/STUDY-001",
        "@type": "ResearchProject",
        "name": "Bioprospecting for ene-reductases in hot spring sediment",
        "identifier": "STUDY-001",
        "description": (
            "Stands in for a sequence archive study record. In a real crate "
            "this would be an ENA or NCBI BioProject accession."),
    })

    g.append({
        "@id": EX + "/sample/SAMPLE-AB-12",
        "@type": ["Sample", "CreativeWork"],
        "name": "Hot spring sediment, site AB, station 12",
        "identifier": "SAMPLE-AB-12",
        "description": (
            "Stands in for a BioSample record. Field names below follow "
            "MIxS, the Minimum Information about any Sequence standard, so "
            "they do not have to be invented here."),
        "isPartOf": {"@id": EX + "/study/STUDY-001"},
        "additionalProperty": [
            {"@id": "#pv-collection-date"},
            {"@id": "#pv-geo-loc"},
            {"@id": "#pv-env-medium"},
            {"@id": "#pv-depth"},
            {"@id": "#pv-temperature"},
            {"@id": "#pv-ph"},
        ],
    })

    for pid, name, value, unit in [
        ("#pv-collection-date", "collection_date", "2026-03-02", None),
        ("#pv-geo-loc", "geo_loc_name", "Iceland: Hveragerdi", None),
        ("#pv-env-medium", "env_medium", "hot spring sediment", None),
        ("#pv-depth", "depth", "0.15", "metres below sediment surface"),
        ("#pv-temperature", "temp", "68.4", "degrees Celsius"),
        ("#pv-ph", "ph", "6.8", "pH units, 0 to 14"),
    ]:
        pv = {"@id": pid, "@type": "PropertyValue",
              "name": name, "value": value}
        if unit:
            pv["unitText"] = unit
        g.append(pv)

    # ---- the physical intermediates ----
    g.append({
        "@id": EX + "/extract/DNA-AB-12",
        "@type": ["Sample", "CreativeWork"],
        "name": "Metagenomic DNA extract from sample AB-12",
        "identifier": "DNA-AB-12",
        "isPartOf": {"@id": EX + "/sample/SAMPLE-AB-12"},
        "additionalProperty": [
            {"@id": "#pv-dna-concentration"},
            {"@id": "#pv-dna-volume"},
            {"@id": "#pv-dna-purity"},
        ],
    })
    g.append({"@id": "#pv-dna-concentration", "@type": "PropertyValue",
              "name": "DNA concentration", "value": "42.6",
              "unitText": "nanograms per microlitre"})
    g.append({"@id": "#pv-dna-volume", "@type": "PropertyValue",
              "name": "DNA volume", "value": "50",
              "unitText": "microlitres"})
    g.append({"@id": "#pv-dna-purity", "@type": "PropertyValue",
              "name": "A260/A280 purity ratio", "value": "1.84",
              "unitText": "ratio of absorbance at 260 and 280 nanometres"})

    g.append({
        "@id": EX + "/library/LIB-AB-12",
        "@type": ["Sample", "CreativeWork"],
        "name": "Shotgun metagenomic library from DNA-AB-12",
        "identifier": "LIB-AB-12",
        "isPartOf": {"@id": EX + "/extract/DNA-AB-12"},
        "additionalProperty": [
            {"@id": "#pv-library-strategy"},
            {"@id": "#pv-insert-size"},
        ],
    })
    g.append({"@id": "#pv-library-strategy", "@type": "PropertyValue",
              "name": "library_strategy", "value": "WGS",
              "description": "whole genome shotgun, as an INSDC term"})
    g.append({"@id": "#pv-insert-size", "@type": "PropertyValue",
              "name": "insert size", "value": "350",
              "unitText": "base pairs"})

    # the reads, as one Collection because they are paired end
    g.append({
        "@id": EX + "/reads/",
        "@type": "Collection",
        "name": "Paired-end shotgun reads for sample AB-12",
        "hasPart": [
            {"@id": EX + "/reads/AB-12_R1.fastq.gz"},
            {"@id": EX + "/reads/AB-12_R2.fastq.gz"},
        ],
        "mainEntity": {"@id": EX + "/reads/AB-12_R1.fastq.gz"},
        "description": (
            "Held outside the crate because of size. In a real crate these "
            "would be the archive's run accession."),
    })
    for side in ("R1", "R2"):
        g.append({
            "@id": EX + "/reads/AB-12_%s.fastq.gz" % side,
            "@type": "File",
            "name": "AB-12 reads, %s" % side,
            "encodingFormat": "application/gzip",
            "alternateName": "AB-12_%s.fastq.gz" % side,
        })

    # ---- the derived files ----
    for fid, name, fmt, note in [
        (EX + "/files/contigs.fasta", "Assembled contigs", "text/x-fasta",
         "47,812 contigs, a count"),
        (EX + "/files/proteins.faa", "All predicted proteins",
         "text/x-fasta", "1,612,043 predicted protein sequences, a count"),
        (EX + "/files/annotations.tsv", "Domain annotations",
         "text/tab-separated-values", None),
        (EX + "/files/clusters.tsv", "Sequence clusters",
         "text/tab-separated-values", None),
    ]:
        e = {"@id": fid, "@type": "File", "name": name,
             "encodingFormat": fmt}
        if note:
            e["description"] = note
        g.append(e)

    for fid, name, fmt, note in [
        ("panel.faa", "The selected panel", "text/x-fasta",
         "%d selected protein sequences, a count. SIMULATED." % PANEL_SIZE),
        ("constructs.json", "Construct designs", "application/json",
         "%d construct designs, a count. SIMULATED." % PANEL_SIZE),
        ("plate-layout.csv", "Intended plate layout", "text/csv",
         "The layout requested from the synthesis vendor. Not a record of "
         "the plate that arrives."),
    ]:
        g.append({"@id": fid, "@type": "File", "name": name,
                  "encodingFormat": fmt, "description": note})

    # ---- the instruments ----
    instruments = [
        (EX + "/kit/dneasy-powersoil-pro", "SoftwareApplication",
         "DNeasy PowerSoil Pro Kit", "47016",
         "A physical extraction kit, not software. RO-Crate requires a "
         "version on every SoftwareApplication, so the catalogue number "
         "stands in for one. This is the strain showing. See the README."),
        (EX + "/service/novogene-shotgun", "SoftwareApplication",
         "Novogene shotgun metagenomic sequencing service", "2026-03",
         "A sequencing service, not software. The version is the month "
         "the service ran. Same caveat as above."),
        (EX + "/tool/read-trimmer", "SoftwareApplication",
         "read trimmer", "0.39", None),
        (EX + "/tool/assembler", "SoftwareApplication",
         "metagenome assembler", "1.4.2", None),
        (EX + "/tool/gene-caller", "SoftwareApplication",
         "gene caller", "2.6.3", None),
        (EX + "/tool/domain-scanner", "SoftwareApplication",
         "domain scanner", "5.72", None),
        (EX + "/tool/clustering-tool", "SoftwareApplication",
         "clustering tool", "2.0", None),
        (EX + "/tool/panel-designer", "SoftwareApplication",
         "panel designer", "0.9", None),
        (EX + "/tool/codon-optimiser", "SoftwareApplication",
         "codon optimiser", "2.1", None),
    ]
    for iid, itype, name, version, note in instruments:
        e = {"@id": iid, "@type": itype, "name": name, "url": iid}
        if version:
            # Process Run Crate's own example uses softwareVersion, while
            # RO-Crate 1.3 requires version on every SoftwareApplication.
            # Both are set so the crate satisfies both.
            e["softwareVersion"] = version
            e["version"] = version
        if note:
            e["description"] = note
        g.append(e)

    g.append({"@id": "#operator", "@type": "Person",
              "name": "Simulated operator"})

    # ---- the promoted parameters ----
    params = [
        ("#pv-sequencing-platform", "sequencing platform",
         "Illumina NovaSeq X Plus", None),
        ("#pv-read-layout", "read layout", "paired end", None),
        ("#pv-read-length", "read length", "150", "base pairs"),
        ("#pv-yield", "sequencing yield", "61.4", "gigabases"),
        ("#pv-min-contig-length", "minimum contig length", "500",
         "base pairs"),
        ("#pv-assembly-n50", "assembly N50", "3140",
         "base pairs, the contig length at which half the assembly sits in "
         "contigs this long or longer"),
        ("#pv-identity-threshold", "sequence identity threshold", "0.90",
         "fraction of identical residues, 0 to 1 where 1 is identical"),
        ("#pv-annotation-db", "annotation reference database release",
         "2026-02", None),
        ("#pv-panel-size", "panel size", str(PANEL_SIZE), "sequences"),
    ]
    if include_gene_calling_mode:
        params.append(("#pv-gene-calling-mode", "gene calling mode",
                       "open ends",
                       "complete ends or open ends. Open ends allows a "
                       "prediction that runs off the end of a contig, so a "
                       "sequence may be a truncated fragment."))
    for pid, name, value, unit in params:
        pv = {"@id": pid, "@type": "PropertyValue",
              "name": name, "value": value}
        if unit:
            pv["unitText"] = unit
        g.append(pv)

    # ---- the actions ----
    actions = [
        ("#act-sampling", "Collect the environmental sample",
         EX + "/kit/dneasy-powersoil-pro",
         [EX + "/study/STUDY-001"],
         [EX + "/sample/SAMPLE-AB-12"],
         "2026-03-02T11:40:00Z",
         "Sediment collected by hand into a sterile tube and frozen on "
         "site. Recorded here only so that the chain is unbroken."),
        ("#act-dna-extraction", "Extract metagenomic DNA",
         EX + "/kit/dneasy-powersoil-pro",
         [EX + "/sample/SAMPLE-AB-12"],
         [EX + "/extract/DNA-AB-12"],
         "2026-03-05T14:05:00Z", None),
        ("#act-library-prep", "Prepare the shotgun library",
         EX + "/service/novogene-shotgun",
         [EX + "/extract/DNA-AB-12"],
         [EX + "/library/LIB-AB-12"],
         "2026-03-09T09:00:00Z", None),
        ("#act-sequencing", "Sequence the library",
         EX + "/service/novogene-shotgun",
         [EX + "/library/LIB-AB-12", "#pv-sequencing-platform",
          "#pv-read-layout", "#pv-read-length", "#pv-yield"],
         [EX + "/reads/"],
         "2026-03-11T22:15:00Z",
         "Novogene shotgun metagenomic sequencing service."),
        ("#act-read-qc", "Trim and quality filter the reads",
         EX + "/tool/read-trimmer",
         [EX + "/reads/"],
         [EX + "/reads/"],
         "2026-03-12T08:30:00Z",
         "Adapter trimming and quality filtering, in place."),
        ("#act-assembly", "Assemble the reads into contigs",
         EX + "/tool/assembler",
         [EX + "/reads/", "#pv-min-contig-length"],
         [EX + "/files/contigs.fasta", "#pv-assembly-n50"],
         "2026-03-13T19:52:00Z", None),
        ("#act-gene-calling", "Predict protein coding genes",
         EX + "/tool/gene-caller",
         ([EX + "/files/contigs.fasta", "#pv-gene-calling-mode"]
          if include_gene_calling_mode
          else [EX + "/files/contigs.fasta"]),
         [EX + "/files/proteins.faa"],
         "2026-03-14T09:21:00Z", None),
        ("#act-annotation", "Annotate the predicted proteins",
         EX + "/tool/domain-scanner",
         [EX + "/files/proteins.faa", "#pv-annotation-db"],
         [EX + "/files/annotations.tsv"],
         "2026-03-15T06:03:00Z", None),
        ("#act-clustering", "Cluster the annotated proteins",
         EX + "/tool/clustering-tool",
         [EX + "/files/proteins.faa", EX + "/files/annotations.tsv",
          "#pv-identity-threshold"],
         [EX + "/files/clusters.tsv"],
         "2026-03-15T15:48:00Z", None),
        ("#act-panel-selection", "Select the panel",
         EX + "/tool/panel-designer",
         [EX + "/files/clusters.tsv", "#pv-panel-size"],
         ["panel.faa"],
         "2026-03-16T10:12:00Z",
         "A person chose the final members. The tool ranked candidates; it "
         "did not decide. See the README on human steps."),
        ("#act-construct-design", "Specify the constructs",
         EX + "/tool/codon-optimiser",
         ["panel.faa"],
         ["constructs.json", "plate-layout.csv"],
         "2026-03-17T13:30:00Z", None),
    ]
    for aid, name, instrument, objs, results, end, desc in actions:
        e = {
            "@id": aid,
            "@type": "CreateAction",
            "name": name,
            "instrument": {"@id": instrument},
            "object": [{"@id": o} for o in objs],
            "result": [{"@id": r} for r in results],
            "agent": {"@id": "#operator"},
            "endTime": end,
            "actionStatus": "http://schema.org/CompletedActionStatus",
        }
        if desc:
            e["description"] = desc
        g.append(e)

    # ---- the plate: the intended layout only ----
    g.append({
        "@id": "#plate-AB-12-01",
        "@type": "CreativeWork",
        "name": "Intended plate layout for panel AB-12",
        "identifier": "PLATE-AB-12-01",
        "description": (
            "What Design asked the synthesis vendor for. It is NOT a record "
            "of the plate that arrives. Build records that separately, and "
            "the difference between the two is the synthesis failures."),
        "additionalProperty": [{"@id": "#pv-plate-format"}],
    })
    g.append({"@id": "#pv-plate-format", "@type": "PropertyValue",
              "name": "plate format", "value": "96",
              "unitText": "wells"})

    # ---- the proteins ----
    for p in proteins:
        g.append({
            "@id": "#protein-" + p["id"],
            "@type": "BioChemEntity",
            "identifier": p["id"],
            "name": "Candidate ene-reductase " + p["id"],
            "description": "SIMULATED sequence. Not a real protein.",
            "isBasedOn": {"@id": EX + "/files/contigs.fasta"},
            "additionalProperty": [
                {"@id": "#pv-%s-seq" % p["id"]},
                {"@id": "#pv-%s-contig" % p["id"]},
                {"@id": "#pv-%s-complete" % p["id"]},
                {"@id": "#pv-%s-cluster" % p["id"]},
                {"@id": "#pv-%s-distance" % p["id"]},
            ],
        })
        g.append({"@id": "#pv-%s-seq" % p["id"], "@type": "PropertyValue",
                  "name": "amino acid sequence", "value": p["aa"],
                  "unitText": "one letter amino acid codes"})
        g.append({"@id": "#pv-%s-contig" % p["id"], "@type": "PropertyValue",
                  "name": "source contig", "value": p["contig"]})
        g.append({"@id": "#pv-%s-complete" % p["id"],
                  "@type": "PropertyValue",
                  "name": "coding sequence completeness",
                  "value": "complete" if p["complete"] else "right partial",
                  "description": ("complete, left partial, right partial or "
                                  "both partial. Anything but complete means "
                                  "the sequence may be truncated.")})
        g.append({"@id": "#pv-%s-cluster" % p["id"],
                  "@type": "PropertyValue",
                  "name": "cluster identifier", "value": p["cluster"],
                  "description": "cluster size %d sequences"
                                 % p["cluster_size"]})
        g.append({"@id": "#pv-%s-distance" % p["id"],
                  "@type": "PropertyValue",
                  "name": "distance to cluster centre",
                  "value": str(p["distance"]),
                  "unitText": ("1 minus fractional identity, 0 to 1 where 0 "
                               "is the cluster centre itself")})

    # ---- the constructs ----
    for c in constructs:
        g.append({
            "@id": "#construct-" + c["id"],
            "@type": "CreativeWork",
            "identifier": c["id"],
            "name": "Expression construct " + c["id"],
            "description": "SIMULATED sequence. Not a real construct.",
            "isBasedOn": {"@id": "#protein-" + c["protein"]},
            "additionalProperty": [
                {"@id": "#pv-%s-dna" % c["id"]},
                {"@id": "#pv-%s-plate" % c["id"]},
                {"@id": "#pv-%s-well" % c["id"]},
                {"@id": "#pv-%s-host" % c["id"]},
            ],
        })
        g.append({"@id": "#pv-%s-dna" % c["id"], "@type": "PropertyValue",
                  "name": "codon optimised coding sequence",
                  "value": c["dna"], "unitText": "DNA bases"})
        g.append({"@id": "#pv-%s-plate" % c["id"], "@type": "PropertyValue",
                  "name": "intended plate", "value": "PLATE-AB-12-01"})
        g.append({"@id": "#pv-%s-well" % c["id"], "@type": "PropertyValue",
                  "name": "intended well", "value": c["well"],
                  "description": "row letter then column number, A1 to H12"})
        g.append({"@id": "#pv-%s-host" % c["id"], "@type": "PropertyValue",
                  "name": "expression host",
                  "value": "Escherichia coli BL21(DE3)"})

    return g, proteins, constructs


# ---------------------------------------------------------------------
# the payload files
# ---------------------------------------------------------------------

def write_payload(out_dir, proteins, constructs):
    with open(os.path.join(out_dir, "panel.faa"), "w") as fh:
        for p in proteins:
            fh.write(">%s SIMULATED sequence, not a real protein\n"
                     % p["id"])
            for i in range(0, len(p["aa"]), 60):
                fh.write(p["aa"][i:i + 60] + "\n")

    with open(os.path.join(out_dir, "constructs.json"), "w") as fh:
        json.dump({
            "note": "SIMULATED. Not real construct sequences.",
            "constructs": [
                {"identifier": c["id"],
                 "based_on_protein": c["protein"],
                 "coding_sequence": c["dna"],
                 "intended_plate": "PLATE-AB-12-01",
                 "intended_well": c["well"],
                 "expression_host": "Escherichia coli BL21(DE3)"}
                for c in constructs],
        }, fh, indent=2)
        fh.write("\n")

    with open(os.path.join(out_dir, "plate-layout.csv"), "w",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["plate", "well", "construct", "protein"])
        for c in constructs:
            w.writerow(["PLATE-AB-12-01", c["well"], c["id"], c["protein"]])


def write_crate(name, graph, proteins, constructs, payload=True):
    out_dir = os.path.join(HERE, name)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    with open(os.path.join(out_dir, "ro-crate-metadata.json"), "w") as fh:
        json.dump({"@context": [RO_CRATE_CONTEXT, WFRUN_CONTEXT],
                   "@graph": graph}, fh, indent=2)
        fh.write("\n")

    if payload:
        write_payload(out_dir, proteins, constructs)
    return out_dir


def main():
    rng = random.Random(20261110)
    g, proteins, constructs = build_graph(rng)
    print("wrote", write_crate("valid", g, proteins, constructs),
          "(%d entities in the graph)" % len(g))

    rng = random.Random(20261110)
    g, p, c = build_graph(rng, include_conformsto=False)
    print("wrote", write_crate(os.path.join("invalid",
                                            "missing-conformsto"),
                               g, p, c))

    rng = random.Random(20261110)
    g, p, c = build_graph(rng, dangling_reference=True)
    print("wrote", write_crate(os.path.join("invalid",
                                            "dangling-reference"), g, p, c))

    rng = random.Random(20261110)
    g, p, c = build_graph(rng, include_gene_calling_mode=False)
    print("wrote", write_crate(os.path.join("invalid",
                                            "missing-gene-calling-mode"),
                               g, p, c))


if __name__ == "__main__":
    main()
