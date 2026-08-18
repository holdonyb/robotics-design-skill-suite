import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.release.evaluator import REQUIRED_PATHS, evaluate_release_delivery, required_paths_for


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class ReleaseDeliveryEvaluatorTests(unittest.TestCase):
    def copy_candidate_tree(self, release_id="v1.0.0"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "candidate"
        for relative in required_paths_for(release_id):
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["suite"]["version"] = release_id.removeprefix("v")
        (root / "manifest.json").write_bytes(canonical(manifest))
        for name in ("README.md", "README.zh-CN.md"):
            path = root / name
            text = path.read_text(encoding="utf-8").replace("upcoming v0.9", "published v0.9").replace("即将到来的 v0.9", "已发布的 v0.9")
            if name == "README.md":
                text += "\nvalidate_release_delivery.py\nThis command verifies public software and evidence delivery; it does not validate physical robot performance or authorize hardware.\n"
            else:
                text += "\nvalidate_release_delivery.py\n此命令验证公开的软件与证据交付，不验证实体机器人性能，也不授权硬件操作。\n"
            path.write_text(text, encoding="utf-8")
        return root

    def write_contract(self, root, release_id="v1.0.0"):
        bindings = [
            {"path": relative, "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest()}
            for relative in sorted(required_paths_for(release_id))
        ]
        contract = root / "release" / f"{release_id}-release-contract.json"
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_bytes(canonical({"schema_version": 1, "release_id": release_id, "artifact_bindings": bindings, "hardware_claims": False}))
        return contract

    def test_pristine_bound_candidate_passes_deterministically(self):
        root = self.copy_candidate_tree()
        contract = self.write_contract(root)
        first = evaluate_release_delivery(root, contract)
        second = evaluate_release_delivery(root, contract)
        self.assertTrue(first.passed)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertFalse(first.hardware_claims)

    def test_v110_profile_binds_the_authority_runtime(self):
        required = required_paths_for("v1.1.0")
        for path in (
            "scripts/run_live_simulation_gate.sh",
            "scripts/validate_live_simulation_trace.py",
            "reference/mobile-manipulator/simulation/Dockerfile.jazzy-harmonic",
            "skills/robotics-design/scripts/assurance/simulation/__init__.py",
            "skills/robotics-design/scripts/assurance/simulation/live_trace.py",
            "skills/robotics-design/scripts/assurance/simulation/replay_features.py",
            "skills/robotics-design/scripts/assurance/simulation/training.py",
        ):
            self.assertIn(path, required)
        root = self.copy_candidate_tree("v1.1.0")
        contract = self.write_contract(root, "v1.1.0")
        self.assertTrue(evaluate_release_delivery(root, contract).passed)
        authority = root / "skills/robotics-design/scripts/assurance/commissioning/authority.py"
        authority.write_text("tampered", encoding="utf-8")
        report = evaluate_release_delivery(root, contract)
        self.assertFalse(report.passed)
        self.assertIn("RELEASE.STALE_ARTIFACT", {item.code for item in report.findings})

    def test_unknown_or_unhashable_release_profile_fails_actionably(self):
        with self.assertRaisesRegex(ValueError, "unsupported release_id"):
            required_paths_for([])

    def test_rehashed_contract_cannot_hide_stale_public_boundary(self):
        root = self.copy_candidate_tree()
        contract = self.write_contract(root)
        readme = root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace("This command verifies public software and evidence delivery", "task validated"), encoding="utf-8")
        self.write_contract(root)
        report = evaluate_release_delivery(root, contract)
        self.assertFalse(report.passed)
        self.assertIn("RELEASE.PUBLIC_BOUNDARY", {item.code for item in report.findings})

    def test_digest_extra_and_nonempty_intake_attacks_fail_closed(self):
        for attack in ("digest", "extra", "nonempty_task_intake"):
            with self.subTest(attack=attack):
                root = self.copy_candidate_tree()
                contract = self.write_contract(root)
                if attack == "digest":
                    (root / "README.md").write_text("tampered", encoding="utf-8")
                elif attack == "extra":
                    payload = json.loads(contract.read_text(encoding="utf-8"))
                    payload["artifact_bindings"].append({"path": "extra.txt", "sha256": "0" * 64})
                    contract.write_bytes(canonical(payload))
                else:
                    index = root / "reference/mobile-manipulator/task-evidence/task-evidence-index.json"
                    index.write_bytes(canonical({"schema_version": 1, "task_evidence_id": "task-evidence-reference", "packages": [{"path": "future.json", "sha256": "0" * 64}]}))
                    self.write_contract(root)
                report = evaluate_release_delivery(root, contract)
                self.assertFalse(report.passed)
                self.assertTrue(any(item.severity == "error" for item in report.findings))

    def test_symlinked_bound_source_fails_closed(self):
        root = self.copy_candidate_tree()
        contract = self.write_contract(root)
        target = root / "README.md"
        backup = root / "README-backup.md"
        target.replace(backup)
        try:
            os.symlink(backup, target)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        report = evaluate_release_delivery(root, contract)
        self.assertFalse(report.passed)
        self.assertIn("RELEASE.BOUND_PATH", {item.code for item in report.findings})


if __name__ == "__main__":
    unittest.main()
