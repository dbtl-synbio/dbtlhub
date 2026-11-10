"""Read a real Design -> Build crate from disk, in the Process Run Crate style.

This exists for one crate in particular: the bioprospecting use case's own
example, `bioprospecting/exampleROcrates/design-to-build-simple/`, written by
Anil Wipat. It is the crate the handover has to accept, so the handover is
checked against it rather than only against the simulated one in `sampling.py`.

What this file does NOT do is change the agent or the contract. It is an
ingest step: it reads the folder and returns the two things Handover 1 takes,
a crate and the list of items being ordered. Everything the agent then does -
align, normalise, verify, project the order, refuse - is the same code that
runs on the simulated crate.

Three things differ between that crate and ours, and all three are handled in
the profile rather than here:

    provenance is walked backwards through CreateAction result/object instead
    of forwards through PROV properties;
    the sample's metadata is in named PropertyValue entries hanging off
    additionalProperty, not in flat keys;
    three entities share the type Sample - the field sample, the DNA extract
    and the library - so the root is the one that belongs to the study.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

# Inside dbtl-synbio/dbtlhub this resolves without an argument.
DEFAULT = (Path(__file__).resolve().parent.parent.parent.parent
           / "bioprospecting" / "exampleROcrates" / "design-to-build-simple")


class CrateError(RuntimeError):
    """The folder is not a crate we can read, and we say exactly why."""


def load(folder: str | Path | None = None) -> tuple[dict, list[dict], dict]:
    """Return (crate, items, report) for a crate folder on disk.

    `report` records what was read and what was missing, so a run against
    somebody else's crate says plainly what it did rather than quietly
    assuming.
    """
    root = Path(folder or DEFAULT).expanduser().resolve()
    descriptor = root / "ro-crate-metadata.json"
    if not descriptor.exists():
        raise CrateError(f"no ro-crate-metadata.json in {root}")

    crate = json.loads(descriptor.read_text())
    graph = crate.get("@graph") or []
    index = {e["@id"]: e for e in graph if isinstance(e, dict) and "@id" in e}

    # In RO-Crate a relative @id is a promise that the file is there. Check it:
    # a dangling reference is invisible to a profile validator and is one of
    # the things the use case's own notes ask an agent to catch.
    promised, missing = [], []
    for node in graph:
        ref = node.get("@id", "")
        if (isinstance(node, dict) and "File" in _types(node)
                and not ref.startswith(("http://", "https://", "#"))):
            promised.append(ref)
            if not (root / ref).exists():
                missing.append(ref)

    constructs = _constructs(root)
    plate = _plate(root)
    proteins = {e.get("identifier"): e["@id"] for e in graph
                if isinstance(e, dict) and "BioChemEntity" in _types(e)}

    items = []
    for row in plate:
        construct = constructs.get(row["construct"])
        entity = proteins.get(row["protein"])
        if construct is None or entity is None:
            # Deliberately not skipped silently: the plate claims something the
            # crate does not contain, and the handover should hear about it.
            items.append({"design_item_id": row["construct"],
                          "crate_entity": entity or f"#protein-{row['protein']}",
                          "sequence_type": "dna", "length_bp": 0,
                          "sequence_sha256": "sha256:" + "0" * 64,
                          "well": row["well"]})
            continue
        dna = construct.get("coding_sequence", "")
        items.append({
            "design_item_id": row["construct"],
            "crate_entity": entity,
            "sequence_type": "dna",
            "length_bp": len(dna),
            "sequence_sha256": "sha256:" + hashlib.sha256(dna.encode()).hexdigest(),
            "well": row["well"],
        })

    report = {
        "root": str(root),
        "entities": len(graph),
        "files_promised": len(promised),
        "files_missing": missing,
        "constructs": len(constructs),
        "plate_rows": len(plate),
        "proteins": len(proteins),
        "conforms_to": _conforms_to(index),
    }
    return crate, items, report


BREAKAGES = {
    "missing-conformsto": "the root no longer declares the profile it follows",
    "dangling-reference": "the crate names a file that is not there",
    "missing-gene-calling-mode": "valid RO-Crate, valid profile, and Build "
                                 "still cannot tell whether the sequences are "
                                 "truncated",
}


def damage(crate: dict, kind: str, root: str | Path) -> tuple[dict, list[str]]:
    """Return a deliberately broken copy of a crate, and its missing files.

    The three breakages are the ones the use case's own notes single out, and
    two of them are invisible to every RO-Crate validator there is. A check
    nobody has seen fail is a check nobody trusts, so they are here to be run
    rather than described.
    """
    if kind not in BREAKAGES:
        raise CrateError(f"no breakage named {kind!r}. Known: {', '.join(BREAKAGES)}")
    crate = json.loads(json.dumps(crate))          # never touch the original
    graph = crate.setdefault("@graph", [])
    index = {e["@id"]: e for e in graph if isinstance(e, dict) and "@id" in e}

    if kind == "missing-conformsto":
        index.get("ro-crate-metadata.json", {}).pop("conformsTo", None)

    elif kind == "dangling-reference":
        ghost = "sequencing-report.pdf"
        graph.append({"@id": ghost, "@type": "File",
                      "name": "Sequencing provider report",
                      "encodingFormat": "application/pdf"})
        root_node = index.get("./") or next(
            (e for e in graph if "Dataset" in _types(e)), None)
        if root_node is not None:
            root_node.setdefault("hasPart", []).append({"@id": ghost})

    elif kind == "missing-gene-calling-mode":
        for node in graph:
            if "CreateAction" not in _types(node):
                continue
            if not any(str(r).endswith("/tool/gene-caller")
                       for r in _ids(node.get("instrument"))):
                continue
            node["object"] = [o for o in node.get("object", [])
                              if not str(o.get("@id", "")).endswith("gene-calling-mode")]

    missing = [e["@id"] for e in graph
               if isinstance(e, dict) and "File" in _types(e)
               and not str(e.get("@id", "")).startswith(("http://", "https://", "#"))
               and not (Path(root) / e["@id"]).exists()]
    return crate, missing


def _ids(value) -> list[str]:
    if isinstance(value, dict):
        return [value["@id"]] if "@id" in value else []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_ids(item))
        return out
    return [value] if isinstance(value, str) else []


def _types(node: dict) -> list[str]:
    value = node.get("@type")
    return value if isinstance(value, list) else [value] if value else []


def _conforms_to(index: dict) -> list[str]:
    node = index.get("ro-crate-metadata.json", {})
    refs = node.get("conformsTo")
    refs = [refs] if isinstance(refs, dict) else (refs or [])
    return [r.get("@id") for r in refs if isinstance(r, dict)]


def _constructs(root: Path) -> dict:
    path = root / "constructs.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    rows = data.get("constructs", data if isinstance(data, list) else [])
    return {r["identifier"]: r for r in rows if isinstance(r, dict) and "identifier" in r}


def _plate(root: Path) -> list[dict]:
    path = root / "plate-layout.csv"
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
