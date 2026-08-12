import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.model import Diagnostic, EvidenceLevel, Report  # noqa: E402


class AssuranceModelTests(unittest.TestCase):
    def test_evidence_levels_are_ordered(self):
        self.assertLess(EvidenceLevel.CALCULATED, EvidenceLevel.SIMULATED)
        self.assertLess(EvidenceLevel.SIMULATED, EvidenceLevel.BENCH_TESTED)
        self.assertLess(
            EvidenceLevel.INTEGRATED_HARDWARE_TESTED,
            EvidenceLevel.TASK_VALIDATED,
        )

    def test_report_is_not_promotable_with_error_or_indeterminate(self):
        report = Report("candidate-a")
        report.add(
            Diagnostic("BOM.MISSING", "error", "components", "missing reducer")
        )
        report.add(
            Diagnostic(
                "PHY.UNKNOWN",
                "indeterminate",
                "analyses.arm",
                "no inertia",
            )
        )
        self.assertFalse(report.promotable)

    def test_report_serialization_is_sorted_and_deterministic(self):
        report = Report("candidate-a")
        report.add(Diagnostic("Z.CODE", "warning", "z", "later"))
        report.add(
            Diagnostic(
                "A.CODE",
                "error",
                "a",
                "first",
                evidence_ids=("ev-2", "ev-1"),
            )
        )
        first = json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"))
        second = json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)
        self.assertEqual(report.to_dict()["diagnostics"][0]["code"], "A.CODE")
        self.assertEqual(
            report.to_dict()["diagnostics"][0]["evidence_ids"],
            ["ev-1", "ev-2"],
        )

    def test_invalid_diagnostic_severity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "severity"):
            Diagnostic("BAD", "pass", "root", "invalid")


if __name__ == "__main__":
    unittest.main()
