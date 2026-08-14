import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.engineering_freeze.model import EngineeringFreezeReport, FreezeFinding
from assurance.engineering_freeze.schema import FreezeSchemaError, load_canonical_json


class EngineeringFreezeModelTests(unittest.TestCase):
    def test_report_cannot_authorize_procurement_or_motion(self):
        finding = FreezeFinding("FREEZE.OPEN", "indeterminate", "package", "open")
        for procurement, motion in ((True, False), (False, True), (True, True)):
            with self.subTest(procurement=procurement, motion=motion):
                with self.assertRaisesRegex(ValueError, "authorization"):
                    EngineeringFreezeReport("freeze-reference", (finding,), False, procurement, motion)

    def test_report_derives_readiness_and_canonical_order(self):
        report = EngineeringFreezeReport(
            "freeze-reference",
            (
                FreezeFinding("FREEZE.Z", "warning", "z", "later"),
                FreezeFinding("FREEZE.A", "info", "a", "earlier"),
            ),
            True,
            False,
            False,
        )
        self.assertTrue(report.freeze_ready)
        self.assertEqual(
            ["FREEZE.A", "FREEZE.Z"],
            [item["code"] for item in report.to_dict()["findings"]],
        )
        self.assertFalse(report.to_dict()["procurement_authorized"])
        self.assertFalse(report.to_dict()["motion_authorized"])

    def test_report_rejects_inconsistent_readiness_and_bad_finding(self):
        with self.assertRaisesRegex(ValueError, "freeze_ready"):
            EngineeringFreezeReport(
                "freeze-reference",
                (FreezeFinding("FREEZE.OPEN", "error", "x", "open"),),
                True,
                False,
                False,
            )
        with self.assertRaisesRegex(ValueError, "severity"):
            FreezeFinding("FREEZE.BAD", "passed", "x", "bad")

    def test_loader_rejects_noncanonical_duplicate_and_unsafe_path(self):
        cases = {
            "duplicate.json": b'{"id":"first","id":"second"}\n',
            "noncanonical.json": b'{ "id": "freeze" }\n',
            "unsafe.json": b'{"path":"../escape"}\n',
            "nonfinite.json": b'{"value":1e999}\n',
        }
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            for name, payload in cases.items():
                with self.subTest(name=name):
                    path = directory / name
                    path.write_bytes(payload)
                    with self.assertRaises(FreezeSchemaError):
                        load_canonical_json(path)

    def test_loader_returns_closed_canonical_mapping(self):
        payload = {"id": "freeze-reference", "records": [{"path": "artifacts/drawing.md"}]}
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "package.json"
            path.write_bytes((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            self.assertEqual(payload, load_canonical_json(path))


if __name__ == "__main__":
    unittest.main()
