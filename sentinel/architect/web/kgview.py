#!/usr/bin/env python3
"""Looking at the knowledge graph: what is in it, and what each step added.

    python3 architect/web/kgview.py [run-id]

WHERE THE KNOWLEDGE GRAPH IS
There is no separate graph database. The RO-Crate IS the knowledge graph, and
it lives in two forms that are the same thing said twice:

    runs/<run>/crate/ro-crate-metadata.json   the crate: JSON-LD, one file,
                                              the authority, append-only
    runs/<run>/graph/*.nt                     the same thing lifted to
                                              N-Triples, for querying

The second is generated from the first on every write, so the crate is the one
to read and the triples are the one to query. Nothing is stored in a third
place, and nothing is stored only in memory.

WHY A COUNT BY TYPE AND A NEIGHBOURHOOD, AND NOT A PICTURE OF THE WHOLE THING
A finished run holds something over four hundred entities. A node-link diagram
of four hundred nodes is a grey cloud: it looks like insight and answers no
question. Two things do answer questions, and they are what this module
computes:

    the shape      how many entities of each type, and which phase added them.
                   This is what changes visibly step by step.
    a neighbourhood  one entity, everything it points at, and everything that
                   points back. This is how you actually follow provenance,
                   and it stays readable at any size.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNS = ROOT / "runs"

# Properties that are bookkeeping rather than a relation worth drawing. The
# descriptor's `about` and a crate's `conformsTo` are true and say nothing
# about the science, and leaving them in buries the edges that matter.
QUIET = {"conformsTo", "about", "@context"}


def types_of(entity: dict) -> list[str]:
    raw = entity.get("@type") or []
    return [raw] if isinstance(raw, str) else list(raw)


def kind_of(entity: dict) -> str:
    """One label per entity, for counting. The first type, or 'untyped'."""
    got = types_of(entity)
    return got[0] if got else "untyped"


def shape(crate: dict) -> list[tuple[str, int]]:
    """How many entities of each type, most common first."""
    graph = crate.get("@graph") or []
    counts = Counter(kind_of(e) for e in graph if isinstance(e, dict))
    return counts.most_common()


def edges(crate: dict) -> list[tuple[str, str, str]]:
    """Every (subject, property, object) where the object is an entity here.

    Only internal edges: a reference to something outside the crate is a
    statement about the world, not an edge in this graph, and counting it
    would make the graph look better connected than it is.
    """
    graph = [e for e in crate.get("@graph") or [] if isinstance(e, dict)]
    present = {e.get("@id") for e in graph}
    out: list[tuple[str, str, str]] = []

    def walk(subject: str, prop: str, value) -> None:
        if isinstance(value, dict):
            ref = value.get("@id")
            if len(value) == 1 and isinstance(ref, str) and ref in present:
                out.append((subject, prop, ref))
            else:
                for key, sub in value.items():
                    walk(subject, prop, sub)
        elif isinstance(value, list):
            for item in value:
                walk(subject, prop, item)

    for entity in graph:
        subject = entity.get("@id")
        if not subject:
            continue
        for prop, value in entity.items():
            if prop.startswith("@") or prop in QUIET:
                continue
            walk(subject, prop, value)
    return out


def neighbourhood(crate: dict, focus: str) -> dict:
    """One entity, what it points at, and what points back at it.

    Both directions, because provenance is usually followed backwards: you
    have a result and you want what produced it, and only the forward edge is
    written down.
    """
    graph = [e for e in crate.get("@graph") or [] if isinstance(e, dict)]
    index = {e.get("@id"): e for e in graph}
    entity = index.get(focus)
    if entity is None:
        return {"found": False, "id": focus}

    out_edges, in_edges = [], []
    for subject, prop, obj in edges(crate):
        if subject == focus:
            out_edges.append({"property": prop, "id": obj,
                              "name": str(index.get(obj, {}).get("name", "")),
                              "kind": kind_of(index.get(obj, {}))})
        elif obj == focus:
            in_edges.append({"property": prop, "id": subject,
                             "name": str(index.get(subject, {}).get("name", "")),
                             "kind": kind_of(index.get(subject, {}))})

    literals = {k: v for k, v in entity.items()
                if not k.startswith("@") and isinstance(v, (str, int, float, bool))}
    return {"found": True, "id": focus, "kind": kind_of(entity),
            "types": types_of(entity),
            "name": str(entity.get("name", "")),
            "literals": literals,
            "points_at": out_edges, "pointed_at_by": in_edges}


def draw(near: dict, width: int = 820, per_side: int = 9) -> str:
    """One neighbourhood as an SVG, drawn rather than tabulated.

    ONE HOP, AND THAT IS THE WHOLE TRICK. Four hundred nodes at once is a grey
    cloud: it looks like insight and answers nothing, and no amount of layout
    work fixes it. One entity, with everything that points AT it on the left
    and everything it points at on the right, stays readable at any size and
    answers the question a person actually has.

    THREE COLUMNS, NOT A FAN. The first version spread the neighbours around
    an arc, which looked like a graph drawing and was unreadable: nine labels
    of twenty characters each do not fit on an arc, so they sat on top of one
    another. One row per neighbour cannot collide, and the eye reads a column.

    Every node is a link back into this view, so following provenance is
    clicking. Colours are CSS variables, so the drawing follows whichever
    palette is in force rather than being drawn twice.
    """
    if not near.get("found"):
        return ""
    ins = near["pointed_at_by"][:per_side]
    outs = near["points_at"][:per_side]
    rows = max(len(ins), len(outs), 1)

    row_height = 46
    top = 52
    height = top + rows * row_height + 34
    # The columns sit well inside the frame: a label runs OUTWARD from its
    # node, and the first version put the columns 128px from the edge, which
    # is narrower than the labels it then drew - every name on the right was
    # clipped by the panel. 24 characters at this size is about 165px.
    left_x, right_x = 214, width - 214
    centre_x, centre_y = width / 2, height / 2

    def column(items: list[dict], x: float, left: bool) -> str:
        out = []
        # Centred on the middle row, so a side with two neighbours sits beside
        # the centre rather than starting at the top of a tall picture.
        first = centre_y - (len(items) - 1) * row_height / 2
        for i, edge in enumerate(items):
            y = first + i * row_height
            label = edge["name"] or edge["id"]
            label = label[:24] + "\u2026" if len(label) > 25 else label
            kind = edge["kind"].split(":")[-1][:18]

            # The line runs between the two circles, never under a label.
            x1, x2 = (x + 13, centre_x - 38) if left else (centre_x + 38, x - 13)
            out.append(
                f'<path d="M{x1:.0f},{y:.0f} C{(x1 + x2) / 2:.0f},{y:.0f} '
                f'{(x1 + x2) / 2:.0f},{centre_y:.0f} {x2:.0f},{centre_y:.0f}" '
                f'fill="none" stroke="var(--fg_dim)" stroke-width="1.1" '
                f'marker-end="url(#tip)"/>')
            anchor = "end" if left else "start"
            text_x = x - 20 if left else x + 20
            out.append(
                f'<a href="/?focus={_attr(edge["id"])}#kg-panel">'
                f'<title>{_attr(edge["id"])} \u2014 {_attr(edge["kind"])}</title>'
                f'<circle cx="{x:.0f}" cy="{y:.0f}" r="11" '
                f'fill="var(--bg_panel)" stroke="var(--fg_dim)" '
                f'stroke-width="1.6"/>'
                f'<text x="{text_x:.0f}" y="{y - 1:.0f}" text-anchor="{anchor}" '
                f'font-size="11.5" fill="var(--fg_bright)">{_attr(label)}</text>'
                f'<text x="{text_x:.0f}" y="{y + 12:.0f}" '
                f'text-anchor="{anchor}" font-size="9" fill="var(--fg_dim)">'
                f'{_attr(edge["property"][:20])} \u00b7 {_attr(kind)}</text>'
                f'</a>')
        return "".join(out)

    more = []
    for items, total, x, anchor in (
            (ins, len(near["pointed_at_by"]), 18, "start"),
            (outs, len(near["points_at"]), width - 18, "end")):
        if total > len(items):
            more.append(f'<text x="{x}" y="{height - 12}" font-size="10" '
                        f'text-anchor="{anchor}" fill="var(--fg_dim)">'
                        f'and {total - len(items)} more</text>')

    centre_label = near["name"] or near["id"]
    centre_label = (centre_label[:34] + "\u2026" if len(centre_label) > 35
                    else centre_label)

    return (
        f'<svg class="kg" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="the neighbourhood of {_attr(near["id"])}">'
        f'<defs><marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="var(--fg_dim)"/></marker></defs>'
        f'<text x="18" y="26" font-size="10.5" fill="var(--fg_dim)">'
        f'{len(near["pointed_at_by"])} point at it</text>'
        f'<text x="{width - 18}" y="26" font-size="10.5" text-anchor="end" '
        f'fill="var(--fg_dim)">it points at {len(near["points_at"])}</text>'
        f'{column(ins, left_x, True)}{column(outs, right_x, False)}'
        f'<circle cx="{centre_x:.0f}" cy="{centre_y:.0f}" r="34" '
        f'fill="var(--bg_panel)" stroke="var(--fg)" stroke-width="2.6"/>'
        f'<text x="{centre_x:.0f}" y="{centre_y + 4:.0f}" text-anchor="middle" '
        f'font-size="11.5" fill="var(--fg_bright)">'
        f'{_attr(near["kind"].split(":")[-1][:13])}</text>'
        f'<text x="{centre_x:.0f}" y="{centre_y + 54:.0f}" text-anchor="middle" '
        f'font-size="11.5" fill="var(--fg)">{_attr(centre_label)}</text>'
        f'{"".join(more)}</svg>')


def _attr(text: object) -> str:
    """Escape for an SVG attribute or text node. Its own function because an
    unescaped `&` in an identifier silently breaks the whole drawing."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def what_changed(before: dict | None, after: dict) -> dict:
    """What one step added to the graph: which ids, and of which types.

    `before` is the crate as it was. None means there was nothing before, so
    everything is new - which is true of the first step and of a crate adopted
    from somewhere else.
    """
    old = {e.get("@id") for e in (before or {}).get("@graph", [])
           if isinstance(e, dict)}
    fresh = [e for e in after.get("@graph") or []
             if isinstance(e, dict) and e.get("@id") not in old]
    return {
        "added": len(fresh),
        "total": len([e for e in after.get("@graph") or [] if isinstance(e, dict)]),
        "by_kind": Counter(kind_of(e) for e in fresh).most_common(),
        "ids": [e.get("@id") for e in fresh][:400],
    }


