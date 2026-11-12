"""Draw the concept behind part one of the demonstration, as one picture.

Part one's notebook has thirteen numbered sections, which is the right
amount of detail for somebody running it and far too much for somebody
being shown what it is. This draws the two things it actually does: it
sets a sentinel up, and then it puts handovers through it.

The picture is deliberately plain. Boxes, arrows, a few words in each.

    python3 draw_demo_part1_concept.py

writes demo_part1_concept.png beside this script.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")                      # no window, just a file
import matplotlib.pyplot as plt            # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent / "demo_part1_concept.png"

INK = "#1f2933"
PALE = "#dce6f0"
EDGE = "#7a90a8"
GREY = "#dfe3e8"
GOLD_FILL, GOLD_EDGE = "#fdf0cd", "#c9a227"
GREEN_FILL, GREEN_EDGE = "#c6e5c6", "#5f9e62"
AMBER_FILL, AMBER_EDGE = "#f8e3b0", "#c9a227"
RED_FILL, RED_EDGE = "#f3c6c2", "#c0564f"


def box(ax, x, y, w, h, text, fill=PALE, edge=EDGE, size=15, bold=False):
    """One box, with its text in the middle. x and y are its bottom left."""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.6, facecolor=fill, edgecolor=edge, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", zorder=4,
            fontsize=size, color=INK, weight="bold" if bold else "normal",
            linespacing=1.4)


def arrow(ax, start, end, rad=0.0, colour=EDGE):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=17, linewidth=1.7,
        color=colour, connectionstyle=f"arc3,rad={rad}", zorder=2,
        shrinkA=3, shrinkB=3))


def panel(ax, x, y, w, h, title):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.2, facecolor="#fafbfc", edgecolor="#c6cdd5", zorder=1))
    ax.text(x + 0.3, y + h - 0.38, title, fontsize=15, weight="bold",
            color=INK, zorder=4)


def line(ax, start, end, colour=EDGE):
    """A plain segment with no arrowhead, for routing a path round boxes."""
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-", mutation_scale=17, linewidth=1.7,
        color=colour, zorder=2, shrinkA=0, shrinkB=0))


figure, ax = plt.subplots(figsize=(12.5, 8.8))
ax.set_xlim(0, 12.5)
ax.set_ylim(0, 8.8)
ax.axis("off")
figure.patch.set_facecolor("white")

ax.text(0.3, 8.4, "What part one of the demonstration does",
        fontsize=21, weight="bold", color=INK)

# ------------------------------------------------------- first: set it up
panel(ax, 0.3, 4.2, 11.9, 3.85, "FIRST: set a sentinel up")

# Four things go in. They are ingredients, not steps, so they are stacked
# and every one of them points at the same box.
for n, (label, fill, edge) in enumerate([
        ("a machine", PALE, EDGE),
        ("the code", PALE, EDGE),
        ("an LLM", PALE, EDGE),
        ("the contract", GOLD_FILL, GOLD_EDGE)]):
    y = 6.95 - n * 0.62
    box(ax, 0.9, y, 2.6, 0.5, label, fill=fill, edge=edge, size=14)
    arrow(ax, (3.5, y + 0.25), (6.5, 6.3), rad=-0.07 + n * 0.035)

box(ax, 6.5, 5.5, 3.0, 1.6, "a sentinel,\nrunning", fill=GREY, bold=True)

ax.text(0.9, 4.33, "the contract is the only one of these four that knows "
                   "anything about the work:\nit is what the receiving phase "
                   "requires, written in a file",
        fontsize=12.5, color=INK, va="bottom")

# ------------------------------------------------- then: use it on handovers
panel(ax, 0.3, 0.35, 11.9, 3.75, "THEN: put handovers through it")

box(ax, 0.8, 2.45, 2.1, 0.95, "Design")
box(ax, 4.0, 2.45, 2.6, 0.95, "the sentinel", fill=GREY, bold=True)
box(ax, 10.0, 2.45, 2.0, 0.95, "Build")

arrow(ax, (2.9, 2.92), (4.0, 2.92))
ax.text(3.45, 3.08, "a crate", fontsize=13, color=INK, ha="center")

# The three answers it can give.
for label, fill, edge, y in [("accepted", GREEN_FILL, GREEN_EDGE, 3.25),
                             ("flagged", AMBER_FILL, AMBER_EDGE, 2.62),
                             ("refused", RED_FILL, RED_EDGE, 1.85)]:
    box(ax, 7.2, y - 0.26, 1.7, 0.52, label, fill=fill, edge=edge, size=13)
    arrow(ax, (6.6, 2.92), (7.2, y))

# Accepted and flagged go on to Build.
arrow(ax, (8.9, 3.25), (10.0, 3.05), colour=GREEN_EDGE)
arrow(ax, (8.9, 2.62), (10.0, 2.85), colour=AMBER_EDGE)

# Refused goes back where it came from, routed underneath everything so
# that the path crosses nothing.
line(ax, (8.05, 1.59), (8.05, 1.05), colour=RED_EDGE)
line(ax, (8.05, 1.05), (1.85, 1.05), colour=RED_EDGE)
arrow(ax, (1.85, 1.05), (1.85, 2.45), colour=RED_EDGE)
ax.text(4.95, 0.78, "back to Design, with the reason written inside the crate",
        fontsize=13, color="#8a3b36", ha="center")

figure.savefig(OUT, dpi=170, bbox_inches="tight", facecolor="white")
print(f"written: {OUT}")
