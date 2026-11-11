"""Section 16.7 of the specification: the rule engine.

Every check now comes from a contract file. There is no check written in
Python anywhere, which is what step 3 of the build order delivers, and the
invariant test that no handover is named in the source is what keeps it true.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel_oo import Crate, Verdict
from sentinel_oo.contract import parse
from sentinel_oo.rules import (
    ContractChecks,
    Report,
    Severity,
    Violation,
    types_of,
    values_of,
)

from conftest import minimal_crate_dict

# The worked example with the root's declaration of its profile deliberately
# removed. A whole generated crate rather than one invented inline here, and
# inside the product, so this file needs nothing outside it.
BROKEN = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "coating-test"
    / "invalid"
    / "missing-conformsto"
)

PROFILE_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: declares_a_profile
    applies_to: root
    property: conformsTo
    must: be recorded
    severity: refuse
    message: "The crate does not say which profile it follows."
"""
)

FLAG_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: mentions_a_licence
    applies_to: root
    property: license
    must: be recorded
    severity: flag
    message: "No licence is recorded."
"""
)

ONE_OF_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: drying_atmosphere_is_known
    applies_to: type:Thing
    property: mode
    must: be recorded
    one_of: ["complete ends", "open ends"]
    severity: refuse
    message: "Build cannot judge comparability without the drying atmosphere."
"""
)


@pytest.fixture
def engine() -> ContractChecks:
    return ContractChecks()


def a_violation(severity: Severity) -> Violation:
    contract = PROFILE_RULE if severity is Severity.REFUSE else FLAG_RULE
    requirement = contract.requirements[0]
    return Violation(requirement=requirement, node="./", message=requirement.message)


def without_root_profile() -> dict:
    """The smallest crate, with the root's profile declaration removed.

    Derived from the fixture rather than written out, so the two cannot drift
    apart.
    """
    body = minimal_crate_dict()
    for entity in body["@graph"]:
        if entity["@id"] == "./":
            del entity["conformsTo"]
    return body


# --------------------------------------------------------------- the report


def test_clean_report_is_accepted():
    assert Report().verdict is Verdict.ACCEPTED


def test_one_blocking_violation_refuses():
    report = Report(violations=(a_violation(Severity.REFUSE),))
    assert report.verdict is Verdict.REFUSED
    assert not report.ok


def test_flags_alone_do_not_refuse():
    report = Report(violations=(a_violation(Severity.FLAG),))
    assert report.verdict is Verdict.ACCEPTED_WITH_FLAGS
    assert report.ok


def test_blocking_and_flags_are_separable():
    report = Report(
        violations=(a_violation(Severity.REFUSE), a_violation(Severity.FLAG))
    )
    assert len(report.blocking) == 1
    assert len(report.flags) == 1
    assert report.verdict is Verdict.REFUSED


def test_verdict_has_no_setter():
    """Nothing downstream may change a verdict once the rules have reached it."""
    with pytest.raises((AttributeError, TypeError)):
        Report().verdict = Verdict.REFUSED


# --------------------------------------------------------- applying a rule


def test_no_contract_means_nothing_is_checked(published, engine):
    report = engine.validate(published, contract=None)
    assert report.violations == ()


def test_published_crate_satisfies_the_profile_rule(published, engine):
    assert engine.validate(published, PROFILE_RULE).verdict is Verdict.ACCEPTED


def test_crate_with_no_profile_is_refused(engine):
    crate = Crate.from_bytes(json.dumps(without_root_profile()).encode())
    report = engine.validate(crate, PROFILE_RULE)
    assert report.verdict is Verdict.REFUSED
    assert report.blocking[0].requirement.name == "declares_a_profile"


def test_the_message_is_the_one_the_author_wrote(engine):
    crate = Crate.from_bytes(json.dumps(without_root_profile()).encode())
    message = engine.validate(crate, PROFILE_RULE).blocking[0].message
    assert message == PROFILE_RULE.requirements[0].message
    assert "shacl" not in message.lower()


def test_violation_names_where_it_failed(engine):
    crate = Crate.from_bytes(json.dumps(without_root_profile()).encode())
    assert engine.validate(crate, PROFILE_RULE).blocking[0].node == "./"


@pytest.mark.skipif(not BROKEN.exists(), reason="the broken crate is not here")
def test_the_real_broken_crate_is_refused(engine):
    report = engine.validate(Crate.from_path(BROKEN), PROFILE_RULE)
    assert report.verdict is Verdict.REFUSED


