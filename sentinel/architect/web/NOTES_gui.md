# GUI notes: reshaping the Architect page

Research for `architect/web/`. Read first: `server.py` (`render_page`, `_rest_of_page`, `render_*`), `static/app.css`, `static/app.js`, `kgview.py`, `STATUS.md`.
Dated 2026-11-12. Pages I fetched are marked "read". Where I only saw a search snippet, or could not find evidence, I say so.

## The shape, in one paragraph

The research agrees on one structure: a short first screen that answers "what state is the run in and what needs me", then detail on request, with at most two levels of hiding. For this interface the first screen is a pipeline strip of Design, Build, Test, Learn and the four sentinels, each coloured by its verdict. Next to it sits a "what is missing" count and a Run button. The live log sits beside or below it in a fixed-height box. Everything else (workflow table, specification form, crate, send-back, knowledge graph) becomes a named view you reach from the strip or from a tab row. Each view is a real URL. The page has one purpose per screen, not 8 panels stacked in order of construction.

---

## 1. Overview first, then detail

**Finding.** The pattern is Shneiderman's Visual Information-Seeking Mantra: "overview first, zoom and filter, then details-on-demand" (1996, IEEE Symposium on Visual Languages, "The eyes have it"). I could not read the PDF (it came back as a binary dump). The wording is from a search result summarising Craft & Cairns. Craft & Cairns (2005), "Beyond Guidelines: What Can We Learn from the Visual Information Seeking Mantra?", is a literature review of papers citing the mantra. Its conclusion is that the mantra is widely cited but needs empirical validation, and that design patterns are a better guide than the slogan. It is a well-loved heuristic, not a tested law. https://www-users.york.ac.uk/~pc530/pubs/craft_cairns.pdf (abstract via search only; I did not read the body).
The operational form is Nielsen Norman Group's progressive disclosure (read): put what users frequently need on the initial display, and defer the rest to a secondary screen. NN/G's documented failure modes are:
- more than two disclosure levels ("typically have low usability");
- a vague label on the control that reveals more;
- staged disclosure for interdependent steps;
- too many stages;
- an initial display that is itself overloaded, because "the very fact that something appears on the initial display tells users that it's important".
https://www.nngroup.com/articles/progressive-disclosure/
Dashboards: NN/G (read) says a dashboard "is focused on a single task: communicating critical information" and its goal "is not to facilitate exploration". Operational ones need a single-screen view. https://www.nngroup.com/articles/dashboards-preattentive/
Grafana's best-practice page (read) says the same from the monitoring side: hierarchical dashboards with drill-downs, "large to small or general to specific", one question per dashboard, rows in data-flow order, "dashboards should reduce cognitive load, not add to it", and alerts should link to dashboards. https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/

**For this interface.** Today there is no overview. The first thing a returning user sees is the setup panel, then a 14-row workflow table. The answer to "where is my run?" is at the bottom, in the cycle log and the crate. The page needs a top band that answers that: run id, status (running / ended / nothing), the four phases with verdicts, the missing-count, the Run button. Grafana's "row order reflects data flow" maps directly: Design to Build to Test to Learn is the natural reading order.
Level 1 is the overview band. Level 2 is the view you open (one of: workflow, specification, cycle log, crate, send back, graph). Do not add a level 3. In particular, do not nest `<details>` inside a view that you reached by clicking.

---

## 2. Cards

**Finding.** NN/G on cards (read): a card is "a container for a few short, related pieces of information" and "a linked entry point to further details, rather than the full details themselves". They work best for heterogeneous items, in browsing and dashboards. They are "a poor choice when users need to compare between multiple options" and they "deemphasize ranking". For homogeneous items, use a list. Width is typically fixed, height may vary. NN/G gives no number of cards. https://www.nngroup.com/articles/cards-component/
Carbon (read) says the most important data should "have the highest contrast and occupy the largest area" and to limit metrics, but gives no number and says nothing on cards. https://carbondesignsystem.com/data-visualization/dashboards/
I found no rule such as "at most N cards" from a named source. Anything I would say on a count is opinion.

