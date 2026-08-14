import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "robotics-design" / "scripts" / "validate_task_evidence.py"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class TaskEvidenceCliTests(unittest.TestCase):
    def test_empty_intake_awaits_authorization_without_task_claim(self):
        with tempfile.TemporaryDirectory() as raw:
            index = Path(raw) / "task-evidence-index.json"
            index.write_bytes(canonical({"schema_version": 1, "task_evidence_id": "task-evidence-reference", "packages": []}))
            result = subprocess.run([sys.executable, str(CLI), "--index", str(index)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("awaiting_authorization", report["status"])
        self.assertFalse(report["procurement_authorized"])
        self.assertFalse(report["motion_authorized"])
        self.assertFalse(report["task_validated"])

    def test_populated_intake_requires_all_hash_bound_upstream_sources(self):
        with tempfile.TemporaryDirectory() as raw:
            index = Path(raw) / "task-evidence-index.json"
            binding = {"path": "missing.json", "sha256": "0" * 64}
            index.write_bytes(canonical({"schema_version": 1, "task_evidence_id": "task-evidence-reference", "packages": [{"path": "package.json", "sha256": "0" * 64}], "design_contract": binding, "freeze_package": binding, "bench_index": binding, "commissioning_index": binding, "task_protocol": binding}))
            result = subprocess.run([sys.executable, str(CLI), "--index", str(index)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("design_contract.path", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
