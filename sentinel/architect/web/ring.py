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
HANDOVER_NUMBER = {"design_to_build": 1, "build_to_test": 2,
                   "test_to_learn": 3, "learn_to_design": 4}

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

    # How many steps each phase owns, read from the PLAN in the crate. The
    # plan is written there before the run, so this works for a run on disk
    # with no session behind it - which is the whole reason the workflow was
    # made an RO-Crate entity rather than left in a YAML file beside it.
    steps: dict[str, int] = {}
    for entity in graph:
        if any(t.endswith("HowToStep") for t in _types(entity)):
            phase = str(entity.get("dbtl:phase", ""))
            if phase in PHASES:
                steps[phase] = steps.get(phase, 0) + 1

    # A phase with no `growth` behind it - which is every run read from disk -
    # still has evidence in the crate that it ran: the sentinel at its own
    # handover recorded an act. Without this, looking at a finished run showed
    # four phases that had apparently never run, beside four verdicts proving
    # they had. The crate is the record, so the crate is what is asked.
    for phase in PHASES:
        if not ran.get(phase) and HANDOVER_AFTER[phase] in checks:
            ran[phase] = checks[HANDOVER_AFTER[phase]].get("times", 1)

    return {
        "entities": len(graph),
        "steps": steps,
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


def draw(state: dict, focus: str = "", width: int = 640,
         height: int = 600) -> str:
    """The ring, as the figure draws it, with this run's state on it.

    The arrangement is the figure's and not a new one: design at the top,
    clockwise, with a sentinel between every pair of phases, the Architect
    holding the crate in the middle, and the verdicts V1..V4 pointing inward.
    People have been reading that picture on slides for days, and an interface
    that rearranged it would make the two harder to hold together.

    WHAT THE STEPS SHOW, AND WHAT THEY CANNOT
    Each phase carries a row of small marks, one per step of the workflow it
    owns. A mark is filled when the phase that owns it has run. It is NOT a
    live position: the phase agents run a phase at a time and nothing reports
    "step 6 of 14 is happening now", so drawing a moving cursor would be
    inventing a measurement. Filled means "the phase that covers this step has
    completed", and the legend says so.
    """
    cx, cy = width / 2, height / 2 + 4
    radius = min(width, height) / 2 - 104
    ring_order = ["design", "design_to_build", "build", "build_to_test",
                  "test", "test_to_learn", "learn", "learn_to_design"]
    where = {}
    for name in ring_order:
        degrees = PHASE_AT.get(name, SENTINEL_AT.get(name))
        where[name] = _at(cx, cy, radius, degrees)

    out = [f'<svg class="ring" viewBox="0 0 {width} {height}" '
           f'xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="the design-build-test-learn cycle">',
           '<defs>'
           '<marker id="flow" viewBox="0 0 10 10" refX="9" refY="5" '
           'markerWidth="6" markerHeight="6" orient="auto">'
           '<path d="M0,0 L10,5 L0,10 z" fill="var(--fg_dim)"/></marker>'
           '<marker id="verdict" viewBox="0 0 10 10" refX="9" refY="5" '
           'markerWidth="6" markerHeight="6" orient="auto">'
           '<path d="M0,0 L10,5 L0,10 z" fill="var(--fg)"/></marker>'
           '</defs>']

    # ---- the work going round, phase to sentinel to phase -----------------
    for i, name in enumerate(ring_order):
        nxt = ring_order[(i + 1) % len(ring_order)]
        x1, y1 = where[name]
        x2, y2 = where[nxt]
        r1 = 30 if name in PHASE_AT else 22
        r2 = 30 if nxt in PHASE_AT else 22
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        out.append(
            f'<line x1="{x1 + ux * r1:.0f}" y1="{y1 + uy * r1:.0f}" '
            f'x2="{x2 - ux * (r2 + 7):.0f}" y2="{y2 - uy * (r2 + 7):.0f}" '
            f'stroke="var(--fg_dim)" stroke-width="1.6" '
            f'marker-end="url(#flow)"/>')

    # ---- the Architect talking to each phase, both ways -------------------
    for phase in PHASES:
        x, y = where[phase]
        dx, dy = x - cx, y - cy
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        out.append(
            f'<line x1="{cx + ux * 50:.0f}" y1="{cy + uy * 50:.0f}" '
            f'x2="{x - ux * 32:.0f}" y2="{y - uy * 32:.0f}" '
            f'stroke="var(--fg_dim)" stroke-width="1.1" '
            f'stroke-dasharray="4 4"/>')

    # ---- the verdicts, pointing in ----------------------------------------
    for handover, degrees in SENTINEL_AT.items():
        x, y = where[handover]
        check = state["checks"].get(handover)
        ink = VERDICT_INK.get((check or {}).get("verdict", ""), "fg_dim")
        dx, dy = cx - x, cy - y
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        out.append(
            f'<line x1="{x + ux * 24:.0f}" y1="{y + uy * 24:.0f}" '
            f'x2="{cx - ux * 52:.0f}" y2="{cy - uy * 52:.0f}" '
            f'stroke="var(--{ink})" stroke-width="1.8" '
            f'marker-end="url(#verdict)"/>')
        label = f"V{HANDOVER_NUMBER[handover]}"
        lx, ly = x + ux * 56, y + uy * 56
        out.append(f'<text x="{lx:.0f}" y="{ly:.0f}" text-anchor="middle" '
                   f'font-size="11" font-weight="bold" fill="var(--{ink})">'
                   f'{label}</text>')

    # ---- the phases, each with its steps ----------------------------------
    for phase in PHASES:
        x, y = where[phase]
        info = state["phases"][phase]
        done = info["ran"] > 0
        ink = "fg" if done else "fg_dim"
        here = focus == f"phase:{phase}"
        out.append(
            f'<a href="/?phase={phase}#overview" class="node">'
            f'<title>{phase}: ' + (f'{info["added"]} entities added'
                                   if done else 'has not run') + '</title>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="30" '
            f'fill="var({"--grid" if here else "--bg_panel"})" '
            f'stroke="var(--{ink})" stroke-width="{3 if here else 1.8}"/>'
            f'<text x="{x:.0f}" y="{y + 5:.0f}" text-anchor="middle" '
            f'font-size="12.5" fill="var({"--fg_bright" if done else "--fg_dim"})">'
            f'{esc_text(phase)}</text></a>')

        # the steps of this phase, as marks just outside the node
        steps = state.get("steps", {}).get(phase, 0)
        if steps:
            dx, dy = x - cx, y - cy
            length = math.hypot(dx, dy) or 1
            ux, uy = dx / length, dy / length
            px, py = -uy, ux                       # along the ring
            span = min(steps, 8)
            for k in range(span):
                offset = (k - (span - 1) / 2) * 11
                mx = x + ux * 44 + px * offset
                my = y + uy * 44 + py * offset
                out.append(
                    f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="3.4" '
                    f'fill="var({"--fg" if done else "--bg"})" '
                    f'stroke="var(--{ink})" stroke-width="1"/>')
            if steps > span:
                out.append(
                    f'<text x="{x + ux * 62:.0f}" y="{y + uy * 62 + 3:.0f}" '
                    f'text-anchor="middle" font-size="8" '
                    f'fill="var(--fg_dim)">{steps} steps</text>')

    # ---- the sentinels -----------------------------------------------------
    for handover, degrees in SENTINEL_AT.items():
        x, y = where[handover]
        check = state["checks"].get(handover)
        verdict = (check or {}).get("verdict", "")
        ink = VERDICT_INK.get(verdict, "fg_dim")
        here = focus == f"sentinel:{handover}"
        mark = {"accepted": "\u2713", "accepted_with_flags": "\u25b2",
                "refused": "\u2715"}.get(verdict, "\u2738")
        short = handover.replace("_to_", "\u2192")
        for word, letter in (("design", "D"), ("build", "B"),
                             ("test", "T"), ("learn", "L")):
            short = short.replace(word, letter)
        out.append(
            f'<a href="/?sentinel={handover}#overview" class="node">'
            f'<title>{handover}: ' + (verdict or 'has not run') + '</title>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="22" '
            f'fill="var({"--grid" if here else "--bg_panel"})" '
            f'stroke="var(--{ink})" stroke-width="{3 if here else 1.8}"/>'
            f'<text x="{x:.0f}" y="{y - 1:.0f}" text-anchor="middle" '
            f'font-size="13" fill="var(--{ink})">{mark}</text>'
            f'<text x="{x:.0f}" y="{y + 11:.0f}" text-anchor="middle" '
            f'font-size="9.5" fill="var(--fg_dim)">{short}</text></a>')

    # ---- the Architect, holding the crate ----------------------------------
    out.append(
        f'<a href="/?phase=architect#overview" class="node">'
        f'<title>the Architect, and the one crate</title>'
        f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="50" fill="var(--bg_panel)" '
        f'stroke="var(--fg)" stroke-width="2.6"/>'
        f'<text x="{cx:.0f}" y="{cy - 10:.0f}" text-anchor="middle" '
        f'font-size="11" fill="var(--fg_bright)">Architect</text>'
        f'<text x="{cx:.0f}" y="{cy + 8:.0f}" text-anchor="middle" '
        f'font-size="16" font-weight="bold" fill="var(--fg)">'
        f'{state["entities"]}</text>'
        f'<text x="{cx:.0f}" y="{cy + 22:.0f}" text-anchor="middle" '
        f'font-size="8" fill="var(--fg_dim)">in the RO-Crate</text></a>')

    # ---- what the marks mean ----------------------------------------------
    out.append(
        f'<text x="14" y="{height - 26}" font-size="9" fill="var(--fg_dim)">'
        f'\u25cf a step of the workflow, filled when its phase has run'
        f'</text>'
        f'<text x="14" y="{height - 13}" font-size="9" fill="var(--fg_dim)">'
        f'V1\u2013V4 the verdict each sentinel sent to the Architect'
        f'</text>')
    out.append('</svg>')
    return "".join(out)


def esc_text(text: object) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


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
