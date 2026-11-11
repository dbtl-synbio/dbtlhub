"""A contract says what it is for, and refuses a crate it does not fit.

Why this exists. On 11 November 2026 two instances were deployed from one
image and a crate was posted to the wrong one. It came back ACCEPTED with 0
findings. The reason was that 12 of that contract's 18 requirements named
entity types the crate did not contain, so each of them matched nothing and
passed. Only 6 requirements looked at anything at all.

Each of those 12 was behaving correctly on its own. A requirement about a
type says nothing about a crate with none of that type, and it should not,
because presence and soundness are separate things. The failure was in the
aggregate: a verdict of ACCEPTED on a crate nobody had checked.

Blessing a crate that was never checked is worse than refusing a good one,
because a refusal is visible and sends somebody to look, while this is
silent and looks like success.

So a contract may now declare the entity types it is written for, and a
crate containing none of them is refused before a single requirement is
applied.
"""

from __future__ import annotations

import json

import pytest

from sentinel_oo import Crate
from sentinel_oo.contract import ContractError, parse
from sentinel_oo.rules import ContractChecks, Verdict

from conftest import minimal_crate_dict

ENGINE = ContractChecks()


def contract_expecting(*types, requires: str = "") -> object:
    expects = "\n".join(f"  - {t}" for t in types)
    return parse(
        f"""
contract: a_handover
version: 1.0.0
expects:
{expects}
requires:
  - name: the_crate_names_itself
    applies_to: root
    property: name
    must: be recorded
    severity: refuse
    message: "The crate has no name."
{requires}
"""
    )


def crate_with(*entities) -> Crate:
    return Crate.from_bytes(
        json.dumps(minimal_crate_dict(extra=list(entities))).encode()
    )


def typed(identifier: str, kind: str) -> dict:
    """An entity carrying a type through additionalType, which is how a crate
    says a thing is a kind the RO-Crate vocabulary has no word for."""
    return {
        "@id": identifier,
        "@type": "CreativeWork",
        "additionalType": kind,
        "name": identifier,
    }


# --------------------------------------------- the fault this exists to stop


def test_a_crate_from_another_domain_is_refused_not_accepted():
    """The exact fault, in miniature.

    Every requirement below is about a type this crate does not contain. All
    of them pass. Before `expects` the verdict was ACCEPTED with no findings.
    """
    contract = contract_expecting("CoatingRecipe", requires="""
  - name: recipe_records_its_thickness
    applies_to: CoatingRecipe
    named_value: film thickness
    must: be recorded
    severity: refuse
    message: "A recipe must say what thickness it is specified to produce."
  - name: one_recipe_per_slot
    applies_to: CoatingRecipe
    property: name
    must: be unique
    severity: refuse
    message: "Two recipes claim the same slot."
""")
    # A crate with nothing the contract is about.
    crate = crate_with(typed("#something-else", "ParkingSpace"))

    report = ENGINE.validate(crate, contract)
    assert report.verdict is Verdict.REFUSED, (
        "a crate containing nothing this contract is about was accepted, "
        "which is the fault of 11 November 2026 returning"
    )
    assert any("CoatingRecipe" in v.message for v in report.violations)


def test_the_two_requirements_about_the_absent_type_still_pass():
    """The point being that they are not the problem.

    Each requirement is right to say nothing about a crate with none of its
    type. What was wrong was the verdict drawn from their silence, and that
    is what `expects` fixes rather than changing how a requirement behaves.
    """
    contract = contract_expecting("CoatingRecipe", requires="""
  - name: recipe_records_its_thickness
    applies_to: CoatingRecipe
    named_value: film thickness
    must: be recorded
    severity: refuse
    message: "A recipe must say what thickness it is specified to produce."
""")
    crate = crate_with(typed("#something-else", "ParkingSpace"))
    report = ENGINE.validate(crate, contract)

    named = {v.requirement.name for v in report.violations}
    assert "recipe_records_its_thickness" not in named
    assert "crate_contains_CoatingRecipe" in named


# ------------------------------------------------------------- the behaviour


def test_a_crate_with_the_expected_type_is_judged_normally():
    contract = contract_expecting("CoatingRecipe")
    crate = crate_with(typed("#r1", "CoatingRecipe"))
    assert ENGINE.validate(crate, contract).verdict is Verdict.ACCEPTED


