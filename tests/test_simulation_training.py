import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.replay_features import (  # noqa: E402
    ReplayFeatureError,
    extract_replay_features,
)
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


def replay(*, trace_sha256="d" * 64, status="passed", final_error=0.001):
    return {
        "scenario_id": "scenario-01",
        "status": status,
        "evidence_level": "simulated",
        "model_sha256": "a" * 64,
        "trajectory_sha256": "b" * 64,
        "environment_sha256": "c" * 64,
        "trace_sha256": trace_sha256,
        "joint_order": ["joint-1", "joint-2"],
        "samples": [
            {"timestamp_ns": 0, "positions": [0.0, 0.0], "state": {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}},
            {"timestamp_ns": 500_000_000, "positions": [0.0005, 0.0005], "state": {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}},
            {"timestamp_ns": 1_000_000_000, "positions": [final_error, final_error], "state": {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}},
        ],
        "metrics": [
            {"name": "elapsed_time", "unit": "s", "status": "passed", "value": 1.0, "limit": 1.0, "details": {}},
            {"name": "final_joint_error", "unit": "rad", "status": "passed", "value": final_error, "limit": 0.01, "details": {}},
        ],
        "diagnostics": [],
    }


def assignments(*, final_error=0.001):
    return [
        {"phase": phase, "seed": seed, "fault_id": fault_id, "replay": replay(trace_sha256=f"{index:064x}", final_error=final_error)}
        for index, (phase, seed, fault_id) in enumerate(
            [("train", 1, None), ("train", 2, None), ("evaluation", 3, None), ("evaluation", 4, None), ("held_out", 3, "fault-stop"), ("held_out", 4, "fault-stop")],
            start=1,
        )
    ]


class TrainingTests(unittest.TestCase):
    def test_extracts_replay_features_without_trusting_callback_outcomes(self):
        features = extract_replay_features(replay())
        self.assertEqual("d" * 64, features.trace_sha256)
        self.assertEqual(("joint-1", "joint-2"), features.joint_order)
        self.assertEqual(1.0, features.elapsed_time_s)
        self.assertEqual(1.0, features.left_wheel_travel_rad)
        self.assertEqual(1.0, features.right_wheel_travel_rad)
        self.assertEqual(1.0, features.wheel_effort_rad2_s)
        self.assertEqual(0.001, features.final_joint_error_rad)
        self.assertEqual([0.001, 0.001], features.observation["joint_rad"])

    def test_replay_feature_extractor_rejects_invalid_trace_outcomes(self):
        attacks = (
            (lambda value: value["samples"][1]["state"].pop("left_wheel_rad_s"), "wheel"),
            (lambda value: value["samples"][1].__setitem__("timestamp_ns", 100_000_000), "sample period"),
            (lambda value: value["samples"][1]["state"].__setitem__("right_wheel_rad_s", float("inf")), "finite"),
            (lambda value: value["metrics"].append(value["metrics"][0].copy()), "duplicate"),
            (lambda value: value.__setitem__("status", "failed"), "passed"),
            (lambda value: value.__setitem__("evidence_level", "claimed_hardware"), "evidence"),
            (lambda value: value.__setitem__("environment_sha256", "not-a-sha"), "environment"),
            (lambda value: value["metrics"][1].__setitem__("value", -0.01), "final_joint_error"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected):
                value = replay()
                mutate(value)
                with self.assertRaisesRegex(ReplayFeatureError, expected):
                    extract_replay_features(value)

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


if __name__ == "__main__":
    unittest.main()
