#!/usr/bin/env python3
"""The checks this framework had not run on itself.

    python3 tests/test_framework.py

No pytest, no dependencies. Every test here locks in behaviour that was
verified by hand at some point and could silently stop being true - which is
exactly what happened: a contract change passed its own demo and broke another
one, and the only reason nobody noticed is that the demo still exited 0.

Three of these would have caught a real defect found by audit:

    test_profile_units_are_coherent   a predicted quantity in g/L against a
                                      measurement in mg/L, inside one profile
    test_graph_query_reaches_ground   the traversal worked in memory and not
                                      on disk, because a predicate IRI was
                                      built by gluing strings
    test_demos_report_the_right_verdicts
                                      a demo that fails but exits 0
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.crate_store import CrateStore                          # noqa: E402
from framework.llm import Patch, RulesEngine                          # noqa: E402
from framework.validator import load_contract, validate               # noqa: E402

PROFILES = ROOT / "framework" / "contracts" / "profiles"
CONTRACTS = ROOT / "framework" / "contracts"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=300)


# --------------------------------------------------------------------------- #
class TestProfilesAndContracts(unittest.TestCase):

    def test_profile_units_are_coherent(self):
        """A prediction and the measurement meant to test it share a unit.

        This failed when it was written: biomanufacturing predicted a titre in
        g/L and measured it in mg/L, so a prediction could never be compared
        with the result that was supposed to check it.
        """
        for path in sorted(PROFILES.glob("*.json")):
            profile = json.loads(path.read_text())
            units = {}
            for handover in profile.get("required_quantities", {}).values():
                for req in handover:
                    units[req["quantity"]] = req.get("unit")
            for quantity, unit in units.items():
                if not quantity.startswith("predicted_"):
                    continue
                measured = quantity[len("predicted_"):]
                if measured in units:
                    self.assertEqual(
                        unit, units[measured],
                        f"{path.name}: {quantity} is in {unit!r} but "
                        f"{measured} is measured in {units[measured]!r}; a "
                        f"prediction that cannot be compared with its own "
                        f"measurement is not a prediction")

    def test_every_check_kind_is_implemented(self):
        from framework.validator import CHECKS
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            contract = json.loads(path.read_text())
            for check in contract.get("x-dbtl-checks", []):
                self.assertIn(check["kind"], CHECKS,
                              f"{path.name} asks for a check kind the "
                              f"validator does not implement")

    def test_every_check_is_blocking_or_says_why_not(self):
        """Nothing is auto-fixable by accident."""
        import importlib
        agents = [("framework.agents.sentinel_d2b", "DesignToBuildAgent"),
                  ("framework.agents.sentinel_b2t", "BuildToTestAgent"),
                  ("framework.agents.sentinel_t2l", "TestToLearnAgent"),
                  ("framework.agents.sentinel_l2d", "LearnToDesignAgent")]
        for module, cls_name in agents:
            agent = getattr(importlib.import_module(module), cls_name)()
            for check in agent.contract.get("x-dbtl-checks", []):
                code = check.get("code")
                blocked = (code in agent.never_autofix
                           or (check.get("fix_hint") or "")
                           .startswith("not auto-fixable"))
                self.assertTrue(blocked,
                                f"{agent.contract_name}: {code} may be "
                                f"patched and nothing says that was intended")

    def test_profiles_declare_the_same_handovers(self):
        names = {}
        for path in sorted(PROFILES.glob("*.json")):
            profile = json.loads(path.read_text())
            names[path.stem] = set(profile.get("required_quantities", {}))
        first = next(iter(names.values()))
        for name, keys in names.items():
            self.assertEqual(keys, first,
                             f"{name} covers {sorted(keys)}, another profile "
                             f"covers {sorted(first)}; a handover required by "
                             f"one use case and silent in another is a gap")


# --------------------------------------------------------------------------- #
class TestCrateStore(unittest.TestCase):
    """The three refusals that belong to a shared crate, not to any contract."""

    def setUp(self):
        self.run_id = "test-store"
        shutil.rmtree(ROOT / "runs" / self.run_id, ignore_errors=True)
        self.store = CrateStore(self.run_id)
        self.store.add("design", [
            {"@id": "#site/S1", "@type": "dwc:Location",
             "dwc:decimalLatitude": 53.4},
            {"@id": "#sample/A", "@type": "bioschemas:BioSample",
             "prov:wasDerivedFrom": {"@id": "#site/S1"}},
        ])

    def tearDown(self):
        shutil.rmtree(ROOT / "runs" / self.run_id, ignore_errors=True)

    def test_a_gap_may_be_filled(self):
        report = self.store.add("build", [
            {"@id": "#sample/A", "dwc:eventDate": "2026-04-12"}])
        self.assertTrue(report.ok)
        self.assertIn("#sample/A", report.extended)
        self.assertEqual(self.store.index["#sample/A"]["dwc:eventDate"],
                         "2026-04-12")

    def test_a_recorded_value_may_not_be_overwritten(self):
        report = self.store.add("build", [
            {"@id": "#site/S1", "dwc:decimalLatitude": 0.0}])
        self.assertFalse(report.ok)
        self.assertEqual(report.conflicts, ["#site/S1.dwc:decimalLatitude"])
        self.assertEqual(self.store.index["#site/S1"]["dwc:decimalLatitude"],
                         53.4, "the original value must survive a refusal")

    def test_one_id_for_two_things_is_a_collision(self):
        report = self.store.add("build", [
            {"@id": "#sample/B", "dbtl:storagePosition": "A1"},
            {"@id": "#sample/B", "dbtl:storagePosition": "A2"},
        ])
        self.assertFalse(report.ok)
        self.assertTrue(report.collisions)
        self.assertFalse(report.conflicts,
                         "a self-collision is not one phase overwriting another")

    def test_a_reference_to_nothing_is_refused(self):
        report = self.store.add("test", [
            {"@id": "#reading/R1", "prov:wasDerivedFrom": {"@id": "#sample/NOPE"}}])
        self.assertFalse(report.ok)
        self.assertTrue(report.dangling)
        self.assertNotIn("#reading/R1", self.store.index,
                         "nothing may be written when the addition is refused")


# --------------------------------------------------------------------------- #
class TestRepairIsConstrained(unittest.TestCase):

    def test_a_patch_outside_the_reported_paths_is_refused(self):
        """The guard that makes a model engine safe to offer at all."""
        from framework.agents.sentinel_b2t import BuildToTestAgent
        from framework.agents.base import Task
        from framework.llm import Engine

        class Hostile(Engine):
            name = "hostile"

            def propose_patches(self, package, report, contract):
                return [Patch(path="samples[0].location.position",
                              action="set_field", value="H12",
                              reason="moved it so the duplicate goes away")]

        agent = BuildToTestAgent(profile="bioprospecting", engine=Hostile())
        package = json.loads((ROOT / "tests" / "fixtures"
                              / "b2t_double_booked.json").read_text())
        before = package["samples"][0]["location"]["position"]
        result = agent.handle(Task(goal="check", inputs={"package": package},
                                   max_repairs=2))
        self.assertEqual(result.status, "escalated")
        self.assertEqual(package["samples"][0]["location"]["position"], before,
                         "the engine wrote where the validator never pointed")

    def test_rules_engine_invents_nothing(self):
        """It restores a unit the profile states, and nothing else."""
        contract = load_contract("build_to_test", profile="bioprospecting")
        package = json.loads((ROOT / "tests" / "fixtures"
                              / "b2t_missing_unit.json").read_text())
        report = validate(package, contract)
        patches = RulesEngine().propose_patches(package, report, contract)
        self.assertTrue(patches, "a dropped unit is derivable from the profile")
        for patch in patches:
            self.assertTrue(patch.path.endswith(".unit"),
                            f"the rules engine proposed {patch.path}, which is "
                            f"not something it can derive")


# --------------------------------------------------------------------------- #
class TestEndToEnd(unittest.TestCase):
    """Run the real scripts and read what they say, not what they exit with."""

    def assert_no_crash(self, done, what):
        self.assertNotIn("Traceback", done.stderr + done.stdout,
                         f"{what} crashed:\n{done.stderr[-1500:]}")

    def test_demos_report_the_right_verdicts(self):
        expected = {
            # four handovers, all clean
            "demo_cycle.py": ("-> PASS", 4),
            # the clean run ends OK after the one repair the contract allows
            "demo_d2b.py": ("[sentinel_d2b] -> OK", 1),
            # the round that closes
            "demo_l2d.py": ("[sentinel_l2d] -> OK", 1),
        }
        for script, (needle, least) in expected.items():
            done = run(script)
            self.assert_no_crash(done, script)
            self.assertGreaterEqual(
                done.stdout.count(needle), least,
                f"{script} no longer reports {least}x {needle!r}")

    def test_a_clean_run_has_no_failing_handover(self):
        """The regression that started this file: a contract change broke a
        demo's clean run and the demo still exited 0."""
        done = run("demo.py")
        self.assert_no_crash(done, "demo.py")
        clean = done.stdout.split("2. BROKEN RUN")[0]
        self.assertNotIn("-> FAIL", clean,
                         "the clean run reports a failing handover")
        self.assertNotIn("ESCALATED", clean,
                         "the clean run escalates")

    def test_the_broken_run_exercises_the_contract_checks(self):
        """A demo that stops before its own checks run demonstrates nothing.

        The crate store began refusing an identifier collision earlier than
        the validator, which silently stopped demo.py before Handover 2's
        cross-reference checks were ever reached. The faults are split so both
        layers are shown.
        """
        done = run("demo.py")
        self.assert_no_crash(done, "demo.py")
        for code in ("unknown_design_item", "unaccounted_item"):
            self.assertIn(code, done.stdout,
                          f"the broken run no longer reaches {code}")
        self.assertIn("share one @id", done.stdout,
                      "the collision refusal is no longer shown")

    def test_handover_one_accepts_the_published_crate(self):
        # Inside the repository the crate is a sibling of this framework;
        # in a working copy kept outside it, the clone is next door.
        candidates = [
            ROOT.parent / "bioprospecting" / "exampleROcrates" / "design-to-build-simple",
            ROOT.parent / "dbtlhub" / "bioprospecting" / "exampleROcrates" / "design-to-build-simple",
        ]
        crate = next((c for c in candidates if c.exists()), None)
        if crate is None:
            self.skipTest("the use case's crate is not checked out here")
        done = run("scripts/check_crate.py", "--break-all", str(crate))
        self.assert_no_crash(done, "check_crate.py")
        out = done.stdout
        self.assertIn("ACCEPTED", out, "the published crate is not accepted")
        self.assertEqual(out.count("REFUSED"), 3,
                         "all three injected faults must be refused")

    def test_graph_query_reaches_the_ground_on_disk(self):
        """In memory is not enough: the query reads the file."""
        run("demo_cycle.py")
        done = run("scripts/ask.py", "cycle", "--behind", "REC-001")
        self.assert_no_crash(done, "ask.py")
        self.assertIn("reaches the ground", done.stdout,
                      "the traversal does not reach a physical sample on disk")

    def test_the_chain_of_packages_resolves(self):
        run("demo_cycle.py")
        done = run("scripts/trace.py", "cycle")
        self.assert_no_crash(done, "trace.py")
        self.assertIn("CHAIN INTACT", done.stdout)
        self.assertEqual(done.returncode, 0)


