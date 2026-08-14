import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "robotics-design" / "scripts" / "validate_commissioning_evidence.py"
INDEX = ROOT / "reference" / "mobile-manipulator" / "commissioning" / "commissioning-index.json"


class ReferenceCommissioningTests(unittest.TestCase):
    def test_reference_intake_awaits_authorization_and_never_claims_hardware(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--index", str(INDEX)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("awaiting_authorization", report["status"])
        self.assertIsNone(report["highest_validated_phase"])
        self.assertFalse(report["procurement_authorized"])
        self.assertFalse(report["motion_authorized"])
        self.assertNotIn("integrated-hardware-tested", result.stdout)

    def test_reference_raw_readme_forbids_fabricated_commissioning_records(self):
        text = (INDEX.parent / "raw" / "README.md").read_text(encoding="utf-8").lower()
        for forbidden in ("generated", "simulated", "copied", "hand-edited", "fabricated"):
            self.assertIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
