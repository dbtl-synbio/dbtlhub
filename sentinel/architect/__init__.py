"""The Architect: the centre of the agreed picture.

Eight agents stand around it. Four do the work and may be people rather than
programs; four check what the first four produced and may refuse it. The
Architect itself does neither. It talks with the researcher, holds what was
agreed, decides what happens after each verdict, and keeps the one crate that
grows.

    architect.contract        the seams: what each part must look like
    architect.consultation    1. getting to a first design, with the researcher
    architect.specification   2. what was agreed, and what the process requires
    architect.conversation    3. what to say when a check fails
    architect.route           4. go on, go back, ask, stop
    architect.memory          5. the crate that grows, including one it adopted

Importing this package is what lets those modules refer to each other as
`architect.x` instead of falling back to a bare `x` when run as a script.
"""
from __future__ import annotations

__all__ = ["contract", "consultation", "specification", "conversation",
           "route", "memory"]
