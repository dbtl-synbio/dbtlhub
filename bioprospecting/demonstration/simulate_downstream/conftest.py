"""Fixtures for the downstream simulator's own tests.

This folder is neither the product nor a deployment. It stands in for the
first process in the downstream workflow, so that the demonstration has
somewhere to hand a checked crate off to. In reality that process is a gene
synthesis vendor's ordering system, which exists already and which we do not
build, change or deploy.

Its tests therefore stand on their own rather than borrowing the product's
test fixtures. The product must be checkable without this folder, and this
folder must be runnable without the product's test suite.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

def _the_product(start: Path) -> Path | None:
    """Where sentinel-oo's source is, found by climbing rather than counting.

    This used to count folders upwards, which broke the day the use case
    moved from its own repository into dbtlhub and gained one level of
    depth. Climbing until the product is seen survives being moved again.
    """
    for folder in [start, *start.parents]:
        candidate = folder / "sentinel-oo" / "src"
        if candidate.is_dir():
            return candidate
    return None


HERE = Path(__file__).resolve().parent

# The product, used as a library. The simulator may import the service. The
# service may never import the simulator, and a test in the product's own
# suite fails if it ever does.
_PRODUCT = _the_product(HERE)
if _PRODUCT is None:
    raise RuntimeError(
        f"sentinel-oo/src was not found above {HERE}. These tests use the "
        "product as a library, so they need it on the path."
    )
sys.path.insert(0, str(_PRODUCT))
sys.path.insert(0, str(HERE))

from sentinel_oo import Crate, ProvenanceWriter  # noqa: E402

# The deployment this demonstration runs against. One of possibly many: the
# simulator is pointed at a deployment rather than containing one.
# This use case's own folder, which holds the contracts and the example
# crates. Two levels up from here: simulate_downstream, demonstration,
# bioprospecting.
USE_CASE = HERE.parents[1]
CONTRACTS = USE_CASE / "contracts"
CRATES = USE_CASE / "exampleROcrates"

PUBLISHED = CRATES / "design-to-build-simple" / "ro-crate-metadata.json"

# Crates built on 10 November 2026 to be broken in one way each. All of them
# pass the third party RO-Crate validator and all of them are refused by the
# contract, which is the argument for the contract in one example.
BROKEN = CRATES / "design-to-build" / "invalid"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test here opens a network connection.

    The simulator reads a file and writes two files. If it ever reaches the
    network, that is a change of kind and somebody should have to notice.
    """

    def refuse(*args, **kwargs):
        raise AssertionError(
            "a test tried to open a network connection. The simulator reads "
            "and writes files and nothing else."
        )

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def published() -> Crate:
    return Crate.from_bytes(PUBLISHED.read_bytes())


@pytest.fixture
def writer() -> ProvenanceWriter:
    return ProvenanceWriter(service_version="0.1.0-test")
