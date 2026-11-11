"""Section 16.1 of the specification.

These are not ordinary tests. Each one encodes a decision, and each exists
because that kind of decision decays quietly: nothing visibly breaks, and six
weeks later the property is gone.

The comment above each one says which decision it protects. Nobody should
delete one without reading that first.

Only the invariants that step 1 of the build order can reach are here. The
rest arrive with the collaborators they guard.
"""

from __future__ import annotations

from pathlib import Path

from sentinel_oo import Crate



SRC = Path(__file__).resolve().parents[1] / "src"


# Decision: `Crate` is immutable; changes produce a new one.
# Why it matters: the crate that arrived still exists at the end, so you can
# show what was sent, and the recorded checksum of the input stays correct
# without anybody having to remember it separately.
# How it would break: an in-place edit added for performance.
def test_crate_is_immutable_under_every_write(published, sentinel):
    before = published.checksum()
    before_length = len(published)
    for _ in range(3):
        sentinel.check(published)
    assert published.checksum() == before
    assert len(published) == before_length


# Decision: the recorded checksum is of the crate as received.
# Why it matters: taken at any later moment it would describe something the
# sender never sent, and a reader could no longer tell whether what was
# blessed has since been altered.
# How it would break: the checksum gets taken at the convenient moment rather
# than the correct one.
def test_input_checksum_is_of_what_arrived(published, sentinel):
    run = sentinel.check(published)
    assert run.blessing.input_checksum == published.checksum()
    assert run.blessing.input_checksum != run.crate.checksum()


# Decision: the orchestrator holds no rule of its own.
# Why it matters: exactly one component may decide whether a package is
# acceptable, and it is not this one.
# How it would break: somebody adds "just one" check to the orchestrator.
# At step 1 there is no rule engine yet, so what is asserted is the weaker
# thing that can be asserted now: the orchestrator reaches no verdict.
def test_orchestrator_reaches_no_verdict(published, sentinel):
    run = sentinel.check(published)
    assert run.verdict is None, (
        "the orchestrator produced a verdict with no rule engine present"
    )


# Decision: a handover is data, not code.
# Why it matters: adding a handover must mean writing a contract file, never
# writing code inside this service and merging it.
# How it would break: one small special case, then another.
# The product's own example contracts, and the four DBTL handovers that
# deployments of it are expected to carry. None of them may appear in the
# service source. The DBTL names are listed even though no deployment of
# them lives in this folder, because those are the names somebody in a hurry
# would be tempted to special-case.
HANDOVER_NAMES = (
    "mixing_to_coating",
    "coating_to_inspection",
    "design_to_build",
    "build_to_test",
    "test_to_learn",
    "learn_to_design",
)


def test_no_handover_name_in_source():
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for name in HANDOVER_NAMES:
            if name in text:
                offenders.append(f"{path.name}: {name}")
    assert offenders == [], (
        "a handover is named in the source. It belongs in a contract file: "
        + ", ".join(offenders)
    )


# Decision: core must not import a use case.
# Why it matters: this is the exact fault that stops one team using another
# team's handover, found in the framework this design departs from.
# How it would break: a convenience import added while in a hurry.
#
# The names below are every folder outside the product that holds use case
# material: a tailored deployment, and the demonstration's simulator of the
# downstream workflow. The product may be imported by any of them. None of
# them may be imported by the product.
NOT_THE_PRODUCT = (
    "usecase",
    "deployments",
    "demonstration",
    "simulate_downstream",
    "make_order",
)


def test_source_imports_no_use_case():
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for name in NOT_THE_PRODUCT:
                if name in stripped:
                    offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], "core imports a use case: " + ", ".join(offenders)


# Decision: the product can be checked out and tested standing alone.
# Why it matters: this is the whole of what makes it a product rather than
# one team's code. Somebody must be able to take `sentinel-oo/`, run its
# tests, build its image and deploy it against their own contracts, with
# none of this repository's other folders present.
# How it would break: it already did. Until 11 November 2026 the fixtures
# read crates from deployments/bioprospecting, two directory levels up, and
# nothing noticed because no test watched that boundary.
def test_fixtures_stay_inside_the_product():
    """Every path a test file holds must resolve inside sentinel-oo/.

    What this checks is the paths held as module level values in the test
    modules, which is where fixture locations are declared. A path built
    inside a function body would not be caught, so this is a guard on the
    normal way of doing it rather than a proof that no path can escape.

    Two limitations, found by planting a leak in another test file on
    11 November 2026 and watching what happened.

    It only sees modules that have been imported, so it catches a leak when
    the whole suite runs and misses one when a single file is run on its
    own. Running this test alone gives a false pass.

    It reports the module, the attribute and the resolved path, which is
    what makes a failure actionable rather than merely red.
    """
    import sys
    from pathlib import Path

    product = SRC.parent
    offenders = []

    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None) or ""
        if "/tests/" not in where.replace("\\", "/"):
            continue
        for attribute, value in vars(module).items():
            if not isinstance(value, Path):
                continue
            resolved = value.resolve()
            if resolved != product and product not in resolved.parents:
                offenders.append(f"{name}.{attribute} = {resolved}")

    assert offenders == [], (
        "a test resolves a path outside the product, so the product cannot "
        "be tested on its own: " + ", ".join(sorted(offenders))
    )


