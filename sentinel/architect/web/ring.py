#!/usr/bin/env python3
"""The cycle as a schema you can click: four phases, four sentinels, one crate.

    python3 architect/web/ring.py

WHY A DIAGRAM AND NOT A LIST OF PANELS
The interface grew one panel at a time down a single page, and a page you
scroll is a page where nothing is beside anything. But this system IS a shape -
a ring of four phases with a sentinel at each boundary and one crate in the
middle - and that shape is the thing a person needs in their head before any
of the detail means anything. The figure in `figures/` has been showing it to
people in slides for days. This is the same drawing, live and clickable.

WHAT IT SHOWS AT A GLANCE
    a phase       whether it has run, and what it added to the crate
    a sentinel    its verdict, in the colour the whole system uses for that
                  verdict, so refused is red here and red everywhere
    the centre    how big the crate is now

WHAT A CLICK DOES
A phase opens that phase's card. A sentinel opens what that sentinel did -
which contract, what it found, in its own words. Both are plain links to the
same page with a query string, so a view can be sent to somebody, and the
whole thing works with JavaScript off.

The geometry is the figure's geometry on purpose: Design at the top and the
cycle running clockwise, which is how every slide and every diagram in this
project draws it. A diagram that disagreed with the slides would make the two
harder to hold together, not easier.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHASES = ("design", "build", "test", "learn")
HANDOVER_AFTER = {"design": "design_to_build", "build": "build_to_test",
                  "test": "test_to_learn", "learn": "learn_to_design"}

# Degrees, clockwise from the top. The same angles the figure uses.
PHASE_AT = {"design": -90, "build": 0, "test": 90, "learn": 180}
SENTINEL_AT = {"design_to_build": -45, "build_to_test": 45,
               "test_to_learn": 135, "learn_to_design": 225}

INITIAL = {"design": "D", "build": "B", "test": "T", "learn": "L"}

# Which palette entry a verdict is drawn in. The names, not the colours, so
# the drawing follows whichever theme is in force.
VERDICT_INK = {"accepted": "fg", "accepted_with_flags": "flag",
               "refused": "refuse"}


def read(crate: dict | None, growth: list[dict] | None = None) -> dict:
    """What the ring needs to know, read off the crate and the run so far.

    Everything here comes from the crate itself rather than from the session,
    so the same drawing works for a run that finished yesterday and is being
    looked at from disk. A session that is mid-run passes `growth` as well,
    because how much each phase added is the one thing the crate does not say.
    """
    graph = [e for e in (crate or {}).get("@graph", []) if isinstance(e, dict)]
    added: dict[str, int] = {}
    ran: dict[str, int] = {}
    for row in growth or []:
        phase = row.get("phase")
        if phase in PHASES:
            added[phase] = added.get(phase, 0) + int(row.get("added", 0))
            ran[phase] = ran.get(phase, 0) + 1

    checks: dict[str, dict] = {}
    for entity in graph:
        ref = str(entity.get("@id", ""))
        if not ref.startswith("#check/") or entity.get("@type") != "CreateAction":
            continue
        handover = ref[len("#check/"):].rsplit("-", 1)[0]
        findings = entity.get("object") or []
        findings = [findings] if isinstance(findings, dict) else findings
        # The LAST check of a handover is the one the ring shows: a phase that
        # was sent back is checked more than once, and the verdict that stands
        # is the most recent. The earlier ones are not lost - they are still
        # in the crate, and the sentinel's own card lists them all.
        checks[handover] = {
            "id": ref,
            "verdict": str(entity.get("dbtl:verdict", "")),
            "contract": str(entity.get("dbtl:contract", "")),
            "profile": str(entity.get("dbtl:profile", "")),
            "at": str(entity.get("endTime", "")),
            "findings": len(findings),
            "times": checks.get(handover, {}).get("times", 0) + 1,
        }

    return {
        "entities": len(graph),
        "phases": {p: {"ran": ran.get(p, 0), "added": added.get(p, 0)}
                   for p in PHASES},
        "checks": checks,
        "plan": next((e.get("name", "") for e in graph
                      if "schema:HowTo" in _types(e)), ""),
    }


def _types(entity: dict) -> list[str]:
    raw = entity.get("@type") or []
    return [raw] if isinstance(raw, str) else list(raw)


def _at(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    rad = math.radians(degrees)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)


def draw(state: dict, focus: str = "", width: int = 560,
         height: int = 440) -> str:
    """The ring, as an SVG where every node is a link."""
    cx, cy = width / 2, height / 2 + 6
    radius = min(width, height) / 2 - 76
    out = [
        f'<svg class="ring" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="the design-build-test-learn cycle">',
        f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{radius:.0f}" fill="none" '
        f'stroke="var(--grid)" stroke-width="1"/>',
    ]

    # ---- the spokes, drawn first so the nodes sit on them ------------------
    for handover, degrees in SENTINEL_AT.items():
        x, y = _at(cx, cy, radius, degrees)
        check = state["checks"].get(handover)
        ink = VERDICT_INK.get((check or {}).get("verdict", ""), "fg_dim")
        out.append(
            f'<line x1="{cx:.0f}" y1="{cy:.0f}" x2="{x:.0f}" y2="{y:.0f}" '
            f'stroke="var(--{ink})" stroke-width="1.2" '
            f'stroke-dasharray="{"0" if check else "3 3"}"/>')

    # ---- the four phases ---------------------------------------------------
    for phase, degrees in PHASE_AT.items():
        x, y = _at(cx, cy, radius, degrees)
        info = state["phases"][phase]
        done = info["ran"] > 0
        ink = "fg" if done else "fg_dim"
        here = focus == f"phase:{phase}"
        out.append(
            f'<a href="/?phase={phase}#overview" class="node">'
            f'<title>{phase}{" — has not run" if not done else ""}</title>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="27" '
            f'fill="var({"--bg_panel" if not here else "--grid"})" '
            f'stroke="var(--{ink})" stroke-width="{2.8 if here else 1.8}"/>'
            f'<text x="{x:.0f}" y="{y + 6:.0f}" text-anchor="middle" '
            f'font-size="17" font-weight="bold" '
            f'fill="var({"--fg_bright" if done else "--fg_dim"})">'
            f'{INITIAL[phase]}</text>'
            f'<text x="{x:.0f}" y="{y + 44:.0f}" text-anchor="middle" '
            f'font-size="10.5" fill="var(--{ink})">{phase}</text>'
            + (f'<text x="{x:.0f}" y="{y + 56:.0f}" text-anchor="middle" '
               f'font-size="9" fill="var(--fg_dim)">+{info["added"]}'
               + (f' · {info["ran"]}×' if info["ran"] > 1 else '')
               + '</text>' if done else '')
            + '</a>')

    # ---- the four sentinels ------------------------------------------------
    for handover, degrees in SENTINEL_AT.items():
        x, y = _at(cx, cy, radius, degrees)
        check = state["checks"].get(handover)
        verdict = (check or {}).get("verdict", "")
        ink = VERDICT_INK.get(verdict, "fg_dim")
        here = focus == f"sentinel:{handover}"
        mark = {"accepted": "✓", "accepted_with_flags": "▲",
                "refused": "✕"}.get(verdict, "✸")
        # D→B rather than design_to_build: at this size the full name is
        # unreadable and the initials are the ones every figure uses.
        short = handover.replace("_to_", "→")
        for word, letter in (("design", "D"), ("build", "B"),
                             ("test", "T"), ("learn", "L")):
            short = short.replace(word, letter)
        out.append(
            f'<a href="/?sentinel={handover}#overview" class="node">'
            f'<title>{handover}'
            + (f" — {verdict}" if verdict else " — has not run") + '</title>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="18" '
            f'fill="var({"--grid" if here else "--bg_panel"})" '
            f'stroke="var(--{ink})" stroke-width="{2.6 if here else 1.6}"/>'
            f'<text x="{x:.0f}" y="{y + 5:.0f}" text-anchor="middle" '
            f'font-size="13" fill="var(--{ink})">{mark}</text>'
            f'<text x="{x:.0f}" y="{y + 32:.0f}" text-anchor="middle" '
            f'font-size="8.5" fill="var(--fg_dim)">'
            f'{short}</text>'
            f'</a>')

    # ---- the Architect, holding the crate ----------------------------------
    out.append(
        f'<a href="/?phase=architect#overview" class="node">'
        f'<title>the Architect, and the one crate</title>'
        f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="44" fill="var(--bg_panel)" '
        f'stroke="var(--fg)" stroke-width="2.6"/>'
        f'<text x="{cx:.0f}" y="{cy - 6:.0f}" text-anchor="middle" '
        f'font-size="11" fill="var(--fg_bright)">Architect</text>'
        f'<text x="{cx:.0f}" y="{cy + 10:.0f}" text-anchor="middle" '
        f'font-size="15" font-weight="bold" fill="var(--fg)">'
        f'{state["entities"]}</text>'
        f'<text x="{cx:.0f}" y="{cy + 24:.0f}" text-anchor="middle" '
        f'font-size="8.5" fill="var(--fg_dim)">in the crate</text></a>')

    out.append('</svg>')
    return "".join(out)


# --------------------------------------------------------------------------- #
def main() -> None:
    from architect.web import kgview                          # noqa: PLC0415

    run = sys.argv[1] if len(sys.argv) > 1 else "wf-bioprospecting"
    try:
        crate = kgview.load(run)
    except FileNotFoundError as exc:
        print(f"\n  {exc}\n  try: python3 scripts/run_workflow.py\n")
        return
    state = read(crate)

    print(f"\n{'=' * 74}\nTHE CYCLE, AS THE RING SEES IT: {run}\n{'=' * 74}\n")
    print(f"  the crate holds {state['entities']} entities")
    if state["plan"]:
        print(f"  the plan it followed: {state['plan']}")
    print()
    for phase in PHASES:
        handover = HANDOVER_AFTER[phase]
        check = state["checks"].get(handover)
        print(f"  {phase:<8}-> {handover:<17}"
              + (f"{check['verdict']:<22}{check['findings']} finding(s)"
                 if check else "no sentinel act recorded"))
    svg = draw(state)
    print(f"\n  the drawing: {len(svg)} bytes, {svg.count('<a href')} links, "
          f"{svg.count('<circle')} nodes\n")


if __name__ == "__main__":
    main()
