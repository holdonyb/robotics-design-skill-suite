import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.backend import (  # noqa: E402
    BackendError,
    BackendMetric,
    BackendResult,
    compare_backends,
    evaluate_independent_dynamics,
    evaluate_trace_kinematics,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def case(**overrides):
    value = {
        "model_sha256": SHA_A,
        "trajectory_sha256": SHA_B,
        "units": "si",
        "timestamps_ns": [0, 1_000_000_000, 2_000_000_000],
        "left_wheel_rad_s": [1.0, 1.0, 1.0],
        "right_wheel_rad_s": [1.0, 1.0, 1.0],
        "wheel_radius_m": 0.1,
        "wheel_separation_m": 0.5,
        "wheel_speed_limit_rad_s": 2.0,
        "mass_kg": 100.0,
        "slope_rad": 0.0,
        "brake_deceleration_m_s2": 1.0,
        "joint_final_rad": [0.1, -0.2],
        "joint_target_rad": [0.1, -0.2],
        "joint_error_limit_rad": 0.01,
    }
    value.update(overrides)
    return value


class IndependentDynamicsTests(unittest.TestCase):
    def test_straight_yaw_stopping_limits_and_arm_metrics_are_calculated(self):
        straight = evaluate_independent_dynamics(case())
        self.assertEqual("passed", straight.status)
        values = {metric.name: metric.value for metric in straight.metrics}
        self.assertAlmostEqual(0.2, values["base_distance_m"])
        self.assertAlmostEqual(0.0, values["base_yaw_rad"])
        self.assertAlmostEqual(0.005, values["braking_distance_m"])
        self.assertAlmostEqual(0.0, values["final_joint_error_rad"])

        yaw = evaluate_independent_dynamics(case(left_wheel_rad_s=[-1.0] * 3, right_wheel_rad_s=[1.0] * 3))
        yaw_value = next(metric.value for metric in yaw.metrics if metric.name == "base_yaw_rad")
        self.assertAlmostEqual(0.8, yaw_value)

        failed = evaluate_independent_dynamics(case(wheel_speed_limit_rad_s=0.5, joint_final_rad=[0.2, -0.2]))
        self.assertEqual("failed", failed.status)
        self.assertEqual({"wheel_speed_rad_s", "final_joint_error_rad"}, {metric.name for metric in failed.metrics if metric.status == "failed"})

    def test_invalid_grid_nonfinite_braking_and_hashes_fail_closed(self):
        attacks = (
            ("timestamps_ns", [0, 2, 1]),
            ("timestamps_ns", [0, 1_000_000_000]),
            ("left_wheel_rad_s", [1.0, float("inf"), 1.0]),
            ("brake_deceleration_m_s2", 0.0),
            ("slope_rad", -0.1),
            ("model_sha256", "A" * 64),
            ("units", "imperial"),
        )
        for key, value in attacks:
            with self.subTest(key=key):
                with self.assertRaises(BackendError):
                    evaluate_independent_dynamics(case(**{key: value}))

    def test_cross_backend_comparison_uses_intervals_not_averages(self):
        primary = BackendResult(SHA_A, SHA_B, "passed", (
            BackendMetric("base_distance_m", "m", 0.2, 0.19, 0.21, "passed"),
            BackendMetric("final_joint_error_rad", "rad", 0.001, 0.0, 0.002, "passed"),
        ), ("level_ground",))
        agreeing = BackendResult(SHA_A, SHA_B, "passed", (
            BackendMetric("base_distance_m", "m", 0.205, 0.20, 0.21, "passed"),
            BackendMetric("final_joint_error_rad", "rad", 0.0015, 0.001, 0.003, "passed"),
        ), ("level_ground",))
        result = compare_backends(primary, agreeing, {"base_distance_m": 0.01, "final_joint_error_rad": 0.01})
        self.assertEqual("passed", result.status)
        self.assertEqual(2, len(result.metrics))

        disagreeing = BackendResult(SHA_A, SHA_B, "passed", (
            BackendMetric("base_distance_m", "m", 0.4, 0.39, 0.41, "passed"),
            BackendMetric("final_joint_error_rad", "rad", 0.0015, 0.001, 0.003, "passed"),
        ), ("level_ground",))
        self.assertEqual("failed", compare_backends(primary, disagreeing, {"base_distance_m": 0.01, "final_joint_error_rad": 0.01}).status)
        domain_mismatch = BackendResult(SHA_A, SHA_B, "passed", agreeing.metrics, ("slope",))
        self.assertEqual("indeterminate", compare_backends(primary, domain_mismatch, {"base_distance_m": 0.01, "final_joint_error_rad": 0.01}).status)

    def test_trace_primary_uses_separate_integration_before_cross_check(self):
        primary = evaluate_trace_kinematics(case(left_wheel_rad_s=[0.0, 1.0, 1.0]))
        independent = evaluate_independent_dynamics(case(left_wheel_rad_s=[0.0, 1.0, 1.0]))
        primary_distance = next(item.value for item in primary.metrics if item.name == "base_distance_m")
        independent_distance = next(item.value for item in independent.metrics if item.name == "base_distance_m")
        self.assertNotEqual(primary_distance, independent_distance)
        tolerances = {item.name: 1.0 for item in primary.metrics}
        self.assertEqual("passed", compare_backends(primary, independent, tolerances).status)


if __name__ == "__main__":
    unittest.main()
