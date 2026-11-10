"""The Learn -> Design sentinel agent (Handover 4: predictions and recommendations).

The handover that closes the cycle, and the template's normal case: Learn
already emits a package in the contract's shape, so there is no translate() and
no logic at all. Three declarations.

What makes this handover different is not the agent, it is the contract. A
recommendation is the one thing in the cycle that is not a measurement of
something that happened - it is a claim about something that has not happened
yet. So the contract insists on the three things that make such a claim
checkable: which measurements it rests on, which model produced it, and how
uncertain it is.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.sentinel_base import SentinelAgent               # noqa: E402

# Every one of these would, if patched, invent a scientific claim rather than
# repair a formatting slip.
#
#   unsupported_recommendation  the cited measurement does not exist. Supplying
#                               one would manufacture the evidence for a claim.
#   unknown_design_item         proposes a variant of something never built.
#   duplicate_recommendation_id renaming hides a collision between what may be
#                               two genuinely different recommendations.
#   duplicate_rank              the ordering is Learn's judgement; breaking a
#                               tie by array position invents a preference.
#   missing_quantity            a prediction the model did not make cannot be
#                               supplied by the agent that checks it.
NEVER_AUTOFIX = {
    "unsupported_recommendation",
    "unknown_design_item",
    "duplicate_recommendation_id",
    "duplicate_rank",
    "missing_quantity",
}


class LearnToDesignAgent(SentinelAgent):
    name = "sentinel_l2d"
    contract_name = "learn_to_design"
    never_autofix = NEVER_AUTOFIX
