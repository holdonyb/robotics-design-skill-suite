import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "skills" / "robotics-design" / "scripts" / "validate_visual_manifest.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VisualManifestTests(unittest.TestCase):
    def _fixture(self, base: Path) -> tuple[Path, dict]:
        model = base / "robot.urdf"
        pose = base / "task_pose.json"
        reference = base / "task_pose_iso.png"
        model.write_text("<robot name='seven_axis_arm'/>", encoding="utf-8")
        pose.write_text('{"J1": 0.1, "J2": -0.2}', encoding="utf-8")
        reference.write_bytes(b"deterministic-render")

        manifest = {
            "schema_version": 1,
            "shot_id": "dual-arm-rover-work-001",
            "status": "promoted",
            "source_model": {"path": model.name, "sha256": sha256(model)},
            "source_pose": {"path": pose.name, "sha256": sha256(pose)},
            "reference_images": [{"path": reference.name, "sha256": sha256(reference)}],
            "required_landmarks": [
                "left_arm.J1",
                "left_arm.J2",
                "left_arm.J3",
                "left_arm.J4",
                "left_arm.J5",
                "left_arm.J6",
                "left_arm.J7",
                "left_arm.interface_A",
                "left_arm.interface_B",
            ],
            "observed_landmarks": [
                "left_arm.J1",
                "left_arm.J2",
                "left_arm.J3",
                "left_arm.J4",
                "left_arm.J5",
                "left_arm.J6",
                "left_arm.J7",
                "left_arm.interface_A",
                "left_arm.interface_B",
            ],
            "allowed_changes": ["materials", "surface_finish", "lighting", "background"],
            "forbidden_changes": [
                "topology",
                "pose",
                "joint_count",
                "joint_axes",
                "interfaces",
                "link_proportions",
            ],
            "review": {
                "reviewer": "mechanism-owner",
                "method": "side-by-side landmark review",
                "notes": "All seven joints and both interfaces are visible.",
            },
        }
        manifest_path = base / "visual_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest_path, manifest

    def _run(self, manifest_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(manifest_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_valid_promoted_manifest_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, _ = self._fixture(Path(raw))
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Visual manifest valid", completed.stdout)

    def test_promoted_manifest_rejects_missing_landmark(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["observed_landmarks"].remove("left_arm.J6")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("landmark mismatch", completed.stderr)
            self.assertIn("left_arm.J6", completed.stderr)

    def test_manifest_rejects_pose_as_an_allowed_change(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["allowed_changes"].append("pose")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("allowed_changes", completed.stderr)
            self.assertIn("pose", completed.stderr)

    def test_manifest_rejects_tampered_source_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            manifest_path, _ = self._fixture(base)
            (base / "robot.urdf").write_text("<robot name='changed'/>", encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("SHA-256 mismatch", completed.stderr)
            self.assertIn("robot.urdf", completed.stderr)

    def test_promoted_manifest_requires_review_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["review"]["reviewer"] = ""
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("review.reviewer", completed.stderr)

    def test_promoted_manifest_rejects_empty_landmark_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["required_landmarks"] = []
            manifest["observed_landmarks"] = []
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("required_landmarks", completed.stderr)
            self.assertIn("at least one", completed.stderr)

    def test_promoted_manifest_requires_review_notes(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["review"].pop("notes")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("review.notes", completed.stderr)


if __name__ == "__main__":
    unittest.main()