def test_a_value_outside_the_permitted_list_is_caught(engine):
    body = minimal_crate_dict(
        extra=[{"@id": "#run", "@type": "Thing", "mode": "whatever it was"}]
    )
    crate = Crate.from_bytes(json.dumps(body).encode())
    report = engine.validate(crate, ONE_OF_RULE)
    assert report.verdict is Verdict.REFUSED
    assert report.blocking[0].value == "whatever it was"


def test_a_permitted_value_passes(engine):
    body = minimal_crate_dict(
        extra=[{"@id": "#run", "@type": "Thing", "mode": "complete ends"}]
    )
    crate = Crate.from_bytes(json.dumps(body).encode())
    assert engine.validate(crate, ONE_OF_RULE).verdict is Verdict.ACCEPTED


def test_no_entity_of_that_type_is_nothing_to_check(engine, published):
    """"There are no things of this kind here" is a different requirement from
    "every thing of this kind must record its mode", and conflating them would
    make one of them unsayable."""
    assert engine.validate(published, ONE_OF_RULE).verdict is Verdict.ACCEPTED


def test_every_entity_of_the_type_is_checked(engine):
    body = minimal_crate_dict(
        extra=[
            {"@id": "#a", "@type": "Thing", "mode": "complete ends"},
            {"@id": "#b", "@type": "Thing"},
            {"@id": "#c", "@type": "Thing", "mode": "nonsense"},
        ]
    )
    crate = Crate.from_bytes(json.dumps(body).encode())
    report = engine.validate(crate, ONE_OF_RULE)
    assert {v.node for v in report.violations} == {"#b", "#c"}


def test_deterministic(published, engine):
    first = engine.validate(published, PROFILE_RULE)
    second = engine.validate(published, PROFILE_RULE)
    assert first.verdict == second.verdict
    assert [v.node for v in first.violations] == [v.node for v in second.violations]


def test_validate_does_not_alter_the_crate(published, engine):
    before = published.checksum()
    engine.validate(published, PROFILE_RULE)
    assert published.checksum() == before


# --------------------------------------------- reading values off an entity


@pytest.mark.parametrize(
    "written,expected",
    [
        ({"@id": "https://w3id.org/ro/crate/1.3"}, ("https://w3id.org/ro/crate/1.3",)),
        ([{"@id": "a"}, {"@id": "b"}], ("a", "b")),
        ("plain text", ("plain text",)),
        (7, ("7",)),
        (["a", {"@id": "b"}], ("a", "b")),
        (None, ()),
        ([], ()),
        ("", ()),
        ("   ", ()),
    ],
)
def test_a_property_is_read_however_it_was_written(written, expected):
    """Crates in the wild write these several ways and all of them mean
    "this entity records these values"."""
    entity = {"@id": "./"}
    if written is not None:
        entity["thing"] = written
    assert values_of(entity, "thing") == expected


def test_types_are_read_whether_one_or_several():
    assert types_of({"@type": "Dataset"}) == ("Dataset",)
    assert types_of({"@type": ["File", "Dataset"]}) == ("File", "Dataset")
    assert types_of({}) == ()


# ------------------------------------------------- the three newer demands
# Written for step 4. Most of what the Design to Build handover actually
# needs could not be said in the language at all until these existed.


UNIQUE_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: one_recipe_per_slot
    applies_to: type:Recipe
    property: slotPosition
    must: be unique
    severity: refuse
    message: "Two recipes claim the same slot, so the rack cannot be ordered."
"""
)

POINTS_AT_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: recipe_names_its_reading
    applies_to: type:Recipe
    property: isBasedOn
    must: point at something in the crate
    of_type: ThicknessReading
    severity: refuse
    message: "Every recipe must name the reading it was designed from."
"""
)

RANGE_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: within_what_can_be_applied
    applies_to: type:Recipe
    property: thicknessMicrometres
    must: be a number between
    between: [300, 1800]
    severity: flag
    message: "This recipe is outside the length the coating line will apply."
