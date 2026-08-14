import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from validate_simulation_bundle import BenchmarkError, _backend_input, run_reference_benchmark  # noqa: E402


class ReferenceSimulationTests(unittest.TestCase):
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

    def test_backend_rejects_missing_or_nonfinite_replayed_wheel_state(self):
        replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
        replay["samples"][1]["state"].pop("left_wheel_rad_s")
        with self.assertRaisesRegex(BenchmarkError, "wheel state"):
            _backend_input(replay)

        replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
        replay["samples"][1]["state"]["right_wheel_rad_s"] = float("inf")
        with self.assertRaisesRegex(BenchmarkError, "finite"):
            _backend_input(replay)

    def test_backend_rejects_missing_replayed_provenance(self):
        replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
        replay.pop("trajectory_sha256")
        with self.assertRaisesRegex(BenchmarkError, "provenance"):
            _backend_input(replay)


if __name__ == "__main__":
    unittest.main()
