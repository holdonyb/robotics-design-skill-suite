import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.calibration import CalibrationError, fit_calibration, load_calibration_dataset  # noqa: E402


SHA_A = "a" * 64


def dataset(evidence_level="simulated"):
    samples = [
        {"sample_id": "sample-1", "command_m_s": 1.0, "observed_m_s": 0.8, "split": "train"},
        {"sample_id": "sample-2", "command_m_s": 2.0, "observed_m_s": 1.6, "split": "train"},
        {"sample_id": "sample-3", "command_m_s": 1.5, "observed_m_s": 1.2, "split": "evaluation"},
        {"sample_id": "sample-4", "command_m_s": 0.5, "observed_m_s": 0.4, "split": "evaluation"},
    ]
    return {
        "schema_version": 1,
        "dataset_id": "calibration-synthetic-v1",
        "artifact_sha256": SHA_A,
        "evidence_level": evidence_level,
        "pipeline_test_only": evidence_level == "simulated",
        "parameter_bounds": {"velocity_scale": {"lower": 0.5, "upper": 1.2}},
        "samples": samples,
    }


class CalibrationTests(unittest.TestCase):
    def test_deterministic_bounded_fit_and_held_out_residuals_stay_simulated(self):
        result = fit_calibration(dataset())
        self.assertEqual("simulated", result.evidence_level)
        self.assertTrue(result.pipeline_test_only)
        self.assertAlmostEqual(0.8, result.parameters["velocity_scale"])
        self.assertLess(result.evaluation_rmse, 1e-12)
        self.assertEqual(result, fit_calibration(copy.deepcopy(dataset())))

    def test_only_bench_or_hardware_data_can_claim_calibrated_simulation(self):
        bench = fit_calibration(dataset("bench_tested"))
        self.assertEqual("calibrated_simulation", bench.evidence_level)
        hardware = fit_calibration(dataset("integrated_hardware_tested"))
        self.assertEqual("calibrated_simulation", hardware.evidence_level)

    def test_rejects_overfit_singular_invalid_or_drifted_data(self):
        attacks = []
        value = dataset(); value["samples"][2]["observed_m_s"] = 9.0; attacks.append((value, "evaluation"))
        value = dataset(); value["samples"][1]["command_m_s"] = 1.0; value["samples"][1]["observed_m_s"] = 0.8; attacks.append((value, "singular"))
        value = dataset(); value["samples"][0]["split"] = "evaluation"; attacks.append((value, "train"))
        value = dataset(); value["samples"][0]["command_m_s"] = float("nan"); attacks.append((value, "finite"))
        value = dataset(); value["parameter_bounds"]["velocity_scale"]["upper"] = 0.7; attacks.append((value, "bounds"))
        value = dataset(); value["extra"] = True; attacks.append((value, "unknown"))
        for value, expected in attacks:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(CalibrationError, expected):
                    fit_calibration(value)

    def test_reference_synthetic_dataset_is_closed_and_loadable(self):
        loaded = load_calibration_dataset(ROOT / "reference" / "mobile-manipulator" / "simulation" / "calibration-synthetic.json")
        self.assertEqual("simulated", fit_calibration(loaded).evidence_level)


if __name__ == "__main__":
    unittest.main()
