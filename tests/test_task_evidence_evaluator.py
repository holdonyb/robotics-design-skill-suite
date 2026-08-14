import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_task_evidence_protocol import protocol


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.task_evidence.evaluator import evaluate_task_packages
from assurance.task_evidence.protocol import validate_task_protocol


def minimal_protocol():
    value = protocol()
    value["envelope"][0]["values"] = [1.0]
    value["repetitions"] = 1
    return value


def bind(root, name, value):
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": name, "sha256": hashlib.sha256(payload).hexdigest()}


def nominal(root):
    command = {"schema_version": 1, "events": [{"timestamp_ns": 0, "phase": "approach", "speed_m_s": 0.1, "torque_nm": 0.2, "watchdog_healthy": True}]}
    state = {"schema_version": 1, "events": [{"timestamp_ns": 0, "phase": "approach", "speed_m_s": 0.1, "torque_nm": 0.2, "watchdog_healthy": True}]}
    task = {"schema_version": 1, "events": [{"timestamp_ns": 0, "phase": "approach", "completed": False}, {"timestamp_ns": 1, "phase": "grasp", "completed": False}, {"timestamp_ns": 2, "phase": "place", "completed": True}]}
    metrics = {"schema_version": 1, "events": [{"timestamp_ns": 0, "metric_id": "completion-time", "value": 2.0}]}
    return {"schema_version": 1, "package_id": "trial-001", "kind": "nominal", "envelope": {"payload": 1.0}, "repetition": 1, "fault_id": None, "fault_record": None, "endurance_record": None, "comparison_record": None, "command_trace": bind(root, "traces/command.json", command), "state_trace": bind(root, "traces/state.json", state), "task_trace": bind(root, "traces/task.json", task), "metric_trace": bind(root, "traces/metrics.json", metrics), "disposition": "passed"}