class TestASentinelIsAFile(unittest.TestCase):
    """The claim the recipe in `template/MAKE_A_SENTINEL.md` makes.

    If a handover ever needs Python again, these fail and the recipe is a
    lie. That is the point of testing it rather than only writing it down.
    """

    HANDOVER = "coat_to_cure"

    def setUp(self):
        from framework.agents import sentinel as mod                # noqa: PLC0415
        self.mod = mod
        # Whichever dialect this machine can read. A sentinel is a file in
        # both, and on a clone without PyYAML the JSON twin is the only one
        # anything can open - so that is the one the claim has to hold for.
        try:
            import yaml                                    # noqa: F401,PLC0415
            name = f"{self.HANDOVER}.yaml"
        except ImportError:                                # pragma: no cover
            name = f"{self.HANDOVER}.schema.json"
        source = ROOT / "template" / "example" / name
        self.assertTrue(source.is_file(),
                        f"{source} is the worked example; if the twin is "
                        f"missing, run `python3 scripts/make_twins.py`")
        self.placed = mod.CONTRACTS / name
        self.placed.write_text(source.read_text())

    def tearDown(self):
        self.placed.unlink(missing_ok=True)

    def test_dropping_a_file_in_is_the_whole_installation(self):
        self.assertIn(self.HANDOVER, self.mod.known(),
                      "a contract on disk is not discovered, so a handover "
                      "still needs code")
        sentinel = self.mod.Sentinel(profile="bioprospecting")
        contract = sentinel.contract(self.HANDOVER)
        self.assertEqual(contract["$id"], "dbtl:coat_to_cure/0.1.0")

    def test_it_accepts_and_refuses_without_any_code_for_it(self):
        sentinel = self.mod.Sentinel(profile="bioprospecting")
        clean = {"contract": self.HANDOVER, "run_id": "r1",
                 "panels": [{"panel_id": "P1", "thickness_um": 42.0}]}
        clashing = {"contract": self.HANDOVER, "run_id": "r1",
                    "panels": [{"panel_id": "P1", "thickness_um": 42.0},
                               {"panel_id": "P1", "thickness_um": 9.0}]}
        self.assertEqual(sentinel.check(self.HANDOVER, clean).verdict,
                         "accepted")
        refused = sentinel.check(self.HANDOVER, clashing)
        self.assertEqual(refused.verdict, "refused")
        self.assertIn("duplicate_panel",
                      [e.code for e in refused.report.errors])

    def test_it_records_its_act_in_the_crate_like_any_other(self):
        sentinel = self.mod.Sentinel(profile="bioprospecting")
        package = {
            "contract": self.HANDOVER, "run_id": "r1",
            "panels": [{"panel_id": "P1"}, {"panel_id": "P1"}],
            "crate": {"@graph": [
                {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
                 "about": {"@id": "./"}},
                {"@id": "./", "@type": "Dataset"}]}}
        sentinel.check_and_record(self.HANDOVER, package)
        acts = [e for e in package["crate"]["@graph"]
                if str(e.get("@id", "")).startswith("#check/")
                and e.get("@type") == "CreateAction"]
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["dbtl:verdict"], "refused")
        self.assertEqual(acts[0]["dbtl:contract"], "dbtl:coat_to_cure/0.1.0")

    def test_a_malformed_check_is_a_finding_and_not_a_crash(self):
        """A contract author must not meet a traceback from inside this code.

        This is how it was found: a `unique` check written with `field`
        instead of `fields` raised KeyError out of the validator, so a run
        stopped having checked nothing and said nothing about the rest.
        """
        from framework.validator import validate                    # noqa: PLC0415
        broken = {"type": "object", "x-dbtl-checks": [
            {"kind": "unique", "of": "panels", "code": "no_fields_given"}]}
        report = validate({"panels": [{"panel_id": "P1"}]}, broken)
        self.assertIn("malformed_check", [e.code for e in report.errors])


