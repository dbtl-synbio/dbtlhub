/* DBTL Reloaded - the two things JavaScript is for.
 *
 *   1. the run log, while a run is going
 *   2. the count of required fields that still have no answer, as you type
 *
 * Nothing else. The form is a plain POST to /save, the run is a plain POST to
 * /run and an answer is a plain POST to /answer, so with this file blocked or
 * broken the interface still works - the page just has to be reloaded to see
 * what changed, and it says so next to the run button.
 *
 * Both jobs ask the server rather than deciding anything here. What counts as
 * missing is `Filled.missing()` in architect/forms.py, and what colour a
 * verdict is drawn in is architect/theme.py; this file holds no copy of
 * either. It renders what /state and /missing hand it.
 */
(function () {
  "use strict";

  var POLL_MS = 1200;          // the run log. Slower than a person reads.
  var TYPING_MS = 400;         // settle before asking what is missing.

  var logBox = document.getElementById("log");
  var crateBox = document.getElementById("crate");
  var countEl = document.getElementById("missing-count");
  var form = document.getElementById("spec-form");
  var seen = { awaiting: null, finished: null, question: null };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  /* ---- 1. the run log -------------------------------------------------- */
  function drawLog(rows) {
    if (!logBox) { return; }
    var list = el("ul", "log");
    rows.forEach(function (row) {
      var li = el("li", row.kind);
      if (row.colour) { li.style.color = row.colour; }
      li.appendChild(el("span", "at", row.at));
      if (row.icon) {
        var glyph = el("span", "icon", row.icon);
        glyph.setAttribute("aria-hidden", "true");
        li.appendChild(glyph);
      }
      li.appendChild(el("span", "said", row.text));
      list.appendChild(li);
    });
    var atBottom = true;
    var old = logBox.querySelector("ul.log");
    if (old) {
      atBottom = old.scrollHeight - old.scrollTop - old.clientHeight < 40;
    }
    logBox.textContent = "";
    logBox.appendChild(list);
    /* Follow the run, but do not drag the page away from somebody who has
     * scrolled back to read an earlier line. */
    if (atBottom) { list.scrollTop = list.scrollHeight; }
  }

  function drawCrate(rows) {
    if (!crateBox || !rows.length) { return; }
    var table = el("table", "crate");
    table.appendChild(el("caption", null,
      "entities in the RO-Crate after each phase"));
    var head = el("tr");
    ["phase", "entities", "added"].forEach(function (name) {
      head.appendChild(el("th", null, name));
    });
    table.appendChild(head);
    rows.forEach(function (row) {
      var tr = el("tr");
      tr.appendChild(el("td", null, row.phase));
      tr.appendChild(el("td", "n", String(row.entities)));
      tr.appendChild(el("td", "n", "+" + row.added));
      table.appendChild(tr);
    });
    crateBox.textContent = "";
    crateBox.appendChild(table);
  }

  function poll() {
    fetch("/state", { credentials: "same-origin" })
      .then(function (response) { return response.json(); })
      .then(function (state) {
        drawLog(state.log || []);
        drawCrate(state.crate || []);
        if (countEl && !typing) { countEl.textContent = String(state.missing); }

        /* A question, or the end of a run, changes the page itself: the
         * question form and its options are rendered by the server so that
         * they work without this file. So reload rather than build them
         * here - one definition of that form, not two. */
        var headline = state.question ? state.question.headline : null;
        var changed = (seen.awaiting !== null &&
          (state.awaiting !== seen.awaiting ||
           state.finished !== seen.finished ||
           headline !== seen.question));
        seen = { awaiting: state.awaiting, finished: state.finished,
                 question: headline };
        if (changed) { window.location.reload(); }
      })
      .catch(function () { /* the server may be restarting; try again later */ })
      .then(function () { window.setTimeout(poll, POLL_MS); });
  }

  /* ---- 2. what is still missing, as it is typed ------------------------ */
  var typing = false;
  var timer = null;

  function askWhatIsMissing() {
    if (!form) { return; }
    var body = new URLSearchParams(new FormData(form));
    fetch("/missing", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString()
    })
      .then(function (response) { return response.json(); })
      .then(function (state) {
        typing = false;
        if (countEl) { countEl.textContent = String(state.missing); }
        var live = document.getElementById("missing-live");
        if (!live) {
          live = el("p", "hint");
          live.id = "missing-live";
          form.parentNode.insertBefore(live, form);
        }
        if (state.ready) {
          live.textContent = "Nothing required is unanswered in what you have "
            + "typed. Save it, and the run can start.";
        } else {
          live.textContent = "Not saved yet. Still unanswered: "
            + state.fields.map(function (f) { return f.label; }).join(" | ");
        }
      })
      .catch(function () { typing = false; });
  }

  if (form) {
    form.addEventListener("input", function () {
      typing = true;
      window.clearTimeout(timer);
      timer = window.setTimeout(askWhatIsMissing, TYPING_MS);
    });
    form.addEventListener("change", function () {
      typing = true;
      window.clearTimeout(timer);
      timer = window.setTimeout(askWhatIsMissing, TYPING_MS);
    });
  }

  poll();
})();
