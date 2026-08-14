import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