# Decision: it runs with nothing installed and nothing configured.
# Why it matters: the default path calls no model, needs no key and reaches no
# network. The conftest fixture makes any socket use fail, so this test passing
# with that fixture active is the assertion.
# How it would break: a convenience default that quietly needs a key.
def test_no_network_when_no_model_is_configured(published, writer):
    """Rewritten on 11 November 2026, when the model became the default.

    The old version checked a crate with no contract, so the repair path
    was never entered and the engine was never called. It passed for a
    reason that had nothing to do with what it claimed.

    What is true now: a service told to use no model touches no network,
    and every test in this suite runs with sockets disabled, so a test that
    quietly needed one would fail rather than pass on a machine that
    happens to have a model running.
    """
    from conftest import CONTRACTS, a_sentinel
    from sentinel_oo.contract import ContractRegistry
    from sentinel_oo.engines import NullEngine
    from sentinel_oo.rules import ContractChecks

    service = a_sentinel(writer, rules=ContractChecks(),
                         registry=ContractRegistry.from_dir(CONTRACTS))
    service.engine = NullEngine()
    run = service.check(published, contract_name="mixing_to_coating")
    assert run.crate is not None
    assert run.blessing.engine_used == "none"


# Decision: the returned crate is still a valid crate.
# Why it matters: writing the record must not break the thing it is written
# into. Full validation against the profile arrives with the validator at a
# later step; what can be asserted now is that the result reloads.
# How it would break: a record written with a malformed reference.
def test_returned_crate_reloads(published, sentinel, tmp_path):
    run = sentinel.check(published)
    written = run.crate.save(tmp_path)
    again = Crate.from_path(written)
    assert again.checksum() == run.crate.checksum()


# Decision: every reference in the record points at something that exists.
# Why it matters: a dangling reference is one of the faults no validator
# catches, and the service must not add one.
# How it would break: an identifier built two different ways in two places.
#
# Only references inside the crate are checked. A reference to a web address
# such as a schema.org action status or a licence names a term defined
# elsewhere and is not expected to be an entity here.
def test_record_has_no_dangling_local_references(published, sentinel):
    run = sentinel.check(published)
    present = {e["@id"] for e in run.crate}
    missing = []

    def visit(value):
        if hasattr(value, "keys"):
            keys = set(value.keys())
            if keys == {"@id"}:
                target = value["@id"]
                external = target.startswith(("http://", "https://"))
                if not external and target not in present:
                    missing.append(target)
            else:
                for inner in value.values():
                    visit(inner)
        elif isinstance(value, (list, tuple)):
            for inner in value:
                visit(inner)

    visit(run.crate.get(f"#sentinel-oo/run/{run.id}"))
    visit(run.crate.root["mentions"])
    assert missing == [], f"the record points at entities that do not exist: {missing}"


# ---------------------------------------------------------------- step 2
# These became reachable when a rule engine arrived. Each guards a decision
# from section 12 of the specification.


# Decision: exactly one component decides whether a package is acceptable.
# Why it matters: if anything else can reach a verdict, there are two deciders
# and they will eventually disagree.
# How it would break: somebody recomputes the verdict downstream from the
# findings, or adds "just one" check to the orchestrator.
def test_only_the_rule_engine_sets_the_verdict(published, writer):
    from conftest import AlwaysAccepts, AlwaysRefuses, a_sentinel

    from sentinel_oo import Verdict

    from conftest import CONTRACTS
    from sentinel_oo.contract import ContractRegistry

    held = ContractRegistry.from_dir(CONTRACTS)
    refusing = a_sentinel(writer, rules=AlwaysRefuses(), registry=held)
    accepting = a_sentinel(writer, rules=AlwaysAccepts(), registry=held)

    # The published crate is good. It must still be refused, because the thing
    # that decides said so.
    assert refusing.check(published, 'mixing_to_coating').verdict is Verdict.REFUSED
    assert accepting.check(published, 'mixing_to_coating').verdict is Verdict.ACCEPTED


