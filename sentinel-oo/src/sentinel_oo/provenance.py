"""Writing the record into the crate.

One action entity of the same kind the crate already uses for every other step,
so a reader needs no new vocabulary to understand it.

This writer alters exactly one thing that was already in the crate: it appends
the new action to the root entity's `mentions`. That is deliberate, and it is
the only exception. Without it the action sits in the crate unreachable from
the root, which was one of the six faults found in the published example crate
on 10 November 2026, and no validator catches it.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from .blessing import Blessing, Verdict
from .crate import Crate

SERVICE_ID = "#sentinel-oo"
SERVICE_NAME = "sentinel-oo"

# Where the software lives. RO-Crate 1.3 requires a SoftwareApplication to
# carry a `url`, which a validator enforces.
#
# Where this product lives. Overridable with SENTINEL_URL, for a fork or a
# mirror, because a wrong address is worse than an awkward one.
SERVICE_URL = os.environ.get(
    "SENTINEL_URL",
    "https://github.com/dbtl-synbio/dbtlhub",
)

COMPLETED = "http://schema.org/CompletedActionStatus"
FAILED = "http://schema.org/FailedActionStatus"


def now() -> str:
    """The current time, to the second, in the form RO-Crate expects."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class ProvenanceWriter:
    """Writes the record. Never alters what it describes, with one exception.

    The exception is the root entity's `mentions`, which gains a reference to
    the action. Everything else in the crate comes out byte for byte as it went
    in.
    """

    def __init__(self, service_version: str, service_url: str = SERVICE_URL,
                 ran_by: str | None = None):
        self.service_version = service_version
        self.service_url = service_url
        # Who asked for the check, if anybody said. Process Run Crate asks
        # every action to name the person or organisation responsible, and
        # this service is not told unless a deployment tells it, so until
        # 11 November 2026 it wrote nothing rather than inventing a name.
        #
        # **It is a claim, not a fact.** Nothing here authenticates anybody,
        # and the record says so in the entity itself, so that a reader a
        # year later does not read it as proof that a particular person ran
        # a particular check.
        self.ran_by = (ran_by or os.environ.get("SENTINEL_RUN_BY") or "").strip()

    def write(self, crate: Crate, blessing: Blessing,
              ran_by: str | None = None) -> Crate:
        """`ran_by` names who asked for this one check, overriding whatever
        the instance was started with. An agent driving the service says who
        it is per request; a deployment that runs on one team's behalf says
        it once, when it starts."""
        who = (ran_by or "").strip() or self.ran_by
        action_id = f"{SERVICE_ID}/run/{blessing.run_id}"
        added: list[dict] = []

        # The instrument. Process Run Crate requires every action to name the
        # tool that performed it. RO-Crate 1.3 wants `version` as well as
        # `softwareVersion`, which is a real validator finding and not a guess.
        added.append(
            {
                "@id": SERVICE_ID,
                "@type": "SoftwareApplication",
                "name": SERVICE_NAME,
                "description": (
                    "Checks that one phase of a Design, Build, Test, Learn "
                    "cycle can accept what the previous phase produced."
                ),
                "url": self.service_url,
                "softwareVersion": self.service_version,
                "version": self.service_version,
            }
        )

        # What was checked, as named values hanging off the action.
        objects = [{"@id": crate.root["@id"]}]
        for name, value in blessing.facts():
            fact_id = f"{action_id}/about/{_slug(name)}"
            added.append(
                {
                    "@id": fact_id,
                    "@type": "PropertyValue",
                    "name": name,
                    "value": str(value),
                }
            )
            objects.append({"@id": fact_id})

        # What was found. A verdict is a result of the check, not an input to
        # it, so it belongs here and not above. Putting a result in `object`
        # was another of the six faults found on 10 November 2026.
        verdict_id = f"{action_id}/found/verdict"
        added.append(
            {
                "@id": verdict_id,
                "@type": "PropertyValue",
                "name": "verdict",
                "value": blessing.verdict_text(),
            }
        )

        # What the rules found. Each violation is its own entity so a reader
        # can cite one, and each carries the sentence a person reads rather
        # than only a rule name.
        results = [{"@id": verdict_id}]
        for position, violation in enumerate(blessing.violations, start=1):
            found_id = f"{action_id}/found/{position:02d}-{_slug(violation.requirement.name)}"
            finding = {
                "@id": found_id,
                "@type": "PropertyValue",
                "name": f"{violation.severity.value}: {violation.requirement.name}",
                "value": violation.message,
                "description": f"at {violation.node}",
            }
            # Where it failed, in a form something other than a person can
            # follow. The description above is prose and Process Run Crate says
            # no structure may be assumed of it, so a location that lives only
            # there cannot be relied on. Only written when the entity is really
            # in the crate, because a record must not add a dangling reference
            # while complaining about the crate.
            if crate.get(violation.node) is not None:
                finding["about"] = {"@id": violation.node}
            added.append(finding)
            results.append({"@id": found_id})

        # What was changed, and by whom. A value somebody wrote down and a
        # value something read out of prose are not equally trustworthy, so
        # the crate says which this was.
        for position, change in enumerate(blessing.changes, start=1):
            change_id = f"{action_id}/changed/{position:02d}-{_slug(change.reads)}"
            added.append({
                "@id": change_id,
                "@type": "PropertyValue",
                "name": f"recovered: {change.reads}",
                "value": change.after,
                "description": change.describe(),
            })
            results.append({"@id": change_id})

        action = {
            "@id": action_id,
            "@type": "CreateAction",
            "name": f"{SERVICE_NAME} handover check",
            "description": (
                f"{SERVICE_NAME} read this crate and recorded what it found. "
                f"Verdict: {blessing.verdict_text()}. "
                f"{len(blessing.violations)} finding(s), "
                f"{len(blessing.changes)} change(s)."
            ),
            "instrument": {"@id": SERVICE_ID},
            "object": objects,
            "result": results,
            "startTime": blessing.started,
            "endTime": blessing.ended,
            # A refused handover is a failed action, and still returns a
            # crate. A refusal that exists only as an error message somewhere
            # is not a record.
            "actionStatus": {
                "@id": FAILED if blessing.verdict is Verdict.REFUSED else COMPLETED
            },
        }
        if who:
            agent_id = f"{SERVICE_ID}/ran-by/{_slug(who) or 'caller'}"
            added.append({
                "@id": agent_id,
                "@type": "Thing",
                "name": who,
                "description": (
                    "Who asked for this check, as supplied by whoever asked. "
                    "This service authenticates nobody, so this is the "
                    "caller's claim about itself and not a verified identity."
                ),
            })
            action["agent"] = {"@id": agent_id}

        added.append(action)

        # The one alteration: make the action reachable from the root.
        root = dict(crate.root)
        mentions = root.get("mentions", [])
        if isinstance(mentions, (dict, str)):
            mentions = [mentions]
        mentions = [dict(m) if not isinstance(m, str) else {"@id": m}
                    for m in mentions]
        if not any(m.get("@id") == action_id for m in mentions):
            mentions.append({"@id": action_id})
        root["mentions"] = mentions
        added.append(root)

        return crate.with_entities(added)