class TestTheRing(unittest.TestCase):
    """The overview the whole interface is now built around.

    It reads the crate rather than the session, so the same drawing works for
    a run that finished yesterday. If that stops being true, looking at an
    old run shows an empty cycle and says nothing about it.
    """

    def crate(self):
        from framework.agents.sentinel import Sentinel, Checked   # noqa: PLC0415
        from framework.validator import Error, Report             # noqa: PLC0415
        crate = {"@graph": [
            {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
             "about": {"@id": "./"}},
            {"@id": "./", "@type": "Dataset"},
            {"@id": "#sample/SAMP-001", "@type": "bioschemas:BioSample"}]}
        Sentinel().record(crate, Checked(
            handover="design_to_build", contract_id="dbtl:design_to_build/0.1.0",
            profile="bioprospecting", verdict="refused",
            report=Report([Error("crate.@graph[#sample/SAMP-001].x",
                                 "missing_provenance", "m", "f", "error")]),
            held_to=("dbtl:design_to_build/0.1.0",
                     "sentinel-oo:design_to_build/0.11.0"),
            checks_applied=33))
        Sentinel().record(crate, Checked(
            handover="build_to_test", contract_id="dbtl:build_to_test/0.2.0",
            profile="bioprospecting", verdict="accepted", report=Report([]),
            checks_applied=5))
        return crate

    def test_it_reads_the_verdicts_off_the_crate(self):
        from architect.web import ring                            # noqa: PLC0415
        state = ring.read(self.crate())
        self.assertEqual(state["checks"]["design_to_build"]["verdict"],
                         "refused")
        self.assertEqual(state["checks"]["build_to_test"]["verdict"],
                         "accepted")
        self.assertNotIn("test_to_learn", state["checks"],
                         "a handover that never ran must not look checked")

    def test_every_phase_and_sentinel_is_a_link(self):
        from architect.web import ring                            # noqa: PLC0415
        svg = ring.draw(ring.read(self.crate()))
        for phase in ring.PHASES:
            self.assertIn(f'href="/?phase={phase}', svg)
        for handover in ring.SENTINEL_AT:
            self.assertIn(f'href="/?sentinel={handover}', svg)
        self.assertIn('href="/?phase=architect', svg)

    def test_the_record_says_what_it_was_held_to(self):
        """A contract that finds nothing must still leave a trace.

        Otherwise a reader cannot tell "it was applied and passed" from "it
        never ran", and those are not the same claim.
        """
        crate = self.crate()
        # The findings share the `#check/<handover>-N/` prefix and are written
        # first, so the type is what tells the act from them.
        act = next(e for e in crate["@graph"]
                   if e.get("@id", "").startswith("#check/design_to_build")
                   and e.get("@type") == "CreateAction")
        self.assertEqual(act["dbtl:heldTo"],
                         ["dbtl:design_to_build/0.1.0",
                          "sentinel-oo:design_to_build/0.11.0"])
        self.assertEqual(act["dbtl:checksApplied"], 33)
        self.assertIn("startTime", act)

    def test_a_finding_points_at_the_entity_it_concerns(self):
        crate = self.crate()
        found = next(e for e in crate["@graph"]
                     if e.get("@type") == "PropertyValue")
        self.assertEqual(found["about"], {"@id": "#sample/SAMP-001"})

    def test_the_serial_counts_acts_and_not_findings(self):
        crate = self.crate()
        acts = sorted(e["@id"] for e in crate["@graph"]
                      if e.get("@type") == "CreateAction")
        self.assertEqual(acts, ["#check/build_to_test-2",
                                "#check/design_to_build-1"])


class TestStartingOver(unittest.TestCase):
    """Starting another run must not land in the last one's crate.

    The crate is append-only and `CrateStore` opens whatever is already at a
    path, so running again under the same id ADDS to the previous crate. That
    is right, and it is the wrong thing to get by pressing a button: a second
    run went from 448 entities to 1039 and the growth column stopped meaning
    what it said.
    """

    def session(self):
        import importlib.util                                   # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "dbtl_web_server", ROOT / "architect" / "web" / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, module.Session("abcdef123456")

    def test_a_restart_gives_the_run_a_new_name(self):
        _, session = self.session()
        first = session.run_id
        session.restart()
        self.assertNotEqual(session.run_id, first)
        self.assertTrue(session.run_id.endswith("-run2"))
        session.restart()
        self.assertTrue(session.run_id.endswith("-run3"),
                        "the number has to keep climbing, not reset")

    def test_the_form_is_told_the_new_name(self):
        """The form's run id wins at the start of a cycle, so if it is not
        updated the next run silently uses the old one."""
        _, session = self.session()
        session.filled.values["run_id"] = "BP-round-1"
        session.restart()
        self.assertEqual(session.filled.values["run_id"], session.run_id)
        self.assertNotEqual(session.filled.values["run_id"], "BP-round-1")

    def test_keeping_the_specification_keeps_it(self):
        _, session = self.session()
        session.filled.values = {"researcher": "Marco", "run_id": "r"}
        session.restart(keep_specification=True)
        self.assertEqual(session.filled.values["researcher"], "Marco")

    def test_from_scratch_clears_it(self):
        _, session = self.session()
        session.filled.values = {"researcher": "Marco", "run_id": "r"}
        session.restart(keep_specification=False)
        self.assertEqual(session.filled.values, {})

    def test_a_restart_clears_the_run_and_not_the_disk(self):
        _, session = self.session()
        session.log = [{"at": "now", "kind": "note", "state": "", "text": "x"}]
        session.crate_growth = [{"phase": "design", "entities": 9, "added": 9}]
        session.finished = True
        session.focus = "#something"
        session.restart()
        self.assertEqual(session.log, [])
        self.assertEqual(session.crate_growth, [])
        self.assertIsNone(session.arch)
        self.assertFalse(session.finished)
        self.assertEqual(session.focus, "")


