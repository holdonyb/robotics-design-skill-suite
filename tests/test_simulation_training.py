import copy
import sys
import unittest
from pathlib import Path
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.replay_features import (  # noqa: E402
    ReplayFeatureError,
    extract_replay_features,
)
from assurance.simulation.model import MetricResult, ScenarioSpec, SimulationResult, TraceSample  # noqa: E402
from assurance.simulation.scenario import CompiledScenario  # noqa: E402
from assurance.simulation.training import TrainingError, evaluate_policy, validate_training_contract  # noqa: E402


SHA_A = "a" * 64


def contract():
    return {
        "schema_version": 1, "contract_id": "training-reference-v1", "artifact_sha256": SHA_A,
        "observation": {"frame": "base_link", "unit": "si", "rate_hz": 20, "fields": ["joint_rad", "left_wheel_rad_s", "right_wheel_rad_s"]},
        "action": {"frame": "base_link", "unit": "si", "rate_hz": 20, "fields": ["linear_m_s", "angular_rad_s"]},
        "reward_weights": {"wheel_progress": 1.0, "wheel_effort": -0.1}, "baseline_mean_reward": 0.0,
        "hard_constraints": {"max_linear_m_s": 0.4, "max_angular_rad_s": 0.8, "max_joint_error_rad": 0.02},
        "budgets": {"episodes": 10, "steps": 1000, "wall_time_s": 60, "memory_mb": 256},
        "train_seeds": [1, 2], "evaluation_seeds": [3, 4],
        "randomization": {"owner": "uncertainty_v1", "friction": {"lower": 0.4, "upper": 0.8}},
        "held_out_faults": ["fault-stop"],
        "physical_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"],
    }


def physical_receipt():
    return {
        "remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"],
        "hardware_promotable": False,
    }


def scenario(*, scenario_id="scenario-01", seed=1, fault_id=None):
    faults = () if fault_id is None else ({"fault_id": fault_id, "at_ns": 500_000_000},)
    spec = ScenarioSpec(
        scenario_id, "v1", "a" * 64, "b" * 64, "c" * 64, seed,
        1_000_000_000, ("joint-1", "joint-2"), {}, faults,
    )
    return CompiledScenario(
        spec,
        (
            MappingProxyType({"name": "elapsed_time", "unit": "s", "direction": "max", "limit": 1.0}),
            MappingProxyType({"name": "final_joint_error", "unit": "rad", "direction": "max", "limit": 0.01}),
        ),
        MappingProxyType({"reason": "duration_elapsed", "at_ns": 1_000_000_000}), "e" * 64,
    )


