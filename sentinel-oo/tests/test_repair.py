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
# A crate broken in a way no model can repair: it does not say which
# profile it follows. Used to show a flag never outranks a refusal.
MISSING_CONFORMSTO = BROKEN / "missing-conformsto"


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


def test_the_default_is_to_ask_the_model(writer, registry):
    """Changed on 11 November 2026. It used to be that no model was called
    unless a caller asked for one, and a capability that is off by default
    is a capability nobody uses.

    Turning it on is safe because of where the model sits, not because
    models are reliable: it is asked one question about a check that has
    already failed, and everything it answers goes back through the rules.
    The tests below are the ones that hold that in place.
    """
    engine = ScriptedEngine({"drying atmosphere": "dry"})
    run = service(writer, registry, engine).check(
        Crate.from_path(IN_PROSE), contract_name="mixing_to_coating"
    )
    assert engine.asked != [], "the model was not asked"
    # ACCEPTED_WITH_FLAGS rather than ACCEPTED since 11 November 2026: a
    # value a model recovered raises a flag. The handover goes through and
    # somebody is told to look.
    assert run.verdict.value == "ACCEPTED_WITH_FLAGS"


def test_a_budget_of_zero_still_asks_nothing(writer, registry):
    """The way to turn it off, for a caller that wants determinism."""
    engine = ScriptedEngine({"drying atmosphere": "dry"})
    run = service(writer, registry, engine).check(
        Crate.from_path(IN_PROSE), contract_name="mixing_to_coating",
        repair_budget=0,
    )
    assert engine.asked == []
    assert run.blessing.changes == ()


# -------------------------------------------------- the rules still rule


def test_a_value_that_satisfies_the_rules_is_kept(writer, registry):
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    assert run.verdict.value == "ACCEPTED_WITH_FLAGS"
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
    assert run.verdict.value == "ACCEPTED_WITH_FLAGS"
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


# ------------------------------------------------- the model over the network


class TestHttpEngine:
    """The engine a deployment actually uses.

    The model runs in its own container, which does not have to be on this
    machine, so this engine reaches it over the network rather than running
    a command. These tests never make a real request: every test in this
    suite runs with sockets disabled, so one that quietly needed a model
    would fail rather than pass on a machine that happens to have one
    running.
    """

    def engine(self, **kwargs):
        from sentinel_oo.engines import HttpEngine

        return HttpEngine(**kwargs)

    def test_it_reads_its_address_and_model_from_the_environment(self, monkeypatch):
        """So a deployment points at its own without anything being rebuilt."""
        monkeypatch.setenv("SENTINEL_MODEL_URL", "http://gpu-box.lan:11434")
        monkeypatch.setenv("SENTINEL_MODEL", "llama3.3:70b")
        e = self.engine()
        assert e.url == "http://gpu-box.lan:11434"
        assert e.model == "llama3.3:70b"
        assert "llama3.3:70b" in e.name and "gpu-box" in e.name

    def test_an_empty_address_means_no_model(self, monkeypatch):
        """A deliberate state rather than a failure."""
        monkeypatch.setenv("SENTINEL_MODEL_URL", "")
        e = self.engine()
        assert e.name == "none"
        assert e.available() is False
        assert e.ask("anything") == ""

    def test_a_model_that_is_not_there_answers_nothing(self):
        """Not an exception. A model being absent must never refuse a good
        crate, so being unreachable is reported the same way as finding
        nothing, which is a correct and expected answer."""
        e = self.engine(url="http://nowhere.invalid:11434")
        assert e.ask("anything") == ""
        assert e.available() is False

    def test_it_says_why_it_could_not_be_reached(self):
        """`GET /health` reports this, so a deployment that wanted a model
        and cannot reach one does not look like one that wanted none."""
        e = self.engine(url="http://nowhere.invalid:11434")
        e.available()
        assert e.last_error
        assert "Error" in e.last_error or "error" in e.last_error

    def test_a_trailing_slash_does_not_produce_a_double_one(self):
        e = self.engine(url="http://model:11434/")
        assert e.url == "http://model:11434"

    def test_an_unreachable_model_proposes_nothing_and_changes_no_verdict(
        self, writer, registry
    ):
        """The whole safety argument, with the engine a deployment uses."""
        run = run_on(IN_PROSE, writer, registry,
                     self.engine(url="http://nowhere.invalid:11434"))
        assert run.verdict.value == "REFUSED"
        assert run.blessing.changes == ()


# ------------------------------------------- what the record says happened