def fault(root):
    value = nominal(root)
    value.update({"package_id": "fault-001", "kind": "fault", "fault_id": "timeout-fault", "fault_record": bind(root, "traces/fault.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "fault_id": "timeout-fault", "detected": True, "safe_state": "motion_inhibited", "recovery": "manual-inspection"}]})})
    return value


def endurance(root):
    value = nominal(root)
    value.update({"package_id": "endurance-001", "kind": "endurance", "endurance_record": bind(root, "traces/endurance.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "health": 1.0, "terminal": False}, {"timestamp_ns": 1_000_000_000, "health": 0.99, "terminal": True}]})})
    return value


def comparison(root):
    value = nominal(root)
    value.update({"package_id": "comparison-001", "kind": "comparison", "comparison_record": bind(root, "traces/comparison.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "quantity_id": "base-speed", "simulated": 0.10, "observed": 0.12}, {"timestamp_ns": 1, "quantity_id": "base-speed", "simulated": 0.20, "observed": 0.18}]})})
    return value


class TaskEvidenceEvaluatorTests(unittest.TestCase):
    def test_nominal_trial_is_valid_but_never_task_validated(self):
        value, findings = validate_task_protocol(minimal_protocol())
        self.assertEqual((), findings)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_task_packages(root, value, [nominal(root), fault(root)])
        self.assertEqual("evidence_complete", result.status)
        self.assertEqual(("completion-time", 1, 2.0, 2.0, 2.0, True), tuple(result.metric_summaries[0].to_dict().values()))
        self.assertFalse(result.task_validated)

    def test_nonobject_event_is_rejected_without_traceback(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = nominal(root)
            package["state_trace"] = bind(root, "traces/state.json", {"schema_version": 1, "events": [[]]})
            result = evaluate_task_packages(root, value, [package])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.TRACE_INVALID", {item.code for item in result.findings})

    def test_fault_requires_declared_safe_state_and_recovery(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_task_packages(root, value, [nominal(root), fault(root)])
            self.assertEqual("evidence_complete", result.status)
            bad = fault(root)
            bad["fault_record"] = bind(root, "traces/fault.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "fault_id": "timeout-fault", "detected": True, "safe_state": "moving", "recovery": "manual-inspection"}]})
            result = evaluate_task_packages(root, value, [nominal(root), bad])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.FAULT_SAFE_STATE", {item.code for item in result.findings})

    def test_endurance_requires_exact_sampling_and_terminal_record(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_task_packages(root, value, [nominal(root), fault(root), endurance(root)])
            self.assertEqual("evidence_complete", result.status)
            bad = endurance(root)
            bad["endurance_record"] = bind(root, "traces/endurance.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "health": 1.0, "terminal": False}, {"timestamp_ns": 2_000_000_000, "health": 0.99, "terminal": True}]})
            result = evaluate_task_packages(root, value, [nominal(root), bad])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.ENDURANCE_TIMESTAMPS", {item.code for item in result.findings})

    def test_comparison_requires_declared_bounded_residuals(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_task_packages(root, value, [nominal(root), fault(root), comparison(root)])
            self.assertEqual("evidence_complete", result.status)
            bad = comparison(root)
            bad["comparison_record"] = bind(root, "traces/comparison.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "quantity_id": "base-speed", "simulated": 0.1, "observed": 0.5}]})
            result = evaluate_task_packages(root, value, [nominal(root), bad])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.COMPARISON_RESIDUAL", {item.code for item in result.findings})

    def test_all_declared_envelope_repetitions_are_required(self):
        value, _ = validate_task_protocol(protocol())
        with tempfile.TemporaryDirectory() as raw:
            result = evaluate_task_packages(Path(raw), value, [nominal(Path(raw))])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.REPETITION_MISSING", {item.code for item in result.findings})

    def test_failed_trial_and_boolean_schema_version_are_rejected(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            failed = nominal(root)
            failed["disposition"] = "failed"
            result = evaluate_task_packages(root, value, [failed])
            self.assertEqual("rejected", result.status)
            self.assertIn("TASK.TRIAL_NOT_PASSED", {item.code for item in result.findings})

            malformed = nominal(root)
            malformed["schema_version"] = True
            result = evaluate_task_packages(root, value, [malformed])
            self.assertEqual("rejected", result.status)
            self.assertIn("TASK.PACKAGE_INVALID", {item.code for item in result.findings})

    def test_metric_threshold_and_undefined_metric_are_rejected(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            over_limit = nominal(root)
            over_limit["metric_trace"] = bind(root, "traces/metrics.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "metric_id": "completion-time", "value": 31.0}]})
            result = evaluate_task_packages(root, value, [over_limit])
            self.assertEqual("rejected", result.status)
            self.assertIn("TASK.METRIC_THRESHOLD", {item.code for item in result.findings})

            unknown = nominal(root)
            unknown["metric_trace"] = bind(root, "traces/metrics.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "metric_id": "invented", "value": 1.0}]})
            result = evaluate_task_packages(root, value, [unknown])
            self.assertEqual("rejected", result.status)
            self.assertIn("TASK.METRIC_INVALID", {item.code for item in result.findings})

    def test_nominal_task_must_retain_ordered_complete_protocol_phases(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = nominal(root)
            package["task_trace"] = bind(root, "traces/task.json", {"schema_version": 1, "events": [{"timestamp_ns": 0, "phase": "grasp", "completed": False}, {"timestamp_ns": 1, "phase": "approach", "completed": True}]})
            result = evaluate_task_packages(root, value, [package])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.PHASE_ORDER", {item.code for item in result.findings})

    def test_each_declared_fault_requires_each_envelope_repetition(self):
        value, _ = validate_task_protocol(minimal_protocol())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_task_packages(root, value, [nominal(root)])
        self.assertEqual("rejected", result.status)
        self.assertIn("TASK.FAULT_MISSING", {item.code for item in result.findings})


if __name__ == "__main__":
    unittest.main()