**For this interface.** The things on the page are heterogeneous (engine, workflow, spec, run, crate, graph), so a small set of cards as entry points fits NN/G's description. Cards are the wrong thing for:
- the 14 workflow steps (homogeneous, compared by row, so they stay a table);
- the crate growth table (a table);
- the 30 spec fields (a form).
A card face should hold: the title, one status word, and one number. Examples: "Specification: 4 missing", "Cycle: Test passed, Learn running", "Crate: 212 entities, +14 last phase", "Graph: 212 nodes". The whole card is one link to the view. A card must not contain a form control or a mini-table.

---

## 3. A 30-field form

**Finding.** Evidence is thin and mostly from e-commerce, so I am cautious.
- Baymard (read, checkout research): "the number of form fields in a checkout impacts overall usability far more than the number of steps", and they recommend hiding optional fields behind links. https://baymard.com/blog/checkout-flow-average-form-fields . Caveat: the people in that study are shoppers, not scientists writing a specification.
- NN/G on accordions (read): they shorten pages but "it is easier to scroll down the page than to decide which heading to click on" when users need most sections. On desktop, show everything. Accordions suit small screens. If you use them, allow several open at once and remember state. https://www.nngroup.com/articles/accordions-complex-content/
- NN/G progressive disclosure: staged (wizard) disclosure is for steps with little interaction and is bad "when the steps are interdependent and users must alternate between them".
- GOV.UK "Complete multiple tasks" (read): for long transactions done over several sessions, show a task list with a status per section, tasks completable in any order, and a short status vocabulary ("Completed" / "Incomplete" at first). Simplify the transaction first. The page defers to a separate research page for evidence, which I did not read. https://design-system.service.gov.uk/patterns/complete-multiple-tasks/ . GOV.UK's "question pages" (read) says one question per page, but it is aimed at citizens with one-off forms. https://design-system.service.gov.uk/patterns/question-pages/
- I found no evidence about scientific instrument or LIMS forms specifically.

**For this interface.** The spec is interdependent (answers to one field change what is missing for another; `/missing` is already fetched while typing) and a scientist fills it in knowing what they want. That argues against a wizard. The evidence-backed shape is the GOV.UK task list: split the form into sections of related fields (the grouping has to come from `FORM` itself; I did not inspect how many natural groups it has). Render each as a `<details>` whose `<summary>` carries the section name and "3 of 5 answered" or "complete". Open by default the sections that still have missing fields. Keep it one `<form>` and one Save. Do not use `name=` exclusivity on these `<details>` (it closes the others, which NN/G warns against). On desktop, an "open all" link, a `?sections=all` query, or just all open is allowed. The "What is still missing" panel is then redundant: fold it into the section summaries and the overview band.

---

## 4. Live log next to static content

**Finding.** I found no named design guidance on this specifically. What I did find:
- Browsers do scroll anchoring by default, keeping the visible content put when content above it changes size; `overflow-anchor: none` opts out (MDN, read). https://developer.mozilla.org/en-US/docs/Web/CSS/overflow-anchor . MDN's scroll-anchoring guide URL returned 404, so I have nothing sourced on what suppresses anchoring.
- Grafana (above) puts the changing panels in fixed positions in rows.
- Airflow's UI docs (search snippet only) make logs the default tab of the task view. That is a product description, not guidance.
What follows is engineering reasoning, not research: the jump happens when the log's height changes and shifts what is below it. The fix is to give the log a fixed height (or `max-height` + `overflow: auto`) so its outer box never changes size, and to put it either at the top of its view or in a sticky column.

**For this interface.** `#log` currently grows with every line, which pushes the crate and everything under it down. Give `#log` a fixed `height` (e.g. `min(24rem, 50vh)`), `overflow: auto`, and `contain: content`. At wide widths, put the cycle in a two-column grid with the log in a `position: sticky; top: <header height>` column. Check `drawLog()` in `app.js`: if it replaces the whole `<ul>`, the inner scroll position resets on every poll. I did not read that function closely enough to say which; it needs checking. The bottom-pinned log trick (`flex-direction: column-reverse`) is widely used but I have no authoritative source for it; treat it as opinion.

---

## 5. A process diagram as navigation

