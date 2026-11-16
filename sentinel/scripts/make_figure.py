#!/usr/bin/env python3
"""The ring on screen, exported as a figure a person can edit.

    python3 scripts/make_figure.py                       # paper palette, SVG + PNG
    python3 scripts/make_figure.py --palette matrix      # the dark one
    python3 scripts/make_figure.py --marks none          # no glyphs at all
    python3 scripts/make_figure.py --run wf-bioprospecting --out figures/fig1

WHY NOT JUST SCREENSHOT IT
The interface draws the cycle from the crate: four phases, a sentinel at each
boundary, the verdicts that came back, and the steps of the plan the run
followed. That is the figure the paper wants, and it is already correct,
because it is generated from a run rather than drawn by hand - a figure drawn
by hand goes stale the first time the architecture changes and nobody notices.

But the page version is not a file anyone can edit:

  * colours are CSS variables (`var(--fg)`), which resolve against the page.
    Opened anywhere else - Canva, Illustrator, Inkscape, a LaTeX run - every
    stroke is black or missing.
  * every node is a link into a local web server, which is meaningless in a
    figure and in the way of selecting the shape under it.
  * there is no background: a transparent PNG on a white slide looks right
    and on a dark one disappears.

So this resolves the palette to hex, unwraps the links, paints the background
and writes a standalone SVG - text stays text, so a person can retype a label
in Canva - plus a PNG at print resolution for anywhere that will not take SVG.

NOTHING ABOUT THE DRAWING IS REDEFINED HERE. It calls the same `ring.draw()`
the interface calls, so the figure cannot drift from what the software shows.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from architect import theme                                        # noqa: E402
from architect.web import kgview, ring                             # noqa: E402

# The glyphs the interface uses for a verdict. In the figure they are optional:
# a reader of a paper has the caption, and a tick inside a 22px circle is the
# first thing to break when somebody retypes the labels in another tool.
GLYPHS = "✓▲✕✸"


def standalone(svg: str, palette: str, marks: str) -> str:
    """One page-bound drawing, turned into a file that stands on its own."""
    colours = dict(theme.palette(palette))

    def resolve(match: re.Match) -> str:
        return colours.get(match.group(1), "#000000")

    svg = re.sub(r"var\(--([a-z_]+)\)", resolve, svg)
    # The links: unwrapped, not deleted - what they wrap is the drawing.
    svg = re.sub(r"<a [^>]*>", "", svg).replace("</a>", "")
    svg = re.sub(r"<title>.*?</title>", "", svg)
    svg = svg.replace(' class="ring"', "")

    if marks == "none":
        svg = re.sub(rf"<text([^>]*)>([{GLYPHS}])</text>", "", svg)

    # A background rectangle, first, so the PNG is not transparent. Taken from
    # the palette rather than assumed white: the matrix palette's page is
    # black, and a white figure on it would be the one thing worse than none.
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    width, height = (box.group(1), box.group(2)) if box else ("640", "640")
    svg = svg.replace(
        ">", f' width="{width}" height="{height}">'
             f'<rect x="0" y="0" width="{width}" height="{height}" '
             f'fill="{colours["bg"]}"/>', 1)
    if "xmlns=" not in svg:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return svg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the interface's cycle diagram as a figure.")
    parser.add_argument("--run", default="wf-bioprospecting",
                        help="which run to draw; it supplies the plan, the "
                             "step counts and the four verdicts")
    parser.add_argument("--palette", default="paper",
                        choices=sorted(theme.PALETTES),
                        help="paper for a manuscript, matrix for a dark slide")
    parser.add_argument("--marks", default="glyphs", choices=("glyphs", "none"),
                        help="keep the verdict ticks and crosses, or drop them")
    parser.add_argument("--width", type=int, default=980,
                        help="drawing width; the PNG is rendered at 3x this")
    parser.add_argument("--out", default=None,
                        help="path without extension "
                             "(default figures/cycle_<palette>)")
    args = parser.parse_args()

    try:
        crate = kgview.load(args.run)
    except FileNotFoundError:
        runs = ", ".join(name for name, _ in kgview.runs_on_disk()[:8]) or "none"
        print(f"\n  no run called {args.run!r}. On disk: {runs}\n")
        return 2

    state = ring.read(crate, None)
    svg = standalone(ring.draw(state, width=args.width), args.palette,
                     args.marks)

    stem = Path(args.out) if args.out else ROOT / "figures" / f"cycle_{args.palette}"
    stem = stem if stem.is_absolute() else ROOT / stem
    stem.parent.mkdir(parents=True, exist_ok=True)
    svg_path = stem.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")

    checks = state["checks"]
    print(f"\n  drawn from run {args.run!r}: {state['entities']} entities, "
          f"{len(checks)} verdict(s) "
          f"({', '.join(sorted({c['verdict'] for c in checks.values()}))})")
    print(f"  {svg_path}  ({svg_path.stat().st_size // 1024} kB, "
          f"palette {args.palette}, marks {args.marks})")

    # The PNG is for anywhere that will not take an SVG. It is a second-class
    # copy on purpose: the SVG is the one to edit, because its text is still
    # text and a label can be retyped rather than re-drawn.
    render = shutil.which("rsvg-convert")
    if render:
        png_path = stem.with_suffix(".png")
        subprocess.run([render, "-w", str(args.width * 3), "-o", str(png_path),
                        str(svg_path)], check=True)
        print(f"  {png_path}  ({png_path.stat().st_size // 1024} kB, "
              f"{args.width * 3}px wide)")
    else:
        print("  no PNG: rsvg-convert is not on this machine "
              "(`brew install librsvg`). The SVG is the one that matters.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
