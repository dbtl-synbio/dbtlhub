"""The orchestrator.

Thin on purpose. It sequences collaborators it was handed and contains no rule
of its own. If a rule ever appears in this file, it has been put in the wrong
place: a rule belongs in a contract, and the decision about a rule belongs to
the rule engine.

At step 1 of the build order there is nothing to sequence except the writer.
Each later step adds one collaborator to the constructor and one line to
`check`, and this file should stay about this length.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .blessing import Blessing, ContractSource
from .contract import Contract, ContractRegistry
from .crate import Crate
from .identity import BuildIdentity
from .blessing import NO_ENGINE
from .engines import Engine, HttpEngine, NullEngine

# How many violations a model may be asked about in one check.
#
# Not zero, because a model that is never asked is a model that is not
# there. Not large, because each question is a round trip to another
# machine and a handover with many repairable violations is a handover with
# a bigger problem than a missing value.
#
# Only violations the contract marks `repairable` are ever counted against
# this, and in a contract of nineteen requirements typically one is.
DEFAULT_REPAIR_BUDGET = 3
from .provenance import ProvenanceWriter, now
from .repair import Repairer
from .rules import Report, RuleEngine, with_flags_for


@dataclass(frozen=True)
class Run:
    """One execution, start to finish."""

    id: str
    crate: Crate
    blessing: Blessing
    report: Report | None = None

    @property
    def verdict(self):
        return self.blessing.verdict


class Sentinel:
    def __init__(
        self,
        provenance: ProvenanceWriter,
        rules: RuleEngine | None = None,
        registry: ContractRegistry | None = None,
        engine: Engine | None = None,
        build: BuildIdentity | None = None,
    ):
        self.provenance = provenance
        self.rules = rules
        self.registry = registry
        # A model by default, reached over the network from its own
        # container. A sentinel at a handover without one is not what this
        # project is about, and a capability that is off by default is a
        # capability nobody uses.
        #
        # Turning it on is safe because of where the model sits in the
        # design, not because models are reliable. It is asked one question,
        # about a check that has already failed, and everything it answers
        # goes back through the rules before it counts. Measured on
        # 10 November 2026, two models that answered wrongly changed no
        # verdict and wrote nothing.
        #
        # Pass NullEngine() for no model, or set SENTINEL_MODEL_URL to
        # nothing, which is a deliberate state rather than a failure.
        self.engine = engine if engine is not None else HttpEngine()
        self.repairer = Repairer(rules) if rules is not None else None
        self.build = build or BuildIdentity()

    def check(
        self,
        crate: Crate,
        contract_name: str | None = None,
        contract: Contract | None = None,
        repair_budget: int = DEFAULT_REPAIR_BUDGET,
    ) -> Run:
        """Read a crate, check it against a contract, record what was found.

        The contract comes from the registry when named, or is supplied by the
        caller. With neither, nothing is checked and the record says so, which
        is not the same as saying the crate was accepted.

        A contract the requester supplied and a contract from the registry are
        recorded differently. "Checked against the published rules" and
        "checked against rules the sender supplied" are different claims about
        a crate and must not look alike afterwards.
        """
        run_id = uuid.uuid4().hex[:12]
        started = now()

        # The checksum is taken here, of the crate as it arrived, and not later.
        # Taken after any repair it would describe something the sender never
        # sent, and a reader could no longer tell whether what was blessed has
        # since been altered.
        input_checksum = crate.checksum()

        if contract is not None:
            source = ContractSource.SUPPLIED_BY_REQUESTER
        elif contract_name is not None:
            if self.registry is None:
                raise LookupError(
                    "a contract was named but this service holds no registry"
                )
            contract = self.registry.get(contract_name)
            source = ContractSource.REGISTRY
        else:
            source = ContractSource.NONE

        # The one component that may decide. This class never inspects the
        # report to reach a view of its own: it carries the verdict across
        # unchanged.
        report = (
            self.rules.validate(crate, contract)
            if self.rules is not None and contract is not None
            else None
        )

        # The repair path. Nothing is attempted without a budget, and with a
        # budget of zero the model is never asked anything at all.
        changes = ()
        asked = 0
        returned = crate
        if report is not None and repair_budget > 0 and self.repairer is not None:
            returned, changes, asked = self.repairer.repair(
                crate, report, contract, self.engine, repair_budget
            )
            if changes:
                # The crate is the authority for content and the report must
                # describe what is being returned, so it is taken again from
                # the repaired crate rather than patched.
                report = self.rules.validate(returned, contract)
                # Then one flag for each value the model recovered, so the
                # verdict says what the crate says. Without this a crate
                # went from REFUSED to ACCEPTED with nothing in the verdict
                # showing a model had supplied the missing value.
                report = with_flags_for(report, changes)

        blessing = Blessing(
            run_id=run_id,
            build=self.build,
            input_checksum=input_checksum,
            started=started,
            ended=now(),
            contract_name=contract.name if contract else None,
            contract_version=contract.version if contract else None,
            contract_checksum=contract.checksum if contract else None,
            contract_source=source,
            engine_used=self.engine.name,
            # Asked once, not per question, so a run makes one extra call at
            # most. Only asked when the model was actually used or could
            # have been: there is nothing to report about a model nobody
            # wanted.
            model_reachable=(
                None if self.engine.name == NO_ENGINE
                else self.engine.available()
            ),
            model_asked=asked,
            model_timed_out=getattr(self.engine, "timed_out", False),
            model_unreachable_detail=getattr(self.engine, "last_error", None),
            verdict=report.verdict if report else None,
            violations=report.violations if report else (),
            changes=changes,
        )

        blessed = self.provenance.write(returned, blessing)
        return Run(id=run_id, crate=blessed, blessing=blessing, report=report)