**Finding.** Weak evidence. Airflow's documented UI (search snippet) does what you want: graph view shows structure and the status of each task for a specific run, clicking a node shows metadata and history, and one more click goes to the log. That is a product doc, not a study; I did not find Nextflow or Argo guidance, and no HCI study on failure modes of diagrams-as-navigation. Grafana's "browsing is directed with links" and Carbon's "drill-down" (above) are the nearest support. The NN/G cards article's "high information scent" idea applies: a node should show its state, so users know whether clicking is worth it. Failure modes I can state only by inference: a diagram that shows structure but no state (nothing to decide on), nodes with no visible affordance, and detail that opens somewhere that loses the diagram.

**For this interface.** The existing 4-phase, 4-sentinel structure is the strongest candidate for the overview. Draw it as inline SVG (the project already uses SVG), each node an `<a href>` carrying its state colour AND a text label (NN/G: colour is a weak primary cue). Click goes to `?run=…&phase=build` or `#phase-build`. The detail shows the sentinel's verdict, the contract it checked, the ledger rows for that phase, and the crate delta. The 14-step workflow table should be grouped under the four phases and appear as the detail of the phase you clicked, not as its own panel in front.

---

## 6. Information density for experts

**Finding.** Honest summary: the strong claim "experts want density" is repeated mostly on blogs. I looked for NN/G support and found none for that exact claim. NN/G's complex-application framework (read) says the opposite emphasis: organise data around the expert's workflow, because otherwise "clutter and confusion ensue", and distil content "to exactly what somebody needs, exactly where they need it". https://www.nngroup.com/articles/complex-application-design-framework/
Carbon (search result, current docs) offers row heights from extra small to extra large, with 40px medium as default, and says compact is for "interfaces that require reduced component height while maintaining comfortable readability". https://carbondesignsystem.com/components/data-table/style
Tufte: I only saw secondary summaries, not the books. They give data density as entries divided by graphic area, the "shrink principle", small multiples, and sparklines as small graphics "embedded in a full context of words, numbers, images". One dissenting blog warns against building a chart merely to maximise data shown. I cite Tufte, *The Visual Display of Quantitative Information*, as the original, unread.
Carbon also says white space "sets elements apart or brings them together to distinguish a point's priority", so whitespace is a grouping tool rather than a virtue.

