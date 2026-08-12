import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = (
    ROOT
    / "skills"
    / "robotics-design"
    / "scripts"
    / "validate_mission_animation_manifest.py"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MissionAnimationManifestTests(unittest.TestCase):
    def _fixture(self, base: Path) -> tuple[Path, dict]:
        records = {}
        for field, name, payload in (
            ("source_model", "robot.urdf", b"urdf"),
            ("source_trajectory", "trajectory.json", b"trajectory"),
            ("physics_trace", "trace.json", b"trace"),
            ("rendered_animation", "mission.mp4", b"video"),
        ):
            path = base / name
            path.write_bytes(payload)
            records[field] = {"path": name, "sha256": sha256(path)}

        manifest = {
            "schema_version": 1,
            "animation_id": "s2_inchworm_transfer",
            "status": "promoted",
            **records,
            "joint_order": ["J1", "J2", "J3", "J4", "J5", "J6", "J7"],
            "required_moving_joints": ["J2", "J4", "J6"],
            "observed_moving_joints": ["J2", "J4", "J6"],
            "contact_interfaces": ["interface_A", "interface_B"],
            "continuous_anchor_required": True,
            "task_phases": [
                {
                    "name": "A anchored, B transfer",
                    "contact_state": {"interface_A": "hard_lock", "interface_B": "free"},
                    "load_case_id": "LC-S2-01",
                },
                {
                    "name": "dual anchor handover",
                    "contact_state": {
                        "interface_A": "hard_lock",
                        "interface_B": "hard_lock",
                    },
                    "load_case_id": "LC-S2-02",
                },
            ],
            "checks": {
                "topology_drift": 0,
                "joint_limit_violations": 0,
                "collision_violations": 0,
                "unconstrained_both_ends_frames": 0,
                "physics_trace_passed": True,
            },
            "review": {
                "reviewer": "independent reviewer",
                "method": "frame-and-trace audit",
                "notes": "All required joints and contacts verified.",
            },
        }
        manifest_path = base / "mission_manifest.json"
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

    def test_promoted_manifest_accepts_traceable_motion(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, _ = self._fixture(Path(raw))
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Mission animation manifest valid", completed.stdout)

    def test_promoted_manifest_rejects_static_required_joint(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["observed_moving_joints"] = ["J2", "J6"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("moving joint mismatch", completed.stderr)
            self.assertIn("J4", completed.stderr)

    def test_promoted_manifest_rejects_dual_release(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["task_phases"][0]["contact_state"] = {
                "interface_A": "free",
                "interface_B": "free",
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("all declared interfaces free", completed.stderr)

    def test_promoted_manifest_rejects_missing_load_case(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["task_phases"][0]["load_case_id"] = ""
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("load_case_id", completed.stderr)

    def test_manifest_rejects_tampered_trajectory_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            manifest_path, _ = self._fixture(base)
            (base / "trajectory.json").write_bytes(b"changed")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("source_trajectory SHA-256 mismatch", completed.stderr)

    def test_promoted_manifest_rejects_empty_motion_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["joint_order"] = []
            manifest["required_moving_joints"] = []
            manifest["observed_moving_joints"] = []
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("joint_order must contain at least one", completed.stderr)
            self.assertIn("required_moving_joints must contain at least one", completed.stderr)

    def test_manifest_rejects_missing_declared_contact_interface(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            del manifest["task_phases"][0]["contact_state"]["interface_B"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("missing declared contact interfaces", completed.stderr)
            self.assertIn("interface_B", completed.stderr)

    def test_manifest_rejects_malformed_types_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["status"] = []
            manifest["task_phases"][0]["contact_state"]["interface_A"] = []
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("status must be one of", completed.stderr)
            self.assertIn("invalid contact states", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_manifest_rejects_boolean_schema_version(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path, manifest = self._fixture(Path(raw))
            manifest["schema_version"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._run(manifest_path)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("schema_version", completed.stderr)


if __name__ == "__main__":
    unittest.main()
