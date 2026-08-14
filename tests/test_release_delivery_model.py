import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.release.model import ReleaseDeliveryFinding, ReleaseDeliveryReport
from assurance.release.schema import ReleaseSchemaError, load_release_contract


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class ReleaseDeliveryModelTests(unittest.TestCase):
    def test_report_derives_status_and_never_claims_hardware(self):
        finding = ReleaseDeliveryFinding(
            "RELEASE.BOUNDARY", "indeterminate", "hardware_claims", "hardware evidence is unavailable"
        )
        report = ReleaseDeliveryReport("v1.0.0", "awaiting_external_publication", (finding,))
        self.assertFalse(report.hardware_claims)
        self.assertFalse(report.passed)
        self.assertEqual("awaiting_external_publication", report.to_dict()["status"])
        with self.assertRaisesRegex(ValueError, "hardware_claims"):
            ReleaseDeliveryReport("v1.0.0", "passed", (), hardware_claims=True)
        with self.assertRaisesRegex(ValueError, "derived"):
            ReleaseDeliveryReport("v1.0.0", "passed", (finding,))

    def test_loader_rejects_duplicate_noncanonical_and_unsafe_contracts(self):
        cases = {
            "duplicate.json": b'{"release_id":"v1.0.0","release_id":"v1.0.1"}\n',
            "noncanonical.json": b'{ "release_id":"v1.0.0"}\n',
            "unsafe.json": b'{"artifact_bindings":[{"path":"../escape","sha256":"' + b"0" * 64 + b'"}],"hardware_claims":false,"release_id":"v1.0.0","schema_version":1}\n',
            "bool.json": canonical({"schema_version": True, "release_id": "v1.0.0", "artifact_bindings": [{"path": "README.md", "sha256": "0" * 64}], "hardware_claims": False}),
        }
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            for name, payload in cases.items():
                with self.subTest(name=name):
                    path = directory / name
                    path.write_bytes(payload)
                    with self.assertRaises(ReleaseSchemaError):
                        load_release_contract(path)

    def test_loader_returns_closed_immutable_contract(self):
        payload = {
            "schema_version": 1,
            "release_id": "v1.0.0",
            "artifact_bindings": [{"path": "README.md", "sha256": "a" * 64}],
            "hardware_claims": False,
        }
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "contract.json"
            path.write_bytes(canonical(payload))
            contract = load_release_contract(path)
        self.assertEqual("v1.0.0", contract.release_id)
        self.assertEqual((("README.md", "a" * 64),), contract.artifact_bindings)
        with self.assertRaisesRegex(AttributeError, "assign"):
            contract.release_id = "v1.0.1"


if __name__ == "__main__":
    unittest.main()
