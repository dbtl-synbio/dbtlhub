"""The crate as boxes and the lines between them.

Built on 11 November 2026. `GET /graph/{run}` and the agent interface's
`get_run_graph` had both answered "not built yet" since the interface was
designed, because the original plan put the graph in a store that was never
written. The store is not needed: the crate the service hands back already
holds all of it.

So this module works nothing out, and these tests are about one thing: that
what comes out is what is in the crate, with nothing invented and nothing
quietly dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel_oo.crate import Crate
from sentinel_oo.graph import of

PRODUCT = Path(__file__).resolve().parents[1]
PLATE = PRODUCT / "examples" / "plate-test"


@pytest.fixture
def registry():
    """The worked example's own contracts, not the test suite's fixtures.

    conftest's `registry` holds the coating laboratory contracts, which the
    rest of the suite uses. These tests are about the picture a reader sees,
    so they use the crates and the contract the documents teach.
    """
    from sentinel_oo.contract import ContractRegistry

    return ContractRegistry.from_dir(PRODUCT / "examples" / "contracts")


@pytest.fixture
def checked(writer, registry):
    """A crate that has actually been through the service, because the
    graph's whole job is to show the check as well as the handover."""
    from sentinel_oo.engines import NullEngine
    from sentinel_oo.rules import ContractChecks
    from sentinel_oo.sentinel import Sentinel

    service = Sentinel(provenance=writer, rules=ContractChecks(),
                       registry=registry, engine=NullEngine())
    return service.check(Crate.from_path(PLATE / "valid"),
                         contract_name="design_to_build")


# ------------------------------------------------- nothing is invented


def test_every_box_is_an_entity_that_is_really_in_the_crate(checked):
    graph = of(checked.crate, run=checked.id)
    in_crate = {str(e.get("@id")) for e in checked.crate}
    for node in graph["nodes"]:
        if node["role"] in ("missing", "elsewhere"):
            continue
        assert node["id"] in in_crate, node


def test_every_line_starts_at_something_in_the_crate(checked):
    graph = of(checked.crate, run=checked.id)
    in_crate = {str(e.get("@id")) for e in checked.crate}
    for edge in graph["edges"]:
        assert edge["from"] in in_crate


def test_nothing_in_the_crate_is_left_out(checked):
    graph = of(checked.crate, run=checked.id)
    drawn = {n["id"] for n in graph["nodes"]}
    for entity in checked.crate:
        assert str(entity.get("@id")) in drawn


def test_the_counts_match_what_was_returned(checked):
    graph = of(checked.crate, run=checked.id)
    assert graph["counts"]["nodes"] == len(graph["nodes"])
    assert graph["counts"]["edges"] == len(graph["edges"])


# ------------------------------------- the check stands out from the crate


def test_the_check_itself_is_marked(checked):
    graph = of(checked.crate, run=checked.id)
    checks = [n for n in graph["nodes"] if n["role"] == "the check"]
    assert len(checks) == 1
    assert checked.id in checks[0]["id"]


def test_the_verdict_is_carried_at_the_top_and_marked_in_the_graph(checked):
    graph = of(checked.crate, run=checked.id)
    assert graph["verdict"]
    assert graph["verdict"].startswith(checked.blessing.verdict.value)
    assert [n for n in graph["nodes"] if n["role"] == "the verdict"]


def test_each_finding_is_its_own_box(writer, registry):
    """So a drawing can point at one of them, and so can a person."""
    from sentinel_oo.engines import NullEngine
    from sentinel_oo.rules import ContractChecks
    from sentinel_oo.sentinel import Sentinel

    service = Sentinel(provenance=writer, rules=ContractChecks(),
                       registry=registry, engine=NullEngine())
    run = service.check(Crate.from_path(PLATE / "invalid" / "dangling-reference"),
                        contract_name="design_to_build")
    graph = of(run.crate, run=run.id)

    findings = [n for n in graph["nodes"] if n["role"] == "a finding"]
    assert len(findings) == len(run.blessing.violations)
    for node in findings:
        assert node.get("value"), "a finding with no sentence in it"


