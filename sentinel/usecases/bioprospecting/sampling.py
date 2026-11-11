"""Design, for bioprospecting: from a field sample to a FASTA worth ordering.

This stands in for the real Design phase. The output the synthesis provider needs
is trivial - a list of sequences and the well each one goes in. Everything else
here exists because of the question somebody will ask in six months: *where did
this sequence come from?*

The chain, every link of which is an entity in the crate:

    site  --collected-->  sample  --stored-->  freezer
      |                      |
      |                  extraction -> DNA -> sequencing -> reads
      |                                                      |
      |                                            assembly -> contigs
      |                                     gene prediction -> proteins
      |                                      HMM annotation -> hits
      |                                   candidate selection -> FASTA
      |                                 codon optimisation -> ordered FASTA

Written the way a lab actually writes it: local keys (`freezer_temp`, `latitude`),
not ontology terms. Aligning those is the agent's job, not the lab's - asking a
technician to type `dwc:decimalLatitude` is how you get no metadata at all.

Deterministic. `faults` injects the three failures that really happen.
"""
from __future__ import annotations

import hashlib
import random

from usecases.bioprospecting.instruments import WELLS

AA = "ACDEFGHIKLMNPQRSTVWY"


def _seq(rng, n: int) -> str:
    return "M" + "".join(rng.choice(AA) for _ in range(n - 1))


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _ref(*ids):
    """JSON-LD reference, the RO-Crate way: {"@id": ...} and never a bare string."""
    return [{"@id": i} for i in ids] if len(ids) > 1 else {"@id": ids[0]}


