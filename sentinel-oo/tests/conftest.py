"""Fixtures, and one rule enforced on every test.

The rule: no test may open a network connection. A test that needs the network
is testing a deployment, and deployments are checked by the demonstrator, not
here. The fixture below makes an attempt fail loudly rather than quietly
passing on a machine that happens to have a model running.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from sentinel_oo import BuildIdentity, Crate, ProvenanceWriter, Sentinel
from sentinel_oo.engines import NullEngine
from sentinel_oo.contract import ContractRegistry, Requirement
from sentinel_oo.rules import ContractChecks, Report, RuleEngine, Severity, Violation

# Every path in this file stays inside the product. Nothing here reaches into
# a deployment, so `sentinel-oo/` can be checked out on its own and tested
# with nothing beside it. `test_fixtures_stay_inside_the_product` in
# test_invariants.py fails the day that stops being true.
PRODUCT = Path(__file__).resolve().parents[1]
EXAMPLES = PRODUCT / "examples"

# The test suite's own fixtures, which are a coating laboratory: recipes
# blended, applied to metal panels in numbered slots on a rack, dried, and
# their film thickness measured.
#
# **Why the tests use a domain the documents never mention.** Nothing in the
# service knows anything about any domain, and these fixtures are how that
# is held in place: the same code that checks a bioprospecting handover in
# the worked example checks a coating line here, with no change but the
# contract file. They were the worked example until 11 November 2026, when
# they moved in here, because the people this product is for are biologists
# and a coating laboratory made the tutorial harder to read for no gain.
#
# They are built by tests/fixtures/make_example.py and are short enough to
# read: 28 entities.
FIXTURES = PRODUCT / "tests" / "fixtures"
PUBLISHED = FIXTURES / "coating-test" / "valid" / "ro-crate-metadata.json"


# The crates built on 10 November 2026 to be broken in one way each. All
# three pass rocrate-validator and all three are refused by the contract.
BROKEN = FIXTURES / "coating-test" / "invalid"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(
            "a test tried to open a network connection. Tests run with no "
            "network, no container and no model."
        )

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class AlwaysRefuses(RuleEngine):
    """A rule engine that refuses everything, whatever it is given.

    Used to prove that the verdict comes from the rule engine and from nowhere
    else. If any crate is ever accepted while this is installed, something
    other than the rule engine is deciding.
    """

    requirement = Requirement(
        name="always_refuses",
        applies_to="root",
        property="anything",
        named_value=None,
        must="be recorded",
        severity="refuse",
        message="this engine refuses everything, by construction",
    )

    def validate(self, subject, contract=None) -> Report:
        return Report(
            violations=(
                Violation(
                    requirement=self.requirement,
                    node="./",
                    message=self.requirement.message,
                ),
            )
        )


class AlwaysAccepts(RuleEngine):
    """The other half of the same proof."""

    def validate(self, subject, contract=None) -> Report:
        return Report()


@pytest.fixture
def published_bytes() -> bytes:
    return PUBLISHED.read_bytes()


@pytest.fixture
def published(published_bytes) -> Crate:
    return Crate.from_bytes(published_bytes)


@pytest.fixture
def writer() -> ProvenanceWriter:
    return ProvenanceWriter(service_version="0.1.0-test")


CONTRACTS = FIXTURES / "contracts"


@pytest.fixture
def registry() -> ContractRegistry:
    """The product's own example contracts, not any deployment's.

    The service ships no contracts that anybody is meant to deploy. These two
    are the worked example: `mixing_to_coating` with 19 requirements, and
    `coating_to_inspection`, a stub with 2, whose job is to demonstrate that
    a second handover is a second file and nothing else.
    """
    return ContractRegistry.from_dir(CONTRACTS)


def a_sentinel(writer, rules=None, registry=None, engine=None) -> Sentinel:
    """No model unless a test asks for one.

    The default engine became a real one over the network on 11 November
    2026. A test that picked that up would pass or fail depending on
    whether a model happened to be running on the machine, which is not a
    property of this code. Tests that are about the model pass their own.
    """
    return Sentinel(
        provenance=writer,
        rules=rules,
        registry=registry,
        engine=engine or NullEngine(),
        build=BuildIdentity(
            image_tag="test",
            git_commit="0000000",
            rules_checksum="none",
        ),
    )


@pytest.fixture
def sentinel(writer) -> Sentinel:
    """No rule engine, so nothing is checked. Step 1 of the build order."""
    return a_sentinel(writer)


@pytest.fixture
def checking(writer) -> Sentinel:
    """With the contract engine and the shipped contracts installed."""
    return a_sentinel(
        writer,
        rules=ContractChecks(),
        registry=ContractRegistry.from_dir(CONTRACTS),
    )


def minimal_crate_dict(extra: list[dict] | None = None) -> dict:
    """The smallest thing that is still an RO-Crate, for tests that are about
    the crate itself rather than about any real data."""
    graph = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.3"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": "a small crate",
            # The profile the contents follow, declared on the root. The
            # descriptor above declares the RO-Crate version instead, and
            # the two are different statements.
            "conformsTo": {"@id": "https://w3id.org/ro/wfrun/process/0.6"},
        },
    ]
    return {
        "@context": [
            "https://w3id.org/ro/crate/1.3/context",
            "https://w3id.org/ro/terms/workflow-run/context",
        ],
        "@graph": graph + (extra or []),
    }


@pytest.fixture
def minimal() -> Crate:
    import json

    return Crate.from_bytes(json.dumps(minimal_crate_dict()).encode())


@pytest.fixture
def zipped_crate() -> bytes:
    """The worked example as a zipped crate: the description and its data.

    This is what a handover actually is. A crate sent as a bare
    ro-crate-metadata.json is its description with the data left behind,
    and from 12 November 2026 a contract that checks the data says so
    rather than passing.
    """
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(PUBLISHED.parent.iterdir()):
            if path.is_file():
                archive.write(path, path.name)
    return buffer.getvalue()