"""
)


def crate_with(*entities) -> Crate:
    return Crate.from_bytes(json.dumps(minimal_crate_dict(extra=list(entities))).encode())


# ------------------------------------------------------------- uniqueness


def test_two_recipes_in_one_slot_are_caught(engine):
    crate = crate_with(
        {"@id": "#one", "@type": "Recipe", "slotPosition": "A1"},
        {"@id": "#two", "@type": "Recipe", "slotPosition": "A1"},
    )
    report = engine.validate(crate, UNIQUE_RULE)
    assert report.verdict is Verdict.REFUSED
    # Both ends of the clash are reported, because a person fixing it needs to
    # see both.
    assert {v.node for v in report.violations} == {"#one", "#two"}
    assert all(v.value == "A1" for v in report.violations)


def test_distinct_slots_pass(engine):
    crate = crate_with(
        {"@id": "#one", "@type": "Recipe", "slotPosition": "A1"},
        {"@id": "#two", "@type": "Recipe", "slotPosition": "A2"},
    )
    assert engine.validate(crate, UNIQUE_RULE).verdict is Verdict.ACCEPTED


def test_uniqueness_says_nothing_about_an_absent_value(engine):
    """"It must be present" and "it must not be shared" are two requirements.

    A rule doing both would make one of them impossible to say.
    """
    crate = crate_with({"@id": "#one", "@type": "Recipe"})
    assert engine.validate(crate, UNIQUE_RULE).verdict is Verdict.ACCEPTED


# ------------------------------------------------------- following a link


def test_a_reference_to_something_absent_is_caught(engine):
    crate = crate_with(
        {"@id": "#c", "@type": "Recipe", "isBasedOn": {"@id": "#not-here"}}
    )
    report = engine.validate(crate, POINTS_AT_RULE)
    assert report.verdict is Verdict.REFUSED
    assert report.blocking[0].value == "#not-here"


def test_a_reference_to_the_wrong_kind_of_thing_is_caught(engine):
    crate = crate_with(
        {"@id": "#c", "@type": "Recipe", "isBasedOn": {"@id": "#p"}},
        {"@id": "#p", "@type": "File", "name": "a file, not a reading"},
    )
    assert engine.validate(crate, POINTS_AT_RULE).verdict is Verdict.REFUSED


def test_a_reference_that_lands_correctly_passes(engine):
    crate = crate_with(
        {"@id": "#c", "@type": "Recipe", "isBasedOn": {"@id": "#p"}},
        {"@id": "#p", "@type": "ThicknessReading", "name": "a thickness reading"},
    )
    assert engine.validate(crate, POINTS_AT_RULE).verdict is Verdict.ACCEPTED


# -------------------------------------------------------------- a number


def test_a_length_outside_the_range_is_flagged(engine):
    crate = crate_with(
        {"@id": "#c", "@type": "Recipe", "thicknessMicrometres": 2400}
    )
    report = engine.validate(crate, RANGE_RULE)
    assert report.verdict is Verdict.ACCEPTED_WITH_FLAGS
    assert report.flags[0].value == "2400"


def test_a_length_inside_the_range_passes(engine):
    crate = crate_with({"@id": "#c", "@type": "Recipe", "thicknessMicrometres": 900})
    assert engine.validate(crate, RANGE_RULE).verdict is Verdict.ACCEPTED


def test_the_ends_of_the_range_are_included(engine):
    crate = crate_with(
        {"@id": "#low", "@type": "Recipe", "thicknessMicrometres": 300},
        {"@id": "#high", "@type": "Recipe", "thicknessMicrometres": 1800},
    )
    assert engine.validate(crate, RANGE_RULE).verdict is Verdict.ACCEPTED


def test_something_that_is_not_a_number_at_all_is_caught(engine):
    crate = crate_with(
        {"@id": "#c", "@type": "Recipe", "thicknessMicrometres": "about nine hundred"}
    )
    assert engine.validate(crate, RANGE_RULE).violations


def test_an_unknown_demand_cannot_pass_silently(engine, published):
    """If a demand is added to the contract reader and not to this engine,
    everything would otherwise pass without being checked."""
    from dataclasses import replace

    from sentinel_oo.contract import Contract

    broken = replace(
        PROFILE_RULE,
        requirements=(replace(PROFILE_RULE.requirements[0], must="be lucky"),),
    )
    assert isinstance(broken, Contract)
    with pytest.raises(NotImplementedError):
        engine.validate(published, broken)


# ------------------------------------------- values that hang off an entity
# Crates following the Process Run Crate profile record most numbers and
# strings as separate entities carrying a name and a value, which the thing
# they describe points at. Reading them is how such a crate is read at all.


NAMED_VALUE_RULE = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: one_recipe_per_slot
    applies_to: CoatingRecipe
    named_value: intended slot
    must: be unique
    severity: refuse
    message: "Two recipes claim the same slot, so the rack cannot be ordered."
"""
)

NAMED_VALUE_PRESENT = parse(
    """
contract: a_handover
version: 0.1.0
requires:
  - name: recipe_has_a_slot
    applies_to: CoatingRecipe
    named_value: intended slot
    must: be recorded
    severity: refuse
    message: "Without a slot, nothing can find this recipe on the rack."
"""
)