def design_crate(n: int = 6, seed: int = 7, faults: set[str] | None = None) -> dict:
    """Build the RO-Crate that Design hands to Build.

    faults:
        missing_geo    the field form was filled in without coordinates
        orphan_fasta   a sequence appears with no link to what produced it
        unaligned_key  a technician used their own key for the storage temperature
    """
    faults = faults or set()
    rng = random.Random(seed)
    graph: list[dict] = []
    temp_key = "box_temp_c" if "unaligned_key" in faults else "freezer_temp"

    # ---- the field site ----------------------------------------------------
    site = {
        "@id": "#site/NS-01", "@type": ["schema:Place", "dwc:Location"],
        "site_name": "Nordseekanal sediment, station 1",
        "biome": "ENVO:00002150",                     # marine biome
        "environmental_material": "ENVO:00002113",    # marine sediment
        "depth_m": 18.5,
    }
    if "missing_geo" not in faults:
        site["latitude"] = 53.4712
        site["longitude"] = 9.8013
    graph.append(site)

    # ---- the collection event and the physical sample ----------------------
    graph.append({
        "@id": "#event/COLL-2026-04-12", "@type": ["prov:Activity", "dwc:Event"],
        "name": "sediment core collection",
        "collection_date": "2026-04-12",
        "collected_by": "https://orcid.org/0000-0002-1825-0097",
        "location": _ref("#site/NS-01"),
        "output": _ref("#sample/SAMP-001"),
    })
    graph.append({
        "@id": "#sample/SAMP-001",
        "@type": ["bioschemas:BioSample", "prov:Entity"],
        "name": "sediment core NS-01 / 0-5 cm",
        "produced_by": _ref("#event/COLL-2026-04-12"),
        "location": _ref("#site/NS-01"),
        "collection_date": "2026-04-12",
        "collected_by": "https://orcid.org/0000-0002-1825-0097",
        "freezer_id": "FRZ-02",
        "rack": "R3/B2/S07",
        temp_key: -80.0,
        "unit": "degC",
        "aliquots": 4,
    })

    # ---- the in silico chain ----------------------------------------------
    steps = [
        ("#action/extract",  "DNA extraction",   "DNeasy PowerSoil Pro", None,
         "#material/DNA-001", ["dbtl:Material", "prov:Entity"], "#sample/SAMP-001"),
        ("#action/sequence", "shotgun sequencing", "Illumina NovaSeq X", None,
         "#file/reads.fastq.gz", ["schema:MediaObject", "prov:Entity"], "#material/DNA-001"),
        ("#action/assemble", "metagenome assembly", "MEGAHIT", "megahit",
         "#file/contigs.fa", ["schema:MediaObject", "prov:Entity"], "#file/reads.fastq.gz"),
        ("#action/predict",  "gene prediction",  "Prodigal", "prodigal",
         "#file/proteins.faa", ["schema:MediaObject", "prov:Entity"], "#file/contigs.fa"),
        ("#action/annotate", "HMM search against Pfam", "HMMER hmmsearch", "hmmer",
         "#file/hits.tbl", ["schema:MediaObject", "prov:Entity"], "#file/proteins.faa"),
    ]
    for aid, label, tool, biotools, out, out_type, src in steps:
        step = {"@id": aid, "@type": ["prov:Activity", "schema:CreateAction"],
                "name": label, "tool": tool, "tool_version": "see run log",
                "input": _ref(src), "output": _ref(out)}
        if biotools:
            step["biotools_id"] = biotools
        graph.append(step)
        graph.append({"@id": out, "@type": out_type, "name": label + " output",
                      "produced_by": _ref(aid), "derived_from": _ref(src)})

    # ---- the candidates themselves ----------------------------------------
    items = []
    for i in range(1, n + 1):
        cid = f"CAND-{i:03d}"
        raw, opt = f"#seq/{cid}", f"#seq/{cid}-opt"
        protein = _seq(rng, rng.randrange(230, 420))
        dna_len = (len(protein) + 1) * 3

        orphan = "orphan_fasta" in faults and i == 3

        graph.append({
            "@id": raw, "@type": ["bioschemas:Protein", "prov:Entity"],
            "name": f"candidate {cid} (predicted glycoside hydrolase)",
            "accession": f"MGYP:{rng.randrange(10**9, 10**10)}",
            "sequence_sha256": _sha(protein),
            "length_aa": len(protein),
            **({} if orphan else {"derived_from": _ref("#file/hits.tbl"),
                                  "produced_by": _ref("#action/select")}),
        })
        graph.append({
            "@id": opt, "@type": ["schema:MediaObject", "prov:Entity"],
            "name": f"{cid} codon-optimised for E. coli BL21",
            "encodingFormat": "application/x-fasta",
            "sequence_sha256": _sha(protein + "/opt"),
            "length_bp": dna_len,
            "derived_from": _ref(raw),
            "produced_by": _ref("#action/codon-opt"),
        })
        items.append({"design_item_id": cid, "crate_entity": opt,
                      "accession": f"MGYP:{rng.randrange(10**9, 10**10)}",
                      "length_bp": dna_len, "sequence_sha256": _sha(protein + "/opt"),
                      "sequence_type": "dna"})

    graph.append({"@id": "#action/select", "@type": ["prov:Activity", "schema:CreateAction"],
                  "name": "candidate selection (maximum diversity over the hit set)",
                  "tool": "in-house, see Atallah et al. 2024",
                  "input": _ref("#file/hits.tbl"),
                  "output": _ref(*[f"#seq/{it['design_item_id']}" for it in items])})
    graph.append({"@id": "#action/codon-opt", "@type": ["prov:Activity", "schema:CreateAction"],
                  "name": "codon optimisation", "tool": "PartsGenie",
                  "biotools_id": "partsgenie",
                  "output": _ref(*[it["crate_entity"] for it in items])})

    return {
        "@context": ["https://w3id.org/ro/crate/1.1/context",
                     {k: v for k, v in _crate_context().items()}],
        "@graph": [
            # The descriptor says which version of RO-Crate the FILE follows.
            # Which profile the CONTENT follows is a different statement and
            # belongs on the root: a reader that has only the first one can
            # parse the crate and cannot interpret it. Both were on the
            # descriptor here until a contract check said so.
            {"@id": "ro-crate-metadata.json", "@type": "schema:CreativeWork",
             "conformsTo": _ref("https://w3id.org/ro/crate/1.1"),
             "about": _ref("./")},
            {"@id": "./", "@type": "schema:Dataset",
             "name": "bioprospecting Design handover, panel of %d candidates" % n,
             "conformsTo": _ref("https://w3id.org/ro/wfrun/process/0.5"),
             "datePublished": "2026-11-10",
             "license": _ref("https://spdx.org/licenses/CC-BY-4.0"),
             "hasPart": _ref(*[it["crate_entity"] for it in items]),
             "mentions": _ref("#sample/SAMP-001")},
            *graph,
        ],
    }, items


def _crate_context() -> dict:
    """Term definitions the RO-Crate 1.1 context does not carry."""
    from framework.vocab import PREFIXES
    return {k: v for k, v in PREFIXES.items() if k != "schema"}


def order_from_crate(items, container: str = "ORDPLATE-1") -> dict:
    """What actually leaves the building.

    The provider gets sequences and wells. Nothing about freezers, coordinates or
    who held the corer - and that is correct: it is not their business, and
    sending it would be a data-sharing decision nobody authorised. The contract's
    job is to guarantee that what we strip here is still recoverable on our side.
    """
    return {
        "provider": "generic synthesis provider",
        "format": "fasta",
        "container_id": container,
        "items": [
            {"order_item_id": f"ORD-{i:03d}", "position": WELLS[i - 1],
             "design_item_id": it["design_item_id"],
             "sequence_type": it["sequence_type"], "length_bp": it["length_bp"],
             "sequence_sha256": it["sequence_sha256"]}
            for i, it in enumerate(items, start=1)
        ],
    }