def landmarks(crate: dict) -> dict:
    """The few entities worth offering as a starting point.

    A person opening a graph of four hundred things needs somewhere to click.
    These are the three kinds that answer a question on their own: the plan
    the run followed, what the sentinel did, and the root.
    """
    graph = [e for e in crate.get("@graph") or [] if isinstance(e, dict)]
    index = {e.get("@id"): e for e in graph}
    descriptor = index.get("ro-crate-metadata.json", {})
    about = descriptor.get("about")
    root = about.get("@id") if isinstance(about, dict) else "./"

    plan = [e["@id"] for e in graph
            if any(t.endswith("HowTo") for t in types_of(e))]
    checks = [{"id": e["@id"], "verdict": e.get("dbtl:verdict", "?"),
               "contract": e.get("dbtl:contract", "?")}
              for e in graph
              if str(e.get("@id", "")).startswith("#check/")
              and e.get("@type") == "CreateAction"]
    actions = [e["@id"] for e in graph
               if "CreateAction" in types_of(e)
               and not str(e.get("@id", "")).startswith("#check/")]
    return {"root": root, "plan": plan, "checks": checks,
            "actions": actions[:40]}


def paths(run_id: str) -> dict:
    """Where this run's graph actually is, as strings a person can open."""
    base = RUNS / run_id
    return {
        "crate": str(base / "crate" / "ro-crate-metadata.json"),
        "graph": str(base / "graph"),
        "ledger": str(base / "architect.jsonl"),
    }