# Decision: a refusal still returns a crate.
# Why it matters: a refusal that exists only as an error message in somebody's
# terminal is not a record. The refused crate is the artefact you want when
# asked in a year why a batch never went to synthesis.
# How it would break: an exception handler added around the failure path.
def test_refusal_returns_a_crate(published, writer, tmp_path):
    from conftest import AlwaysRefuses, a_sentinel

    from sentinel_oo import Crate, Verdict

    from conftest import CONTRACTS
    from sentinel_oo.contract import ContractRegistry

    run = a_sentinel(
        writer, rules=AlwaysRefuses(),
        registry=ContractRegistry.from_dir(CONTRACTS),
    ).check(published, 'mixing_to_coating')

    assert run.verdict is Verdict.REFUSED
    assert run.crate is not None

    # It is a real crate: it writes out and reads back.
    again = Crate.from_path(run.crate.save(tmp_path))
    assert len(again) > len(published)

    # And it says why it was refused, in words.
    values = " ".join(
        str(e.get("value", "")) for e in again if e.get("@type") == "PropertyValue"
    )
    assert "refuses everything" in values


# Decision: a refused handover is recorded as a failed action.
# Why it matters: a reader scanning the crate for what happened must be able to
# see that this check did not pass, without reading the verdict text.
# How it would break: the status gets written from a default.
def test_refusal_is_recorded_as_a_failed_action(published, writer):
    from conftest import AlwaysRefuses, a_sentinel

    from sentinel_oo.provenance import FAILED

    from conftest import CONTRACTS
    from sentinel_oo.contract import ContractRegistry

    run = a_sentinel(
        writer, rules=AlwaysRefuses(),
        registry=ContractRegistry.from_dir(CONTRACTS),
    ).check(published, 'mixing_to_coating')
    action = run.crate.get(f"#sentinel-oo/run/{run.id}")
    assert action["actionStatus"]["@id"] == FAILED


# Decision: the record names every finding, not only the verdict.
# Why it matters: "refused" with no reason sends somebody back to a 46 kilobyte
# file to guess. The sentence the rule author wrote is the whole point of
# writing it.
# How it would break: the findings get summarised into a count.
def test_every_finding_reaches_the_crate(published, writer):
    from conftest import AlwaysRefuses, a_sentinel

    from conftest import CONTRACTS
    from sentinel_oo.contract import ContractRegistry

    run = a_sentinel(
        writer, rules=AlwaysRefuses(),
        registry=ContractRegistry.from_dir(CONTRACTS),
    ).check(published, 'mixing_to_coating')
    recorded = [
        e for e in run.crate
        if e.get("@type") == "PropertyValue"
        and str(e.get("name", "")).startswith("refuse:")
    ]
    assert len(recorded) == len(run.blessing.violations) == 1


# ---------------------------------------------------------------- step 5


# Decision: two ways in, one decision.
# Why it matters: the web interface and the agent interface are both thin
# adapters over the same orchestrator. If either ever reaches a verdict of its
# own, there are two things deciding and they will eventually disagree.
# How it would break: somebody adds a shortcut to one of them.
def test_both_interfaces_give_the_same_verdict(writer, tmp_path):
    import json

    from conftest import BROKEN, CONTRACTS, PUBLISHED
    from sentinel_oo import BuildIdentity, RunStore, Sentinel
    from sentinel_oo.agent_interface import AgentInterface
    from sentinel_oo.api import Api
    from sentinel_oo.contract import ContractRegistry
    from sentinel_oo.rules import ContractChecks

    def zipped(folder):
        """The crate as a handover is: its description and its data.

        Restated on 12 November 2026, when the web interface learned to
        carry a whole crate. The two interfaces agree when given the SAME
        crate. A bare ro-crate-metadata.json is not the same crate as a
        folder with data in it, and a contract that checks the data is
        right to tell them apart.
        """
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in sorted(Path(folder).iterdir()):
                if path.is_file():
                    archive.write(path, path.name)
        return buffer.getvalue()

    def service():
        return Sentinel(
            provenance=writer,
            rules=ContractChecks(),
            registry=ContractRegistry.from_dir(CONTRACTS),
            build=BuildIdentity("test", "0000000", "none"),
        )

    for label, folder in [
        ("good", PUBLISHED.parent),
        ("broken", BROKEN / "dangling-reference"),
    ]:
        over_http = Api(service(), RunStore(5)).dispatch(
            "POST", "/check/mixing_to_coating", zipped(folder),
        )[1]
        to_an_agent = AgentInterface(service(), RunStore(5)).check_handover(
            "mixing_to_coating", str(folder), str(tmp_path / label)
        )

        assert over_http.verdict == to_an_agent["verdict"], label
        assert over_http.findings == len(to_an_agent["findings"]), label


