#!/usr/bin/env python3
"""Drawing helpers for the system manual's diagrams.

The diagrams were Mermaid, which is text and renders only in viewers that
know about it. The manuals are PDFs, and a PDF cannot render Mermaid at all,
so they are drawn as images instead. An image also works in every viewer,
which Mermaid does not, so this is not only a concession to the PDF.

Each diagram is a short script using the helpers here. Run make_diagrams.py
to build all of them.

    /usr/local/bin/python3 make_diagrams.py

Use that interpreter and not plain `python3`: on this machine it is the only
installation with matplotlib available.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon

# The palette the project's slides already use, so a diagram in a manual and
# a diagram on a slide look like the same system.
BLUE, BLUE_FILL = "#2b6cb0", "#e3eefa"
GREEN, GREEN_FILL = "#2f855a", "#e4f1ea"
TEAL, TEAL_FILL = "#2c7a7b", "#e2f3f3"
AMBER, AMBER_FILL = "#b7791f", "#fbf0dc"
RED, RED_FILL = "#9b2c2c", "#fae6e6"
PURPLE, PURPLE_FILL = "#5b2a86", "#f1e9fb"
GREY, GREY_FILL = "#718096", "#f2f4f7"
INK = "#1a202c"

PAIRS = {
    "blue": (BLUE, BLUE_FILL),
    "green": (GREEN, GREEN_FILL),
    "teal": (TEAL, TEAL_FILL),
    "amber": (AMBER, AMBER_FILL),
    "red": (RED, RED_FILL),
    "purple": (PURPLE, PURPLE_FILL),
    "grey": (GREY, GREY_FILL),
}


class Sheet:
    """One diagram. Coordinates are 0 to 100 across and 0 to `height` up."""

    def __init__(self, width=100.0, height=60.0, scale=0.072):
        # The scale sets how big the figure is in inches, and so how large the
        # text inside it looks once LaTeX has fitted the figure to the text
        # column. Drawn at 0.16 the figures were about 16 inches wide, LaTeX
        # shrank them to about 6.5 inches, and every label came out at a third
        # of its size and could not be read. At 0.072 a 100 unit wide figure
        # is 7.2 inches, so it is barely scaled at all.
        self.w, self.h = width, height
        self.fig, self.ax = plt.subplots(figsize=(width * scale, height * scale))
        self.fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        self.ax.set_xlim(0, width)
        self.ax.set_ylim(0, height)
        self.ax.axis("off")

    # ------------------------------------------------------------- shapes

    def box(self, x, y, w, h, text, colour="blue", size=10.5, bold=False,
            zorder=3, align="center"):
        """A rounded box with text in it. x and y are the bottom left."""
        edge, fill = PAIRS[colour]
        self.ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.25,rounding_size=1.1",
            linewidth=1.7, edgecolor=edge, facecolor=fill, zorder=zorder))
        self.ax.text(
            x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=size, color=edge,
            fontweight="bold" if bold else "normal",
            zorder=zorder + 1, linespacing=1.45,
            multialignment=align)
        return (x, y, w, h)

    def plain(self, x, y, text, size=9.5, colour=GREY, bold=False,
              ha="left", va="center", style="normal", zorder=6):
        self.ax.text(x, y, text, fontsize=size, color=colour,
                     fontweight="bold" if bold else "normal",
                     ha=ha, va=va, style=style, zorder=zorder,
                     linespacing=1.45)

    def group(self, x, y, w, h, title, colour="grey", size=10.0):
        """A labelled region holding several boxes, drawn behind them."""
        edge, fill = PAIRS[colour]
        self.ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.3,rounding_size=1.4",
            linewidth=1.6, edgecolor=edge, facecolor=fill,
            zorder=1, linestyle="-"))
        self.ax.text(x + 1.6, y + h - 2.2, title, fontsize=size, color=edge,
                     fontweight="bold", ha="left", va="center", zorder=2)

    def diamond(self, cx, cy, w, h, text, colour="amber", size=9.5):
        """A decision. Drawn as a diamond because a reader expects one."""
        edge, fill = PAIRS[colour]
        self.ax.add_patch(Polygon(
            [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
            closed=True, linewidth=1.7, edgecolor=edge, facecolor=fill, zorder=3))
        self.ax.text(cx, cy, text, ha="center", va="center", fontsize=size,
                     color=edge, zorder=4, linespacing=1.4)

    # ------------------------------------------------------------- arrows

    def arrow(self, start, end, label=None, colour=INK, dashed=False,
              size=8.6, label_offset=(0, 1.6), label_ha="center", bend=0.0):
        style = "arc3,rad=%.2f" % bend
        self.ax.annotate(
            "", xy=end, xytext=start,
            arrowprops=dict(arrowstyle="-|>", color=colour, linewidth=1.5,
                            linestyle=(0, (4, 3)) if dashed else "solid",
                            shrinkA=2, shrinkB=2, connectionstyle=style),
            zorder=5)
        if label:
            mx = (start[0] + end[0]) / 2 + label_offset[0]
            my = (start[1] + end[1]) / 2 + label_offset[1]
            self.ax.text(mx, my, label, fontsize=size, color=colour,
                         ha=label_ha, va="center", zorder=6,
                         linespacing=1.35,
                         bbox=dict(boxstyle="round,pad=0.22", facecolor="white",
                                   edgecolor="none"))

    def lifeline(self, x, top, bottom, colour=GREY):
        """The dashed vertical line under an actor in a sequence diagram."""
        self.ax.plot([x, x], [bottom, top], linestyle=(0, (3, 4)),
                     linewidth=1.1, color=colour, zorder=1)

    def message(self, x1, x2, y, text, colour=INK, dashed=False, size=8.8):
        """One horizontal arrow between two lifelines, with its text above."""
        self.ax.annotate(
            "", xy=(x2, y), xytext=(x1, y),
            arrowprops=dict(arrowstyle="-|>", color=colour, linewidth=1.4,
                            linestyle=(0, (4, 3)) if dashed else "solid",
                            shrinkA=0, shrinkB=0),
            zorder=5)
        self.ax.text((x1 + x2) / 2, y + 1.15, text, ha="center", va="bottom",
                     fontsize=size, color=colour, zorder=6, linespacing=1.3)

    def note(self, x, y, w, h, text, colour="amber", size=8.6):
        """A note beside a sequence, for something that is not a message."""
        edge, fill = PAIRS[colour]
        self.ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.5",
            linewidth=1.2, edgecolor=edge, facecolor=fill, zorder=4))
        self.ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                     fontsize=size, color=edge, zorder=5, linespacing=1.35)

    def title(self, text, sub=None):
        self.ax.text(self.w / 2, self.h - 2.4, text, ha="center", va="center",
                     fontsize=13.5, color=INK, fontweight="bold")
        if sub:
            self.ax.text(self.w / 2, self.h - 6.0, sub, ha="center",
                         va="center", fontsize=9.5, color=GREY)

    def save(self, path):
        self.fig.savefig(path, dpi=200, facecolor="white",
                         bbox_inches="tight", pad_inches=0.12)
        plt.close(self.fig)
        print(f"  {path}")
