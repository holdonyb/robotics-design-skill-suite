import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.release.evaluator import REQUIRED_PATHS, required_paths_for


GENERATOR = ROOT / "skills/robotics-design/scripts/generate_release_delivery_contract.py"
CLI = ROOT / "skills/robotics-design/scripts/validate_release_delivery.py"


class TestReleaseDeliveryCli(unittest.TestCase):
    def copy_candidate_tree(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "candidate"
        for relative in REQUIRED_PATHS:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["suite"]["version"] = "1.0.0"
        (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        english = root / "README.md"
        english.write_text(english.read_text(encoding="utf-8").replace("upcoming v0.9", "published v0.9") + "\nvalidate_release_delivery.py\nThis command verifies public software and evidence delivery; it does not validate physical robot performance or authorize hardware.\n", encoding="utf-8")
        chinese = root / "README.zh-CN.md"
        chinese.write_text(chinese.read_text(encoding="utf-8").replace("即将到来的 v0.9", "已发布的 v0.9") + "\nvalidate_release_delivery.py\n此命令验证公开的软件与证据交付，不验证实体机器人性能，也不授权硬件操作。\n", encoding="utf-8")
        return root

    def run_cli(self, script, *args):
        return subprocess.run(
            [sys.executable, str(script), *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_generator_and_cli_emit_canonical_passing_report(self):
        root = self.copy_candidate_tree()
        contract = root / "release/v1-release-contract.json"
        created = self.run_cli(GENERATOR, "--root", root, "--out", contract)
        self.assertEqual(0, created.returncode, created.stderr)
        result = self.run_cli(CLI, "--root", root, "--contract", contract)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["hardware_claims"])
        self.assertEqual((json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"), result.stdout)

    def test_generator_refuses_overwrite_and_cli_fails_safely(self):
        root = self.copy_candidate_tree()
        contract = root / "release/v1-release-contract.json"
        first = self.run_cli(GENERATOR, "--root", root, "--out", contract)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(2, self.run_cli(GENERATOR, "--root", root, "--out", contract).returncode)
        contract.write_text("not JSON", encoding="utf-8")
        result = self.run_cli(CLI, "--root", root, "--contract", contract)
        self.assertEqual(2, result.returncode)
        self.assertIn("failed safely", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_v110_generator_binds_the_authority_intake_surface(self):
        root = self.copy_candidate_tree()
        for relative in sorted(required_paths_for("v1.1.0") - REQUIRED_PATHS):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["suite"]["version"] = "1.1.0"
        (root / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        contract = root / "release/v1.1-release-contract.json"
        created = self.run_cli(
            GENERATOR, "--root", root, "--release-id", "v1.1.0", "--out", contract
        )
        self.assertEqual(0, created.returncode, created.stderr)
        self.assertEqual(0, self.run_cli(CLI, "--root", root, "--contract", contract).returncode)
        authority = root / "skills/robotics-design/scripts/assurance/commissioning/authority.py"
        authority.write_text("tampered", encoding="utf-8")
        self.assertEqual(1, self.run_cli(CLI, "--root", root, "--contract", contract).returncode)


if __name__ == "__main__":
    unittest.main()
