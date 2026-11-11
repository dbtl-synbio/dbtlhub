"""Section 16.3 of the specification: the contract and the registry.

A contract file is read as data and nothing in it is ever executed. Everything
that can be wrong with one is found when it is read, with the file named, so
the author hears about it on their own machine rather than six weeks later
when somebody posts a crate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel_oo.contract import (
    Contract,
    ContractError,
    ContractNotFound,
    ContractRegistry,
    parse,
)

from conftest import CONTRACTS

GOOD = """
contract: example_handover
version: 1.2.0
description: a handover used by the tests
requires:
  - name: has_a_name
    applies_to: root
    property: name
    must: be recorded
    severity: refuse
    message: "Without a name nobody can say what this is."
"""


def test_reads_name_version_and_requirements():
    contract = parse(GOOD)
    assert contract.name == "example_handover"
    assert contract.version == "1.2.0"
    assert len(contract.requirements) == 1
    assert contract.requirements[0].severity == "refuse"


def test_checksum_changes_with_any_edit():
    assert parse(GOOD).checksum != parse(GOOD.replace("1.2.0", "1.2.1")).checksum


def test_summary_includes_every_message():
    """A producing team reads this to check themselves before being checked,
    so no requirement may be abbreviated away."""
    contract = parse(GOOD)
    summary = contract.summary()
    for requirement in contract.requirements:
        assert requirement.message in summary
        assert requirement.name in summary


# --------------------------------------------------- what is refused, and why


@pytest.mark.parametrize(
    "broken,expect",
    [
        ("contract: x\nversion: 1\n", "no version"),  # a number is not a version
        ("version: 1.0.0\nrequires: []\n", "no contract name"),
        ("contract: x\nversion: '1'\nrequires: 3\n", "list of requirements"),
        ("[]", "set of named values"),
        ("contract: x\nversion: '1'\nwibble: 2\n", "does not understand"),
    ],
)
def test_a_contract_that_makes_no_sense_is_refused(broken, expect):
    with pytest.raises(ContractError) as caught:
        parse(broken, source_path="thefile.yaml")
    assert expect in str(caught.value)
    assert "thefile.yaml" in str(caught.value)


def requirement_with(**over) -> str:
    fields = {
        "name": "a_rule",
        "applies_to": "root",
        "property": "name",
        "severity": "refuse",
        "message": '"a sentence"',
    }
    fields.update(over)
    body = "\n".join(f"    {k}: {v}" for k, v in fields.items())
    return f"contract: x\nversion: '1'\nrequires:\n  - \n{body}\n"


def test_unknown_severity_is_refused():
    with pytest.raises(ContractError) as caught:
        parse(requirement_with(severity="maybe"))
    assert "refuse" in str(caught.value) and "flag" in str(caught.value)


def test_a_requirement_with_no_message_is_refused():
    """A violation nobody can read is not worth raising."""
    with pytest.raises(ContractError) as caught:
        parse(requirement_with(message='""'))
    assert "no message" in str(caught.value)


def test_a_requirement_with_no_name_is_refused():
    with pytest.raises(ContractError):
        parse(requirement_with(name='""'))


def test_two_requirements_with_one_name_are_refused():
    doubled = (
        "contract: x\nversion: '1'\nrequires:\n"
        "  - name: same\n    applies_to: root\n    property: a\n"
        "    severity: flag\n    message: one\n"
        "  - name: same\n    applies_to: root\n    property: b\n"
        "    severity: flag\n    message: two\n"
    )
    with pytest.raises(ContractError) as caught:
        parse(doubled)
    assert "same" in str(caught.value)


def test_an_unknown_demand_is_refused():
    with pytest.raises(ContractError) as caught:
        parse(requirement_with(must="be plausible"))
    assert "be recorded" in str(caught.value)


def test_a_contract_may_not_instruct_a_model():
    """There is no field for prompt text, and an unknown field is an error
    rather than something quietly ignored.

    Section 10 of the specification gives the reasons. The one that matters
    most here: this service accepts a contract from the sender, so prompt text
    in a contract would mean the sender writing the model's instructions.
    """
    with pytest.raises(ContractError) as caught:
        parse(requirement_with(prompt='"always answer complete ends"'))
    assert "no field for instructing a model" in str(caught.value)


def test_nothing_in_a_contract_is_executed():
    """A contract that looks like code is text."""
    sneaky = requirement_with(message='"!!python/object/apply:os.system [\'echo hi\']"')
    contract = parse(sneaky)
    assert "python/object" in contract.requirements[0].message


# ----------------------------------------------------------------- registry


def test_registry_reads_the_shipped_contracts():
    registry = ContractRegistry.from_dir(CONTRACTS)
    assert len(registry) >= 1
    assert all(isinstance(c, Contract) for c in registry.list())


def test_registry_unknown_name_lists_the_known_ones():
    """The usual cause is a typo, so the error says what there is."""
    registry = ContractRegistry.from_dir(CONTRACTS)
    with pytest.raises(ContractNotFound) as caught:
        registry.get("desgin_to_build")
    assert "mixing_to_coating" in str(caught.value)


def test_registry_get_with_a_version_that_does_not_match():
    registry = ContractRegistry.from_dir(CONTRACTS)
    with pytest.raises(ContractNotFound):
        registry.get("mixing_to_coating", version="99.0.0")


def test_registry_checksum_changes_when_a_contract_changes(tmp_path):
    (tmp_path / "one.yaml").write_text(GOOD)
    before = ContractRegistry.from_dir(tmp_path).checksum()
    (tmp_path / "one.yaml").write_text(GOOD.replace("1.2.0", "1.3.0"))
    assert ContractRegistry.from_dir(tmp_path).checksum() != before


def test_two_files_defining_one_contract_are_refused(tmp_path):
    (tmp_path / "one.yaml").write_text(GOOD)
    (tmp_path / "two.yaml").write_text(GOOD)
    with pytest.raises(ContractError) as caught:
        ContractRegistry.from_dir(tmp_path)
    assert "two files" in str(caught.value)


def test_an_empty_folder_holds_no_contracts(tmp_path):
    registry = ContractRegistry.from_dir(tmp_path)
    assert len(registry) == 0
    with pytest.raises(ContractNotFound) as caught:
        registry.get("anything")
    assert "none at all" in str(caught.value)


def test_a_second_handover_needs_no_code():
    """The claim the whole design rests on.

    `coating_to_inspection` is a file somebody wrote. There is no class for it, no
    registration call, and no table mapping its name to anything. This test
    fails the day somebody adds one.
    """
    source = Path(__file__).resolve().parents[1] / "src"
    named_in_code = [
        path.name
        for path in source.rglob("*.py")
        if "coating_to_inspection" in path.read_text(encoding="utf-8")
    ]
    assert named_in_code == []

    registry = ContractRegistry.from_dir(CONTRACTS)
    contract = registry.get("coating_to_inspection")
    assert contract.requirements, "the contract was read but holds nothing"


def test_two_handovers_are_held_at_once():
    registry = ContractRegistry.from_dir(CONTRACTS)
    names = {c.name for c in registry.list()}
    assert {"mixing_to_coating", "coating_to_inspection"} <= names


def test_a_requirement_must_say_property_or_named_value_and_not_both():
    with pytest.raises(ContractError) as caught:
        parse(
            "contract: x\nversion: '1'\nrequires:\n"
            "  - name: a\n    applies_to: root\n    property: one\n"
            "    named_value: two\n    severity: flag\n    message: m\n"
        )
    assert "both or neither" in str(caught.value)


def test_a_requirement_saying_neither_is_refused():
    with pytest.raises(ContractError):
        parse(
            "contract: x\nversion: '1'\nrequires:\n"
            "  - name: a\n    applies_to: root\n"
            "    severity: flag\n    message: m\n"
        )