def test_a_value_a_model_recovered_is_marked(writer, registry):
    """The one thing in a checked crate that nobody wrote down, so the one
    a reader should be able to find in the picture."""
    from sentinel_oo.rules import ContractChecks
    from sentinel_oo.sentinel import Sentinel
    from sentinel_oo.engines import ScriptedEngine

    service = Sentinel(provenance=writer, rules=ContractChecks(),
                       registry=registry,
                       engine=ScriptedEngine({"edge handling": "closed"}))
    run = service.check(
        Crate.from_path(PLATE / "invalid" / "edge-handling-in-prose"),
        contract_name="design_to_build")
    assert run.blessing.changes, "the model changed nothing, so nothing to mark"

    graph = of(run.crate, run=run.id)
    recovered = [n for n in graph["nodes"]
                 if n["role"] in ("a value a model recovered", "a change made")]
    assert recovered


# --------------------------- a pointer at nothing, and a pointer elsewhere


def test_a_file_the_crate_lists_and_never_describes_is_shown_as_missing():
    """The fault one of the example crates carries. A picture that dropped
    the broken pointer would hide exactly what the reader is looking for."""
    graph = of(Crate.from_path(PLATE / "invalid" / "dangling-reference"))
    missing = [n for n in graph["nodes"] if n["role"] == "missing"]
    assert [n["id"] for n in missing] == ["sequencing-report.pdf"]


def test_a_web_address_is_not_called_missing():
    """A web address says the thing lives elsewhere on purpose: the standard
    the crate follows, its licence. Calling those missing would tell a reader
    the crate is broken when it is not."""
    graph = of(Crate.from_path(PLATE / "valid"))
    assert graph["counts"]["missing"] == 0
    elsewhere = {n["id"] for n in graph["nodes"] if n["role"] == "elsewhere"}
    assert any(e.startswith("https://") for e in elsewhere)


# ------------------------------------------------------- what a drawing needs


def test_a_type_a_picture_can_colour_by(checked):
    """RO-Crate has no term for a plate well, so the crate types those
    entities as something general and says what they are in additionalType.
    A picture showing CreativeWork four times would say nothing."""
    graph = of(checked.crate, run=checked.id)
    types = {n["type"] for n in graph["nodes"]}
    assert "PlateWell" in types
    assert "ExpressionConstruct" in types


def test_packaging_lines_are_marked_so_they_can_be_left_out(checked):
    """hasPart from the root to every file turns any picture into a star
    with the root in the middle and nothing else visible."""
    graph = of(checked.crate, run=checked.id)
    packaging = [e for e in graph["edges"] if e["packaging"]]
    assert packaging
    assert any(e["property"] == "hasPart" for e in packaging)


def test_it_is_json_a_client_can_read(checked):
    """It travels over the web interface, so it has to survive being
    written out and read back."""
    graph = of(checked.crate, run=checked.id)
    assert json.loads(json.dumps(graph)) == graph


def test_it_says_how_to_read_itself(checked):
    """A client that has never seen this before should not have to guess
    what a role of missing means."""
    graph = of(checked.crate, run=checked.id)
    assert "missing" in graph["how_to_read_it"]
    assert "packaging" in graph["how_to_read_it"]


# ------------------------------------- it works with no service at all


def test_a_crate_alone_is_enough():
    """The lasting copy is the crate, not anything this service keeps. A
    reader a year later has the crate and nothing else."""
    graph = of(Crate.from_path(PLATE / "valid"))
    assert graph["nodes"]
    assert graph["run"] is None


def test_a_crate_that_was_never_checked_still_draws():
    """Somebody will point this at a crate before sending it anywhere."""
    graph = of(Crate.from_path(PLATE / "valid"))
    assert not [n for n in graph["nodes"] if n["role"] == "the check"]
    assert graph["verdict"] is None
