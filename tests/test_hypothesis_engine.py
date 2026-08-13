import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes
from assurance.hypothesis.engine import EngineError, _uncertainty_work, run_space
from assurance.hypothesis.model import StageResult
from tests.test_assurance_contract import valid_contract


def _space(base, **overrides):
    result = {
        "schema_version": 1,
        "space_id": "engine-test",
        "base_contract": {
            "path": "base.json",
            "sha256": hashlib.sha256(canonical_bytes(base)).hexdigest(),
        },
        "max_candidates": 1,
        "axes": [
            {
                "id": "payload",
                "choices": [
                    {
                        "id": "nominal",
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": 2.0, "unit": "kg"},
                            }
                        ],
                    }
                ],
            }
        ],
        "uncertainties": [],
        "objectives": [],
        "repair_rules": [],
        "evaluation": {
            "max_stage_evaluations": 8,
            "stages": ["contract_v1", "physical_v030"],
        },
    }
    result.update(overrides)
    return result


def _write_inputs(root, base, space):
    (root / "base.json").write_bytes(canonical_bytes(base))
    path = root / "space.json"
    path.write_bytes(canonical_bytes(space))
    return path


class ControlledScheduler:
    instances = []

    def __init__(self, *, max_stage_evaluations, artifact_root):
        self.max_stage_evaluations = max_stage_evaluations
        self.artifact_root = artifact_root
        self.evaluation_count = 0
        self.tool_versions = {
            "assurance_kernel": "test",
            "hypothesis_scheduler": "test",
        }
        self.calls = []
        self.__class__.instances.append(self)

    @staticmethod
    def _quantity(candidate):
        return next(
            item["value"]["value"]
            for item in candidate.resolved_contract["quantities"]
            if item["id"] == "Q-PAYLOAD"
        )

    @staticmethod
    def _stage(name, status, report=None, diagnostics=()):
        output = {} if report is None else {"report": report}
        return StageResult(
            name=name,
            version="1",
            status=status,
            cache_key="a" * 64,
            input_hash="b" * 64,
            output=output,
            diagnostics=tuple(diagnostics),
        )

    def evaluate(self, candidate, cache_dir, *, stages, uncertainty_case=None):
        requested = tuple(stages)
        self.calls.append((candidate.candidate_id, requested, uncertainty_case))
        emitted = []
        for name in requested:
            if self.evaluation_count >= self.max_stage_evaluations:
                raise ValueError(
                    f"max_stage_evaluations {self.max_stage_evaluations} would be exceeded"
                )
            self.evaluation_count += 1
            if name == "contract_v1":
                emitted.append(self._stage(name, "passed"))
                continue
            if name == "physical_v030":
                passed = self._quantity(candidate) <= 2.0
                diagnostics = () if passed else (
                    {
                        "code": "LOAD.HIGH",
                        "severity": "error",
                        "path": "quantity:Q-PAYLOAD.value",
                        "message": "payload exceeds the bounded test limit",
                        "evidence_ids": [],
                    },
                )
                report = {
                    "candidate_id": candidate.candidate_id,
                    "promotable": passed,
                    "diagnostics": list(diagnostics),
                    "analyses": [],
                    "metadata": {"minimum_evidence_level": "assumed"},
                }
                emitted.append(
                    self._stage(
                        name,
                        "passed" if passed else "failed",
                        report,
                        diagnostics,
                    )
                )
                if not passed:
                    break
                continue
            emitted.append(self._stage(name, "passed"))
        return tuple(emitted)


class AlwaysFailScheduler(ControlledScheduler):
    @staticmethod
    def _quantity(candidate):
        return float("inf")


