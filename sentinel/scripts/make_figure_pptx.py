#!/usr/bin/env python3
"""The same figure, as PowerPoint shapes a person can move and retype.

    python3 scripts/make_figure_pptx.py                  # figures/cycle_paper.pptx
    python3 scripts/make_figure_pptx.py --palette matrix
    python3 scripts/make_figure_pptx.py --marks none --out figures/fig1

WHY A SECOND EXPORT
`make_figure.py` writes an SVG, which is the right thing for a manuscript and
the wrong thing for the half hour before a deadline: PowerPoint will import it
only as a picture, and a picture cannot have one circle nudged or one label
rewritten. Canva treats it the same way unless the account allows SVG at all.

So this writes the same drawing as NATIVE SHAPES - an oval per node, a line
per arrow, a text box per label, each named - so every element is selectable,
movable and editable, and the text is text rather than outlines.

It reads the SVG that `make_figure.py` produced rather than re-deriving the
geometry, for the same reason that one draws the figure from a run: two pieces
of code computing the same layout is two layouts, and the second one is wrong
the first time somebody changes the first.

WHAT IT IS NOT. It is not a deck, and it is not a drawing tool. Curves are not
supported because the figure has none; if one is ever added here, this will
say so rather than quietly straightening it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Inches, Pt
except ImportError:                                        # pragma: no cover
    print("\n  This one script needs python-pptx:\n"
          "\n      pip install python-pptx\n"
          "\n  The SVG from make_figure.py needs nothing.\n")
    sys.exit(2)

# 13.333in over the drawing's 980 units puts one unit at almost exactly one
# point, so a font size in the SVG is the same number in PowerPoint and the
# figure does not have to be re-judged after the export.
SLIDE_WIDTH_IN = 13.333


def colour(value: str) -> RGBColor:
    return RGBColor.from_string(value.lstrip("#").upper()[:6])


def attrs(raw: str) -> dict[str, str]:
    # Digits belong in an attribute name here: `x1`, `y2`. Leaving them out
    # dropped every coordinate of every line and kept everything else, so the
    # failure was a KeyError on the first arrow rather than a wrong drawing.
    return dict(re.findall(r'([a-zA-Z][a-zA-Z0-9-]*)="([^"]*)"', raw))


def arrowhead(line, kind: str = "triangle") -> None:
    """A real arrowhead on the line's own XML. python-pptx exposes no API."""
    from pptx.oxml.ns import qn                            # noqa: PLC0415
    ln = line.line._get_or_add_ln()
    end = ln.makeelement(qn("a:tailEnd"), {"type": kind, "w": "med",
                                           "len": "med"})
    ln.append(end)


def dashed(line) -> None:
    from pptx.oxml.ns import qn                            # noqa: PLC0415
    ln = line.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:prstDash"), {"val": "dash"}))