class TestWorkflows(unittest.TestCase):
    """The workflows that ship, and the rules a researcher's own is held to.

    A workflow decides how many things a run is about and where each handover
    falls, so a broken one is not a cosmetic problem - it is a run that checks
    the wrong boundary or none at all. These are the same five rules the
    interface refuses an edited workflow with.
    """

    @classmethod
    def setUpClass(cls):
        # No skip without PyYAML any more: every workflow has a JSON twin and
        # the loader reads it, so these run on a plain clone. The skip that
        # used to be here hid the one thing worth knowing - whether a machine
        # with no PyYAML can still run the cycle.
        from architect.workflows import loader             # noqa: PLC0415
        cls.loader = loader

    def test_every_shipped_workflow_holds_together(self):
        """Whatever we ship has to pass what we ask of other people."""
        found = self.loader.available()
        self.assertGreaterEqual(len(found), 4,
                                f"expected the four demonstrations, found {found}")
        for name in found:
            with self.subTest(workflow=name):
                flow = self.loader.load(name)
                self.assertEqual(flow.problems(), [],
                                 f"{name}.yaml does not pass its own rules")

    def test_each_one_marks_all_four_handovers(self):
        """Four phases have four boundaries. An unmarked one is unchecked."""
        for name in self.loader.available():
            flow = self.loader.load(name)
            for handover in ("design_to_build", "build_to_test",
                             "test_to_learn", "learn_to_design"):
                with self.subTest(workflow=name, handover=handover):
                    step = flow.handover_step(handover)
                    self.assertIsNotNone(
                        step, f"{name} never marks {handover}")
                    self.assertEqual(
                        step.number,
                        [s for s in flow.steps if s.phase == step.phase][-1].number,
                        f"{name} marks {handover} before the phase ends")

    def test_attrition_only_goes_one_way(self):
        flow = self.loader.load("bioprospecting")
        counts = [c for _, c, _ in flow.attrition()]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(counts, [96, 86, 75],
                         "the worked cycle's real numbers have changed")

    def test_a_workflow_that_gains_things_is_refused(self):
        """The fault that is easiest to write and hardest to see by eye."""
        flow = self.loader.from_dict({
            "name": "gains", "steps": [
                {"number": 1, "name": "a", "phase": "design",
                 "count_observed": 10, "handover_after": "design_to_build",
                 "handover_number": 1},
                {"number": 2, "name": "b", "phase": "build",
                 "count_observed": 40, "handover_after": "build_to_test",
                 "handover_number": 2},
                {"number": 3, "name": "c", "phase": "test",
                 "handover_after": "test_to_learn", "handover_number": 3},
                {"number": 4, "name": "d", "phase": "learn",
                 "handover_after": "learn_to_design", "handover_number": 4},
            ]})
        self.assertTrue(any("attrition only goes one way" in p
                            for p in flow.problems()),
                        f"a count that grew was not refused: {flow.problems()}")

    def test_a_missing_handover_is_refused(self):
        flow = self.loader.from_dict({
            "name": "unmarked", "steps": [
                {"number": 1, "name": "a", "phase": "design"},
                {"number": 2, "name": "b", "phase": "build",
                 "handover_after": "build_to_test", "handover_number": 2},
                {"number": 3, "name": "c", "phase": "test",
                 "handover_after": "test_to_learn", "handover_number": 3},
                {"number": 4, "name": "d", "phase": "learn",
                 "handover_after": "learn_to_design", "handover_number": 4},
            ]})
        self.assertTrue(any("design_to_build" in p for p in flow.problems()),
                        f"an unmarked handover was not refused: {flow.problems()}")

    def test_the_workflow_decides_how_big_a_run_is(self):
        """If this stops being true the workflow is decoration."""
        self.assertEqual(self.loader.load("bioprospecting").to_inputs(),
                         {"n": 96})
        # The blank one counts nothing on purpose, and must not invent a size.
        self.assertEqual(self.loader.load("blank").to_inputs(), {})

    def test_each_workflow_and_its_json_twin_agree(self):
        """Two files holding one workflow is two files that can drift.

        The twin exists because the deployment image installs nothing, so a
        YAML-only workflow would be absent on the machine where the interface
        actually runs. That is only worth having while the two say the same
        thing.
        """
        import json                                         # noqa: PLC0415
        for name in self.loader.available():
            twin = Path(self.loader.HERE) / f"{name}.json"
            with self.subTest(workflow=name):
                self.assertTrue(twin.is_file(),
                                f"{name}.yaml has no .json twin; the image "
                                f"has no PyYAML and would not see it")
                from_yaml = self.loader.load(name)
                from_json = self.loader.from_dict(
                    json.loads(twin.read_text()), twin)
                self.assertEqual(
                    [(s.number, s.name, s.phase, s.count_observed,
                      s.manual_parts, s.routes, s.handover_after)
                     for s in from_json.steps],
                    [(s.number, s.name, s.phase, s.count_observed,
                      s.manual_parts, s.routes, s.handover_after)
                     for s in from_yaml.steps],
                    f"{name}.json and {name}.yaml have drifted apart")

    def test_a_workflow_survives_the_trip_through_a_crate(self):
        """The crate form is a format, not a summary.

        If anything is lost here, "attach your own workflow as an RO-Crate"
        quietly means "attach most of your own workflow".
        """
        for name in self.loader.available():
            with self.subTest(workflow=name):
                before = self.loader.load(name)
                after = self.loader.Workflow.from_crate(
                    {"@graph": before.to_crate()})
                self.assertEqual([s.number for s in after.steps],
                                 [s.number for s in before.steps])
                self.assertEqual([s.name for s in after.steps],
                                 [s.name for s in before.steps])
                self.assertEqual([s.phase for s in after.steps],
                                 [s.phase for s in before.steps])
                self.assertEqual([s.count_observed for s in after.steps],
                                 [s.count_observed for s in before.steps])
                self.assertEqual([s.manual_parts for s in after.steps],
                                 [s.manual_parts for s in before.steps])
                self.assertEqual([s.routes for s in after.steps],
                                 [s.routes for s in before.steps])
                self.assertEqual([s.handover_after for s in after.steps],
                                 [s.handover_after for s in before.steps])
                self.assertEqual(after.problems(), [])

    def test_the_plan_lands_in_the_crate(self):
        """A refused addition leaves no plan, and says nothing unless asked.

        This caught exactly that: the action named an agent that was never
        written, the store refused the whole addition because it was dangling,
        and the run carried on with no plan in its crate.
        """
        from framework.crate_store import CrateStore                # noqa: PLC0415
        store = CrateStore("test-plan-lands", root=Path(self.tmp))
        flow = self.loader.load("bioprospecting")
        report = self.loader.record_in(store, flow, by="a tester")
        self.assertEqual(report.dangling, [],
                         f"the plan was refused: {report.dangling}")
        ids = {e.get("@id") for e in store.crate["@graph"]}
        self.assertIn(flow.crate_id(), ids)
        for step in flow.steps:
            self.assertIn(flow.step_id(step), ids)

    def test_the_graph_is_drawn_and_every_node_is_a_link(self):
        """A graph that is only ever tabulated is a graph nobody has seen.

        One hop: the centre, and at most `per_side` on each side. If this
        ever draws the whole crate it becomes a grey cloud, so the cap is
        part of the claim and not an implementation detail.
        """
        from architect.web import kgview                            # noqa: PLC0415
        flow = self.loader.load("bioprospecting")
        crate = {"@graph": flow.to_crate()}
        near = kgview.neighbourhood(crate, flow.crate_id())
        svg = kgview.draw(near, per_side=4)
        self.assertTrue(svg.startswith('<svg class="kg"'))
        # four neighbours drawn, plus the centre
        self.assertEqual(svg.count("<circle"), 5)
        self.assertEqual(svg.count('<a href="/?focus='), 4)
        self.assertIn("and 10 more", svg)
        self.assertNotIn("#000000", svg)        # colours come from the palette
        self.assertIn("var(--fg)", svg)

    def test_a_link_to_an_entity_is_percent_encoded(self):
        """An entity id starts with `#`, and a URL takes that as a fragment.

        Left raw in `?focus=`, the browser never sends it - nor anything
        after it - so every link into the graph did nothing at all and the
        page simply stayed where it was. It looked like the graph was
        missing rather than like the link was broken.
        """
        from architect.web import kgview                            # noqa: PLC0415
        flow = self.loader.load("bioprospecting")
        crate = {"@graph": flow.to_crate()}
        svg = kgview.draw(kgview.neighbourhood(crate, flow.crate_id()))
        self.assertIn("?focus=%23workflow%2Fbioprospecting", svg)
        self.assertNotIn('?focus=#', svg)

    def test_an_identifier_cannot_break_the_drawing(self):
        """An unescaped `&` or `<` in an id would silently ruin the SVG."""
        from architect.web import kgview                            # noqa: PLC0415
        # `result`, not `about`: `about` is in kgview.QUIET, so an edge made
        # with it is deliberately not drawn and this would test nothing.
        crate = {"@graph": [
            {"@id": "#a&b", "@type": "Thing", "name": "a & b",
             "result": {"@id": "#c<d"}},
            {"@id": "#c<d", "@type": "Thing", "name": "c < d"}]}
        svg = kgview.draw(kgview.neighbourhood(crate, "#a&b"))
        self.assertIn("&amp;", svg)
        self.assertIn("&lt;", svg)
        # no raw `&` that is not the start of an entity
        self.assertNotIn("& ", svg)

    def test_the_sentinels_own_subgraph_can_be_read_and_drawn(self):
        """A verdict is a node, and what it is about is an edge.

        The guards write into the same crate as everything else, so what they
        said is readable without this process: a run that finished last week,
        or one a sentinel at the far end of a protocol handed back.
        """
        from architect.web import kgview                             # noqa: PLC0415
        crate = {"@graph": [
            {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
             "about": {"@id": "./"}},
            {"@id": "./", "@type": "Dataset"},
            {"@id": "#sample/S1", "@type": "bioschemas:BioSample"},
            {"@id": "#check/design_to_build-1", "@type": "CreateAction",
             "dbtl:verdict": "refused", "dbtl:checksApplied": 13,
             "dbtl:heldTo": ["dbtl:design_to_build/0.1.0"],
             "endTime": "2026-11-13T10:00:00Z",
             "object": [{"@id": "#check/design_to_build-1/finding-1"},
                        {"@id": "#check/design_to_build-1/finding-2"}]},
            {"@id": "#check/design_to_build-1/finding-1",
             "@type": "PropertyValue", "name": "missing_provenance",
             "dbtl:severity": "error", "about": {"@id": "#sample/S1"},
             "dbtl:path": "crate.@graph[#sample/S1].dbtl:storageContainer"},
            # No `about`: written before that field existed. The entity has to
            # be recovered from the path, or every old run loses its links.
            {"@id": "#check/design_to_build-1/finding-2",
             "@type": "PropertyValue", "name": "missing_provenance",
             "dbtl:severity": "error",
             "dbtl:path": "crate.@graph[#sample/S1].dbtl:storagePosition"},
        ]}
        acts = kgview.sentinels(crate)
        self.assertEqual(1, len(acts))
        self.assertEqual("refused", acts[0]["verdict"])
        self.assertEqual(13, acts[0]["checks_applied"])
        self.assertEqual("design_to_build", acts[0]["handover"])
        self.assertEqual(["#sample/S1", "#sample/S1"],
                         [f["about"] for f in acts[0]["findings"]],
                         "a finding lost the entity it is about")

        svg = kgview.draw_sentinels(acts)
        self.assertIn("<svg", svg)
        self.assertIn("?sentinel=design_to_build", svg)
        self.assertIn("%23sample%2FS1", svg)
        self.assertNotIn("?focus=#", svg, "an id starting with # is a fragment")

    def test_a_finding_never_points_at_something_absent(self):
        """A link that leads nowhere is worse than no link."""
        from architect.web import kgview                             # noqa: PLC0415
        crate = {"@graph": [
            {"@id": "#check/build_to_test-1", "@type": "CreateAction",
             "dbtl:verdict": "refused",
             "object": [{"@id": "#check/build_to_test-1/finding-1"}]},
            {"@id": "#check/build_to_test-1/finding-1",
             "@type": "PropertyValue", "name": "unknown_design_item",
             "dbtl:severity": "error",
             "dbtl:path": "crate.@graph[#item/NEVER-WRITTEN].name"},
        ]}
        acts = kgview.sentinels(crate)
        self.assertIsNone(acts[0]["findings"][0]["about"])

    def test_the_graph_view_finds_both_directions(self):
        """Provenance is read backwards, so one direction is not enough."""
        from architect.web import kgview                            # noqa: PLC0415
        flow = self.loader.load("bioprospecting")
        crate = {"@graph": flow.to_crate()}
        near = kgview.neighbourhood(crate, flow.step_id(flow.steps[0]))
        self.assertTrue(near["found"])
        self.assertTrue(any(e["id"] == flow.crate_id()
                            for e in near["pointed_at_by"]),
                        "the plan does not point at its own first step")
        shape = dict(kgview.shape(crate))
        self.assertEqual(shape.get("schema:HowToStep"), len(flow.steps))

    def setUp(self):
        import tempfile                                             # noqa: PLC0415
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTheUniformSocket(unittest.TestCase):
    """Phase agents and sentinels reaching the Architect over one protocol.

    The Architect has two sockets, `Runner` and `Checker`, and until now you
    had to write Python in this repository to plug anything into either. These
    tests hold the protocol version of them: a real child process, a real
    pipe, and no import between the two sides.

    Against `sentinel-oo` as well, when that checkout is here - the point of
    an interoperability project is the agent somebody else wrote.
    """

    @classmethod
    def setUpClass(cls):
        from architect import mcp                               # noqa: PLC0415
        cls.mcp = mcp
        cls.server = mcp.Server(mcp.ours(lab="newcastle"))

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_it_says_who_it_is_and_what_it_can_do(self):
        info = self.server.info
        self.assertEqual("2025-06-18", info.get("protocolVersion"))
        self.assertEqual("dbtl-sentinel", info["serverInfo"]["name"])
        self.assertEqual(
            {"check_handover", "list_handovers", "read_contract", "run_phase"},
            {t["name"] for t in self.server.tools()})

    def test_every_tool_declares_what_it_takes(self):
        """A schema is how a coordinator calls a tool it has never seen."""
        for tool in self.server.tools():
            with self.subTest(tool=tool["name"]):
                self.assertIn("inputSchema", tool)
                self.assertEqual("object", tool["inputSchema"].get("type"))
                self.assertTrue(tool.get("description"))

    def test_a_phase_and_its_handover_both_come_over_the_pipe(self):
        made = self.server.call("run_phase", {"phase": "design",
                                              "run_id": "test-socket"})
        self.assertTrue(made["entities"], "the phase produced nothing")
        self.assertIsInstance(made.get("package"), dict,
                              f"no handover package came back: {made['notes']}")
        seen = self.server.call("check_handover",
                                {"handover": "design_to_build",
                                 "package": made["package"],
                                 "crate": made["package"].get("crate", {})})
        self.assertEqual("ACCEPTED", seen["verdict"], seen["findings"])

    def test_a_refusal_is_a_verdict_and_not_an_error(self):
        """A client that reads a refusal as a failure retries for ever."""
        crate = {"@graph": [
            {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
             "about": {"@id": "./"}},
            {"@id": "./", "@type": "Dataset"}]}
        seen = self.server.call("check_handover",
                                {"handover": "design_to_build", "crate": crate})
        self.assertEqual("REFUSED", seen["verdict"])
        self.assertTrue(seen["findings"])

    def test_an_unknown_tool_is_an_error_and_says_what_there_is(self):
        with self.assertRaises(self.mcp.McpError) as caught:
            self.server.call("do_the_science", {})
        self.assertIn("run_phase", str(caught.exception))

    def test_the_architect_accepts_a_sentinel_at_the_end_of_a_pipe(self):
        """The whole point: a real run, checked by another process.

        Not the pipe in isolation - the Architect's own `run_phase`, with a
        checker that happens to be a protocol away, and the sentinel's act
        landing in the crate that grows just as it does in process.
        """
        import shutil as _shutil                               # noqa: PLC0415
        from architect.architect import Architect              # noqa: PLC0415
        from architect.contract import Verdict                 # noqa: PLC0415
        from architect.wiring import phase_runner              # noqa: PLC0415

        run_id = "test-over-mcp"
        _shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)
        arch = Architect(run_id, researcher="tests")
        arch.consult(objective="a handover checked by another process")

        before = len(arch.memory.store.crate["@graph"])
        over_the_pipe = self.mcp.checker_over_mcp(self.server)
        seen = []

        def checker(handover, package, a):
            answer = over_the_pipe(handover, package, a)
            seen.append(answer)
            return answer

        decision = arch.run_phase(
            "design",
            phase_runner(profile="bioprospecting", lab="newcastle"),
            checker)
        step = arch.history[-1]

        self.assertEqual(Verdict.ACCEPTED, step.verdict, step.notes)
        self.assertTrue(seen, "the Architect never called the checker")
        trace = " ".join(seen[-1].trace)
        self.assertIn("dbtl-sentinel", trace)
        self.assertIn("over MCP", trace)
        self.assertIn("merged", trace, f"nothing came back into the crate: {trace}")
        self.assertGreater(len(arch.memory.store.crate["@graph"]), before)
        acts = [e for e in arch.memory.store.crate["@graph"]
                if str(e.get("@id", "")).startswith("#check/")
                and e.get("@type") == "CreateAction"]
        self.assertTrue(acts, "the sentinel's act never reached our crate")
        self.assertEqual("accepted", acts[-1].get("dbtl:verdict"))
        self.assertIsNotNone(decision.move)
        _shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)

    def test_the_architect_runs_a_phase_at_the_end_of_a_pipe(self):
        """The other socket: the work itself done by another process.

        A phase agent reached this way may be in another language, in another
        laboratory, or a person pressing a button four months from now. What
        the Architect sees is the same `PhaseResult` either way, which is the
        only reason this substitution is allowed to be invisible.
        """
        import shutil as _shutil                               # noqa: PLC0415
        from architect.architect import Architect              # noqa: PLC0415
        from architect.contract import Verdict                 # noqa: PLC0415
        from architect.wiring import sentinel_checker          # noqa: PLC0415

        run_id = "test-phase-over-mcp"
        _shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)
        arch = Architect(run_id, researcher="tests")
        arch.consult(objective="a phase run by another process")

        runner = self.mcp.runner_over_mcp({"design": self.server})
        arch.run_phase("design", runner,
                       sentinel_checker(profile="bioprospecting"))
        step = arch.history[-1]

        self.assertEqual("phase_design", step.actor,
                         "the Architect did not record who did the work")
        self.assertTrue(any("over MCP" in n for n in step.notes), step.notes)
        self.assertIn(step.verdict, (Verdict.ACCEPTED,
                                     Verdict.ACCEPTED_WITH_FLAGS,
                                     Verdict.REFUSED))
        self.assertGreater(len(arch.memory.store.crate["@graph"]), 2,
                           "nothing the remote phase produced reached the crate")
        _shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)

    def test_a_phase_with_no_server_falls_back(self):
        """One phase moved to a protocol must not strand the other three."""
        asked = []

        def in_process(phase, arch):
            asked.append(phase)
            from architect.architect import PhaseResult         # noqa: PLC0415
            return PhaseResult(entities=[], by="in-process")

        runner = self.mcp.runner_over_mcp({"design": self.server},
                                          fallback=in_process)

        class Bare:
            run_id = "test-fallback"
            memory = None
            spec = None

        self.assertEqual("in-process", runner("build", Bare()).by)
        self.assertEqual(["build"], asked)

    def test_it_also_drives_the_sentinel_somebody_else_wrote(self):
        """`sentinel-oo` over the same client, on his own example crates."""
        from framework.oo_contract import dbtlhub               # noqa: PLC0415
        hub = dbtlhub()
        crates = (hub / "bioprospecting" / "exampleROcrates" / "design-to-build"
                  if hub else None)
        if hub is None or not (hub / "sentinel-oo" / "src").is_dir() \
                or not crates.is_dir():                        # pragma: no cover
            raise unittest.SkipTest("needs the dbtlhub checkout beside this one")
        try:
            import yaml                                    # noqa: F401,PLC0415
        except ImportError:                                # pragma: no cover
            raise unittest.SkipTest(
                "his service imports PyYAML at startup, and it is started "
                "with this interpreter; nothing of ours needs it")

        class Nowhere:
            run_id = "test-oo"
            memory = None
            spec = None

        with self.mcp.Server(self.mcp.sentinel_oo()) as his:
            self.assertEqual("sentinel-oo",
                             his.info["serverInfo"]["name"])
            check = self.mcp.checker_over_mcp(his, merge_back=False)
            good = json.loads((crates / "valid"
                               / "ro-crate-metadata.json").read_text())
            seen = check("design_to_build",
                         {"crate": good, "crate_dir": crates / "valid"},
                         Nowhere())
            self.assertEqual("accepted", seen.verdict.value, seen.findings)

            folder = crates / "invalid" / "mode-in-prose"
            bad = json.loads((folder / "ro-crate-metadata.json").read_text())
            seen = check("design_to_build",
                         {"crate": bad, "crate_dir": folder}, Nowhere())
            self.assertEqual("refused", seen.verdict.value)
            self.assertIn("edge_handling_is_recorded",
                          [f.code for f in seen.findings])