**For this interface.** The evidence supports "dense but organised": tighter table rows (Carbon's short/compact sizes), small inline sparklines or phase-state glyphs in the workflow and crate tables, and grouping by workflow. It does not support "put more on the first screen". The density belongs inside the views, and the overview stays sparse.

---

## 7. Without JavaScript: what CSS can do and what it cannot

All from MDN (read) unless marked.
- **`<details>/<summary>`**: baseline widely available since January 2020. `name` groups them into an exclusive accordion. `open` is server-controlled, so the server can open the sections that need attention. `::details-content` can be styled. The summary is the label, so it must be descriptive. https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details . The page does not cover find-in-page. MDN notes the `name` and `::details-content` support varies and says to check the table. Browser behaviour for find-in-page opening closed details is from my memory, not the page.
- **`:target`**: matches the element named by the URL fragment, set on load and on history back/forward. Limits MDN states: not updated by `pushState`. Limits I am adding from general knowledge, which the page does not cover: following a fragment scrolls to the element; it does not move keyboard focus; and every click adds a history entry. The fragment never reaches the server, so server-rendered state cannot depend on it.
- **Default pane trick**: `main:not(:has(.pane:target)) .default {display:block}` needs `:has`; I did not verify its support in this research.
- **Grid / flex / sticky / container queries**: no sourced limits found. The practical limits are mine: sticky stops working if an ancestor has `overflow` other than visible, and none of these can fetch new data.
- **What CSS cannot do**: update the log or the crate (that needs reload or the existing fetch poll), collapse and restore state across page loads, or remember which view you were in. Keep state in the URL.

**For this interface.** Prefer real query-string views for primary navigation (`?run=…&view=cycle`), which are server-rendered, work with JS off, and are linkable. This is what Grafana means by "directed with links". Use `:target` or `<details>` only for in-view secondary content such as the "Write your own workflow" and "Rewrite phase" disclosures that already exist. A server-rendered view change reloads the page, which for the cycle view means the running log restarts from the server's copy; that is acceptable because the server already holds state.

---

## What to do here (ordered)

1. **Add an overview band at the top** (finding 1, Grafana, NN/G dashboards): run id, status, a pipeline SVG (D-B-T-L plus four sentinels, each a link with state colour and text), missing-count, Run button. Move session/form-source text to the footer.
2. **Make the views real URLs**: `?run=…&view=setup|workflow|spec|cycle|crate|back|graph`, default `cycle` when running, `spec` when anything is missing. A tab row under the band links them. Keep `?focus=` and `?theme=` working and carry them through every link. Reason: finding 7.
3. **Show one view at a time** below the band, built from the existing `render_*` functions. Setup becomes a small "engine" chip in the band that links to the setup view (it gates running, so it stays visible until answered, as `_rest_of_page` does now).
4. **Turn the pipeline nodes into the phase navigation** (finding 5): the clicked phase shows its sentinel verdict, its workflow steps from the 14-row table, its ledger rows and its crate delta.
5. **Split the specification form into task-list sections** with per-section status in the `<summary>`, missing sections open (finding 3). Remove the separate "What is still missing" panel; show the count in the band and in the summaries.
6. **Fix the log box**: fixed height, own scroll, `contain`, and a sticky column on wide screens (finding 4). Check `drawLog` for scroll reset.
7. **Cards on the overview only**, if at all, as a row of 3-5 entry points with a title, one status word and one number (finding 2). The same links can live in the tab row; cards are optional.
8. **Densify tables** (workflow, crate): tighter rows, a state glyph per row, group the 14 steps under the four phases (finding 6).
9. **Knowledge graph**: its own view, counts and landmarks first, the drawn neighbourhood second. I did not read `kgview.py` for its sizing, so no further advice.
10. Keep both themes using the same variable names; state colours must not be the only cue.

## What the research says NOT to do

- Do not stack panels in construction order and call that an overview; there is no summary level (NN/G, Grafana).
- Do not exceed two disclosure levels (NN/G).
- Do not turn the 30-field form into a wizard when answers are interdependent (NN/G progressive disclosure).
- Do not hide most of a form behind accordions that the user needs to open all of (NN/G accordions). Opening and remembering state matters.
- Do not use exclusive (`name=`) `<details>` for form sections.
- Do not use cards for homogeneous or comparable items such as the workflow rows or the crate table (NN/G cards).
- Do not put full detail or forms on a card face.
- Do not rely on colour alone for state (NN/G dashboards).
- Do not use donut charts, radial gauges or 3D for counts (NN/G dashboards); a number and a bar do it.
- Do not give the same destination several routes (NN/G progressive disclosure).
- Do not use whitespace to fill the first screen at the cost of showing less data in the views; and do not put everything on the first screen either.

## Evidence honesty

**Well evidenced (named source read, and the claim is in the source):**
- Overview, then details; a two-level cap on disclosure (NN/G progressive disclosure).
- One purpose per dashboard, a single-screen operational view, and the chart cautions (NN/G dashboards).
- Hierarchical drill-down, data-flow order and linking (Grafana documentation; practitioner guidance, not a study).
- Cards as entry points, not as a place for full detail or comparison (NN/G cards).
- Accordions are costly when users need most of the content (NN/G accordions).
- Task list with per-section status for long forms (GOV.UK, which is a design-system pattern with its own research page I did not read).
- Field count matters more than step count (Baymard, but in checkout, not science).
- What `<details>`, `:target` and scroll anchoring do (MDN).

**Weakly evidenced or inferred:**
- Diagrams as navigation: only Airflow's own docs (snippet) and inference.
- The shrink/density guidance from Tufte: second-hand summaries only. The expert-density claim: blogs; NN/G says organise rather than add.
- Whether the Shneiderman mantra is empirically sound (Craft & Cairns say it is not validated).
- Carbon's row-height numbers (from a search snippet, differing across versions).

**My opinion, with no source found:**
- The fixed-height, sticky log column; the `column-reverse` bottom-pinning trick; the "overview stays sparse, views get dense" split; the specific card face contents; the server-query-first, `:target`-second ordering; and the claim that this spec form is interdependent enough to rule out a wizard (I did not audit the field dependencies).

**Not found:** NASA/JPL mission-control UI guidance (search returned Open MCT project pages and a spacecraft engineering standard, not UI principles); Datadog design writing (not looked up); any study of laboratory information system forms; any numeric limit on cards per screen; any HCI study of pipeline-diagram navigation.
