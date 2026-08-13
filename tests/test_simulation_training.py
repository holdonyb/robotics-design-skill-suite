import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.training import TrainingError, evaluate_policy, validate_training_contract  # noqa: E402


SHA_A = "a" * 64


def contract():
    return {
        "schema_version": 1, "contract_id": "training-reference-v1", "artifact_sha256": SHA_A,
        "observation": {"frame": "base_link", "unit": "si", "rate_hz": 20, "fields": ["scan_m", "joint_rad"]},
        "action": {"frame": "base_link", "unit": "si", "rate_hz": 20, "fields": ["linear_m_s", "angular_rad_s"]},
        "reward_weights": {"progress": 1.0, "energy": -0.1},
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


class TrainingTests(unittest.TestCase):
    def test_contract_is_closed_and_policy_stays_simulated_with_firewall(self):
        self.assertEqual([], validate_training_contract(contract()))
        physical = physical_receipt()
        def policy(observation):
            observation["scan_m"] = 999
            return {"linear_m_s": 0.2, "angular_rad_s": 0.1}
        result = evaluate_policy(contract(), policy, physical)
        self.assertEqual("simulated", result.evidence_level)
        self.assertEqual("not_justified", result.status)
        self.assertEqual(("BOM.PLACEHOLDER_BLOCKS_CLAIM",), result.physical_blockers)
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
                    evaluate_policy(contract(), callback, physical_receipt())

    def test_physical_blocker_receipt_is_required_and_can_never_authorize_hardware(self):
        callback = lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}
        for physical, expected in (
            ({"remaining_blockers": [], "hardware_promotable": False}, "blockers"),
            ({"remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"], "hardware_promotable": True}, "hardware"),
            ({"remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"], "hardware_promotable": False, "extra": 1}, "fields"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(TrainingError, expected):
                    evaluate_policy(contract(), callback, physical)

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
        first = evaluate_policy(contract(), callback, physical_receipt())
        second = evaluate_policy(contract(), callback, physical_receipt())
        self.assertEqual(first.policy_id, second.policy_id)
        self.assertEqual(("BOM.PLACEHOLDER_BLOCKS_CLAIM",), first.physical_blockers)


if __name__ == "__main__":
    unittest.main()