class TestAContractTheWizardWrote(unittest.TestCase):
    """A contract drafted by Anil Wipat's wizard has to run on this side.

    `dbtlhub/contract-wizard/` drafts a sentinel-oo contract from a crate and
    six paragraphs of English, with a model held to the language by a schema.
    The whole claim of two sentinels is that such a file runs here unchanged,
    so the shape it emits is pinned here: those keys, those five demands,
    those two severities, and nothing else.

    The contract below is in exactly that shape, written by hand rather than
    by a model, so this test needs no Ollama and no network.
    """

    DRAFTED = {
        "contract": "wizard_shaped", "version": "0.1.0",
        "description": "the shape the wizard emits, run by this reader",
        "expects": ["bioschemas:BioSample"],
        "requires": [
            {"name": "the_sample_says_where_it_came_from",
             "applies_to": "type:bioschemas:BioSample",
             "property": "location", "must": "be recorded",
             "severity": "refuse",
             "message": "a sample with no site cannot be re-collected"},
            {"name": "that_site_is_in_the_crate",
             "applies_to": "type:bioschemas:BioSample",
             "property": "location",
             "must": "point at something in the crate",
             "severity": "refuse",
             "message": "a reference to a site that is not here is a dead end"},
            {"name": "the_aliquot_count_is_sane",
             "applies_to": "type:bioschemas:BioSample",
             "property": "dbtl:aliquotCount",
             "must": "be a number between", "between": [1, 96],
             "severity": "flag",
             "message": "zero aliquots, or hundreds, is a typing mistake"},
        ],
    }

    def contract(self):
        from framework import oo_contract as oo                  # noqa: PLC0415
        import tempfile                                          # noqa: PLC0415
        folder = Path(tempfile.mkdtemp())
        path = folder / "wizard_shaped.json"     # load() reads the JSON twin too
        path.write_text(json.dumps(self.DRAFTED, indent=1))
        return oo, oo.load(path)

    @staticmethod
    def crate():
        """The sample from the worked bioprospecting cycle, as handed over."""
        return {"@graph": [
            {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
             "about": {"@id": "./"}},
            {"@id": "./", "@type": "Dataset"},
            {"@id": "#site/NS-01", "@type": "Place", "name": "North Sea NS-01"},
            {"@id": "#sample/SAMP-001",
             "@type": ["bioschemas:BioSample", "prov:Entity"],
             "name": "sediment core NS-01 / 0-5 cm",
             "location": {"@id": "#site/NS-01"},
             "dbtl:aliquotCount": 4}]}

    def test_the_shape_it_emits_loads_here(self):
        oo, contract = self.contract()
        self.assertEqual("wizard_shaped", contract.name)
        self.assertEqual(3, len(contract.requirements))
        self.assertEqual([], oo.check(contract, self.crate()),
                         "a sound crate must come back with nothing to report")

    def test_it_refuses_what_it_should_refuse(self):
        oo, contract = self.contract()
        crate = self.crate()
        crate["@graph"][3]["location"] = {"@id": "#site/NOWHERE"}
        crate["@graph"][3]["dbtl:aliquotCount"] = 0
        found = {e.code.split(":")[0] for e in oo.check(contract, crate)}
        self.assertIn("that_site_is_in_the_crate", found)
        self.assertIn("the_aliquot_count_is_sane", found)

    def test_a_sixth_demand_is_refused_and_named(self):
        """The wizard imports the five demands from his code, not ours.

        The day a sixth is added there, a contract using it must stop here
        loudly. Silently ignoring an unknown demand would mean a requirement
        nobody checks and a crate that passes for the wrong reason.
        """
        oo, _ = self.contract()
        import tempfile                                          # noqa: PLC0415
        drafted = json.loads(json.dumps(self.DRAFTED))
        drafted["requires"][0]["must"] = "be plausible"
        path = Path(tempfile.mkdtemp()) / "later_dialect.json"
        path.write_text(json.dumps(drafted))
        with self.assertRaises(oo.ForeignContractError) as caught:
            oo.load(path)
        self.assertIn("be plausible", str(caught.exception))

    def test_a_requirement_that_can_never_fire_is_reported(self):
        """His check 2, on this side: silence is not approval."""
        oo, _ = self.contract()
        import tempfile                                          # noqa: PLC0415
        drafted = json.loads(json.dumps(self.DRAFTED))
        drafted["requires"].append(
            {"name": "about_a_type_this_crate_has_not_got",
             "applies_to": "type:schema:MolecularEntity",
             "property": "schema:inChIKey", "must": "be unique",
             "severity": "refuse", "message": "two constructs, one key"})
        drafted["requires"].append(
            {"name": "about_a_property_nobody_wrote",
             "applies_to": "type:bioschemas:BioSample",
             "property": "dbtl:massGrams", "must": "be a number between",
             "between": [0, 1000], "severity": "flag",
             "message": "a mass outside this range is a typing mistake"})
        path = Path(tempfile.mkdtemp()) / "thin.json"
        path.write_text(json.dumps(drafted))
        contract = oo.load(path)
        quiet = dict(oo.silent(contract, self.crate()))
        self.assertIn("about_a_type_this_crate_has_not_got", quiet)
        self.assertIn("about_a_property_nobody_wrote", quiet)
        self.assertNotIn("the_aliquot_count_is_sane", quiet,
                         "a requirement that does fire was reported as silent")

    def test_a_yaml_contract_still_opens_without_pyyaml(self):
        """The wizard hands a person a YAML file. A clone may have no PyYAML.

        This reader needed it to open anything at all, so a contract from the
        wizard - or any of his - could not be read on a plain clone. A JSON
        twin beside the file is now read instead, and when there is none the
        error names both files rather than saying "not installed".
        """
        oo, _ = self.contract()
        import tempfile                                          # noqa: PLC0415
        folder = Path(tempfile.mkdtemp())
        (folder / "drafted.yaml").write_text("contract: unreadable-by-design\n")
        had = sys.modules.get("yaml", "absent")
        sys.modules["yaml"] = None          # exactly what a clone without it sees
        try:
            with self.assertRaises(oo.ForeignContractError) as caught:
                oo.load(folder / "drafted.yaml")
            self.assertIn("drafted.json", str(caught.exception))

            (folder / "drafted.json").write_text(json.dumps(self.DRAFTED))
            contract = oo.load(folder / "drafted.yaml")
        finally:
            if had == "absent":
                del sys.modules["yaml"]
            else:
                sys.modules["yaml"] = had
        self.assertEqual("wizard_shaped", contract.name)
        self.assertEqual([], oo.check(contract, self.crate()))

    def test_his_own_contract_has_nothing_silent_in_it(self):
        """20 requirements, and every one of them has something to say."""
        from framework import oo_contract as oo                  # noqa: PLC0415
        hub = oo.dbtlhub()
        if hub is None:                                # pragma: no cover
            raise unittest.SkipTest("needs the dbtlhub checkout for his "
                                    "contract and his crate")
        try:
            import yaml                                    # noqa: F401,PLC0415
        except ImportError:                                # pragma: no cover
            raise unittest.SkipTest(
                "his contracts are YAML only and this reader will not write "
                "a JSON twin into his folder; reading them needs PyYAML")
        path = hub / "sentinel-oo" / "examples" / "contracts" / "design_to_build.yaml"
        crate = (hub / "bioprospecting" / "exampleROcrates" / "design-to-build"
                 / "valid" / "ro-crate-metadata.json")
        if not path.is_file() or not crate.is_file():  # pragma: no cover
            raise unittest.SkipTest(f"{path} or {crate} is not here")
        self.assertEqual([], oo.silent(oo.load(path),
                                       json.loads(crate.read_text())))


