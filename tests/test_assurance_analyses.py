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


def load_envelope_inputs():
    return {
        "joint_order": ["joint_1"],
        "joints": [
            {
                "id": "joint_1",
                "parent": "base_link",
                "child": "arm_link_1",
                "origin_xyz_m": [0.0, 0.0, 0.0],
                "origin_rpy_rad": [0.0, 0.0, 0.0],
                "axis_xyz": [0.0, 1.0, 0.0],
            }
        ],
        "links": [
            {"id": "arm_link_1", "mass_kg": 2.0, "com_xyz_m": [1.0, 0.0, 0.0]}
        ],
        "payload": {
            "mass_kg": 0.0,
            "parent": "arm_link_1",
            "origin_xyz_m": [0.0, 0.0, 0.0],
        },
        "load_cases": [
            {
                "id": "LC-HORIZONTAL",
                "joint_positions_rad": [0.0],
                "gravity_xyz_m_s2": [0.0, 0.0, -9.80665],
            },
            {
                "id": "LC-VERTICAL",
                "joint_positions_rad": [math.pi / 2.0],
                "gravity_xyz_m_s2": [0.0, 0.0, -9.80665],
            },
        ],
        "continuous_safety_factor": 1.5,
        "brake_safety_factor": 2.0,
        "rated_continuous_torque_nm": [{"id": "joint_1", "value": 40.0}],
        "brake_holding_torque_nm": [{"id": "joint_1", "value": 40.0}],
        "motor_continuous_torque_nm": [{"id": "joint_1", "value": 4.0}],
        "reducer_gear_ratio": [{"id": "joint_1", "value": 10.0}],
        "reducer_efficiency": [{"id": "joint_1", "value": 0.8}],
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

    def test_drivetrain_rejects_unmodelled_downhill_braking_regime(self):
        inputs = drivetrain_inputs()
        inputs["acceleration_m_s2"] = 0.0
        inputs["slope_rad"] = math.radians(-10.0)
        result = run_plugin("drivetrain_v1", inputs)
        self.assertTrue(
            any(item.code == "PHY.DRIVE.BRAKING_REGIME" for item in result.diagnostics)
        )
        self.assertFalse(result.passed)

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
                "com_height_m": 0.5,
                "slope_x_rad": 0.0,
                "slope_y_rad": 0.0,
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

    def test_increasing_slope_cannot_increase_static_tip_margin(self):
        inputs = {
            "support_min_x_m": -0.3,
            "support_max_x_m": 0.3,
            "support_min_y_m": -0.25,
            "support_max_y_m": 0.25,
            "com_x_m": 0.0,
            "com_y_m": 0.0,
            "com_height_m": 0.5,
            "slope_x_rad": 0.0,
            "slope_y_rad": 0.0,
        }
        level = run_plugin("stability_v1", inputs)
        inputs["slope_x_rad"] = math.radians(10.0)
        sloped = run_plugin("stability_v1", inputs)
        self.assertLess(
            sloped.outputs["static_margin_m"], level.outputs["static_margin_m"]
        )
        self.assertGreater(sloped.outputs["projected_com_x_m"], 0.0)

    def test_slope_uses_worst_direction_for_off_center_com(self):
        inputs = {
            "support_min_x_m": -0.3,
            "support_max_x_m": 0.3,
            "support_min_y_m": -0.3,
            "support_max_y_m": 0.3,
            "com_x_m": -0.2,
            "com_y_m": 0.0,
            "com_height_m": 0.5,
            "slope_x_rad": 0.0,
            "slope_y_rad": 0.0,
        }
        level = run_plugin("stability_v1", inputs)
        inputs["slope_x_rad"] = 0.1
        sloped = run_plugin("stability_v1", inputs)
        self.assertLess(sloped.outputs["static_margin_m"], level.outputs["static_margin_m"])
        self.assertLess(sloped.outputs["projected_com_x_m"], inputs["com_x_m"])

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

    def test_arm_load_envelope_calculates_pose_dependent_static_torque(self):
        result = run_plugin("arm_load_envelope_v1", load_envelope_inputs())
        joint = result.outputs["joints"][0]
        self.assertAlmostEqual(joint["maximum_gravity_torque_nm"], 19.6133)
        self.assertEqual(joint["worst_case_id"], "LC-HORIZONTAL")
        self.assertAlmostEqual(joint["continuous_required_torque_nm"], 29.41995)
        self.assertAlmostEqual(joint["brake_required_torque_nm"], 39.2266)
        per_case = {item["id"]: item["gravity_torque_nm"] for item in joint["cases"]}
        self.assertAlmostEqual(per_case["LC-HORIZONTAL"], 19.6133)
        self.assertAlmostEqual(per_case["LC-VERTICAL"], 0.0, places=10)
        self.assertTrue(result.passed)

    def test_arm_load_envelope_screens_motor_reducer_transmission(self):
        inputs = load_envelope_inputs()
        inputs.update(
            {
                "motor_continuous_torque_nm": [{"id": "joint_1", "value": 4.0}],
                "reducer_gear_ratio": [{"id": "joint_1", "value": 10.0}],
                "reducer_efficiency": [{"id": "joint_1", "value": 0.8}],
            }
        )
        result = run_plugin("arm_load_envelope_v1", inputs)
        joint = result.outputs["joints"][0]
        self.assertAlmostEqual(joint["motor_continuous_required_torque_nm"], 29.41995 / 10.0 / 0.8)
        self.assertAlmostEqual(joint["motor_continuous_margin_nm"], 4.0 - 29.41995 / 10.0 / 0.8)
        self.assertTrue(result.passed)

        inputs["motor_continuous_torque_nm"][0]["value"] = 3.0
        overloaded = run_plugin("arm_load_envelope_v1", inputs)
        self.assertIn("PHY.ARM.MOTOR_CONTINUOUS_TORQUE", {item.code for item in overloaded.diagnostics})

        inputs["reducer_efficiency"][0]["value"] = 0.0
        invalid = run_plugin("arm_load_envelope_v1", inputs)
        self.assertIn("PHY.ARM.TRANSMISSION_DOMAIN", {item.code for item in invalid.diagnostics})

    def test_arm_load_envelope_increasing_downstream_mass_cannot_reduce_demand(self):
        baseline = run_plugin("arm_load_envelope_v1", load_envelope_inputs())
        heavier = load_envelope_inputs()
        heavier["links"][0]["mass_kg"] = 3.0
        increased = run_plugin("arm_load_envelope_v1", heavier)
        self.assertGreater(
            increased.outputs["joints"][0]["maximum_gravity_torque_nm"],
            baseline.outputs["joints"][0]["maximum_gravity_torque_nm"],
        )

    def test_arm_load_envelope_rejects_bad_axis_and_finite_extremes(self):
        bad_axis = load_envelope_inputs()
        bad_axis["joints"][0]["axis_xyz"] = [0.0, 0.0, 0.0]
        bad_result = run_plugin("arm_load_envelope_v1", bad_axis)
        self.assertFalse(bad_result.passed)
        self.assertTrue(any(item.code == "PHY.INPUT.DOMAIN" for item in bad_result.diagnostics))

        extreme = load_envelope_inputs()
        extreme["links"][0]["mass_kg"] = 1e308
        extreme["links"][0]["com_xyz_m"] = [1e308, 0.0, 0.0]
        extreme_result = run_plugin("arm_load_envelope_v1", extreme)
        self.assertFalse(extreme_result.passed)
        self.assertEqual(extreme_result.outputs, {})
        self.assertTrue(any(item.code == "PHY.NUMERIC.OVERFLOW" for item in extreme_result.diagnostics))

    def test_bearing_static_equivalent_load_checks_force_moment_and_safety_factor(self):
        inputs = {
            "joints": [
                {
                    "id": "joint_2",
                    "radial_load_n": 1000.0,
                    "axial_load_n": 500.0,
                    "moment_nm": 100.0,
                    "pitch_diameter_m": 0.1,
                    "static_load_rating_n": 10000.0,
                    "safety_factor": 2.0,
                }
            ]
        }
        result = run_plugin("bearing_static_v1", inputs)
        joint = result.outputs["joints"][0]
        self.assertAlmostEqual(3220.0, joint["static_equivalent_load_n"])
        self.assertAlmostEqual(6440.0, joint["required_static_load_n"])
        self.assertAlmostEqual(3560.0, joint["static_margin_n"])
        self.assertTrue(result.passed)

        overloaded = run_plugin(
            "bearing_static_v1",
            {"joints": [{**inputs["joints"][0], "static_load_rating_n": 6000.0}]},
        )
        self.assertFalse(overloaded.passed)
        self.assertIn(
            "PHY.BEARING.STATIC_LOAD",
            {item.code for item in overloaded.diagnostics},
        )

    def test_component_mass_closure_detects_omission_and_double_count(self):
        inputs = {
            "links": [
                {
                    "id": "arm_link_2",
                    "link_mass_kg": 10.0,
                    "structural_residual_mass_kg": 2.0,
                    "components": [
                        {"id": "CMP-BRAKE-J2", "mass_kg": 3.0},
                        {"id": "CMP-DRIVER-J2", "mass_kg": 5.0},
                    ],
                }
            ]
        }
        result = run_plugin("component_mass_closure_v1", inputs)
        link = result.outputs["links"][0]
        self.assertTrue(result.passed)
        self.assertEqual(link["component_mass_kg"], 8.0)
        self.assertEqual(link["closure_margin_kg"], 0.0)

        duplicate_across_links = {
            "links": [
                inputs["links"][0],
                {
                    "id": "arm_link_3",
                    "link_mass_kg": 5.0,
                    "structural_residual_mass_kg": 2.0,
                    "components": [{"id": "CMP-BRAKE-J2", "mass_kg": 3.0}],
                },
            ]
        }
        duplicated = run_plugin("component_mass_closure_v1", duplicate_across_links)
        self.assertFalse(duplicated.passed)
        self.assertIn("PHY.INPUT.TYPE", {item.code for item in duplicated.diagnostics})

        inputs["links"][0]["link_mass_kg"] = 9.0
        mismatched = run_plugin("component_mass_closure_v1", inputs)
        self.assertFalse(mismatched.passed)
        self.assertIn(
            "PHY.MASS.CLOSURE", {item.code for item in mismatched.diagnostics}
        )

        inputs["links"][0]["link_mass_kg"] = float("inf")
        nonfinite = run_plugin("component_mass_closure_v1", inputs)
        self.assertFalse(nonfinite.passed)
        self.assertTrue(nonfinite.diagnostics)

    def test_missing_and_invalid_inputs_are_fail_closed_not_tracebacks(self):
        missing = run_plugin("drivetrain_v1", {"base_mass_kg": 10.0})
        self.assertTrue(any(item.severity == "indeterminate" for item in missing.diagnostics))
        invalid = drivetrain_inputs()
        invalid["efficiency"] = 0.0
        result = run_plugin("drivetrain_v1", invalid)
        self.assertTrue(any(item.code == "PHY.INPUT.DOMAIN" for item in result.diagnostics))

    def test_thermal_duty_checks_steady_state_winding_margin(self):
        inputs = {
            "ambient_temperature_k": 298.15,
            "winding_resistance_ohm": 0.5,
            "on_current_a": 10.0,
            "duty_cycle": 0.5,
            "thermal_resistance_k_per_w": 2.0,
            "max_winding_temperature_k": 373.15,
        }
        result = run_plugin("thermal_duty_v1", inputs)
        self.assertAlmostEqual(result.outputs["copper_loss_w"], 25.0)
        self.assertAlmostEqual(
            result.outputs["estimated_steady_state_temperature_k"], 348.15
        )
        self.assertAlmostEqual(result.outputs["temperature_margin_k"], 25.0)
        self.assertTrue(result.passed)

        inputs["on_current_a"] = 20.0
        overloaded = run_plugin("thermal_duty_v1", inputs)
        self.assertTrue(
            any(
                item.code == "PHY.THERMAL.WINDING_OVER_TEMPERATURE"
                for item in overloaded.diagnostics
            )
        )

    def test_thermal_duty_rejects_current_above_driver_continuous_rating(self):
        result = run_plugin(
            "thermal_duty_v1",
            {
                "ambient_temperature_k": 298.15,
                "winding_resistance_ohm": 0.1,
                "on_current_a": 10.0,
                "driver_continuous_current_a": 6.0,
                "duty_cycle": 0.1,
                "thermal_resistance_k_per_w": 1.0,
                "max_winding_temperature_k": 373.15,
            },
        )
        self.assertFalse(result.passed)
        self.assertIn(
            "PHY.THERMAL.DRIVER_CONTINUOUS_CURRENT",
            {item.code for item in result.diagnostics},
        )

    def test_finite_extremes_fail_closed_without_nonfinite_outputs(self):
        thermal = {
            "ambient_temperature_k": 300.0,
            "winding_resistance_ohm": 1e308,
            "on_current_a": 1e308,
            "duty_cycle": 1.0,
            "thermal_resistance_k_per_w": 1e308,
            "max_winding_temperature_k": 400.0,
        }
        drive = drivetrain_inputs()
        drive["base_mass_kg"] = 1e308
        drive["wheel_radius_m"] = 1e308
        battery = {
            "voltage_v": 1e-308,
            "peak_power_w": 1e308,
            "continuous_power_w": 1e308,
            "max_continuous_current_a": 1e308,
            "max_peak_current_a": 1e308,
            "usable_energy_j": 1e308,
            "required_runtime_s": 1.0,
        }
        stability = {
            "support_min_x_m": -1e308,
            "support_max_x_m": 1e308,
            "support_min_y_m": -1e308,
            "support_max_y_m": 1e308,
            "com_x_m": 1e308,
            "com_y_m": 0.0,
            "com_height_m": 1e308,
            "slope_x_rad": 1.0,
            "slope_y_rad": 0.0,
        }
        arm = {
            "joints": [
                {
                    "id": "joint_1",
                    "loads": [{"mass_kg": 1e308, "horizontal_lever_m": 1e308}],
                    "rated_continuous_torque_nm": 1e308,
                    "brake_holding_torque_nm": 1e308,
                    "safety_factor": 1e308,
                }
            ]
        }
        cases = (
            ("thermal_duty_v1", thermal),
            ("drivetrain_v1", drive),
            ("battery_v1", battery),
            ("stability_v1", stability),
            ("arm_gravity_v1", arm),
        )
        for plugin, inputs in cases:
            with self.subTest(plugin=plugin):
                result = run_plugin(plugin, inputs)
                self.assertFalse(result.passed)
                self.assertEqual(result.outputs, {})
                self.assertTrue(any(item.code == "PHY.NUMERIC.OVERFLOW" for item in result.diagnostics))

    def test_unknown_plugin_is_indeterminate(self):
        result = run_plugin("imaginary_solver", {})
        self.assertTrue(any(item.code == "PHY.PLUGIN.UNKNOWN" for item in result.diagnostics))


if __name__ == "__main__":
    unittest.main()
