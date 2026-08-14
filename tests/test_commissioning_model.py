import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.commissioning.model import CommissioningFinding, CommissioningReport


class CommissioningModelTests(unittest.TestCase):
    def test_awaiting_report_is_immutable_and_never_authorizes_hardware(self):
        finding = CommissioningFinding(
            "COMM.AUTHORIZATION_REQUIRED",
            "indeterminate",
            "phases",
            "external authority is required",
        )
        report = CommissioningReport(
            "commissioning-reference",
            "awaiting_authorization",
            (finding,),
            None,
        )
        self.assertFalse(report.procurement_authorized)
        self.assertFalse(report.motion_authorized)
        self.assertEqual("awaiting_authorization", report.to_dict()["status"])
        with self.assertRaisesRegex(AttributeError, "assign"):
            report.status = "ready"

    def test_model_rejects_invalid_status_and_authorization(self):
        with self.assertRaisesRegex(ValueError, "invalid commissioning status"):
            CommissioningReport("commissioning-reference", "passed", (), None)
        with self.assertRaisesRegex(ValueError, "authorization"):
            CommissioningReport(
                "commissioning-reference",
                "ready",
                (),
                None,
                motion_authorized=True,
            )

    def test_model_derives_status_from_blocking_findings(self):
        finding = CommissioningFinding("COMM.REJECT", "error", "phase", "record is rejected")
        with self.assertRaisesRegex(ValueError, "derived"):
            CommissioningReport("commissioning-reference", "ready", (finding,), None)

    def test_report_rejects_mutable_findings_collection(self):
        with self.assertRaisesRegex(ValueError, "tuple"):
            CommissioningReport("commissioning-reference", "ready", [], None)

    def test_findings_are_closed_and_reports_sort_them_deterministically(self):
        with self.assertRaisesRegex(ValueError, "severity"):
            CommissioningFinding("COMM.BAD", "critical", "x", "bad")
        report = CommissioningReport(
            "commissioning-reference",
            "rejected",
            (
                CommissioningFinding("COMM.Z", "error", "z", "z"),
                CommissioningFinding("COMM.A", "warning", "a", "a"),
            ),
            None,
        )
        self.assertEqual(["COMM.A", "COMM.Z"], [item["code"] for item in report.to_dict()["findings"]])


if __name__ == "__main__":
    unittest.main()