def replay(*, scenario_value=None, trace_sha256="d" * 64, status="passed", final_error=0.001, metric_error=None):
    scenario_value = scenario_value or scenario()
    metric_error = final_error if metric_error is None else metric_error
    return SimulationResult(
        scenario_value.scenario_id, status, "simulated", "a" * 64, "b" * 64, "c" * 64,
        trace_sha256, ("joint-1", "joint-2"),
        (
            TraceSample(0, (0.0, 0.0), {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
            TraceSample(500_000_000, (0.0005, 0.0005), {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
            TraceSample(1_000_000_000, (final_error, final_error), {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
        ),
        (
            MetricResult("elapsed_time", "s", "passed", 1.0, 1.0, {}),
            MetricResult("final_joint_error", "rad", "passed", metric_error, 0.01, {}),
        ), (),
    )


def assignments(*, final_error=0.001):
    cases = [
        ("train", 1, None), ("train", 2, None), ("evaluation", 3, None),
        ("evaluation", 4, None), ("held_out", 3, "fault-stop"), ("held_out", 4, "fault-stop"),
    ]
    return [
        {
            "phase": phase, "seed": seed, "fault_id": fault_id,
            "scenario": scenario(scenario_id=f"scenario-{index:02d}", seed=seed, fault_id=fault_id),
            "replay": replay(
                scenario_value=scenario(scenario_id=f"scenario-{index:02d}", seed=seed, fault_id=fault_id),
                trace_sha256=f"{index:064x}", final_error=final_error,
            ),
        }
        for index, (phase, seed, fault_id) in enumerate(cases, start=1)
    ]


class TrainingTests(unittest.TestCase):
    def test_extracts_features_only_from_validated_result_and_recomputes_joint_error(self):
        features = extract_replay_features(replay())
        self.assertEqual("d" * 64, features.trace_sha256)
        self.assertEqual(("joint-1", "joint-2"), features.joint_order)
        self.assertEqual(1.0, features.elapsed_time_s)
        self.assertEqual(1.0, features.left_wheel_travel_rad)
        self.assertEqual(1.0, features.right_wheel_travel_rad)
        self.assertEqual(1.0, features.wheel_effort_rad2_s)
        self.assertEqual(0.001, features.final_joint_error_rad)
        self.assertEqual([0.001, 0.001], features.observation["joint_rad"])
        with self.assertRaisesRegex(ReplayFeatureError, "SimulationResult"):
            extract_replay_features({"samples": []})
        with self.assertRaisesRegex(ReplayFeatureError, "final_joint_error"):
            extract_replay_features(replay(final_error=0.1, metric_error=0.001))

    def test_replay_feature_extractor_rejects_invalid_trace_outcomes(self):
        with self.assertRaisesRegex(ReplayFeatureError, "passed"):
            extract_replay_features(replay(status="failed"))

    def test_contract_is_closed_and_policy_stays_simulated_with_firewall(self):
        self.assertEqual([], validate_training_contract(contract()))
        physical = physical_receipt()
        def policy(observation):
            observation["joint_rad"][0] = 999
            return {"linear_m_s": 0.2, "angular_rad_s": 0.1}
        result = evaluate_policy(contract(), policy, physical, assignments())
        self.assertEqual("simulated", result.evidence_level)
        self.assertEqual("not_justified", result.status)
        self.assertEqual(("BOM.PLACEHOLDER_BLOCKS_CLAIM",), result.physical_blockers)
        self.assertEqual(6, result.evaluation_count)
        self.assertEqual(2, result.held_out_evaluation_count)
        self.assertNotIn("hardware_promotable", result.to_dict())
        self.assertEqual(physical_receipt(), physical)

    def test_rejects_schema_budget_seed_randomization_and_callback_attacks(self):
        attacks = (
            (lambda x: x.__setitem__("extra", True), "unknown"),
            (lambda x: x["budgets"].__setitem__("episodes", 0), "budgets"),
            (lambda x: x.__setitem__("evaluation_seeds", [1]), "distinct"),
            (lambda x: x["randomization"].__setitem__("owner", "policy"), "owner"),
            (lambda x: x["randomization"]["friction"].__setitem__("upper", 2.0), "randomization"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected):
                value = contract(); mutate(value)
                self.assertTrue(any(expected in item for item in validate_training_contract(value)))
        for callback, expected in (
            (lambda x: {"linear_m_s": float("nan"), "angular_rad_s": 0.0}, "finite"),
            (lambda x: {"linear_m_s": 9.0, "angular_rad_s": 0.0}, "constraint"),
            (lambda x: {"linear_m_s": 0.0}, "fields"),
            (lambda x: (_ for _ in ()).throw(RuntimeError("bad")), "callback"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(TrainingError, expected):
                    evaluate_policy(contract(), callback, physical_receipt(), assignments())

    def test_physical_blocker_receipt_is_required_and_can_never_authorize_hardware(self):
        callback = lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}
        for physical, expected in (
            ({"remaining_blockers": [], "hardware_promotable": False}, "blockers"),
            ({"remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"], "hardware_promotable": True}, "hardware"),
            ({"remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"], "hardware_promotable": False, "extra": 1}, "fields"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(TrainingError, expected):
                    evaluate_policy(contract(), callback, physical, assignments())

    def test_rejects_unbounded_or_ambiguous_contract_collections(self):
        attacks = (
            (lambda x: x["reward_weights"].__setitem__("progress", True), "reward_weights"),
            (lambda x: x["hard_constraints"].__setitem__("extra", 1.0), "hard_constraints"),
            (lambda x: x.__setitem__("held_out_faults", ["fault-stop", "fault-stop"]), "held_out_faults"),
            (lambda x: x.__setitem__("physical_blockers", []), "physical_blockers"),
            (lambda x: x["observation"].__setitem__("fields", ["scan_m", "scan_m"]), "observation"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected):
                value = contract()
                mutate(value)
                self.assertTrue(any(expected in item for item in validate_training_contract(value)))

    def test_policy_identity_and_blocker_order_are_stable(self):
        callback = lambda x: {"linear_m_s": 0.2, "angular_rad_s": -0.1}
        first = evaluate_policy(contract(), callback, physical_receipt(), assignments())
        second = evaluate_policy(contract(), callback, physical_receipt(), assignments())
        self.assertEqual(first.policy_id, second.policy_id)
        self.assertEqual(("BOM.PLACEHOLDER_BLOCKS_CLAIM",), first.physical_blockers)

    def test_executes_each_evaluation_seed_with_held_out_fault_and_baseline_comparison(self):
        seen = []

        def callback(observation):
            seen.append((observation["phase"], observation["seed"], observation["fault_id"]))
            return {"linear_m_s": 0.2, "angular_rad_s": 0.0}

        result = evaluate_policy(contract(), callback, physical_receipt(), assignments())
        self.assertEqual(
            [
                ("train", 1, None),
                ("train", 2, None),
                ("evaluation", 3, None),
                ("evaluation", 4, None),
                ("held_out", 3, "fault-stop"),
                ("held_out", 4, "fault-stop"),
            ],
            seen,
        )
        self.assertEqual(6, result.evaluation_count)
        self.assertEqual(2, result.held_out_evaluation_count)

    def test_rejects_baseline_regression_and_budget_excess(self):
        baseline = contract()
        baseline["baseline_mean_reward"] = 1.0
        with self.assertRaisesRegex(TrainingError, "baseline"):
            evaluate_policy(baseline, lambda x: {"linear_m_s": -0.1, "angular_rad_s": 0.0}, physical_receipt(), assignments())
        with self.assertRaisesRegex(TrainingError, "fields"):
            evaluate_policy(contract(), lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0, "mean_reward": 9999}, physical_receipt(), assignments())
        value = contract()
        value["budgets"]["episodes"] = 5
        with self.assertRaisesRegex(TrainingError, "episodes"):
            evaluate_policy(value, lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}, physical_receipt(), assignments())

        with self.assertRaisesRegex(TrainingError, "constraint"):
            evaluate_policy(contract(), lambda x: {"linear_m_s": 1.0, "angular_rad_s": 0.0}, physical_receipt(), assignments())

    def test_trace_derived_joint_error_and_case_assignments_are_hard_gates(self):
        callback = lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}
        with self.assertRaisesRegex(TrainingError, "joint"):
            evaluate_policy(contract(), callback, physical_receipt(), assignments(final_error=0.1))
        missing = assignments()[:-1]
        with self.assertRaisesRegex(TrainingError, "assignments"):
            evaluate_policy(contract(), callback, physical_receipt(), missing)
        duplicate = assignments()
        duplicate[-1]["seed"] = 3
        with self.assertRaisesRegex(TrainingError, "assignments"):
            evaluate_policy(contract(), callback, physical_receipt(), duplicate)

    def test_rejects_reused_trace_and_case_without_matching_scenario_provenance(self):
        callback = lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}
        duplicate = assignments()
        object.__setattr__(duplicate[-1]["replay"], "trace_sha256", duplicate[-2]["replay"].trace_sha256)
        with self.assertRaisesRegex(TrainingError, "unique"):
            evaluate_policy(contract(), callback, physical_receipt(), duplicate)
        wrong_scenario = assignments()
        wrong_scenario[-1]["scenario"] = scenario(scenario_id="scenario-other", seed=4, fault_id="fault-stop")
        with self.assertRaisesRegex(TrainingError, "scenario"):
            evaluate_policy(contract(), callback, physical_receipt(), wrong_scenario)


if __name__ == "__main__":
    unittest.main()
