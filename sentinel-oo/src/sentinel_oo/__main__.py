"""Run the service over one crate from the command line.

At step 1 of the build order this is the whole of the service's surface. The
web interface and the agent interface arrive at step 5, and both will call the
same orchestrator this does.

    python -m sentinel_oo <crate> --out <folder>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .blessing import Verdict
from .crate import Crate, CrateMalformed
from .identity import BuildIdentity
from .provenance import ProvenanceWriter
from .contract import ContractNotFound, ContractRegistry
from .rules import ContractChecks
from .sentinel import Sentinel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sentinel-oo",
        description=(
            "Read a crate, check it, record what was found, and write it out."
        ),
    )
    parser.add_argument(
        "crate",
        nargs="?",
        help="an ro-crate-metadata.json file, or its folder",
    )
    parser.add_argument("--out", help="where to write the returned crate")
    parser.add_argument(
        "--contract",
        help="which handover to check against, by name",
    )
    parser.add_argument(
        "--contracts",
        default=os.environ.get("SENTINEL_CONTRACTS", "/contracts"),
        help=(
            "the folder of contract files. The service ships none of its own. "
            "A deployment supplies them, mounted at /contracts inside the "
            "container, or named here, or set in SENTINEL_CONTRACTS"
        ),
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="run as a service instead of checking one crate",
    )
    parser.add_argument(
        "--agent-interface",
        action="store_true",
        help="speak the Model Context Protocol on standard input and output",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--runs-held",
        type=int,
        default=20,
        help="how many recent runs to keep, as a count rather than a time",
    )
    parser.add_argument(
        "--describe", metavar="CRATE",
        help=("say what is in a crate: its entity types with counts, and the "
              "named values hanging off them. That is the list a contract "
              "has to match"),
    )
    parser.add_argument(
        "--list-contracts",
        action="store_true",
        help="say what this service knows how to check, and stop",
    )
    parser.add_argument(
        "--show-contract",
        help="print one contract in plain words, and stop",
    )
    args = parser.parse_args(argv)

    identity = BuildIdentity.from_env()
    registry = ContractRegistry.from_dir(args.contracts)

    if args.agent_interface:
        from .agent_interface import AgentInterface, serve as serve_agent
        from .runs import RunStore
        serve_agent(AgentInterface(
            Sentinel(
                provenance=ProvenanceWriter(service_version=__version__),
                rules=ContractChecks(),
                registry=registry,
                build=identity,
            ),
            RunStore(limit=args.runs_held),
        ))
        return 0

    if args.serve:
        from . import serve
        serve(contracts=args.contracts, host=args.host, port=args.port,
              runs_held=args.runs_held)
        return 0

    if args.describe:
        from .crate import describe

        try:
            print(describe(Crate.from_path(args.describe)))
        except CrateMalformed as exc:
            print(f"not a crate: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.list_contracts:
        for contract in registry.list():
            print(f"{contract.name}  version {contract.version}  "
                  f"{len(contract.requirements)} requirement(s)")
        print(f"\nchecksum over all of them: {registry.checksum()}")
        return 0

    if args.show_contract:
        try:
            print(registry.get(args.show_contract).summary())
        except ContractNotFound as exc:
            print(exc, file=sys.stderr)
            return 2
        return 0

    if not args.crate:
        parser.error("say which crate to read")

    try:
        crate = Crate.from_path(args.crate)
    except CrateMalformed as exc:
        print(f"not a crate: {exc}", file=sys.stderr)
        return 2

    # Wired by hand rather than through a convenience function, because
    # watching the pieces get handed to each other is most of the design.
    sentinel = Sentinel(
        provenance=ProvenanceWriter(service_version=__version__),
        rules=ContractChecks(),
        registry=registry,
        build=identity,
    )
    try:
        run = sentinel.check(crate, contract_name=args.contract)
    except ContractNotFound as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"sentinel-oo {__version__}   {identity.describe()}")
    print(f"read {args.crate}")
    print(f"  {len(crate)} entities in, {len(run.crate)} out")
    print()
    for name, value in run.blessing.facts():
        print(f"  {name:38} {value}")
    print(f"  {'verdict':38} {run.blessing.verdict_text()}")

    if run.blessing.violations:
        print()
        for violation in run.blessing.violations:
            print(f"  {violation.severity.value.upper()}  {violation.message}")
            print(f"         at {violation.node}")

    if args.out:
        written = run.crate.save(Path(args.out))
        print()
        print(f"written to {written}")

    return 0 if run.blessing.verdict is not Verdict.REFUSED else 1


if __name__ == "__main__":
    raise SystemExit(main())
