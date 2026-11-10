"""The Test -> Learn sentinel agent (Handover 3: screening results).

Written from template/handover_agent.py, and it is the template's normal case:
Test already emits a package in the contract's shape, so there is no translate()
and no logic at all. Four lines.

If a handover agent ever needs much more than this, either the contract is
carrying work the agent should do, or the agent is carrying work the contract
should state.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.sentinel_base import SentinelAgent                 # noqa: E402

# A measurement that was never taken cannot be supplied, and renaming a sample
# to make an id unique hides the collision instead of resolving it. Both are
# also declared in the contract's fix_hints, which is where a reviewer reads
# them; this set is the belt to that pair of braces.
NEVER_AUTOFIX = {"duplicate_sample_id", "missing_quantity",
                 "unusable_reading"}


class TestToLearnAgent(SentinelAgent):
    name = "sentinel_t2l"
    contract_name = "test_to_learn"
    never_autofix = NEVER_AUTOFIX
