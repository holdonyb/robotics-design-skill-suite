import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "robotics-design" / "scripts" / "validate_simulation_bundle.py"


class SimulationCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_reference_exit_codes_are_valid_failed_and_invalid(self):
        valid = self.run_cli("--reference-root", ROOT / "reference" / "mobile-manipulator")
        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertEqual(10, json.loads(valid.stdout)["passed_scenarios"])

        failed = self.run_cli("--reference-root", ROOT / "reference" / "mobile-manipulator", "--force-failed-scenario")
        self.assertEqual(1, failed.returncode, failed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            invalid = self.run_cli("--reference-root", Path(raw) / "not-a-reference")
        self.assertEqual(2, invalid.returncode)
        self.assertNotIn("Traceback", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
