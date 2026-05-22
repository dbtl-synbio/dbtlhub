<<<<<<< HEAD
# DBTL Tool Extractor

A Python pipeline that automatically extracts, classifies, and analyses all tools registered in the [bio.tools](https://bio.tools) repository, organising them according to their role in the **Design–Build–Test–Learn (DBTL)** cycle used in Systems and Synthetic Biology.

The output is a structured CSV and Excel report designed to serve as a **consultation directory** for researchers building or auditing DBTL workflows, with a focus on tool interoperability and data format compatibility.

---

## What it does

1. **Downloads** the full bio.tools catalogue via its REST API (~33 000 tools)
2. **Classifies** each tool into one or more DBTL phases using EDAM ontology topic annotations
3. **Extracts** functional metadata — input/output data types, file formats, programming languages, tool types
4. **Detects** all 15 possible DBTL phase combinations (D, B, T, L, DB, DT, ..., DBTL)
5. **Resolves** the country of origin of each tool via the [ROR API](https://ror.org) and the ELIXIR node registry
6. **Flags** interoperable tools — those with defined standard formats enabling pipeline integration
7. **Exports** results to CSV and a multi-sheet Excel report

---

## DBTL Phase Mapping

Tools are classified using EDAM ontology topic URIs mapped to each phase:

| Phase | Examples of mapped topics |
|-------|--------------------------|
| **Design** | Molecular modelling, Synthetic biology, Metabolic engineering, Systems biology |
| **Build** | Genetic engineering, Sequence assembly, Nucleic acid design, Sequencing |
| **Test** | Transcriptomics, Proteomics, Metabolomics, Gene expression, Omics |
| **Learn** | Machine learning, Bioinformatics, Statistics, Data management |

A tool can belong to **multiple phases simultaneously**, and all combinations are recorded.

---

## Output columns

| Column | Description |
|--------|-------------|
| `Tool` | Tool name |
| `Type` | Tool type (e.g. Web application, Command-line tool) |
| `Topic` | EDAM topic terms |
| `Language` | Programming language(s) |
| `Input` / `Output` | Data types accepted/produced |
| `Format input` / `Format output` | Standard file formats (e.g. FASTA, SBML, CSV) |
| `Design`, `Build`, `Test`, `Learn` | Binary phase flags (0/1) |
| `In_DBTL_Cycle` | 1 if the tool belongs to at least one phase |
| `DB`, `DT`, ..., `DBTL` | All 15 phase combination flags |
| `Country/Node` | Country resolved via ELIXIR node or ROR API |
| `Sequence (i)` | 1 if the tool accepts sequence data as input |
| `Protein structure (o)` | 1 if the tool produces protein structure data |

---

## Requirements

```
Python 3.8+
requests
pandas
openpyxl
urllib3
```

Install with:

```bash
pip install requests pandas openpyxl urllib3
```

---

## Usage

```bash
python "Bio Tools DBTL Extractor.py"
```

To run a quick test with only 2 pages (~100 tools) before the full run:

```python
# In the __main__ block, change:
df_raw = get_all_tools(max_pages=2)
```

Output files are saved in the **same directory as the script**:

| File | Description |
|------|-------------|
| `bio_tools_dbtl_5.csv` | Full dataset as CSV |
| `ror_cache.json` | ROR API cache (speeds up future runs) |

---

## Performance notes

- Full download: ~660 pages, roughly **10–15 minutes** depending on connection
- Processing without ROR: **~2 minutes**
- Processing with ROR (DBTL tools only): **~20–45 minutes** on first run, much faster on subsequent runs thanks to the cache
- ROR lookups are only performed for tools that belong to at least one DBTL phase, to avoid unnecessary API calls

---

## Project context

Developed in the context of **Systems Biology and Synthetic Biology research** as part of the DBTLHub.

The goal is to provide a structured, reproducible, and automatically updatable directory of bioinformatics tools relevant to DBTL-based workflows, with a focus on **interoperability** — identifying tools that share standard data formats and can therefore be chained into integrated pipelines.

---

## Acknowledgements

- [bio.tools](https://bio.tools) — ELIXIR's registry of bioinformatics tools
- [EDAM Ontology](https://edamontology.org) — used for topic-based classification
- [ROR](https://ror.org) — Research Organization Registry, used for country resolution
