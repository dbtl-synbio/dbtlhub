"""The repair path: sections 16.8 and 16.9 of the specification.

A model is given a check that has already failed, at a place the rules named,
and asked whether the value is already written down somewhere. Everything it
answers is checked by the rules before it counts.

Every test here uses a stub model that answers from a dictionary, so the
results are the same on every machine and every run, with no model installed.
What a real model actually does with this task is a separate question, and
the answer on 10 November 2026 is recorded in the README: it could not do it.
"""

from __future__ import annotations

import json

import pytest

from sentinel_oo import (
    BuildIdentity,
    CommandEngine,
    Crate,
    NullEngine,
    ProvenanceWriter,
    ScriptedEngine,
    Sentinel,
)
from sentinel_oo.contract import ContractRegistry
from sentinel_oo.engines import build_prompt, permitted_values, read_answer
from sentinel_oo.rules import ContractChecks

from conftest import BROKEN, CONTRACTS

IN_PROSE = BROKEN / "atmosphere-in-prose"
NOTHING_SAYS = BROKEN / "missing-atmosphere"


@pytest.fixture
def registry():
    return ContractRegistry.from_dir(CONTRACTS)


@pytest.fixture
def contract(registry):
    return registry.get("mixing_to_coating")


def service(writer, registry, engine):
    return Sentinel(
        provenance=writer,
        rules=ContractChecks(),
        registry=registry,
        engine=engine,
        build=BuildIdentity("test", "0000000", "none"),
    )


def run_on(path, writer, registry, engine, budget=1):
    return service(writer, registry, engine).check(
        Crate.from_path(path), contract_name="mixing_to_coating",
        repair_budget=budget,
    )


# ------------------------------------------------------------- the budget


def test_no_budget_means_the_model_is_never_asked(writer, registry):
    """Not "asked and ignored". Never asked at all."""
    engine = ScriptedEngine({"drying atmosphere": "dry"})
    run = run_on(IN_PROSE, writer, registry, engine, budget=0)
    assert engine.asked == []
    assert run.verdict.value == "REFUSED"


def test_a_budget_of_one_makes_at_most_one_change(writer, registry):
    engine = ScriptedEngine({"drying atmosphere": "dry"})
    run = run_on(IN_PROSE, writer, registry, engine, budget=1)
    assert len(run.blessing.changes) == 1


def test_the_default_is_no_repair_at_all(writer, registry):
    engine = ScriptedEngine({"drying atmosphere": "dry"})
    run = service(writer, registry, engine).check(
        Crate.from_path(IN_PROSE), contract_name="mixing_to_coating"
    )
    assert engine.asked == []
    assert run.blessing.changes == ()


# -------------------------------------------------- the rules still rule


def test_a_value_that_satisfies_the_rules_is_kept(writer, registry):
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    assert run.verdict.value == "ACCEPTED"
    change = run.blessing.changes[0]
    assert change.after == "dry"
    assert change.proposed_by == "scripted"
    assert change.confirmed_by == "drying_atmosphere_is_recorded"


def test_a_wrong_value_is_discarded(writer, registry):
    """The model says the opposite of the truth. Nothing is written.

    A real local model did exactly this, on a real deployment's crate rather
    than on this worked example. On 10 November 2026 `qwen2.5:14b`, a model
    with 14 billion parameters running locally, was told what the gene
    calling flag meant and asked only to apply it to a command line
    containing that flag. It answered with the opposite value. The record of
    that measurement is in sentinel-oo/README.md, and the value here is the
    same mistake in this example's vocabulary: "humid" where the command
    line says dry.
    """
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "humid"}))
    assert run.verdict.value == "REFUSED"
    assert run.blessing.changes == ()
    assert "humid" not in _recovered_values(run.crate)


def test_a_value_in_the_wrong_words_is_discarded(writer, registry):
    """Answering with the flag itself rather than what it means."""
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "--atmosphere dry"}))
    assert run.blessing.changes == ()
    assert "--atmosphere dry" not in _recovered_values(run.crate)


def test_a_proposal_must_satisfy_every_rule_about_that_value(writer, registry):
    """Found by running it.

    Checking only the requirement being repaired let a value through that
    satisfied "must be recorded" and failed "must be one of these". The
    handover was refused and the invented phrase was written into the crate
    anyway. A refusal carrying a fabricated value is worse than a refusal.
    """
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "whatever it felt like"}))
    assert run.verdict.value == "REFUSED"
    assert "whatever it felt like" not in run.crate.to_json()


