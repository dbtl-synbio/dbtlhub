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

# TWO PALETTES, ONE SET OF NAMES.
# Green on black, and nothing competing with it. The two off-greens are state,
# not decoration: amber for something flagged, red for something refused. They
# must not be used anywhere else, or a reader stops trusting them.
#
# And a light one, because a screen in a bright room is not the same screen,
# and because a figure or a screenshot bound for a paper cannot be black. The
# KEYS are identical in both and every one of them is used by name, so nothing
# downstream knows which is in force - swapping them is one lookup and not a
# second stylesheet that drifts.
PALETTES = {
    "matrix": {
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
    },
    "paper": {
        # Darker than the dark one's foregrounds, because contrast on white
        # runs the other way: these are inks, not glows. Checked against
        # WCAG AA on #ffffff - the dimmest, #5a6b66, is 4.6:1.
        "bg": "#ffffff",
        "bg_panel": "#f7f9f8",
        "grid": "#d8e0db",
        "fg": "#0e5c6b",
        "fg_dim": "#5a6b66",
        "fg_bright": "#0b3d46",
        "flag": "#b9761a",
        "refuse": "#a62b2b",
        "human": "#3a56a8",
    },
}

DEFAULT_THEME = "matrix"

# Kept as a name because everything that was written before there were two
# reaches for it. It is the dark one, which is still the default.
PALETTE = PALETTES[DEFAULT_THEME]


def palette(name: str | None = None) -> dict:
    """One palette by name, falling back to the default rather than raising.

    A theme arriving from a query string is a thing a person typed, and an
    unknown one should give them the interface in the usual colours, not an
    error page.
    """
    return PALETTES.get(name or DEFAULT_THEME, PALETTES[DEFAULT_THEME])

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

# Which palette entry a state is drawn in. The NAME, not the colour: the two
# palettes agree on what amber means and disagree on which amber, and storing
# the resolved colour here would have frozen one of them.
STATE_KEY = {
    "accepted": "fg",
    "accepted_with_flags": "flag",
    "refused": "refuse",
    "go_on": "fg",
    "go_back": "flag",
    "ask": "human",
    "stop": "refuse",
}

# The dark one resolved, for everything written before there were two.
STATE_COLOUR = {state: PALETTE[key] for state, key in STATE_KEY.items()}


def icon(kind: str) -> str:
    """The glyph for a kind of thing, or nothing if it has none.

    Nothing rather than a placeholder: a missing icon should leave a gap in a
    row of text, not a box that looks like a broken character.
    """
    return ICONS.get(kind, "")


def colour(state: str, theme: str | None = None) -> str:
    """The colour a state is drawn in, in whichever palette is in force."""
    here = palette(theme)
    return here.get(STATE_KEY.get(state, "fg"), here["fg"])


if __name__ == "__main__":
    print(f"\n  {PROJECT} — {TAGLINE}\n")
    for kind, glyph in ICONS.items():
        print(f"   {glyph}  {kind}")
    print(f"\n  {'state':<22}{'matrix':<12}{'paper'}")
    for state in STATE_KEY:
        print(f"   {state:<22}{colour(state, 'matrix'):<12}"
              f"{colour(state, 'paper')}")
    print(f"\n  {'palette key':<22}{'matrix':<12}{'paper'}")
    for key in PALETTES["matrix"]:
        print(f"   {key:<22}{PALETTES['matrix'][key]:<12}"
              f"{PALETTES['paper'][key]}")
    print("\n  Two palettes, one set of names. Icons and colours only:")
    print("  every name on screen is the real one.\n")
