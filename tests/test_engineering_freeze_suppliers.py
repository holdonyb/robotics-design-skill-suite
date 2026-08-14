import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.engineering_freeze.suppliers import validate_supplier_manifest


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class EngineeringFreezeSupplierTests(unittest.TestCase):
    def write_manifest(self, directory, entries):
        manifest = {"schema_version": 1, "supplier_manifest_id": "supplier-reference", "snapshots": entries}
        path = directory / "supplier-manifest.json"
        path.write_bytes(canonical(manifest))
        return path

    def complete_entry(self, directory):
        snapshot = {
            "manufacturer": "Example Robotics", "part_number": "MTR-001",
            "limits": {"continuous_torque": {"unit": "N*m", "value": 10}},
        }
        relative = "supplier-snapshots/motor.json"
        target = directory / relative
        target.parent.mkdir()
        target.write_bytes(canonical(snapshot))
        return {
            "id": "supplier-motor", "component_id": "CMP-MOTOR", "manufacturer": "Example Robotics",
            "part_number": "MTR-001", "source_url": "https://example.com/motor.pdf", "source_date": "2026-08-14",
            "review_date": "2026-08-14", "reviewer": "engineering-review", "snapshot_path": relative,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "limits": snapshot["limits"], "supports_requirements": ["REQ-PHYSICAL"],
        }

    def test_complete_snapshot_is_valid_but_not_an_authorization(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = self.write_manifest(directory, [self.complete_entry(directory)])
            findings = validate_supplier_manifest(
                directory, manifest, {"CMP-MOTOR"}, {"REQ-PHYSICAL"}
            )
            self.assertEqual([], findings)

    def test_missing_snapshot_and_identity_or_hash_drift_are_actionable(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            entry = self.complete_entry(directory)
            entry["manufacturer"] = "Mismatch"
            entry["sha256"] = "0" * 64
            (directory / entry["snapshot_path"]).unlink()
            manifest = self.write_manifest(directory, [entry])
            codes = {item.code for item in validate_supplier_manifest(directory, manifest, {"CMP-MOTOR"}, {"REQ-PHYSICAL"})}
            self.assertIn("FREEZE.SUPPLIER_SNAPSHOT_MISSING", codes)

    def test_unknown_graph_edge_unsafe_path_and_duplicate_id_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            entry = self.complete_entry(directory)
            duplicate = dict(entry)
            duplicate["component_id"] = "CMP-UNKNOWN"
            duplicate["supports_requirements"] = ["REQ-UNKNOWN"]
            duplicate["snapshot_path"] = "../escape.json"
            manifest = self.write_manifest(directory, [entry, duplicate])
            codes = {item.code for item in validate_supplier_manifest(directory, manifest, {"CMP-MOTOR"}, {"REQ-PHYSICAL"})}
            self.assertTrue({"FREEZE.SUPPLIER_DUPLICATE_ID", "FREEZE.SUPPLIER_COMPONENT_UNKNOWN", "FREEZE.SUPPLIER_REQUIREMENT_UNKNOWN", "FREEZE.SUPPLIER_SNAPSHOT_PATH"} <= codes)


if __name__ == "__main__":
    unittest.main()
