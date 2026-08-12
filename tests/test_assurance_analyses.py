import copy
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.analyses import run_plugin  # noqa: E402


def drivetrain_inputs():
    return {
        "base_mass_kg": 90.0,
        "payload_mass_kg": 10.0,
        "rolling_resistance": 0.02,
        "slope_rad": 0.0,
        "acceleration_m_s2": 0.5,
        "wheel_radius_m": 0.1,
        "driven_wheels": 2,
        "gear_ratio": 10.0,
        "efficiency": 0.8,
        "target_speed_m_s": 1.0,
        "motor_continuous_torque_nm": 1.0,
        "motor_peak_torque_nm": 2.0,
        "motor_max_speed_rad_s": 120.0,
        "duty_cycle": 0.5,
    }


class AssuranceAnalysisTests(unittest.TestCase):
    def test_drivetrain_matches_independent_level_ground_calculation(self):
        result = run_plugin("drivetrain_v1", drivetrain_inputs())
        expected_force = 100.0 * (0.5 + 9.80665 * 0.02)
        expected_motor_torque = expected_force * 0.1 / 2.0 / 10.0 / 0.8
        self.assertAlmostEqual(result.outputs["tractive_force_n"], expected_force)
        self.assertAlmostEqual(
            result.outputs["motor_torque_nm"], expected_motor_torque
        )
        self.assertAlmostEqual(result.outputs["motor_speed_rad_s"], 100.0)
        self.assertEqual(result.evidence_level.value, "calculated")
        self.assertFalse(any(item.severity == "error" for item in result.diagnostics))

    def test_payload_slope_and_lower_efficiency_cannot_reduce_motor_demand(self):
        baseline = drivetrain_inputs()
        baseline_result = run_plugin("drivetrain_v1", baseline)
        for field, value in (
            ("payload_mass_kg", 20.0),
            ("slope_rad", math.radians(5.0)),
            ("efficiency", 0.6),
        ):
            changed = copy.deepcopy(baseline)
            changed[field] = value
            result = run_plugin("drivetrain_v1", changed)
            self.assertGreater(
                result.outputs["motor_torque_nm"],
                baseline_result.outputs["motor_torque_nm"],
                field,
            )

    def test_drivetrain_rejects_overspeed_and_continuous_overload(self):
        inputs = drivetrain_inputs()
        inputs["motor_continuous_torque_nm"] = 0.1
        inputs["motor_max_speed_rad_s"] = 80.0
        result = run_plugin("drivetrain_v1", inputs)
        codes = {item.code for item in result.diagnostics}
        self.assertIn("PHY.DRIVE.CONTINUOUS_TORQUE", codes)
        self.assertIn("PHY.DRIVE.OVERSPEED", codes)

    def test_battery_power_current_and_runtime_are_calculated(self):
        result = run_plugin(
            "battery_v1",
            {
                "voltage_v": 48.0,
                "peak_power_w": 2400.0,
                "continuous_power_w": 500.0,
                "max_continuous_current_a": 60.0,
                "max_peak_current_a": 80.0,
                "usable_energy_j": 3_600_000.0,
                "required_runtime_s": 3600.0,
            },
        )
        self.assertEqual(result.outputs["peak_current_a"], 50.0)
        self.assertEqual(result.outputs["continuous_current_a"], 500.0 / 48.0)
        self.assertEqual(result.outputs["estimated_runtime_s"], 7200.0)
        self.assertFalse(any(item.severity == "error" for item in result.diagnostics))

    def test_less_usable_energy_cannot_increase_runtime(self):
        inputs = {
            "voltage_v": 48.0,
            "peak_power_w": 1000.0,
            "continuous_power_w": 500.0,
            "max_continuous_current_a": 30.0,
            "max_peak_current_a": 40.0,
            "usable_energy_j": 3_600_000.0,
            "required_runtime_s": 1000.0,
        }
        baseline = run_plugin("battery_v1", inputs)
        inputs["usable_energy_j"] /= 2.0
        reduced = run_plugin("battery_v1", inputs)
        self.assertLess(
            reduced.outputs["estimated_runtime_s"],
            baseline.outputs["estimated_runtime_s"],
        )

    def test_static_stability_margin_is_signed(self):
        inside = run_plugin(
            "stability_v1",
            {
                "support_min_x_m": -0.3,
                "support_max_x_m": 0.3,
                "support_min_y_m": -0.25,
                "support_max_y_m": 0.25,
                "com_x_m": 0.1,
                "com_y_m": 0.0,
            },
        )
        self.assertAlmostEqual(inside.outputs["static_margin_m"], 0.2)
        outside_inputs = dict(inside.inputs)
        outside_inputs["com_x_m"] = 0.35
        outside = run_plugin("stability_v1", outside_inputs)
        self.assertAlmostEqual(outside.outputs["static_margin_m"], -0.05)
        self.assertTrue(
            any(item.code == "PHY.STABILITY.OUTSIDE_SUPPORT" for item in outside.diagnostics)
        )

    def test_arm_gravity_and_brake_holding_torque_are_checked(self):
        result = run_plugin(
            "arm_gravity_v1",
            {
                "joints": [
                    {
                        "id": "joint_2",
                        "loads": [
                            {"mass_kg": 2.0, "horizontal_lever_m": 0.5},
                            {"mass_kg": 1.0, "horizontal_lever_m": 0.8},
                        ],
                        "rated_continuous_torque_nm": 20.0,
                        "brake_holding_torque_nm": 10.0,
                        "safety_factor": 1.5,
                    }
                ]
            },
        )
        expected = 9.80665 * (2.0 * 0.5 + 1.0 * 0.8)
        self.assertAlmostEqual(result.outputs["joints"][0]["gravity_torque_nm"], expected)
        codes = {item.code for item in result.diagnostics}
        self.assertIn("PHY.ARM.CONTINUOUS_TORQUE", codes)
        self.assertIn("PHY.ARM.BRAKE_HOLDING", codes)

    def test_missing_and_invalid_inputs_are_fail_closed_not_tracebacks(self):
        missing = run_plugin("drivetrain_v1", {"base_mass_kg": 10.0})
        self.assertTrue(any(item.severity == "indeterminate" for item in missing.diagnostics))
        invalid = drivetrain_inputs()
        invalid["efficiency"] = 0.0
        result = run_plugin("drivetrain_v1", invalid)
        self.assertTrue(any(item.code == "PHY.INPUT.DOMAIN" for item in result.diagnostics))

    def test_unknown_plugin_is_indeterminate(self):
        result = run_plugin("imaginary_solver", {})
        self.assertTrue(any(item.code == "PHY.PLUGIN.UNKNOWN" for item in result.diagnostics))


if __name__ == "__main__":
    unittest.main()
