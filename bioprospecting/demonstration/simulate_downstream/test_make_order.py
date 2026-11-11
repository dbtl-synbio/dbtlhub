"""The simulated first process of the downstream workflow.

In reality this is a gene synthesis vendor's ordering system: it exists
already, we do not build it, and the boundary where it sits is fixed. It is
simulated here only so the demonstration has somewhere to hand a checked
crate off to.

It is not part of the service and must never become part of it. The service
decides; this acts on the decision. Everything here is about that separation
holding: the simulator reads a verdict somebody else reached and never
reaches one of its own.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from sentinel_oo import BuildIdentity, Crate, ProvenanceWriter, Sentinel
from sentinel_oo.contract import ContractRegistry, parse
from sentinel_oo.rules import ContractChecks

from conftest import BROKEN, CONTRACTS

from make_order import (
    NoRecord,
    Refused,
    build_order,
    main,
)

# A contract with a flag that names a well, so that the holding-back path can
# be exercised. The shipped contract's only flag is about the crate's licence,
# which names the root and holds no well back.
FLAGS_A_WELL = parse(
    """
contract: trial
version: 0.1.0
requires:
  - name: well_records_its_purpose
    applies_to: PlateWell
    property: disambiguatingDescription
    must: be recorded
    severity: flag
    message: "This well does not say what it is for."
"""
)


def checked(published, writer, contract=None, name=None):
    """Put a crate through the service and hand back what came out."""
    sentinel = Sentinel(
        provenance=writer,
        rules=ContractChecks(),
        registry=ContractRegistry.from_dir(CONTRACTS),
        build=BuildIdentity("test", "0000000", "none"),
    )
    return sentinel.check(published, contract_name=name, contract=contract).crate


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ----------------------------------------------------------- the happy path


def test_an_accepted_crate_produces_an_order(published, writer):
    order, held = build_order(checked(published, writer, name="design_to_build"))
    assert len(order) == 4
    assert held == []


def test_the_order_carries_what_the_vendor_needs(published, writer):
    order, _ = build_order(checked(published, writer, name="design_to_build"))
    plate, well, name, sequence = order[0]
    assert plate == "PLATE-AB-12-01"
    assert well == "A1"
    assert name == "CON-001"
    assert set(sequence) <= set("ACGT"), "the sequence is not DNA"
    assert len(sequence) > 100


def test_the_order_is_in_well_order(published, writer):
    order, _ = build_order(checked(published, writer, name="design_to_build"))
    positions = [row[1] for row in order]
    assert positions == sorted(positions)


# ------------------------------------------------- it acts on the decision


def test_a_refused_crate_produces_nothing(published, writer):
    """The whole point of the tool. A refusal is not advice."""
    broken = Crate.from_path(BROKEN / "dangling-reference")
    with pytest.raises(Refused):
        build_order(checked(broken, writer, name="design_to_build"))


def test_a_crate_that_was_never_checked_produces_nothing(published, writer):
    """Read by the service but never checked against a contract. That is not
    the same as being accepted, and the tool must not treat it as such."""
    sentinel = Sentinel(provenance=writer, build=BuildIdentity())
    with pytest.raises(NoRecord):
        build_order(sentinel.check(published).crate)


def test_a_crate_the_service_never_saw_produces_nothing(published):
    with pytest.raises(NoRecord):
        build_order(published)


def test_the_tool_reaches_no_verdict_of_its_own(published, writer):
    """It reads a verdict. It never works one out.

    If the service's record said refused and the tool decided otherwise from
    the findings, there would be two things deciding.
    """
    crate = checked(published, writer, name="design_to_build")
    raw = json.loads(crate.to_json())
    for entity in raw["@graph"]:
        if entity.get("name") == "verdict":
            entity["value"] = "REFUSED"
    with pytest.raises(Refused):
        build_order(Crate.from_bytes(json.dumps(raw).encode()))


# --------------------------------------------------------- holding back


def test_a_flagged_well_is_held_back_with_its_reason(published, writer):
    order, held = build_order(checked(published, writer, contract=FLAGS_A_WELL))
    assert len(order) == 0
    assert len(held) == 4
    assert all(row[3] == "This well does not say what it is for." for row in held)


def test_a_well_with_no_construct_is_held_back(published, writer):
    raw = json.loads(published.to_json())
    for entity in raw["@graph"]:
        if entity.get("@id") == "#well-PLATE-AB-12-01-A4":
            entity.pop("mainEntity", None)
    crate = Crate.from_bytes(json.dumps(raw).encode())
    # Checked against a contract that does not mind, so the handover is
    # accepted and the tool has to notice for itself.
    order, held = build_order(checked(crate, writer, contract=parse(
        "contract: t\nversion: '1'\nrequires: []\n")))
    assert len(order) == 3
    assert held[0][3].startswith("no construct named")


# ------------------------------------------------------- the command line


def test_the_command_writes_two_files(published, writer, tmp_path):
    crate = checked(published, writer, name="design_to_build")
    written = crate.save(tmp_path / "crate")
    out = tmp_path / "order"
    assert main([str(written), "--out", str(out)]) == 0

    order = rows(out / "vendor_upload.csv")
    held = rows(out / "held_back.csv")
    assert len(order) == 4 and len(held) == 0
    assert list(order[0]) == ["plate", "well", "name", "sequence"]


def test_the_command_refuses_a_refused_crate(writer, tmp_path):
    broken = Crate.from_path(BROKEN / "dangling-reference")
    crate = checked(broken, writer, name="design_to_build")
    written = crate.save(tmp_path / "crate")
    out = tmp_path / "order"
    assert main([str(written), "--out", str(out)]) == 1
    assert not (out / "vendor_upload.csv").exists()


def test_the_command_refuses_something_that_is_not_a_crate(tmp_path):
    bad = tmp_path / "notacrate.json"
    bad.write_text("{ not json")
    assert main([str(bad), "--out", str(tmp_path / "order")]) == 2