def build(svg: str, out: Path, background: str) -> Path:
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    width, height = (float(box.group(1)), float(box.group(2))) if box \
        else (980.0, 600.0)
    scale = SLIDE_WIDTH_IN / width                         # inches per unit

    def at(value: float) -> Emu:
        return Inches(value * scale)

    deck = Presentation()
    deck.slide_width = at(width)
    deck.slide_height = at(height)
    slide = deck.slides.add_slide(deck.slide_layouts[6])   # blank

    page = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0,
                                  at(width), at(height))
    page.name = "background"
    page.fill.solid()
    page.fill.fore_color.rgb = colour(background)
    page.line.fill.background()
    page.shadow.inherit = False

    # Everything outside <defs>: the markers in there are arrowheads, which
    # become a property of a line rather than a shape of their own.
    body = re.sub(r"<defs>.*?</defs>", "", svg, flags=re.S)
    made = {"oval": 0, "line": 0, "text": 0}

    for match in re.finditer(r"<(circle|line|text)([^>]*?)/?>"
                             r"(?:([^<]*)</text>)?", body):
        tag, raw, label = match.group(1), match.group(2), match.group(3)
        a = attrs(raw)

        if tag == "circle":
            r = float(a["r"])
            shape = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, at(float(a["cx"]) - r), at(float(a["cy"]) - r),
                at(r * 2), at(r * 2))
            shape.name = f"node {made['oval'] + 1}" if r > 8 else \
                f"step dot {made['oval'] + 1}"
            shape.fill.solid()
            shape.fill.fore_color.rgb = colour(a.get("fill", "#ffffff"))
            shape.line.color.rgb = colour(a.get("stroke", "#000000"))
            shape.line.width = Pt(float(a.get("stroke-width", 1)))
            shape.shadow.inherit = False
            made["oval"] += 1

        elif tag == "line":
            shape = slide.shapes.add_connector(
                1,                                         # straight
                at(float(a["x1"])), at(float(a["y1"])),
                at(float(a["x2"])), at(float(a["y2"])))
            shape.name = f"arrow {made['line'] + 1}"
            shape.line.color.rgb = colour(a.get("stroke", "#000000"))
            shape.line.width = Pt(float(a.get("stroke-width", 1)))
            if "marker-end" in a:
                arrowhead(shape)
            if "stroke-dasharray" in a:
                dashed(shape)
            made["line"] += 1

        elif tag == "text" and (label or "").strip():
            size = float(a.get("font-size", 11))
            centred = a.get("text-anchor") == "middle"
            # The SVG y is a baseline; a PowerPoint box is anchored by its
            # middle. Without this correction every label sits a third of its
            # own height too low, which is visible on a 22-unit circle.
            middle = float(a["y"]) - size * 0.36
            wide = max(len(label) * size * 0.75, 60)
            left = float(a["x"]) - (wide / 2 if centred else 0)
            box_shape = slide.shapes.add_textbox(
                at(left), at(middle - size), at(wide), at(size * 2))
            box_shape.name = f"label: {label[:28]}"
            frame = box_shape.text_frame
            frame.word_wrap = False
            frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            frame.margin_left = frame.margin_right = 0
            frame.margin_top = frame.margin_bottom = 0
            run = frame.paragraphs[0].add_run()
            run.text = label
            frame.paragraphs[0].alignment = (PP_ALIGN.CENTER if centred
                                             else PP_ALIGN.LEFT)
            run.font.size = Pt(size)
            run.font.bold = a.get("font-weight") == "bold"
            run.font.color.rgb = colour(a.get("fill", "#000000"))
            run.font.name = "Arial"
            made["text"] += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    deck.save(str(out))
    print(f"  {out}  ({out.stat().st_size // 1024} kB)")
    print(f"  {made['oval']} ovals, {made['line']} arrows, "
          f"{made['text']} text boxes - every one of them editable")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="The cycle diagram as editable PowerPoint shapes.")
    parser.add_argument("--run", default="wf-bioprospecting")
    parser.add_argument("--palette", default="paper")
    parser.add_argument("--marks", default="glyphs", choices=("glyphs", "none"))
    parser.add_argument("--width", type=int, default=980)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    # The SVG first, from the one place that knows the layout.
    from architect import theme                             # noqa: PLC0415
    from architect.web import kgview, ring                  # noqa: PLC0415
    from make_figure import standalone                      # noqa: PLC0415

    try:
        crate = kgview.load(args.run)
    except FileNotFoundError:
        print(f"\n  no run called {args.run!r}\n")
        return 2
    svg = standalone(ring.draw(ring.read(crate, None), width=args.width),
                     args.palette, args.marks)

    stem = Path(args.out) if args.out else ROOT / "figures" / f"cycle_{args.palette}"
    stem = stem if stem.is_absolute() else ROOT / stem
    print(f"\n  from run {args.run!r}, palette {args.palette}")
    build(svg, stem.with_suffix(".pptx"),
          dict(theme.palette(args.palette))["bg"])
    print()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main())