def test_answering_nothing_is_a_correct_answer(writer, registry):
    run = run_on(IN_PROSE, writer, registry, ScriptedEngine({}))
    assert run.blessing.changes == ()
    assert run.verdict.value == "REFUSED"


def test_a_value_that_is_not_there_is_not_invented(writer, registry):
    """The crate says nothing at all about the drying atmosphere. A model that
    answers anyway must not be believed, and here it cannot be: the value
    would have to satisfy the rules, and it does, which is the uncomfortable
    case. What protects the record is that the crate says the value was
    recovered rather than stated."""
    run = run_on(NOTHING_SAYS, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    assert run.verdict.value == "ACCEPTED"
    change = run.blessing.changes[0]
    assert "recovered" in change.describe() or change.before is None
    assert "Recovered from the text" in run.crate.to_json()


# -------------------------------------------------- what reaches the crate


def _recovered_values(crate) -> str:
    return json.dumps([
        dict(e) for e in crate
        if "recovered" in str(e.get("name", "")).lower()
    ])


def test_the_crate_says_the_value_was_recovered_not_stated(writer, registry):
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    body = run.crate.to_json()
    assert "Recovered from the text" in body
    assert "recovered: drying atmosphere" in body


def test_the_crate_records_which_engine_proposed_it(writer, registry):
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    assert "proposed by scripted" in run.crate.to_json()
    assert run.blessing.engine_used == "scripted"


def test_a_run_with_no_model_says_so_in_the_crate(writer, registry):
    run = run_on(IN_PROSE, writer, registry, NullEngine())
    assert run.blessing.engine_used == "none"


# -------------------------------------------------------------- the prompt


def test_the_prompt_carries_what_the_contract_permits(contract):
    """Without this the model guesses at the vocabulary, and a right answer
    in the wrong words is thrown away."""
    crate = Crate.from_path(IN_PROSE)
    violation = next(
        v for v in ContractChecks().validate(crate, contract).violations
        if v.requirement.repairable
    )
    prompt = build_prompt(crate, violation, contract)
    assert "dry" in prompt
    assert "Answering nothing is correct and expected" in prompt
    # The record itself is shown, including the free text holding the answer.
    assert "--atmosphere dry" in prompt


def test_permitted_values_are_gathered_from_the_whole_contract(contract):
    """The requirement being repaired says only that the value must be
    recorded. A second requirement about the same value says which words
    mean anything, and the model needs both."""
    repairable = next(r for r in contract.requirements if r.repairable)
    assert repairable.one_of is None
    assert "dry" in permitted_values(repairable, contract)


def test_the_prompt_is_the_same_whatever_the_contract_says(contract):
    """Contract text fills labelled slots. It never becomes an instruction."""
    crate = Crate.from_path(IN_PROSE)
    violation = next(
        v for v in ContractChecks().validate(crate, contract).violations
        if v.requirement.repairable
    )
    prompt = build_prompt(crate, violation, contract)
    instructions = prompt.split("The record:")[0].splitlines()
    # Everything from the contract sits after a label on its own line.
    for line in instructions:
        if line.strip() and ":" not in line:
            assert line.strip() in ("A check failed on a laboratory record.",)


# --------------------------------------------------- reading what came back


@pytest.mark.parametrize(
    "said,expected",
    [
        ('{"value": "dry"}', "dry"),
        ('  {"value":"dry"}  \n', "dry"),
        ('Here you go:\n```json\n{"value": "dry"}\n```', "dry"),
        ("{}", None),
        ('{"value": ""}', None),
        ('{"value": null}', None),
        ("I could not find it.", None),
        ("", None),
        ("   ", None),
        ('{"value": "dry", "why": "the -c flag"}', "dry"),
    ],
)
def test_an_answer_is_read_out_of_whatever_the_model_said(said, expected):
    """Small models wrap output, add prose and fence it in backticks. None of
    that is an error worth raising."""
    assert read_answer(said) == expected


def test_a_model_that_fails_proposes_nothing():
    """A model being slow, broken or absent must never refuse a good crate."""
    engine = CommandEngine(model="nothing", command=["this-command-does-not-exist"])
    assert engine.ask("anything") == ""


def test_a_model_that_is_not_installed_does_not_raise(writer, registry):
    engine = CommandEngine(model="nothing", command=["this-command-does-not-exist"])
    run = run_on(IN_PROSE, writer, registry, engine)
    assert run.verdict.value == "REFUSED"
    assert run.blessing.changes == ()
