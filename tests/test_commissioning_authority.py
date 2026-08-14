import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.commissioning.authority import validate_authority_record


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(root, value):
    path = root / "authority.json"
    payload = canonical(value)
    path.write_bytes(payload)
    return {"path": "authority.json", "sha256": hashlib.sha256(payload).hexdigest()}


def phase():
    return {
        "phase": "isolated_joint",
        "execution_date": "2026-08-14",
        "site_id": "site-lab",
        "area_id": "area-bounded",
        "estop_id": "estop-wired",
        "roles": ["operator", "observer"],
        "limits": {"energy_j": 10.0, "speed_m_s": 0.2, "torque_nm": 1.0},
        "watchdog_timeout_ns": 100_000_000,
    }


def authority():
    return {
        "schema_version": 1,
        "authority_record_id": "authority-isolated-joint",
        "authorization_kind": "external_human_attestation",
        "design_contract_sha256": "a" * 64,
        "phase": "isolated_joint",
        "execution_window": {"start_date": "2026-08-14", "end_date": "2026-08-14"},
        "site_id": "site-lab",
        "area_id": "area-bounded",
        "estop_id": "estop-wired",
        "roles": ["operator", "observer"],
        "limits": {"energy_j": 20.0, "speed_m_s": 0.3, "torque_nm": 2.0},
        "watchdog_timeout_ns": 200_000_000,
        "attested_by_role": "site-safety-authority",
        "approval_reference": "approval-2026-08-14",
    }


class CommissioningAuthorityTests(unittest.TestCase):
    def test_bound_record_covers_matching_phase_without_granting_authority(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            findings = validate_authority_record(root, write_json(root, authority()), phase(), "a" * 64)
        self.assertEqual(findings, ())

    def test_scope_drift_and_expired_record_fail_closed(self):
        for field, value, code in (
            ("design_contract_sha256", "b" * 64, "COMM.AUTHORITY_DESIGN_MISMATCH"),
            ("phase", "integrated_low_energy", "COMM.AUTHORITY_PHASE_MISMATCH"),
            ("site_id", "site-other", "COMM.AUTHORITY_SCOPE_MISMATCH"),
            ("execution_window", {"start_date": "2026-08-13", "end_date": "2026-08-13"}, "COMM.AUTHORITY_DATE_INVALID"),
        ):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    record = authority()
                    record[field] = value
                    findings = validate_authority_record(root, write_json(root, record), phase(), "a" * 64)
                self.assertIn(code, {item.code for item in findings})

    def test_hash_and_phase_limit_attacks_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            binding = write_json(root, authority())
            binding["sha256"] = "0" * 64
            findings = validate_authority_record(root, binding, phase(), "a" * 64)
            self.assertIn("COMM.AUTHORITY_HASH_MISMATCH", {item.code for item in findings})
            record = authority()
            record["limits"]["speed_m_s"] = 0.1
            findings = validate_authority_record(root, write_json(root, record), phase(), "a" * 64)
        self.assertIn("COMM.AUTHORITY_LIMIT_EXCEEDED", {item.code for item in findings})


if __name__ == "__main__":
    unittest.main()