def test_one_violation_per_absent_type():
    """Which type is missing is the actionable part, so each is named."""
    contract = contract_expecting("CoatingRecipe", "RackSlot", "DryingStep")
    crate = crate_with(typed("#r1", "CoatingRecipe"))

    report = ENGINE.validate(crate, contract)
    missing = sorted(
        v.requirement.name for v in report.violations
        if v.requirement.name.startswith("crate_contains_")
    )
    assert missing == ["crate_contains_DryingStep", "crate_contains_RackSlot"]


def test_an_absent_type_is_a_refusal_not_a_flag():
    """There is no useful middle position. A contract that cannot tell
    whether it checked anything has not checked anything."""
    contract = contract_expecting("CoatingRecipe")
    crate = crate_with(typed("#x", "ParkingSpace"))

    violation = next(
        v for v in ENGINE.validate(crate, contract).violations
        if v.requirement.name == "crate_contains_CoatingRecipe"
    )
    assert violation.requirement.severity == "refuse"


def test_the_violation_is_reported_against_the_crate_itself():
    """There is no entity to blame, because the fault is that there is no
    entity. So it is reported against the root."""
    contract = contract_expecting("CoatingRecipe")
    crate = crate_with(typed("#x", "ParkingSpace"))

    violation = next(
        v for v in ENGINE.validate(crate, contract).violations
        if v.requirement.name == "crate_contains_CoatingRecipe"
    )
    assert violation.node == "./"


def test_the_message_says_what_might_have_happened():
    """A refusal that only says "wrong" sends nobody anywhere."""
    contract = contract_expecting("CoatingRecipe")
    crate = crate_with(typed("#x", "ParkingSpace"))

    violation = next(
        v for v in ENGINE.validate(crate, contract).violations
        if v.requirement.name == "crate_contains_CoatingRecipe"
    )
    full = violation.requirement.message
    assert "different phase" in full
    assert "type name" in full


def test_a_type_found_through_at_type_counts_too():
    """Not only additionalType. A crate may say what a thing is either way."""
    contract = contract_expecting("Dataset")
    crate = crate_with()
    assert ENGINE.validate(crate, contract).verdict is Verdict.ACCEPTED


def test_the_type_prefix_is_accepted_and_stripped():
    contract = contract_expecting("type:CoatingRecipe")
    assert contract.expects == ("CoatingRecipe",)
    crate = crate_with(typed("#r1", "CoatingRecipe"))
    assert ENGINE.validate(crate, contract).verdict is Verdict.ACCEPTED


def test_a_contract_with_no_expects_still_works():
    """Every contract written before this existed must keep working, and the
    hazard is reported in the summary rather than by refusing to load."""
    contract = parse("""
contract: a_handover
version: 1.0.0
requires:
  - name: the_crate_names_itself
    applies_to: root
    property: name
    must: be recorded
    severity: refuse
    message: "The crate has no name."
""")
    assert contract.expects == ()
    assert ENGINE.validate(crate_with(), contract).verdict is Verdict.ACCEPTED


# ----------------------------------------------------- what the reader refuses


def test_expects_must_be_a_list():
    with pytest.raises(ContractError) as caught:
        parse("""
contract: a_handover
version: 1.0.0
expects: CoatingRecipe
requires: []
""")
    assert "`expects` is a list" in str(caught.value)


def test_an_entry_that_is_not_a_type_name_is_refused():
    with pytest.raises(ContractError) as caught:
        parse("""
contract: a_handover
version: 1.0.0
expects:
  - CoatingRecipe
  - 42
requires: []
""")
    assert "entry 2" in str(caught.value)


# --------------------------------------------------- what a person is told


def test_the_summary_says_what_the_contract_is_for():
    contract = contract_expecting("CoatingRecipe", "RackSlot")
    said = contract.summary()
    assert "It is for crates containing all of: CoatingRecipe, RackSlot" in said


def test_the_summary_warns_when_a_contract_says_nothing_about_what_it_is_for():
    """A contract with no `expects` accepts any crate whose packaging is
    sound. Somebody reading it should be told so without having to work it
    out."""
    contract = parse("""
contract: a_handover
version: 1.0.0
requires:
  - name: the_crate_names_itself
    applies_to: root
    property: name
    must: be recorded
    severity: refuse
    message: "The crate has no name."
""")
    assert "does not say what it is for" in contract.summary()
