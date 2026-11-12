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


class TestWorkflows(unittest.TestCase):
    """The workflows that ship, and the rules a researcher's own is held to.

    A workflow decides how many things a run is about and where each handover
    falls, so a broken one is not a cosmetic problem - it is a run that checks
    the wrong boundary or none at all. These are the same five rules the
    interface refuses an edited workflow with.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import yaml                                    # noqa: F401,PLC0415
        except ImportError:                                # pragma: no cover
            raise unittest.SkipTest(
                "the workflows are YAML and PyYAML is not installed; the "
                "framework itself still runs without it")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
