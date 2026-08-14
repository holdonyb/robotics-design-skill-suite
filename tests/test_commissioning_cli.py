import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_commissioning_evaluator import package


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "robotics-design" / "scripts" / "validate_commissioning_evidence.py"
REFERENCE = ROOT / "reference" / "mobile-manipulator" / "commissioning" / "commissioning-index.json"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class CommissioningCliTests(unittest.TestCase):
    def run_cli(self, index=REFERENCE):
        return subprocess.run(
            [sys.executable, str(CLI), "--index", str(index)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_empty_intake_awaits_authorization(self):
        with tempfile.TemporaryDirectory() as raw:
            index = Path(raw) / "commissioning-index.json"
            index.write_bytes(canonical({"schema_version": 1, "commissioning_id": "commissioning-reference", "phases": []}))
            result = self.run_cli(index)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn('"status":"awaiting_authorization"', result.stdout)
        self.assertIn('"procurement_authorized":false', result.stdout)
        self.assertIn('"motion_authorized":false', result.stdout)

    def test_nonempty_intake_binds_design_freeze_and_bench_sources(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "reference"
            shutil.copytree(ROOT / "reference" / "mobile-manipulator", root)
            design_sha256 = hashlib.sha256((root / "design-contract.json").read_bytes()).hexdigest()
            value = package(root, design_contract_sha256=design_sha256)
            source = {
                "schema_version": 1,
                "commissioning_id": "commissioning-reference",
                "phases": value["phases"],
                "design_contract": {"path": "design-contract.json", "sha256": design_sha256},
                "freeze_package": {"path": "engineering-freeze/freeze-package.json", "sha256": hashlib.sha256((root / "engineering-freeze" / "freeze-package.json").read_bytes()).hexdigest()},
                "bench_index": {"path": "bench-evidence/intake-index.json", "sha256": hashlib.sha256((root / "bench-evidence" / "intake-index.json").read_bytes()).hexdigest()},
            }
            index = root / "commissioning-index.json"
            index.write_bytes(canonical(source))
            result = self.run_cli(index)
            self.assertEqual(1, result.returncode, result.stderr)
            ready_stdout = result.stdout
            self.assertIn('"status":"awaiting_authorization"', ready_stdout)
            self.assertIn("COMM.FREEZE_NOT_READY", ready_stdout)
            self.assertIn("COMM.BENCH_EVIDENCE_REQUIRED", ready_stdout)
            freeze_path = root / "engineering-freeze" / "freeze-package.json"
            freeze_path.write_bytes(canonical({"schema_version": 1, "freeze_id": "freeze-invalid"}))
            source["freeze_package"]["sha256"] = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
            index.write_bytes(canonical(source))
            result = self.run_cli(index)
            self.assertEqual(2, result.returncode)
            self.assertIn("freeze package", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        self.assertIn('"motion_authorized":false', ready_stdout)

    def test_nonempty_but_rejected_bench_package_keeps_commissioning_blocked(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "reference"
            shutil.copytree(ROOT / "reference" / "mobile-manipulator", root)
            bench_root = root / "bench-evidence"
            bench_contract = bench_root / "design-contract.json"
            shutil.copy2(root / "design-contract.json", bench_contract)
            invalid_package = root / "bench-evidence" / "invalid-package.json"
            invalid_package.write_bytes(canonical({
                "schema_version": 1,
                "package_id": "bench-invalid",
                "raw_data": {"sha256": "0" * 64},
            }))
            bench_index = root / "bench-evidence" / "intake-index.json"
            bench_index.write_bytes(canonical({
                "schema_version": 1,
                "intake_id": "rejected-bench",
                "design_contract": {
                    "path": "design-contract.json",
                    "sha256": hashlib.sha256(bench_contract.read_bytes()).hexdigest(),
                },
                "packages": [{
                    "path": "invalid-package.json",
                    "sha256": hashlib.sha256(invalid_package.read_bytes()).hexdigest(),
                }],
            }))
            design_sha256 = hashlib.sha256((root / "design-contract.json").read_bytes()).hexdigest()
            value = package(root, design_contract_sha256=design_sha256)
            value.update({
                "design_contract": {"path": "design-contract.json", "sha256": design_sha256},
                "freeze_package": {"path": "engineering-freeze/freeze-package.json", "sha256": hashlib.sha256((root / "engineering-freeze" / "freeze-package.json").read_bytes()).hexdigest()},
                "bench_index": {"path": "bench-evidence/intake-index.json", "sha256": hashlib.sha256(bench_index.read_bytes()).hexdigest()},
            })
            index = root / "commissioning-index.json"
            index.write_bytes(canonical(value))
            result = self.run_cli(index)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn('"status":"awaiting_authorization"', result.stdout)
        self.assertIn("COMM.BENCH_EVIDENCE_REQUIRED", result.stdout)

    def test_recorded_authority_must_bind_the_index_design_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "reference"
            shutil.copytree(ROOT / "reference" / "mobile-manipulator", root)
            value = package(root)
            value.update({
                "design_contract": {"path": "design-contract.json", "sha256": hashlib.sha256((root / "design-contract.json").read_bytes()).hexdigest()},
                "freeze_package": {"path": "engineering-freeze/freeze-package.json", "sha256": hashlib.sha256((root / "engineering-freeze" / "freeze-package.json").read_bytes()).hexdigest()},
                "bench_index": {"path": "bench-evidence/intake-index.json", "sha256": hashlib.sha256((root / "bench-evidence" / "intake-index.json").read_bytes()).hexdigest()},
            })
            index = root / "commissioning-index.json"
            index.write_bytes(canonical(value))
            result = self.run_cli(index)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("COMM.AUTHORITY_DESIGN_MISMATCH", result.stdout)
        self.assertIn('"motion_authorized":false', result.stdout)

    def test_malformed_or_tampered_input_exits_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            index = root / "bad.json"
            index.write_text("{bad}\n", encoding="utf-8")
            result = self.run_cli(index)
            self.assertEqual(2, result.returncode)
            self.assertIn("ERROR:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            index.write_bytes(canonical({"schema_version": 1, "commissioning_id": "bad", "phases": [{"path": "../escape"}]}))
            result = self.run_cli(index)
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