# Decision: the agent interface never returns the crate.
# Why it matters: a crate is tens of kilobytes of JSON. Handing one to a
# coordinator spends its context and tells it nothing it can act on.
# How it would break: somebody adds it "just for debugging".
def test_the_agent_interface_returns_no_crate(writer, tmp_path):
    import json

    from conftest import CONTRACTS, PUBLISHED
    from sentinel_oo import BuildIdentity, RunStore, Sentinel
    from sentinel_oo.agent_interface import AgentInterface
    from sentinel_oo.contract import ContractRegistry
    from sentinel_oo.rules import ContractChecks

    agent = AgentInterface(
        Sentinel(
            provenance=writer,
            rules=ContractChecks(),
            registry=ContractRegistry.from_dir(CONTRACTS),
            build=BuildIdentity("test", "0000000", "none"),
        ),
        RunStore(5),
    )
    answer = agent.check_handover(
        "mixing_to_coating", str(PUBLISHED.parent), str(tmp_path)
    )
    assert "@graph" not in json.dumps(answer)


# ---------------------------------------------------------------- step 6


# Decision: the model decides nothing.
# Why it matters: it is the claim people will doubt, and the one that makes
# the difference between a checking service and a guess.
# How it would break: somebody lets a proposal through without re-checking.
def test_the_verdict_is_the_same_with_a_model_and_without(writer):
    """Where nothing needs recovering, a model must change no outcome."""
    from conftest import CONTRACTS, PUBLISHED
    from sentinel_oo import (BuildIdentity, NullEngine, ScriptedEngine,
                             Sentinel)
    from sentinel_oo.contract import ContractRegistry
    from sentinel_oo.rules import ContractChecks

    registry = ContractRegistry.from_dir(CONTRACTS)

    def verdict(engine):
        s = Sentinel(provenance=writer, rules=ContractChecks(),
                     registry=registry, engine=engine,
                     build=BuildIdentity("test", "0", "none"))
        return s.check(Crate.from_path(PUBLISHED.parent),
                       contract_name="mixing_to_coating",
                       repair_budget=5).verdict

    talkative = ScriptedEngine({
        "drying atmosphere": "open",
        "partial": "11",
        "film thickness": "999999",
        "name": "something else entirely",
    })
    assert verdict(NullEngine()) == verdict(talkative)


# Decision: the model never sees a violation that must not be repaired.
# Why it matters: filtering after the call rather than before it would mean a
# model being asked to fix something that must never be fixed, and only the
# discipline of the code stopping it.
# How it would break: the filter moves inside the loop that applies changes.
def test_the_model_is_never_asked_about_what_must_not_be_repaired(writer):
    from conftest import BROKEN, CONTRACTS
    from sentinel_oo import BuildIdentity, ScriptedEngine, Sentinel
    from sentinel_oo.contract import ContractRegistry
    from sentinel_oo.rules import ContractChecks

    registry = ContractRegistry.from_dir(CONTRACTS)
    contract = registry.get("mixing_to_coating")
    engine = ScriptedEngine({})

    Sentinel(provenance=writer, rules=ContractChecks(), registry=registry,
             engine=engine, build=BuildIdentity("test", "0", "none")).check(
        Crate.from_path(BROKEN / "dangling-reference"),
        contract_name="mixing_to_coating", repair_budget=10)

    repairable = {r.name for r in contract.requirements if r.repairable}
    asked_about = {a.split("@")[0] for a in engine.asked}
    assert asked_about <= repairable, (
        f"the model was asked about {asked_about - repairable}, which the "
        "contract does not allow to be repaired"
    )


# Decision: nothing is invented.
# Why it matters: a refusal carrying a fabricated value is worse than a
# refusal, because the fabrication stays in the record.
# How it would break: a change is kept because the rule it targeted passed,
# while another rule about the same value still fails.
def test_a_discarded_proposal_leaves_no_trace(writer):
    from conftest import BROKEN, CONTRACTS
    from sentinel_oo import BuildIdentity, ScriptedEngine, Sentinel
    from sentinel_oo.contract import ContractRegistry
    from sentinel_oo.rules import ContractChecks

    registry = ContractRegistry.from_dir(CONTRACTS)
    run = Sentinel(
        provenance=writer, rules=ContractChecks(), registry=registry,
        engine=ScriptedEngine({"drying atmosphere": "a plausible sounding lie"}),
        build=BuildIdentity("test", "0", "none"),
    ).check(Crate.from_path(BROKEN / "atmosphere-in-prose"),
            contract_name="mixing_to_coating", repair_budget=3)

    assert run.blessing.changes == ()
    assert "a plausible sounding lie" not in run.crate.to_json()
