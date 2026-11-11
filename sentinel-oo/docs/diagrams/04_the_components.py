#!/usr/bin/env python3
"""Class diagram of the sentinel-oo software architecture.

Usage:  /usr/local/bin/python3 sentinel_oo_classes.py ../11_sentinel_oo_classes.png
"""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

out = sys.argv[1]

DESIGN = "#2b6cb0"
DESIGN_FILL = "#e3eefa"
TEAL = "#2c7a7b"
TEAL_FILL = "#e2f3f3"
GREEN = "#2f855a"
GREEN_FILL = "#e4f1ea"
AMBER = "#b7791f"
AMBER_FILL = "#fbf0dc"
RED = "#9b2c2c"
RED_FILL = "#fae6e6"
PURPLE = "#5b2a86"
PURPLE_FILL = "#f1e9fb"
GREY = "#718096"
GREY_FILL = "#f2f4f7"
INK = "#1a202c"

fig, ax = plt.subplots(figsize=(16, 9))
fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
ax.set_xlim(0, 160)
ax.set_ylim(0, 90)
ax.axis("off")

M = 7.0


def box(x, y, w, h, title, sub=None, items=None, edge=GREY, fill=GREY_FILL,
        dashed=False, title_size=14, sub_size=10, item_size=9.5,
        title_colour=None, top_pad=2.9, sub_gap=3.0, line_gap=2.5,
        item_gap=3.2, item_step=2.35):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.35,rounding_size=0.9",
        linewidth=2.0, edgecolor=edge, facecolor=fill,
        linestyle="--" if dashed else "-", zorder=2))
    cx = x + w / 2.0
    ty = y + h - top_pad
    ax.text(cx, ty, title, ha="center", va="center", fontsize=title_size,
            color=title_colour or edge, fontweight="bold",
            style="italic" if dashed else "normal", zorder=3)
    if sub:
        ty -= sub_gap
        for ln in sub.split("\n"):
            ax.text(cx, ty, ln, ha="center", va="center", fontsize=sub_size,
                    color=INK, zorder=3)
            ty -= line_gap
        ty += line_gap
    if items:
        ty -= item_gap
        for it in items:
            ax.text(cx, ty, it, ha="center", va="center", fontsize=item_size,
                    color=GREY, zorder=3)
            ty -= item_step


def arrow(x1, y1, x2, y2, colour=GREY, lw=1.7):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=12, linewidth=lw,
                                 color=colour, zorder=4,
                                 shrinkA=0, shrinkB=0))


# ----------------------------------------------------------------- title
ax.text(80, 87.4, "sentinel-oo: the classes", ha="center", va="center",
        fontsize=28, color=INK, fontweight="bold")
ax.text(80, 84.2,
        "a crate arrives, a crate leaves.   one component decides, and it is "
        "neither the orchestrator nor the model.",
        ha="center", va="center", fontsize=13, color=GREY)

# ------------------------------------------------- two ways in: api and mcp
GAP = 5.0
WIN = (160 - 2 * M - GAP) / 2.0

box(M, 71.4, WIN, 8.4, "api      for pipelines and people",
    sub="POST /check/{contract}      GET /graph/{run}\n"
        "GET /contracts      GET /contracts/{name}      GET /health",
    edge=DESIGN, fill=DESIGN_FILL, title_size=12.5, sub_size=9.8,
    top_pad=2.4, sub_gap=2.5, line_gap=2.3)

box(M + WIN + GAP, 71.4, WIN, 8.4, "mcp      for the coordinator agent",
    sub="check_handover      list_handovers\n"
        "read_contract      get_run_graph",
    edge=DESIGN, fill=DESIGN_FILL, title_size=12.5, sub_size=9.8,
    top_pad=2.4, sub_gap=2.5, line_gap=2.3)

arrow(M + WIN / 2.0, 71.2, M + WIN / 2.0, 70.2, colour=DESIGN)
arrow(M + WIN + GAP + WIN / 2.0, 71.2,
      M + WIN + GAP + WIN / 2.0, 70.2, colour=DESIGN)

ax.text(80, 81.4, "two thin adapters, one orchestrator.  neither holds a rule.",
        ha="center", va="center", fontsize=10.5, color=GREY, style="italic")

# ----------------------------------------------------------------- sentinel
SEN_Y, SEN_H = 61.4, 8.6
box(M, SEN_Y, 160 - 2 * M, SEN_H, "Sentinel",
    sub="sequences the collaborators it was handed.  holds no rule of its own.",
    edge=DESIGN, fill=DESIGN_FILL, title_size=18, sub_size=11.5,
    top_pad=3.0, sub_gap=3.6)
ax.text(160 - M - 3.0, 62.9,
        "no subclass.  a handover is a Contract, never a class.",
        ha="right", va="center", fontsize=10, color=DESIGN, style="italic")

