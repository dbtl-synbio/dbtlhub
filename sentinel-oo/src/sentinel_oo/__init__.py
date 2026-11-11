"""sentinel-oo: a service that decides whether one phase of a Design, Build,
Test, Learn cycle can accept what the previous phase produced.

A crate goes in and a crate comes out, carrying a record of what was checked.
"""

__version__ = "0.1.0"

from .blessing import Blessing, ContractSource, Verdict
from .crate import Crate, CrateMalformed
from .engines import (
    CommandEngine,
    Engine,
    NullEngine,
    ScriptedEngine,
)
from .repair import Change, Repairer
from .identity import BuildIdentity
from .provenance import ProvenanceWriter
from .runs import RunStore
from .contract import (
    Contract,
    ContractError,
    ContractNotFound,
    ContractRegistry,
    Requirement,
)
from .rules import ContractChecks, Report, RuleEngine, Severity, Violation
from .sentinel import Run, Sentinel

__all__ = [
    "Blessing",
    "BuildIdentity",
    "ContractSource",
    "Change",
    "CommandEngine",
    "Crate",
    "Engine",
    "NullEngine",
    "Repairer",
    "ScriptedEngine",
    "CrateMalformed",
    "Contract",
    "ContractChecks",
    "ContractError",
    "ContractNotFound",
    "ContractRegistry",
    "Requirement",
    "ProvenanceWriter",
    "RunStore",
    "Report",
    "RuleEngine",
    "Severity",
    "Violation",
    "Run",
    "Sentinel",
    "Verdict",
    "__version__",
]


def build(
    build_identity: BuildIdentity | None = None,
    rules: RuleEngine | None = None,
    contracts: str | None = None,
) -> Sentinel:
    """A Sentinel with the ordinary collaborators, for people who do not want
    to wire it up themselves. Everything is still injectable.

    Leaving `rules` out installs the engine that applies contracts. To check
    nothing, construct `Sentinel` directly with `rules=None`: there is
    deliberately no way to ask for that here, because a convenience function
    that can silently turn the checking off is a convenience nobody needs.

    `contracts` is a folder of contract files. Without one the service holds no
    contracts and can check nothing, which it says rather than implies.
    """
    return Sentinel(
        provenance=ProvenanceWriter(service_version=__version__),
        rules=ContractChecks() if rules is None else rules,
        registry=ContractRegistry.from_dir(contracts) if contracts else None,
        build=build_identity or BuildIdentity.from_env(),
    )


def serve(contracts: str, host: str = "0.0.0.0", port: int = 8080,
          runs_held: int = 20) -> None:
    """Run the web interface. One line, so that a container can start it."""
    from .api import Api, serve as _serve

    _serve(Api(build(contracts=contracts), RunStore(limit=runs_held)),
           host=host, port=port)
