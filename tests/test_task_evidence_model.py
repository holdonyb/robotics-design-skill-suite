import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.task_evidence.model import TaskEvidenceFinding, TaskEvidenceReport


class TaskEvidenceModelTests(unittest.TestCase):
    def test_indeterminate_report_is_immutable_and_never_claims_task_validation(self):
        finding = TaskEvidenceFinding("TASK.MISSING", "indeterminate", "packages", "records are missing")
        report = TaskEvidenceReport("task-evidence-reference", "awaiting_authorization", (finding,), (), (), ())
        self.assertFalse(report.procurement_authorized)
        self.assertFalse(report.motion_authorized)
        self.assertFalse(report.task_validated)
        with self.assertRaisesRegex(AttributeError, "assign"):
            report.status = "evidence_complete"

    def test_status_is_derived_and_collections_are_immutable(self):
        finding = TaskEvidenceFinding("TASK.BAD", "error", "packages[0]", "record failed")
        with self.assertRaisesRegex(ValueError, "derived"):
            TaskEvidenceReport("task-evidence-reference", "evidence_complete", (finding,), (), (), ())
        with self.assertRaisesRegex(ValueError, "tuple"):
            TaskEvidenceReport("task-evidence-reference", "evidence_complete", [], (), (), ())
        with self.assertRaisesRegex(ValueError, "task_validated"):
            TaskEvidenceReport("task-evidence-reference", "evidence_complete", (), (), (), (), task_validated=True)


if __name__ == "__main__":
    unittest.main()
