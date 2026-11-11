"""The Architect in a browser: one HTTP server, no dependencies.

    python3 architect/web/server.py

`server.py` is the whole interface. It renders the structured specification
form from a `Form` (`architect/forms.py`), runs the four phases through
`architect.wiring`, and puts the Architect's questions to the researcher with
the same rules the terminal uses - `architect/interface.py` is driven directly
rather than copied, so there is one place where "nothing is answered for you"
is implemented.

`static/app.css` and `static/app.js` are plain CSS and vanilla JavaScript. The
JavaScript does two things only: the live run log and the count of required
fields still unanswered. With it switched off the form still posts, the run
still starts, and a question can still be answered.

`architect/theme.py` is imported by `server.py` and by nothing else in this
package. It holds a palette, a font and one icon per kind of thing, and no
display names: every word on the page is the word the contracts and the code
already use.
"""
from __future__ import annotations

__all__ = ["server"]