class EngineTests(unittest.TestCase):
    def setUp(self):
        ControlledScheduler.instances.clear()
        AlwaysFailScheduler.instances.clear()

    def test_missing_space_is_actionable(self):
        with self.assertRaisesRegex(EngineError, "does not exist"):
            run_space("missing-space.json", "missing-output", seed=1)

    def test_run_space_emits_candidates_and_aliases_without_duplicate_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(
                base,
                max_candidates=2,
                axes=[
                    {
                        "id": "a",
                        "choices": [
                            {
                                "id": "x",
                                "operations": [
                                    {
                                        "target": "architecture.features",
                                        "value": ["mobile_base"],
                                    }
                                ],
                            },
                            {
                                "id": "y",
                                "operations": [
                                    {
                                        "target": "architecture.features",
                                        "value": ["mobile_base"],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            )
            path = _write_inputs(root, base, space)
            result = run_space(path, root / "out", seed=1)
            self.assertEqual(2, result["candidate_count"])
            self.assertEqual(
                1, len(list((root / "out" / "candidates").glob("*/stages.json")))
            )

    def test_same_seed_is_reproducible_and_base_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(base, space_id="repro")
            path = _write_inputs(root, base, space)
            run_space(path, root / "one", seed=1)
            run_space(path, root / "two", seed=1)
            one = {
                item.relative_to(root / "one").as_posix(): item.read_bytes()
                for item in (root / "one").rglob("*.json")
            }
            two = {
                item.relative_to(root / "two").as_posix(): item.read_bytes()
                for item in (root / "two").rglob("*.json")
            }
            self.assertEqual(one, two)
            space["base_contract"]["sha256"] = "0" * 64
            (root / "bad.json").write_bytes(canonical_bytes(space))
            with self.assertRaisesRegex(EngineError, "SHA-256 mismatch"):
                run_space(root / "bad.json", root / "bad", seed=1)

    def test_base_contract_duplicate_key_is_actionable_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(base)
            path = _write_inputs(root, base, space)
            (root / "base.json").write_bytes(
                b'{"schema_version":1,"schema_version":1}\n'
            )
            with self.assertRaisesRegex(EngineError, "duplicate JSON key"):
                run_space(path, root / "out", seed=1)
            self.assertFalse((root / "out").exists())

    def test_nominal_failure_skips_counterexample_without_raw_uncertainty_error(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(
                base,
                uncertainties=[
                    {
                        "id": "payload",
                        "target": "quantity:Q-PAYLOAD.value",
                        "values": [{"value": 3.0, "unit": "kg"}],
                        "hard": True,
                    }
                ],
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                AlwaysFailScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            self.assertEqual(0, result["accepted_count"])
            counterexample = json.loads(
                next((root / "out" / "candidates").glob("*/counterexample.json")).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("skipped", counterexample["status"])

    def test_hard_counterexample_rejects_candidate_and_excludes_it_from_pareto(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(
                base,
                uncertainties=[
                    {
                        "id": "payload",
                        "target": "quantity:Q-PAYLOAD.value",
                        "values": [{"value": 3.0, "unit": "kg"}],
                        "hard": True,
                    }
                ],
                objectives=[
                    {"id": "mass", "source": "quantity:Q-PAYLOAD", "direction": "min"}
                ],
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            candidate_id = result["candidates"][0]["candidate_id"]
            pareto = json.loads((root / "out" / "pareto.json").read_text(encoding="utf-8"))
            self.assertEqual(0, result["accepted_count"])
            self.assertEqual("rejected", result["candidates"][0]["status"])
            self.assertNotIn(candidate_id, sum(pareto["fronts"], []))
            self.assertIn(candidate_id, pareto["ineligible"])

    def test_uncertainty_budget_is_reserved_for_future_nominal_candidates(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(
                base,
                max_candidates=2,
                axes=[
                    {
                        "id": "payload",
                        "choices": [
                            {
                                "id": "light",
                                "operations": [
                                    {
                                        "target": "quantity:Q-PAYLOAD.value",
                                        "value": {"value": 1.0, "unit": "kg"},
                                    }
                                ],
                            },
                            {
                                "id": "nominal",
                                "operations": [
                                    {
                                        "target": "quantity:Q-PAYLOAD.value",
                                        "value": {"value": 2.0, "unit": "kg"},
                                    }
                                ],
                            },
                        ],
                    }
                ],
                uncertainties=[
                    {
                        "id": "payload",
                        "target": "quantity:Q-PAYLOAD.value",
                        "values": [
                            {"value": 1.5, "unit": "kg"},
                            {"value": 2.0, "unit": "kg"},
                        ],
                        "hard": False,
                    }
                ],
                evaluation={
                    "max_stage_evaluations": 6,
                    "stages": ["contract_v1", "physical_v030"],
                },
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ), self.assertRaisesRegex(
                EngineError, "uncertainty.*after reserving.*future nominal"
            ):
                run_space(path, root / "out", seed=1)
            self.assertFalse((root / "out").exists())

    def test_uncertainty_budget_counts_shared_counterexample_and_sensitivity_once(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            space = _space(
                base,
                uncertainties=[
                    {
                        "id": "payload",
                        "target": "quantity:Q-PAYLOAD.value",
                        "values": [{"value": 1.5, "unit": "kg"}],
                        "hard": False,
                    }
                ],
                evaluation={
                    "max_stage_evaluations": 4,
                    "stages": ["contract_v1", "physical_v030"],
                },
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            self.assertEqual(1, result["accepted_count"])
            self.assertEqual(4, result["metadata"]["stage_evaluations"])

    def test_uncertainty_budget_precheck_does_not_materialize_cartesian_cases(self):
        declarations = [
            {
                "id": f"u-{index}",
                "target": f"quantity:Q-{index}.value",
                "values": [
                    {"value": 1.0, "unit": "1"},
                    {"value": 2.0, "unit": "1"},
                ],
                "hard": False,
            }
            for index in range(30)
        ]
        total_cases, required_stages = _uncertainty_work(declarations)
        self.assertEqual(2**30 + 1, total_cases)
        self.assertEqual(2 * (2**30 + 60), required_stages)

    def test_repair_child_reruns_contract_dependency_and_emits_objectives(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            base["quantities"][0]["owner"] = "component:CMP-BASE-MOTOR-L"
            stages = [
                "contract_v1",
                "physical_v030",
                "uncertainty_v1",
                "counterexample_v1",
                "objectives_v1",
            ]
            space = _space(
                base,
                max_candidates=2,
                axes=[
                    {
                        "id": "payload",
                        "choices": [
                            {
                                "id": "overload",
                                "operations": [
                                    {
                                        "target": "quantity:Q-PAYLOAD.value",
                                        "value": {"value": 3.0, "unit": "kg"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
                objectives=[
                    {"id": "mass", "source": "quantity:Q-PAYLOAD", "direction": "min"}
                ],
                repair_rules=[
                    {
                        "id": "reduce-payload",
                        "diagnostic_code": "LOAD.HIGH",
                        "owner_prefix": "component:CMP-BASE-MOTOR-L",
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": 1.0, "unit": "kg"},
                            }
                        ],
                        "max_applications": 1,
                    }
                ],
                evaluation={"max_stage_evaluations": 10, "stages": stages},
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            scheduler = ControlledScheduler.instances[-1]
            self.assertEqual(tuple(stages), scheduler.calls[1][1])
            children = [item for item in result["candidates"] if item["parent_id"]]
            self.assertEqual(1, len(children))
            child_id = children[0]["candidate_id"]
            self.assertTrue((root / "out" / "candidates" / child_id / "objectives.json").is_file())
            self.assertEqual("accepted", children[0]["status"])

    def test_repair_reserves_candidate_and_stage_budget_for_future_nominals(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            base["quantities"][0]["owner"] = "component:CMP-BASE-MOTOR-L"
            choices = []
            for identifier, mass in (("overload-a", 3.0), ("overload-b", 4.0)):
                choices.append(
                    {
                        "id": identifier,
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": mass, "unit": "kg"},
                            }
                        ],
                    }
                )
            space = _space(
                base,
                max_candidates=2,
                axes=[{"id": "payload", "choices": choices}],
                repair_rules=[
                    {
                        "id": "reduce-payload",
                        "diagnostic_code": "LOAD.HIGH",
                        "owner_prefix": "component:CMP-BASE-MOTOR-L",
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": 1.0, "unit": "kg"},
                            }
                        ],
                        "max_applications": 1,
                    }
                ],
                evaluation={
                    "max_stage_evaluations": 4,
                    "stages": ["contract_v1", "physical_v030"],
                },
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            self.assertEqual(2, result["candidate_count"])
            self.assertEqual(4, result["metadata"]["stage_evaluations"])
            self.assertEqual([], [item for item in result["candidates"] if item["parent_id"]])
            skipped = list((root / "out" / "candidates").glob("*/repair-skipped.json"))
            self.assertTrue(skipped)
            self.assertIn("budget", skipped[0].read_text(encoding="utf-8"))

    def test_repair_reserves_every_declared_child_stage(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            base["quantities"][0]["owner"] = "component:CMP-BASE-MOTOR-L"
            stages = [
                "contract_v1",
                "physical_v030",
                "uncertainty_v1",
                "counterexample_v1",
                "objectives_v1",
            ]
            space = _space(
                base,
                max_candidates=2,
                axes=[
                    {
                        "id": "payload",
                        "choices": [
                            {
                                "id": "overload",
                                "operations": [
                                    {
                                        "target": "quantity:Q-PAYLOAD.value",
                                        "value": {"value": 3.0, "unit": "kg"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
                repair_rules=[
                    {
                        "id": "reduce-payload",
                        "diagnostic_code": "LOAD.HIGH",
                        "owner_prefix": "component:CMP-BASE-MOTOR-L",
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": 1.0, "unit": "kg"},
                            }
                        ],
                        "max_applications": 1,
                    }
                ],
                evaluation={"max_stage_evaluations": 6, "stages": stages},
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            self.assertEqual(1, result["candidate_count"])
            skipped = next(
                (root / "out" / "candidates").glob("*/repair-skipped.json")
            )
            record = json.loads(skipped.read_text(encoding="utf-8"))
            self.assertEqual(5, record["required_stage_evaluations"])

    def test_repaired_child_must_pass_the_same_hard_uncertainty_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = valid_contract()
            base["quantities"][0]["owner"] = "component:CMP-BASE-MOTOR-L"
            space = _space(
                base,
                max_candidates=2,
                axes=[
                    {
                        "id": "payload",
                        "choices": [
                            {
                                "id": "overload",
                                "operations": [
                                    {
                                        "target": "quantity:Q-PAYLOAD.value",
                                        "value": {"value": 3.0, "unit": "kg"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
                uncertainties=[
                    {
                        "id": "payload",
                        "target": "quantity:Q-PAYLOAD.value",
                        "values": [{"value": 3.0, "unit": "kg"}],
                        "hard": True,
                    }
                ],
                objectives=[
                    {"id": "mass", "source": "quantity:Q-PAYLOAD", "direction": "min"}
                ],
                repair_rules=[
                    {
                        "id": "reduce-payload",
                        "diagnostic_code": "LOAD.HIGH",
                        "owner_prefix": "component:CMP-BASE-MOTOR-L",
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": 1.0, "unit": "kg"},
                            }
                        ],
                        "max_applications": 1,
                    }
                ],
                evaluation={
                    "max_stage_evaluations": 10,
                    "stages": ["contract_v1", "physical_v030"],
                },
            )
            path = _write_inputs(root, base, space)
            with mock.patch(
                "assurance.hypothesis.engine.HypothesisScheduler",
                ControlledScheduler,
            ):
                result = run_space(path, root / "out", seed=1)
            child = next(item for item in result["candidates"] if item["parent_id"])
            self.assertEqual("rejected", child["status"])
            self.assertEqual(0, result["accepted_count"])
            child_root = root / "out" / "candidates" / child["candidate_id"]
            self.assertTrue((child_root / "counterexample.json").is_file())
            objective = json.loads((child_root / "objectives.json").read_text(encoding="utf-8"))
            self.assertFalse(objective["eligible"])


if __name__ == "__main__":
    unittest.main()
