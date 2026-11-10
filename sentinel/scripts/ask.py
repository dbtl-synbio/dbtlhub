#!/usr/bin/env python3
"""Ask one run's graph a question, instead of walking files by hand.

    python3 scripts/ask.py <run-id>                  what the graph holds
    python3 scripts/ask.py <run-id> --behind BP1-A01 one item, back to the ground

`trace.py` follows file paths and proves the chain resolves. This reads the
graph those files wrote, which is a different thing: by the end of a run,
`runs/<id>/graph/run.nt` holds the crate's own provenance *and* the spine
joining the four handovers, in one file. So "which sediment core is behind
this?" is a traversal in one place rather than a tour of four packages.

The graph is append-only and grows as the run goes: every step that produces
a package adds to it, and the Design crate's triples join the same file. No
database, no server - N-Triples on disk, which `rdflib` or `pyoxigraph` will
load unchanged when a real query engine is wanted.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUNS = ROOT / "runs"

BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, BLUE = "\033[31m", "\033[32m", "\033[34m"

# What to follow when walking backwards. Expanded through the vocabulary the
# lifter itself uses, never by gluing strings onto a base: the first version of
# this file built "<base>restsOn" by hand while the graph held
# "<base>terms/restsOn", so the traversal silently walked two nodes and
# reported that nothing reached a sample. A prefix table exists; use it.
from framework.vocab import DEFAULT                                   # noqa: E402

BACK_CURIES = [
    "dbtl:builtFrom", "dbtl:liftsFrom", "dbtl:measures", "dbtl:restsOn",
    "prov:wasDerivedFrom", "prov:wasGeneratedBy", "prov:used",
    "schema:isBasedOn", "schema:isPartOf",
    # An action's inputs. Walking an action without these stops at the action.
    "schema:object",
]
BACK = [DEFAULT.expand(c) for c in BACK_CURIES]
# The handover spine is written with bare base IRIs by framework.kg, not
# through the dbtl: prefix. Both are real; neither is guessed here.
BASE = DEFAULT.base
LABELS = [DEFAULT.expand(c) for c in
          ("schema:name", "dbtl:identifier", "schema:description")]
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def parse(path: Path):
    """N-Triples, one line each, as written by to_ntriples. No parser needed."""
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line.endswith("."):
            continue
        line = line[:-1].strip()
        if line.startswith("_:"):
            subject, _, rest = line.partition(" ")
            rest = rest.strip()
        elif line.startswith("<"):
            subject, rest = line[1:].split(">", 1)
            rest = rest.strip()
        else:
            continue
        if not rest.startswith("<"):
            continue
        predicate, rest = rest[1:].split(">", 1)
        obj = rest.strip()
        if obj.startswith("<") and obj.endswith(">"):
            out.append((subject, predicate, obj[1:-1], True))
        elif obj.startswith("_:"):
            # A measurement is a blank node. Dropping it loses exactly the
            # shape this framework insists on: quantity, value, unit, method.
            out.append((subject, predicate, obj, True))
        else:
            out.append((subject, predicate, obj.strip('"'), False))
    return out


def index(triples):
    out, back = defaultdict(list), defaultdict(list)
    for s, p, o, is_iri in triples:
        out[s].append((p, o, is_iri))
        if is_iri:
            back[o].append((p, s))
    return out, back


def label(out, node: str) -> str:
    props = dict((p, o) for p, o, _ in out.get(node, []))
    for key in LABELS:
        if props.get(key):
            return props[key]
    return node.rsplit("/", 1)[-1].lstrip("#")


def kind(out, node: str) -> str:
    types = [o for p, o, i in out.get(node, []) if p == RDF_TYPE]
    return ", ".join(t.rsplit("/", 1)[-1].split("#")[-1] for t in types)


def find(out, needle: str) -> list[str]:
    hits = [n for n in out if n.rsplit("/", 1)[-1] == needle]
    if hits:
        return hits
    return [s for s, props in out.items()
            if any(p in LABELS and o == needle for p, o, _ in props)]


def walk_back(out, start: str, limit: int = 40) -> list[str]:
    chain, seen, queue = [], {start}, [start]
    while queue and len(chain) < limit:
        node = queue.pop(0)
        chain.append(node)
        for p, o, is_iri in out.get(node, []):
            if is_iri and p in BACK and o not in seen:
                seen.add(o)
                queue.append(o)
    return chain


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_id")
    ap.add_argument("--behind", metavar="ID",
                    help="an identifier: a sample, an ordered item, a recommendation")
    args = ap.parse_args()

    paths = [RUNS / args.run_id / "graph" / name
             for name in ("run.nt", "handovers.nt")]
    present = [p for p in paths if p.exists()]
    if not present:
        sys.exit(f"no graph for run {args.run_id!r}. Run the cycle first.")

    triples = [t for p in present for t in parse(p)]
    out, _ = index(triples)
    handovers = sorted(s for s, props in out.items()
                       if any(p == RDF_TYPE and o.endswith("Handover")
                              for p, o, _ in props))

    print(f"\n{BOLD}runs/{args.run_id}/graph/{OFF}  "
          f"{DIM}{', '.join(p.name for p in present)} - {len(triples)} triples, "
          f"{len(out)} subjects{OFF}")
    print(f"{DIM}one file: the Design crate's own provenance, plus the spine "
          f"joining the handovers{OFF}\n")

    for h in handovers:
        props = dict((p, o) for p, o, _ in out.get(h, []))
        carried = [o for p, o, i in out.get(h, []) if p == f"{BASE}carries"]
        print(f"  {GREEN}●{OFF} {props.get(f'{BASE}contract', '?'):<18}"
              f"{DIM}{len(carried)} item(s) · {props.get(f'{BASE}agent', '?')}"
              f" · engine {props.get(f'{BASE}engine', '?')}{OFF}")

    if not args.behind:
        print(f"\n{DIM}  --behind <id> to walk one item back to the ground.{OFF}\n")
        return

    hits = find(out, args.behind)
    if not hits:
        sys.exit(f"\n  {RED}nothing in this graph is called {args.behind!r}{OFF}\n")

    node = hits[0]
    print(f"\n{BOLD}What is behind {args.behind}{OFF}")
    chain = walk_back(out, node)
    for i, step in enumerate(chain):
        tag = kind(out, step)
        print(f"  {i:>2}. {label(out, step)[:62]:<64}{DIM}{tag[:28]}{OFF}")

    ground = [s for s in chain
              if "BioSample" in kind(out, s) or "Sample" in kind(out, s)]
    print()
    if ground:
        print(f"  {GREEN}{BOLD}reaches the ground{OFF}: {label(out, ground[-1])}")
        print(f"{DIM}  One traversal, one file. The vendor was sent a sequence and "
              f"a well;\n  this is everything that was kept.{OFF}\n")
    else:
        print(f"  {RED}{BOLD}does not reach a physical sample{OFF}")
        print(f"{DIM}  Walked {len(chain)} node(s) and found no sample. Either a "
              f"handover did not\n  write its spine, or the chain really is "
              f"broken.{OFF}\n")


if __name__ == "__main__":
    main()
