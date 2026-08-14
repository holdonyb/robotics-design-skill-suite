import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_task_evidence_protocol import protocol
from tests.test_task_evidence_evaluator import minimal_protocol, nominal


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "robotics-design" / "scripts" / "validate_task_evidence.py"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_bound(root, relative, value):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical(value))
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def bound_existing(root, relative):
    target = root / relative
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


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

    def test_bound_task_protocol_is_parsed_before_package_evaluation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            protocol = root / "protocol.json"
            protocol.write_bytes(canonical({"schema_version": 1}))
            sha = __import__("hashlib").sha256(protocol.read_bytes()).hexdigest()
            binding = {"path": "protocol.json", "sha256": sha}
            index = root / "task-evidence-index.json"
            index.write_bytes(canonical({"schema_version": 1, "task_evidence_id": "task-evidence-reference", "packages": [{"path": "package.json", "sha256": "0" * 64}], "design_contract": binding, "freeze_package": binding, "bench_index": binding, "commissioning_index": binding, "task_protocol": binding}))
            result = subprocess.run([sys.executable, str(CLI), "--index", str(index)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("task protocol", result.stderr)

    def test_bound_task_packages_are_loaded_after_protocol(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            protocol_path = root / "protocol.json"
            protocol_path.write_bytes(canonical(protocol()))
            sha = __import__("hashlib").sha256(protocol_path.read_bytes()).hexdigest()
            binding = {"path": "protocol.json", "sha256": sha}
            index = root / "task-evidence-index.json"
            index.write_bytes(canonical({"schema_version": 1, "task_evidence_id": "task-evidence-reference", "packages": [{"path": "missing-package.json", "sha256": "0" * 64}], "design_contract": binding, "freeze_package": binding, "bench_index": binding, "commissioning_index": binding, "task_protocol": binding}))
            result = subprocess.run([sys.executable, str(CLI), "--index", str(index)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("packages[0].path", result.stderr)

    def test_populated_intake_binds_and_evaluates_all_upstream_evidence(self):
        reference = ROOT / "reference" / "mobile-manipulator"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "reference"
            shutil.copytree(reference, root)
            protocol_binding = write_bound(root, Path("task-protocol.json"), minimal_protocol())
            package = nominal(root)
            package_binding = write_bound(root, Path("task-package.json"), package)
            bench_binding = write_bound(root, Path("bench-index.json"), {"schema_version": 1, "intake_id": "bench-reference", "packages": []})
            index = root / "task-evidence-index.json"
            index.write_bytes(canonical({
                "schema_version": 1,
                "task_evidence_id": "task-evidence-reference",
                "packages": [package_binding],
                "design_contract": bound_existing(root, Path("design-contract.json")),
                "freeze_package": bound_existing(root, Path("engineering-freeze/freeze-package.json")),
                "bench_index": bench_binding,
                "commissioning_index": bound_existing(root, Path("commissioning/commissioning-index.json")),
                "task_protocol": protocol_binding,
            }))
            result = subprocess.run([sys.executable, str(CLI), "--index", str(index)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("awaiting_authorization", report["status"])
        self.assertIn("TASK.FREEZE_NOT_READY", {item["code"] for item in report["findings"]})
        self.assertIn("TASK.BENCH_EVIDENCE_REQUIRED", {item["code"] for item in report["findings"]})
        self.assertIn("TASK.COMMISSIONING_REQUIRED", {item["code"] for item in report["findings"]})


if __name__ == "__main__":
    unittest.main()
