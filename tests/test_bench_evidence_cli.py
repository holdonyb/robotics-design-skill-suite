import json
import hashlib
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_bench_evidence import package


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "robotics-design" / "scripts" / "validate_bench_evidence.py"
REFERENCE = ROOT / "reference" / "mobile-manipulator" / "bench-evidence" / "intake-index.json"


class BenchEvidenceCliTests(unittest.TestCase):
    def run_cli(self, index=REFERENCE, *extra):
        return subprocess.run(
            [sys.executable, str(CLI), "--index", str(index), *extra], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def test_empty_reference_intake_awaits_authorization(self):
        result = self.run_cli()
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn('"status":"awaiting_authorization"', result.stdout)
        self.assertIn('"procurement_authorized":false', result.stdout)
        self.assertIn('"motion_authorized":false', result.stdout)

    def test_invalid_index_exits_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            index = Path(raw) / "bad.json"
            index.write_text("{bad}\n", encoding="utf-8")
            result = self.run_cli(index)
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_nonobject_and_empty_populated_indexes_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            nonobject = root / "nonobject.json"
            nonobject.write_text("[{}]\n", encoding="utf-8")
            result = self.run_cli(nonobject)
            self.assertEqual(2, result.returncode)
            self.assertNotIn("Traceback", result.stderr)
            empty_populated = root / "empty-populated.json"
            index = {"schema_version": 1, "intake_id": "bad", "design_contract": {"path": "x", "sha256": "0" * 64}, "packages": []}
            empty_populated.write_bytes((json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(empty_populated)
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_index_validates_nonempty_hash_bound_package(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract_path = root / "design-contract.json"
            shutil.copy2(ROOT / "reference" / "mobile-manipulator" / "design-contract.json", contract_path)
            bench = package(root, fixture_only=False, component_id="CMP-TRACTION-MOTOR-L")
            bench_path = root / "package.json"
            bench_path.write_bytes((json.dumps(bench, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            index = {
                "schema_version": 1, "intake_id": "fixture-intake",
                "design_contract": {"path": "design-contract.json", "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest()},
                "packages": [{"path": "package.json", "sha256": hashlib.sha256(bench_path.read_bytes()).hexdigest()}],
            }
            index_path = root / "intake-index.json"
            index_path.write_bytes((json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(index_path)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('"accepted_packages":1', result.stdout)
        self.assertIn('"evidence_level":"bench-tested"', result.stdout)

    def test_fixture_only_package_cannot_claim_bench_tested_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract_path = root / "design-contract.json"
            shutil.copy2(ROOT / "reference" / "mobile-manipulator" / "design-contract.json", contract_path)
            bench_path = root / "package.json"
            bench_path.write_bytes((json.dumps(package(root, component_id="CMP-TRACTION-MOTOR-L"), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            index = {"schema_version": 1, "intake_id": "fixture-intake", "design_contract": {"path": "design-contract.json", "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest()}, "packages": [{"path": "package.json", "sha256": hashlib.sha256(bench_path.read_bytes()).hexdigest()}]}
            index_path = root / "intake-index.json"
            index_path.write_bytes((json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(index_path)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn('"status":"awaiting_authorization"', result.stdout)
        self.assertIn('"accepted_packages":0', result.stdout)
        self.assertIn('"evidence_level":null', result.stdout)

    def test_populated_index_rejects_path_escape_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            index_path = Path(raw) / "intake-index.json"
            index = {"schema_version": 1, "intake_id": "bad", "design_contract": {"path": "../outside.json", "sha256": "0" * 64}, "packages": [{"path": "package.json", "sha256": "0" * 64}]}
            index_path.write_bytes((json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(index_path)
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_package_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract_path = root / "design-contract.json"
            shutil.copy2(ROOT / "reference" / "mobile-manipulator" / "design-contract.json", contract_path)
            hashes = []
            for position, name in enumerate(("one.json", "two.json")):
                bench_path = root / name
                bench = package(root, fixture_only=False, component_id="CMP-TRACTION-MOTOR-L")
                bench["operator_id"] = f"operator-{position}"
                bench_path.write_bytes((json.dumps(bench, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
                hashes.append({"path": name, "sha256": hashlib.sha256(bench_path.read_bytes()).hexdigest()})
            index = {"schema_version": 1, "intake_id": "duplicate", "design_contract": {"path": "design-contract.json", "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest()}, "packages": hashes}
            index_path = root / "intake-index.json"
            index_path.write_bytes((json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(index_path)
        self.assertEqual(2, result.returncode)
        self.assertIn("unique package_id", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_intake_id_and_duplicate_package_hash_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bad_id = root / "bad-id.json"
            bad_id.write_bytes((json.dumps({"intake_id": "bad id", "packages": [], "schema_version": 1}, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(bad_id)
            self.assertEqual(2, result.returncode)
            self.assertIn("intake_id", result.stderr)
            duplicate = root / "duplicate.json"
            index = {"schema_version": 1, "intake_id": "duplicate", "design_contract": {"path": "contract.json", "sha256": "0" * 64}, "packages": [{"path": "one.json", "sha256": "1" * 64}, {"path": "two.json", "sha256": "1" * 64}]}
            duplicate.write_bytes((json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            result = self.run_cli(duplicate)
        self.assertEqual(2, result.returncode)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
