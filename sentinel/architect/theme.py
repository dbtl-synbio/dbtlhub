"""DBTL Reloaded: the look. Not the names.

The interface is skinned after The Matrix — green on black, monospace, an icon
per kind of thing. The names stay exactly what they are: Architect, phase
agent, sentinel, RO-Crate, verdict. Those are the words the contracts, the
code, the papers and the other two use cases already use, and changing them on
a screen would mean the person reading the screen and the person reading the
repository are talking about different things.

So this file holds a palette, a font, and an icon per kind of thing. It holds
no labels. If you ever find a display name in here, delete it.

The characters are a source for the icons and nothing more: the Architect
watching a wall of screens, the Sentinels hunting, four of the same agent, and
the cookie the Oracle hands over.
"""
from __future__ import annotations

PROJECT = "DBTL Reloaded"
TAGLINE = "Four handovers. One crate. No unchecked promises."

# Green on black, and nothing competing with it. The two off-greens are state,
# not decoration: amber for something flagged, red for something refused. They
# must not be used anywhere else, or a reader stops trusting them.
PALETTE = {
    "bg": "#000000",
    "bg_panel": "#050b06",
    "grid": "#0d2411",
    "fg": "#00ff41",           # the rain
    "fg_dim": "#1f7a33",
    "fg_bright": "#b6ffc4",
    "flag": "#ffd166",         # accepted, with something to read
    "refuse": "#ff4d4d",       # refused
    "human": "#9bb8ff",        # what the researcher typed, so it is never
                               # mistaken for the system's own voice
}

FONT_STACK = ('"SF Mono", "Cascadia Mono", "JetBrains Mono", Menlo, '
              'Consolas, "DejaVu Sans Mono", monospace')

# One glyph per kind of thing. Unicode rather than an image file, so the
# interface stays one server and no assets to lose.
ICONS = {
    "architect": "◉",      # the wall of screens
    "researcher": "⌁",     # the one who answers
    "phase_agent": "⧉",    # four of the same thing in different places
    "sentinel": "✸",       # the hunter
    "crate": "◍",          # the cookie
    "ledger": "▤",
    "graph": "⌗",
    "accepted": "✓",
    "flagged": "▲",
    "refused": "✕",
    "go_on": "→",
    "go_back": "↺",
    "ask": "?",
    "stop": "■",
}

# What colour a state is drawn in. Keyed by the real verdict and move values,
# so nothing has to be translated first.
STATE_COLOUR = {
    "accepted": PALETTE["fg"],
    "accepted_with_flags": PALETTE["flag"],
    "refused": PALETTE["refuse"],
    "go_on": PALETTE["fg"],
    "go_back": PALETTE["flag"],
    "ask": PALETTE["human"],
    "stop": PALETTE["refuse"],
}


def icon(kind: str) -> str:
    """The glyph for a kind of thing, or nothing if it has none.

    Nothing rather than a placeholder: a missing icon should leave a gap in a
    row of text, not a box that looks like a broken character.
    """
    return ICONS.get(kind, "")


def colour(state: str) -> str:
    return STATE_COLOUR.get(state, PALETTE["fg"])


if __name__ == "__main__":
    print(f"\n  {PROJECT} — {TAGLINE}\n")
    for kind, glyph in ICONS.items():
        print(f"   {glyph}  {kind}")
    print()
    for state, hex_colour in STATE_COLOUR.items():
        print(f"   {state:<22}{hex_colour}")
    print("\n  Icons and colours only. Every name on screen is the real one.\n")
