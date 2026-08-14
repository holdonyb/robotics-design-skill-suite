import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.bench_evidence import validate_bench_package


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_ns", "command_m_s", "observed_m_s"])
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(root, *, fixture_only=True, component_id="CMP-MOTOR"):
    raw = root / "raw" / "velocity.csv"
    raw.parent.mkdir(exist_ok=True)
    raw_hash = write_csv(raw, [(0, 1.0, 0.8), (1_000_000_000, 2.0, 1.6)])
    calibration = {"certificate_id": "CAL-001", "instrument_id": "INS-VELOCITY", "valid_from": "2026-01-01", "valid_to": "2026-12-31", "measured_columns": ["observed_m_s"]}
    calibration_path = root / "calibration.json"
    calibration_path.write_bytes(canonical(calibration))
    return {
        "schema_version": 1, "package_id": "bench-velocity-fixture", "fixture_only": fixture_only,
        "component_id": component_id, "supports_claims": ["REQ-PHYSICAL"],
        "observed_date": "2026-08-14", "site_id": "site-fixture", "operator_id": "operator-fixture",
        "test_card": {"id": "TC-VELOCITY", "status": "approved_for_recording", "authority": "fixture-authority", "reachable_estop": "required", "energy_limit": "defined", "abort_criteria": ["unexpected motion"]},
        "instrument": {"id": "INS-VELOCITY", "calibration_path": "calibration.json", "calibration_sha256": hashlib.sha256(calibration_path.read_bytes()).hexdigest()},
        "raw_data": {"path": "raw/velocity.csv", "sha256": raw_hash, "columns": {"timestamp_ns": "ns", "command_m_s": "m/s", "observed_m_s": "m/s"}, "sample_count": 2, "start_timestamp_ns": 0, "end_timestamp_ns": 1_000_000_000},
    }


class BenchEvidenceTests(unittest.TestCase):
    def test_fixture_is_accepted_but_cannot_claim_bench_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = package(root)
            result = validate_bench_package(root, value, {"CMP-MOTOR"}, {"REQ-PHYSICAL"})
            self.assertEqual("accepted", result.status)
            self.assertIsNone(result.evidence_level)
            self.assertTrue(result.fixture_only)
            self.assertFalse(result.procurement_authorized)
            self.assertFalse(result.motion_authorized)

    def test_hash_path_timestamp_and_calibration_attacks_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = package(root)
            value["raw_data"]["path"] = "../escape.csv"
            value["raw_data"]["sha256"] = "0" * 64
            value["instrument"]["calibration_sha256"] = "1" * 64
            result = validate_bench_package(root, value, {"CMP-MOTOR"}, {"REQ-PHYSICAL"})
            self.assertEqual("rejected", result.status)
            codes = {item["code"] for item in result.findings}
            self.assertTrue({"BENCH.RAW_PATH_INVALID", "BENCH.CALIBRATION_HASH_MISMATCH"} <= codes)

    def test_unknown_component_nonmonotonic_raw_and_expired_calibration_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = package(root)
            value["component_id"] = "CMP-NOPE"
            value["observed_date"] = "2027-01-01"
            write_csv(root / "raw" / "velocity.csv", [(1_000_000_000, 1.0, 0.8), (0, 2.0, 1.6)])
            value["raw_data"]["sha256"] = hashlib.sha256((root / "raw" / "velocity.csv").read_bytes()).hexdigest()
            result = validate_bench_package(root, value, {"CMP-MOTOR"}, {"REQ-PHYSICAL"})
            codes = {item["code"] for item in result.findings}
            self.assertEqual("rejected", result.status)
            self.assertTrue({"BENCH.COMPONENT_UNKNOWN", "BENCH.CALIBRATION_EXPIRED", "BENCH.RAW_TIMESTAMPS"} <= codes)

    def test_calibration_column_and_raw_sample_bounds_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = package(root)
            calibration_path = root / "calibration.json"
            calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            calibration["measured_columns"] = ["command_m_s"]
            calibration_path.write_bytes(canonical(calibration))
            value["instrument"]["calibration_sha256"] = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
            write_csv(root / "raw" / "velocity.csv", [(number, 1.0, 0.8) for number in range(10_001)])
            value["raw_data"].update({"sha256": hashlib.sha256((root / "raw" / "velocity.csv").read_bytes()).hexdigest(), "sample_count": 10_001, "end_timestamp_ns": 10_000})
            result = validate_bench_package(root, value, {"CMP-MOTOR"}, {"REQ-PHYSICAL"})
        self.assertEqual("rejected", result.status)
        codes = {item["code"] for item in result.findings}
        self.assertIn("BENCH.CALIBRATION_EXPIRED", codes)
        self.assertIn("BENCH.RAW_BOUNDS", codes)


if __name__ == "__main__":
    unittest.main()