def recipe(identifier, slot=None, extra=None):
    """A recipe shaped the way the published crate shapes one."""
    entity = {
        "@id": f"#recipe-{identifier}",
        "@type": "CreativeWork",
        "additionalType": "CoatingRecipe",
        "identifier": identifier,
        "additionalProperty": [],
    }
    entity.update(extra or {})
    carriers = []
    if slot is not None:
        entity["additionalProperty"].append({"@id": f"#pv-{identifier}-slot"})
        carriers.append(
            {
                "@id": f"#pv-{identifier}-slot",
                "@type": "PropertyValue",
                "name": "intended slot",
                "value": slot,
            }
        )
    return [entity] + carriers


def test_a_named_value_is_read_through_the_entity_that_carries_it(engine):
    crate = crate_with(*recipe("CON-001", slot="A1"))
    assert engine.validate(crate, NAMED_VALUE_PRESENT).verdict is Verdict.ACCEPTED


def test_a_missing_named_value_is_caught(engine):
    crate = crate_with(*recipe("CON-001"))
    report = engine.validate(crate, NAMED_VALUE_PRESENT)
    assert report.verdict is Verdict.REFUSED
    # The recipe is named, not the internal value entity, because that is
    # what a person fixing it needs to be told.
    assert report.blocking[0].node == "#recipe-CON-001"


def test_two_recipes_sharing_a_slot_are_caught(engine):
    crate = crate_with(*recipe("CON-001", slot="A1"), *recipe("CON-002", slot="A1"))
    report = engine.validate(crate, NAMED_VALUE_RULE)
    assert report.verdict is Verdict.REFUSED
    assert {v.node for v in report.violations} == {
        "#recipe-CON-001",
        "#recipe-CON-002",
    }


def test_different_slots_pass(engine):
    crate = crate_with(*recipe("CON-001", slot="A1"), *recipe("CON-002", slot="A2"))
    assert engine.validate(crate, NAMED_VALUE_RULE).verdict is Verdict.ACCEPTED


def test_a_broken_reference_to_a_value_does_not_raise(engine):
    """That the reference is broken is a fault of its own, and one a
    requirement can be written for. Reading values is not the place to decide
    that."""
    entity = {
        "@id": "#recipe-CON-001",
        "@type": "CreativeWork",
        "additionalType": "CoatingRecipe",
        "additionalProperty": [{"@id": "#pv-that-is-not-here"}],
    }
    report = engine.validate(crate_with(entity), NAMED_VALUE_PRESENT)
    assert report.verdict is Verdict.REFUSED


# ------------------------------------------------------- additionalType


def test_a_rule_can_name_a_kind_that_schema_org_has_no_word_for(engine):
    """A recipe and a rack are both CreativeWork. Without this, a rule
    could not say "every recipe" at all."""
    crate = crate_with(
        *recipe("CON-001", slot="A1"),
        {
            "@id": "#rack-01",
            "@type": "CreativeWork",
            "additionalType": "IntendedRackLayout",
            "name": "a rack, which has no slot of its own",
        },
    )
    report = engine.validate(crate, NAMED_VALUE_PRESENT)
    assert report.verdict is Verdict.ACCEPTED, (
        "the rule reached the rack, which has no intended slot and should "
        "never have been asked for one"
    )


def test_a_named_value_is_found_through_any_reference(published):
    """A recipe hangs its values off additionalProperty. A step hangs the
    setting it ran with off object, because that is what Process Run Crate
    says a parameter is. A reader that knew only one of those would see half
    the crate."""
    from sentinel_oo.rules import named_values_of

    # Off `object`, on a process step.
    step = published.get("#act-drying")
    assert named_values_of(step, "drying atmosphere", published) == ("dry",)

    # Off `additionalProperty`, on a recipe. The value is a number in the
    # crate, so it is compared as text rather than assumed to be a string.
    recipe = published.get("#recipe-REC-001")
    found = named_values_of(recipe, "film thickness", published)
    assert [str(v) for v in found] == ["42"], "film thickness in micrometres"


def test_only_property_values_are_read_as_named_values(published):
    """A step points at files and tools as well as settings. A file with a
    name must not be mistaken for a value."""
    from sentinel_oo.rules import named_values_of

    # This step's `object` holds recipes.csv, which is a File carrying a
    # name. Asking for that name must find no value.
    step = published.get("#act-blending")
    assert named_values_of(
        step, "The three recipes, one per row", published
    ) == ()
