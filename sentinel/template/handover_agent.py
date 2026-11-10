"""TEMPLATE — a checking agent for one handover. Copy this file and change four things.

    cp template/handover_agent.py framework/agents/sentinel_t2l.py

Or let the scaffolder do it and write the matching contract too:

    python3 scripts/new_handover.py test_to_learn --number 3 \
        --label "screening results" --from test --to learn

Everything a handover agent does in common already lives in
`framework.agents.sentinel_base.SentinelAgent`:

    translate   reshape what the upstream phase emitted into the contract's shape
    validate    ask the validator — never itself — whether that worked
    repair      fix what was flagged, within a budget, inventing nothing
    escalate    hand the rest to a human, and stop the route

You do not reimplement that. It is the same four steps, in the same order, for
every handover, and keeping it that way is what lets two pairs build different
agents in parallel and plug them together on Friday.

So an agent is a declaration. Below is the whole of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from framework.agents.base import Task                    # noqa: E402
from framework.agents.sentinel_base import SentinelAgent    # noqa: E402


# --------------------------------------------------------------------------- #
# 1. Which errors must NEVER be patched automatically
# --------------------------------------------------------------------------- #
# The test is not "is it hard to fix" but "would fixing it invent something a
# human did not record". A guessed well, a guessed derivation step, a renamed
# duplicate — each of those writes a lab record nobody observed, which is worse
# than a failed handover. Say so here, by error code.
#
# You can also say it in the contract: any check whose `fix_hint` begins with
# "not auto-fixable" is blocking without appearing in this set. Prefer that one
# when the reason is worth reading — the decision then lives in the contract,
# in prose a reviewer sees, rather than in a Python set only you know about.

NEVER_AUTOFIX: set[str] = {
    # "double_booked_location",
    # "broken_provenance_chain",
}


class HandoverAgent(SentinelAgent):
    # ----------------------------------------------------------------------- #
    # 2. What this agent is called. It goes in the ledger, on every step.
    # ----------------------------------------------------------------------- #
    name = "sentinel_XXX"

    # ----------------------------------------------------------------------- #
    # 3. Which contract it enforces — the file stem in framework/contracts/
    # ----------------------------------------------------------------------- #
    contract_name = "XXX_to_YYY"

    never_autofix = NEVER_AUTOFIX

    # ----------------------------------------------------------------------- #
    # 4. OPTIONAL — only if the upstream phase does not already emit a package
    #    in the contract's shape.
    # ----------------------------------------------------------------------- #
    # Delete this method entirely when it does. `sentinel_b2t.py` has no body at
    # all and that is the normal case; `sentinel_d2b.py` overrides it because the
    # Design handover has to project an order out of a crate and keep the two
    # joined, which is real work.
    #
    # Return (package, notes). The notes end up in the ledger, so write them for
    # whoever reads the run next week, not for yourself today.

    def translate(self, task: Task) -> tuple[dict, list[str]]:
        raw = task.inputs["package"]
        trace: list[str] = []

        package = {
            # The envelope every handover shares. Keep these names identical
            # across contracts: the coordinator, the ledger and the eventual
            # cross-use-case comparison all read them.
            "contract": self.contract_name,
            "contract_version": "0.1.0",
            "profile": self.profile,
            "run_id": task.inputs.get("run_id", "adhoc"),
            "produced_by": {"agent": self.name, "tool": "TODO",
                            "engine": self.engine.name},
            "produced_at": _now(),

            # The link back to the previous package. Mandatory, always: a result
            # that cannot be traced to what produced it is not a result.
            "TODO_ref": {},

            # The payload. Whatever this handover actually carries.
            "TODO_items": [],
        }
        trace.append(f"translated {len(raw)} field(s) into {self.contract_name}")
        return package, trace


def _now() -> str:
    from framework.ledger import now
    return now()


# --------------------------------------------------------------------------- #
# Using it
# --------------------------------------------------------------------------- #
# The coordinator runs it, records it, and stops the route if it escalates:
#
#     coord.step(HandoverAgent(profile="bioprospecting"),
#                Task(goal="hand over", inputs={"package": upstream},
#                     max_repairs=2),
#                label="handover xxx", store_as="xxx")
#
# Swapping the decision layer is one argument and touches no agent:
#
#     HandoverAgent(profile="bioprospecting", engine=MyModelEngine())
#
# Every ledger entry records `engine`, so comparing a large model against a
# small open one is a query over runs/*/ledger.jsonl, not a separate experiment.