ax.text(M, 59.6, "Replaceable.  handed in when the service starts.",
        ha="left", va="center", fontsize=12.5, color=INK, fontweight="bold")
ax.text(160 - M, 59.6, "dashed border means abstract",
        ha="right", va="center", fontsize=10.5, color=GREY, style="italic")

# ------------------------------------------------------- abstract row
AB_Y, AB_H = 39.6, 17.3
W4 = (160 - 2 * M - 5.0) / 2.0
X4 = [M + i * (W4 + 5.0) for i in range(2)]

specs = [
    ("RuleEngine", "the only thing\nthat decides",
     ["ContractChecks"], RED, RED_FILL),
    ("Engine", "the model.\nadvises, never decides",
     ["NullEngine (the default)", "ScriptedEngine",
      "CommandEngine"], AMBER, AMBER_FILL),
]
for (title, sub, items, edge, fill), x in zip(specs, X4):
    arrow(x + W4 / 2.0, 58.4, x + W4 / 2.0, AB_Y + AB_H + 0.5, colour=edge)
    box(x, AB_Y, W4, AB_H, title, sub=sub, items=items, edge=edge, fill=fill,
        dashed=True, title_size=15, sub_size=10, item_size=9.2,
        top_pad=3.0, sub_gap=3.2, line_gap=2.4, item_gap=2.8, item_step=2.2)

ax.text(M, 36.0, "Fixed.  one of each.",
        ha="left", va="center", fontsize=12.5, color=INK, fontweight="bold")

# ---------------------------------------------------------- concrete row
CO_Y, CO_H = 24.0, 9.8
W5 = (160 - 2 * M - 4 * 4.0) / 5.0
X5 = [M + i * (W5 + 4.0) for i in range(5)]

concrete = [
    ("ContractRegistry", "holds contracts.\nexecutes nothing"),
    ("Repairer", "changes only what\nthe rules pointed at"),
    ("ProvenanceWriter", "writes the record.\nalters nothing else"),
    ("RunStore", "the last N runs.\noldest dropped"),
    ("BuildIdentity", "which image, commit\nand contracts ran"),
]
for (title, sub), x in zip(concrete, X5):
    box(x, CO_Y, W5, CO_H, title, sub=sub, edge=GREEN, fill=GREEN_FILL,
        title_size=12.5, sub_size=9.5, top_pad=2.8, sub_gap=3.0, line_gap=2.5)

# ------------------------------------------------------------- data row
ax.text(M, 21.4, "Data that moves between them.",
        ha="left", va="center", fontsize=12.5, color=INK, fontweight="bold")
ax.text(160 - M, 21.4,
        "value objects:  Requirement   Violation   Change   Verdict",
        ha="right", va="center", fontsize=10, color=GREY, style="italic")

DA_Y, DA_H = 10.2, 9.4
data = [
    ("Crate", "immutable. a change\nreturns a new one"),
    ("Contract", "one handover's rules.\na file, not code"),
    ("Report", "what the rules found,\nand the verdict"),
    ("Blessing", "the record written\ninto the crate"),
    ("Run", "one execution,\nstart to finish"),
]
for (title, sub), x in zip(data, X5):
    box(x, DA_Y, W5, DA_H, title, sub=sub, edge=PURPLE, fill=PURPLE_FILL,
        title_size=12.5, sub_size=9.5, top_pad=2.8, sub_gap=3.0, line_gap=2.5)

# ------------------------------------------------ what tailors an instance
box(M, 1.6, 160 - 2 * M, 6.8, "Outside the service, and what makes an instance yours",
    sub="contract files, mounted at /contracts          "
        "deploy.py   validates them, builds the image, starts it, "
        "then checks it serves what was validated",
    edge=GREEN, fill="#ffffff", dashed=True, title_size=12, sub_size=10.5,
    title_colour=GREEN, top_pad=2.6, sub_gap=3.0)

fig.savefig(out, dpi=150, facecolor="white")

# The layout above is tuned for a 16 inch slide: the font sizes are in
# points and do not move when the canvas does, so redrawing it smaller made
# every label overflow its box. Instead the drawing is kept exactly as it is
# and only the physical size recorded in the file is changed, so a page
# scales it by about 0.86 rather than by 0.4 and the labels stay legible.
try:
    from PIL import Image
    FOR_A_PAGE_INCHES = 7.6
    im = Image.open(out)
    im.save(out, dpi=(im.size[0] / FOR_A_PAGE_INCHES,
                      im.size[1] / (FOR_A_PAGE_INCHES * 9 / 16)))
except ImportError:
    print("  Pillow not installed: the figure stays at slide size")
print("wrote", out)