def runs_on_disk() -> list[tuple[str, int]]:
    """Every run that has a crate, newest first, with how big it is.

    So the graph can be looked at without starting a run. A person who opens
    this interface to SEE something should not have to make something first,
    and the runs from yesterday are the interesting ones anyway.
    """
    out: list[tuple[str, int, float]] = []
    if not RUNS.is_dir():
        return []
    for folder in RUNS.iterdir():
        if not folder.is_dir():
            continue
        for spot in (folder / "crate" / "ro-crate-metadata.json",
                     folder / "ro-crate-metadata.json"):
            if not spot.is_file():
                continue
            try:
                crate = json.loads(spot.read_text())
            except (OSError, ValueError):
                break
            graph = [e for e in crate.get("@graph", []) if isinstance(e, dict)]
            out.append((folder.name, len(graph), spot.stat().st_mtime))
            break
    out.sort(key=lambda row: -row[2])
    return [(name, size) for name, size, _ in out]


def load(run_id: str) -> dict:
    path = RUNS / run_id / "crate" / "ro-crate-metadata.json"
    if not path.is_file():                     # older runs wrote it flat
        path = RUNS / run_id / "ro-crate-metadata.json"
    if not path.is_file():
        raise FileNotFoundError(f"no crate for run {run_id!r} under {RUNS}")
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else "wf-bioprospecting"
    try:
        crate = load(run_id)
    except FileNotFoundError as exc:
        print(f"\n  {exc}\n  try: python3 scripts/run_workflow.py\n")
        return

    where = paths(run_id)
    print(f"\n{'=' * 78}\nWHERE THE KNOWLEDGE GRAPH IS\n{'=' * 78}\n")
    print(f"  the crate (the authority)  {where['crate']}")
    print(f"  the same, as triples       {where['graph']}")
    print(f"  the ledger                 {where['ledger']}")

    graph = [e for e in crate["@graph"] if isinstance(e, dict)]
    links = edges(crate)
    print(f"\n{'=' * 78}\nITS SHAPE\n{'=' * 78}\n")
    print(f"  {len(graph)} entities, {len(links)} internal edges\n")
    for kind, count in shape(crate)[:14]:
        print(f"    {count:>5}  {kind}")

    marks = landmarks(crate)
    print(f"\n{'=' * 78}\nWHERE TO START\n{'=' * 78}\n")
    print(f"  root        {marks['root']}")
    for plan in marks["plan"]:
        print(f"  the plan    {plan}")
    for check in marks["checks"]:
        print(f"  a check     {check['id']:<28}{check['verdict']:<20}"
              f"{check['contract']}")

    focus = marks["plan"][0] if marks["plan"] else marks["root"]
    near = neighbourhood(crate, focus)
    print(f"\n{'=' * 78}\nONE NEIGHBOURHOOD: {focus}\n{'=' * 78}\n")
    print(f"  {near['kind']}  {near['name'][:70]}")
    print(f"\n  it points at {len(near['points_at'])} thing(s):")
    for edge in near["points_at"][:8]:
        print(f"    {edge['property']:<18}{edge['id'][:44]:<46}{edge['kind']}")
    print(f"\n  {len(near['pointed_at_by'])} thing(s) point at it:")
    for edge in near["pointed_at_by"][:8]:
        print(f"    {edge['property']:<18}{edge['id'][:44]:<46}{edge['kind']}")
    print()


if __name__ == "__main__":
    main()
