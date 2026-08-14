import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

import validate_simulation_bundle as simulation_bundle  # noqa: E402
from validate_simulation_bundle import (  # noqa: E402
    BenchmarkError,
    _backend_input,
    _load_backend_profile,
    run_reference_benchmark,
)


class ReferenceSimulationTests(unittest.TestCase):
    def test_backend_profile_is_extracted_from_bound_ros_workspace(self):
        profile = _load_backend_profile(ROOT / "reference" / "mobile-manipulator")
        self.assertEqual(0.15, profile["wheel_radius_m"])
        self.assertEqual(0.68, profile["wheel_separation_m"])
        self.assertEqual(140.2, profile["mass_kg"])
        self.assertEqual(0.8, profile["brake_deceleration_m_s2"])
        self.assertAlmostEqual(0.4 / 0.15, profile["wheel_speed_limit_rad_s"])
        self.assertIn(
            "ros2_ws/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro",
            [item["path"] for item in profile["sources"]],
        )
        self.assertNotIn(
            "ros2_ws/src/jx_mobile_manipulator_moveit_config/config/reference_mobile_manipulator.urdf",
            [item["path"] for item in profile["sources"]],
        )

    def test_reference_benchmark_is_admitted_replayable_and_never_hardware_promotable(self):
        report = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")
        self.assertEqual("simulation_admitted", report["admission"]["status"])
        self.assertFalse(report["admission"]["hardware_promotable"])
        self.assertEqual(10, report["scenario_count"])
        self.assertEqual(10, report["passed_scenarios"])
        self.assertEqual("passed", report["independent_backend"]["status"])
        self.assertEqual("simulated", report["calibration"]["evidence_level"])
        self.assertEqual("simulated", report["training"]["evidence_level"])
        self.assertEqual("not_justified", report["training"]["status"])
        self.assertNotIn("hardware_promotable", report["training"])

    def test_reference_failure_is_a_valid_nonzero_result_not_an_invalid_bundle(self):
        report = run_reference_benchmark(
            ROOT / "reference" / "mobile-manipulator", force_failed_scenario=True
        )
        self.assertEqual(9, report["passed_scenarios"])
        self.assertEqual(1, report["failed_scenarios"])
        self.assertEqual("failed", report["independent_backend"]["status"])
        self.assertEqual("failed", report["backend_crosschecks"][0]["status"])

    def test_backend_cross_check_consumes_replayed_wheel_trace(self):
        report = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")
        first = report["replays"][0]
        self.assertEqual(3, len(first["samples"]))
        self.assertEqual(1.0, first["samples"][0]["state"]["left_wheel_rad_s"])

    def test_backend_crosschecks_bind_every_replay(self):
        report = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")
        records = report["backend_crosschecks"]
        self.assertEqual(10, len(records))
        self.assertEqual(
            [(item["scenario_id"], item["trace_sha256"]) for item in report["replays"]],
            [(item["scenario_id"], item["trace_sha256"]) for item in records],
        )
        self.assertTrue(all(item["status"] == "passed" for item in records))

    def test_crosschecks_report_bound_physical_profile(self):
        report = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")
        profile = report["backend_crosschecks"][0]["profile"]
        self.assertEqual("parsed", profile["evidence_level"])
        self.assertEqual(
            "09a754c3253be4f799a8a7ea0bdea526db04c6741f81abdf5b765803b3bb3fb7",
            profile["workspace_manifest_sha256"],
        )
        self.assertEqual(0.15, profile["wheel_radius_m"])
        self.assertEqual(0.68, profile["wheel_separation_m"])
        self.assertEqual(140.2, profile["mass_kg"])
        primary = {
            item["name"]: item["value"]
            for item in report["backend_crosschecks"][0]["primary"]["metrics"]
        }
        self.assertEqual(0.15, primary["base_distance_m"])
        self.assertAlmostEqual(0.0140625, primary["braking_distance_m"])

    def test_backend_profile_rejects_workspace_source_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "reference"
            shutil.copytree(ROOT / "reference" / "mobile-manipulator", copied)
            controllers = copied / "ros2_ws" / "src" / "jx_mobile_manipulator_sim" / "config" / "controllers.yaml"
            controllers.write_text(
                controllers.read_text(encoding="utf-8").replace(
                    "wheel_radius: 0.15", "wheel_radius: 0.14"
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(BenchmarkError, "receipt-valid"):
                _load_backend_profile(copied)

    def test_backend_profile_rejects_source_replaced_after_manifest_validation(self):
        from assurance.simulation.artifacts import validate_ros_workspace_manifest

        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "reference"
            shutil.copytree(ROOT / "reference" / "mobile-manipulator", copied)
            nav2 = copied / "ros2_ws" / "src" / "jx_mobile_manipulator_nav" / "config" / "nav2_params.yaml"

            def validate_then_replace(*args):
                errors = validate_ros_workspace_manifest(*args)
                nav2.write_text(
                    nav2.read_text(encoding="utf-8").replace(
                        "max_velocity: [0.4, 0.0, 0.8]", "max_velocity: [0.3, 0.0, 0.8]"
                    ),
                    encoding="utf-8",
                )
                return errors

            with patch(
                "validate_simulation_bundle.validate_ros_workspace_manifest",
                side_effect=validate_then_replace,
            ):
                with self.assertRaisesRegex(BenchmarkError, "profile source SHA"):
                    _load_backend_profile(copied)

    def test_backend_profile_ignores_unexpanded_xacro_macro_body(self):
        xacro = b'''<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="fake">
  <link name="base_link"><xacro:inertial mass="100" ixx="1" iyy="1" izz="1"/></link>
  <xacro:macro name="unused">
    <xacro:cylinder_link name="left_wheel_link" radius="0.15" mass="5"/>
    <xacro:cylinder_link name="right_wheel_link" radius="0.15" mass="5"/>
    <joint name="left_wheel_joint"><origin xyz="0 0.34 0"/></joint>
    <joint name="right_wheel_joint"><origin xyz="0 -0.34 0"/></joint>
  </xacro:macro>
</robot>'''
        root = ROOT / "reference" / "mobile-manipulator"
        snapshot = {
            simulation_bundle._PROFILE_SOURCES[0]: xacro,
            simulation_bundle._PROFILE_SOURCES[1]: (
                root / simulation_bundle._PROFILE_SOURCES[1]
            ).read_bytes(),
            simulation_bundle._PROFILE_SOURCES[2]: (
                root / simulation_bundle._PROFILE_SOURCES[2]
            ).read_bytes(),
        }
        with patch(
            "validate_simulation_bundle._profile_source_snapshot",
            return_value=snapshot,
        ):
            with self.assertRaisesRegex(BenchmarkError, "top-level drive wheels"):
                _load_backend_profile(root)

    def test_backend_rejects_missing_or_nonfinite_replayed_wheel_state(self):
        profile = _load_backend_profile(ROOT / "reference" / "mobile-manipulator")
        replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
        replay["samples"][1]["state"].pop("left_wheel_rad_s")
        with self.assertRaisesRegex(BenchmarkError, "wheel state"):
            _backend_input(replay, profile)

        replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
        replay["samples"][1]["state"]["right_wheel_rad_s"] = float("inf")
        with self.assertRaisesRegex(BenchmarkError, "finite"):
            _backend_input(replay, profile)

    def test_backend_rejects_missing_replayed_provenance(self):
        profile = _load_backend_profile(ROOT / "reference" / "mobile-manipulator")
        replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
        replay.pop("trajectory_sha256")
        with self.assertRaisesRegex(BenchmarkError, "provenance"):
            _backend_input(replay, profile)


if __name__ == "__main__":
    unittest.main()
