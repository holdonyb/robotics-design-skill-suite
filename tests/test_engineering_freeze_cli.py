import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "robotics-design" / "scripts" / "validate_engineering_freeze.py"
REFERENCE = ROOT / "reference" / "mobile-manipulator" / "engineering-freeze" / "freeze-package.json"


class EngineeringFreezeCliTests(unittest.TestCase):
    def run_cli(self, package=REFERENCE, *extra):
        return subprocess.run(
            [sys.executable, str(CLI), "--package", str(package), *extra],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_reference_is_valid_input_but_not_ready_or_hardware_authorized(self):
        result = self.run_cli()
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn('"procurement_authorized":false', result.stdout)
        self.assertIn('"motion_authorized":false', result.stdout)
        self.assertIn("FREEZE.PLACEHOLDER_COMPONENT", result.stdout)
        self.assertIn("FREEZE.REQUIRED_ARTIFACT_MISSING", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_input_exits_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            package = Path(raw) / "bad.json"
            package.write_text("{not-json}\n", encoding="utf-8")
            result = self.run_cli(package)
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_report_write_is_canonical_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as raw:
            report = Path(raw) / "report.json"
            first = self.run_cli(REFERENCE, "--report", str(report))
            self.assertEqual(1, first.returncode, first.stderr)
            self.assertTrue(report.read_bytes().endswith(b"\n"))
            second = self.run_cli(REFERENCE, "--report", str(report))
            self.assertEqual(2, second.returncode)
            self.assertIn("already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
