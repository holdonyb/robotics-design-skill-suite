import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.task_evidence.protocol import validate_task_protocol


def protocol():
    return {
        "schema_version": 1,
        "task_id": "reference-pick-place",
        "phases": ["approach", "grasp", "place"],
        "envelope": [{"id": "payload", "unit": "kg", "values": [1.0, 2.0]}],
        "repetitions": 2,
        "metrics": [{"id": "completion-time", "unit": "s", "direction": "maximum", "threshold": 30.0}],
        "faults": [{"id": "timeout-fault", "safe_state": "motion_inhibited", "recovery": "manual-inspection"}],
        "endurance": {"sample_interval_ns": 1_000_000_000, "max_duration_ns": 10_000_000_000, "max_samples": 10},
        "comparison": [{"id": "base-speed", "unit": "m/s", "max_abs_residual": 0.1, "max_rel_residual": 0.2}],
    }


class TaskEvidenceProtocolTests(unittest.TestCase):
    def test_valid_protocol_normalizes_to_immutable_record(self):
        value, findings = validate_task_protocol(protocol())
        self.assertIsNotNone(value)
        self.assertEqual((), findings)
        self.assertEqual("reference-pick-place", value.task_id)

    def test_nonfinite_duplicate_and_unknown_protocol_values_are_actionable(self):
        value = protocol()
        value["metrics"][0]["threshold"] = float("nan")
        value["envelope"][0]["values"] = [1.0, 1.0]
        value["comparison"][0]["unit"] = "made-up"
        _, findings = validate_task_protocol(value)
        codes = {item.code for item in findings}
        self.assertTrue({"TASK.PROTOCOL_METRIC_INVALID", "TASK.PROTOCOL_ENVELOPE_INVALID", "TASK.PROTOCOL_COMPARISON_INVALID"} <= codes)


if __name__ == "__main__":
    unittest.main()