class TestItRunsWithoutPyYAML(unittest.TestCase):
    """The claim that a clone needs no install step.

    YAML is not in the standard library, so every YAML file this code reads
    has a JSON twin that is read instead when PyYAML is absent. A twin that
    drifts is worse than no twin: the person gets an old rule and no warning.
    The forms had no twin at all, and the Architect silently fell back to the
    generic form on any machine without PyYAML - so the use case someone chose
    was not actually available to them.
    """

    @staticmethod
    def _twins():
        """`scripts/make_twins.py`, loaded by path: scripts/ is not a package."""
        import importlib.util                                       # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "make_twins", ROOT / "scripts" / "make_twins.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_yaml_file_has_a_twin(self):
        """Not one YAML file without the JSON a stdlib-only reader needs."""
        make_twins = self._twins()
        missing = [make_twins.twin_of(source, suffix).relative_to(ROOT)
                   for folder, suffix in make_twins.PLACES
                   for source in sorted(folder.glob("*.yaml"))
                   if not make_twins.twin_of(source, suffix).is_file()]
        self.assertEqual([], missing,
                         f"no JSON twin for {missing}: without PyYAML these "
                         f"files cannot be read at all")

    def test_no_twin_has_drifted(self):
        """The twin says what the YAML says, or it is a second, older rule."""
        try:
            import yaml                                    # noqa: PLC0415
        except ImportError:                                # pragma: no cover
            raise unittest.SkipTest("checking a twin against its YAML needs "
                                    "PyYAML; reading the twin does not")
        make_twins = self._twins()
        for folder, suffix in make_twins.PLACES:
            for source in sorted(folder.glob("*.yaml")):
                twin = make_twins.twin_of(source, suffix)
                with self.subTest(twin=str(twin.relative_to(ROOT))):
                    self.assertEqual(
                        yaml.safe_load(source.read_text(encoding="utf-8")),
                        json.loads(twin.read_text(encoding="utf-8")),
                        f"{twin.name} no longer matches {source.name}. "
                        f"Run `python3 scripts/make_twins.py`.")

    def test_the_chosen_use_case_survives_a_missing_pyyaml(self):
        """With PyYAML taken away, the bioprospecting form still loads.

        Not the generic fallback: the form the person asked for, read from
        its twin, with its own questions in it.
        """
        from architect.forms import loader as forms                 # noqa: PLC0415
        had = forms.yaml
        forms.yaml = None                       # exactly what a clone without it sees
        try:
            form, source = forms.load_form(
                ROOT / "architect" / "forms" / "bioprospecting.yaml")
        finally:
            forms.yaml = had
        self.assertTrue(form.sections, "the twin produced an empty form")
        self.assertIn("profile", [f.key for f in form.all_fields()],
                      "this is not the bioprospecting form")


if __name__ == "__main__":
    unittest.main(verbosity=2)
