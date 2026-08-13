import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from validate_simulation_bundle import run_reference_benchmark  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
