import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.commissioning.evaluator import evaluate_commissioning_package


PHASES = (
    "unpowered_inspection",
    "protected_power",
    "isolated_joint",
    "separated_base_arm",
    "integrated_low_energy",
)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(root, path, value):
    payload = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(payload).hexdigest()}


def phase_record(root, phase, status="recorded"):
    common = {
        "phase": phase,
        "status": status,
        "test_card_id": f"TC-{phase}",
        "authority_record_id": "authority-record",
        "roles": ["operator", "observer"],
        "area_id": "area-bounded",
        "estop_id": "estop-wired",
        "limits": {"energy_j": 10.0, "speed_m_s": 0.2, "torque_nm": 1.0},
        "watchdog_timeout_ns": 100_000_000,
        "abort_criteria": ["unexpected motion"],
    }
    if status == "planned":
        return common | {"command_trace": None, "state_trace": None, "stop_trace": None, "inspection_record": None}
    motion_inhibited = phase in {"unpowered_inspection", "protected_power"}
    command = {"schema_version": 1, "events": [{"timestamp_ns": 0, "mode": "inhibited" if motion_inhibited else "bounded_motion", "energy_j": 0.0 if motion_inhibited else 1.0, "speed_m_s": 0.0 if motion_inhibited else 0.1, "torque_nm": 0.0 if motion_inhibited else 0.5}]}
    state = {"schema_version": 1, "events": [{"timestamp_ns": 0, "mode": "inhibited" if motion_inhibited else "bounded_motion", "motion_inhibited": motion_inhibited, "speed_m_s": 0.0 if motion_inhibited else 0.1, "torque_nm": 0.0 if motion_inhibited else 0.5, "watchdog_healthy": True}]}
    stop = {"schema_version": 1, "events": [{"timestamp_ns": 10, "initiating_event": "emergency_stop", "safe_state": "motion_inhibited", "latency_ns": 10}, {"timestamp_ns": 20, "initiating_event": "command_timeout", "safe_state": "motion_inhibited", "latency_ns": 20}]}
    inspection = {"schema_version": 1, "checks": ["fasteners", "wiring"], "disposition": "accepted"}
    return common | {
        "command_trace": write_json(root, root / "records" / phase / "command.json", command),
        "state_trace": write_json(root, root / "records" / phase / "state.json", state),
        "stop_trace": write_json(root, root / "records" / phase / "stop.json", stop),
        "inspection_record": write_json(root, root / "records" / phase / "inspection.json", inspection),
    }


def package(root, phases=PHASES):
    return {"schema_version": 1, "commissioning_id": "commissioning-reference", "phases": [phase_record(root, phase) for phase in phases]}


class CommissioningEvaluatorTests(unittest.TestCase):
    def test_empty_package_awaits_authorization(self):
        with tempfile.TemporaryDirectory() as raw:
            result = evaluate_commissioning_package(Path(raw), {"schema_version": 1, "commissioning_id": "commissioning-reference", "phases": []})
        self.assertEqual("awaiting_authorization", result.status)
        self.assertIn("COMM.AUTHORIZATION_REQUIRED", {item.code for item in result.findings})

    def test_reordered_phase_and_missing_stop_trace_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_commissioning_package(root, package(root, ("protected_power",)))
            self.assertIn("COMM.PHASE_ORDER", {item.code for item in result.findings})
            value = package(root)
            value["phases"][2]["stop_trace"] = None
            result = evaluate_commissioning_package(root, value)
        self.assertEqual("rejected", result.status)
        self.assertIn("COMM.STOP_TRACE_REQUIRED", {item.code for item in result.findings})

    def test_complete_bounded_stages_are_ready_but_never_authorized(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = evaluate_commissioning_package(root, package(root))
        self.assertEqual("ready", result.status)
        self.assertEqual("integrated_low_energy", result.highest_validated_phase)
        self.assertFalse(result.procurement_authorized)
        self.assertFalse(result.motion_authorized)

    def test_limit_violation_and_abort_are_retained_as_blockers(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = package(root)
            command_path = root / "records" / "isolated_joint" / "command.json"
            command = json.loads(command_path.read_text(encoding="utf-8"))
            command["events"][0]["speed_m_s"] = 0.3
            value["phases"][2]["command_trace"] = write_json(root, command_path, command)
            value["phases"][3]["status"] = "aborted"
            result = evaluate_commissioning_package(root, value)
        self.assertEqual("rejected", result.status)
        self.assertTrue({"COMM.COMMAND_LIMIT_EXCEEDED", "COMM.PHASE_ABORTED"} <= {item.code for item in result.findings})

    def test_dependency_path_and_timestamp_attacks_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = package(root)
            value["phases"][0] = phase_record(root, "unpowered_inspection", "planned")
            result = evaluate_commissioning_package(root, value)
            self.assertIn("COMM.PHASE_DEPENDENCY", {item.code for item in result.findings})
            value = package(root)
            value["phases"][0]["command_trace"]["path"] = "../escape.json"
            result = evaluate_commissioning_package(root, value)
            self.assertIn("COMM.EVIDENCE_PATH_INVALID", {item.code for item in result.findings})
            value = package(root)
            command_path = root / "records" / "isolated_joint" / "command.json"
            command = json.loads(command_path.read_text(encoding="utf-8"))
            command["events"].append(command["events"][0].copy())
            value["phases"][2]["command_trace"] = write_json(root, command_path, command)
            result = evaluate_commissioning_package(root, value)
        self.assertIn("COMM.TRACE_TIMESTAMPS", {item.code for item in result.findings})

    def test_malformed_package_returns_actionable_report(self):
        result = evaluate_commissioning_package(Path("."), {"schema_version": True, "commissioning_id": [], "phases": {}})
        self.assertEqual("rejected", result.status)
        self.assertIn("COMM.PACKAGE_INVALID", {item.code for item in result.findings})


if __name__ == "__main__":
    unittest.main()
