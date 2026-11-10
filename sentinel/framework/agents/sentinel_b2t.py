"""The Build -> Test sentinel agent.

Build already emits a package in the contract's shape, so `translate` is the
default and this file is only a declaration: which contract, and which errors
must never be patched. Everything else is in sentinel_base.SentinelAgent.

That is the shape every handover should end up with. If one of them needs much
more than this, the contract is carrying work the agent should be doing, or the
other way round.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from framework.agents.sentinel_base import SentinelAgent                # noqa: E402

# A guess here would fabricate a lab record. Renaming a sample to make an id
# unique belongs in the same category: it hides the collision instead of
# resolving it.
NEVER_AUTOFIX = {"double_booked_location", "unknown_design_item", "duplicate_sample_id",
                 "unaccounted_item"}


class BuildToTestAgent(SentinelAgent):
    name = "sentinel_b2t"
    contract_name = "build_to_test"
    never_autofix = NEVER_AUTOFIX