class TestTheRecordSaysWhatHappened:
    """Finding 26 of the deployment trial, 11 November 2026, and the worst
    of the 26.

    A crate was refused on a requirement marked `repairable`, so the model
    should have been asked. No model was reachable. The record written into
    the returned crate said:

        model engine: qwen2.5:14b at http://model:11434
        ... Verdict: REFUSED. 1 finding(s), 0 change(s).

    Anybody reading that later concludes a model looked for the value and
    found nothing. No model was reached and the sentence holding the value
    was never read. The record misstated what happened, in the place this
    service exists to produce and asks people to trust.

    Four states, and the old record could say only one of them.
    """

    def test_no_model_configured(self, writer, registry):
        run = run_on(IN_PROSE, writer, registry, NullEngine())
        assert run.blessing.model_text() == "none configured"

    def test_a_model_that_could_not_be_reached_says_so(self, writer, registry):
        """The fault itself. This is the line that was missing."""
        from sentinel_oo.engines import HttpEngine

        run = run_on(IN_PROSE, writer, registry,
                     HttpEngine(url="http://nowhere.invalid:11434"))
        said = run.blessing.model_text()

        assert "NOT REACHED" in said
        assert "nowhere.invalid" in said
        # It says why, and what follows from it, so a reader is not left to
        # work out whether the value was looked for.
        assert "URLError" in said or "Error" in said
        assert "No value was recovered from free text" in said

    def test_it_reaches_the_crate_and_not_only_the_terminal(self, writer, registry):
        """deploy.py warned about this once, at start-up, and that warning
        is in no record. The record is the durable thing."""
        from sentinel_oo.engines import HttpEngine

        run = run_on(IN_PROSE, writer, registry,
                     HttpEngine(url="http://nowhere.invalid:11434"))
        assert "NOT REACHED" in run.crate.to_json()

    def test_reachable_but_never_asked_is_a_different_state(self, writer, registry):
        """A model can be there and not asked, because no failing
        requirement was marked repairable. That is a good run, and it must
        not read like a model that looked and found nothing."""
        engine = ScriptedEngine({})
        engine.available = lambda: True
        run = service(writer, registry, engine).check(
            Crate.from_path(BROKEN / "missing-conformsto"),
            contract_name="mixing_to_coating",
        )
        said = run.blessing.model_text()
        assert "not asked" in said
        assert "no failing requirement was marked repairable" in said

    def test_asked_and_kept_nothing_is_not_the_same_as_not_asked(
        self, writer, registry
    ):
        """The distinction the count exists for. A model that answered
        wrongly was asked; a model that was never consulted was not."""
        engine = ScriptedEngine({"drying atmosphere": "humid"})
        engine.available = lambda: True
        run = run_on(IN_PROSE, writer, registry, engine)

        said = run.blessing.model_text()
        assert "asked once" in said
        assert "0 change(s) kept" in said
        assert run.verdict.value == "REFUSED"

    def test_asked_and_kept_something(self, writer, registry):
        engine = ScriptedEngine({"drying atmosphere": "dry"})
        engine.available = lambda: True
        run = run_on(IN_PROSE, writer, registry, engine)
        assert "asked once, 1 change(s) kept" in run.blessing.model_text()


# ------------------------------------- a recovered value raises a flag
#
# Decided by Neil on 11 November 2026, after the test on a rented machine
# with graphics hardware showed a crate going from REFUSED to ACCEPTED with
# nothing in the verdict saying a model had supplied the missing value.


def test_a_recovered_value_raises_exactly_one_flag(writer, registry):
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    flags = [v for v in run.blessing.violations
             if v.severity.value == "flag"]
    assert len(flags) == 1, [v.requirement.name for v in flags]
    assert len(run.blessing.changes) == 1


def test_the_flag_names_the_model_the_value_and_the_rule(writer, registry):
    """A person reading the flag can tell what was supplied, by what, and
    what checked it, without opening the crate."""
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    flag = [v for v in run.blessing.violations
            if v.severity.value == "flag"][0]
    assert "drying atmosphere" in flag.message
    assert "'dry'" in flag.message
    assert "scripted" in flag.message
    assert "drying_atmosphere_is_recorded" in flag.message
    assert flag.value == "dry"


def test_the_flag_does_not_block_the_handover(writer, registry):
    """A flag means look, not stop. The command line's exit code and the
    report's own test of whether the handover may proceed must both say so."""
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    assert run.verdict.value != "REFUSED"


def test_no_recovery_means_no_flag(writer, registry):
    """With no model, nothing is recovered, so nothing is flagged. The
    verdict is whatever the rules alone decided."""
    run = run_on(IN_PROSE, writer, registry, ScriptedEngine({}))
    assert run.blessing.changes == ()
    assert [v for v in run.blessing.violations
            if v.severity.value == "flag"] == []
    assert run.verdict.value == "REFUSED"


def test_a_crate_still_broken_stays_refused(writer, registry):
    """One value recovered does not rescue a crate that fails something
    else. A flag never outranks a refusal."""
    run = run_on(MISSING_CONFORMSTO, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    assert run.verdict.value == "REFUSED"


def test_the_flag_is_written_into_the_checked_crate(writer, registry):
    """The crate is the lasting record, so the flag has to be in it and not
    only in the reply a caller happened to read at the time."""
    run = run_on(IN_PROSE, writer, registry,
                 ScriptedEngine({"drying atmosphere": "dry"}))
    text = run.crate.to_json()
    assert "recovered by a model" in text
