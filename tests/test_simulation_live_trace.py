import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.live_trace import (  # noqa: E402
    LiveTraceError,
    publish_live_trace_bundle,
    validate_live_capture,
    validate_retained_live_trace_bundle,
)


PROFILE = {
    "wheel_radius_m": 0.15,
    "wheel_speed_limit_rad_s": 0.4 / 0.15,
    "workspace_manifest_sha256": "a" * 64,
    "sources": [{"path": "profile.yaml", "sha256": "b" * 64}],
}


def capture():
    return {
        "clock_ns": [0, 1_000_000_000, 2_000_000_000],
        "joint_samples": [
            {
                "timestamp_ns": 0,
                "names": ["left_wheel_joint", "right_wheel_joint", "joint_1"],
                "positions": [0.0, 0.0, 0.0],
            },
            {
                "timestamp_ns": 2_000_000_000,
                "names": ["left_wheel_joint", "right_wheel_joint", "joint_1"],
                "positions": [1.0, 1.0, 0.0],
            },
        ],
        "odom_samples": [
            {"timestamp_ns": 0, "x_m": 0.0, "y_m": 0.0, "yaw_rad": 0.0},
            {"timestamp_ns": 2_000_000_000, "x_m": 0.15, "y_m": 0.0, "yaw_rad": 0.0},
        ],
        "command_samples": [
            {"timestamp_ns": 500_000_000, "linear_x_m_s": 0.1, "angular_z_rad_s": 0.0},
            {"timestamp_ns": 1_500_000_000, "linear_x_m_s": 0.1, "angular_z_rad_s": 0.0},
        ],
    }


class LiveTraceTests(unittest.TestCase):
    def test_valid_capture_is_simulated_and_hardware_firewalled(self):
        result = validate_live_capture(capture(), PROFILE)
        self.assertEqual("live_simulation_trace", result["kind"])
        self.assertEqual("simulated", result["evidence_level"])
        self.assertEqual("passed", result["status"])
        self.assertFalse(result["hardware_promotable"])
        self.assertGreaterEqual(result["forward_displacement_m"], 0.01)

    def test_capture_rejects_unknown_or_invalid_observations(self):
        cases = []
        unknown = capture(); unknown["rogue"] = []
        cases.append((unknown, "fields are not closed"))
        reversed_clock = capture(); reversed_clock["clock_ns"] = [0, 2, 1]
        cases.append((reversed_clock, "strictly increasing"))
        nonfinite = capture(); nonfinite["odom_samples"][1]["x_m"] = float("nan")
        cases.append((nonfinite, "finite"))
        over_limit = capture(); over_limit["command_samples"][0]["linear_x_m_s"] = 0.5
        cases.append((over_limit, "linear command"))
        missing_joint = capture(); missing_joint["joint_samples"][0]["names"] = ["right_wheel_joint", "joint_1"]; missing_joint["joint_samples"][0]["positions"] = [0.0, 0.0]
        cases.append((missing_joint, "drive joints"))
        no_motion = capture(); no_motion["odom_samples"][1]["x_m"] = 0.0
        cases.append((no_motion, "forward displacement"))
        for invalid, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(LiveTraceError, message):
                validate_live_capture(invalid, PROFILE)

    def test_retained_bundle_binds_raw_mcap_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bag = root / "live-drive"
            bag.mkdir()
            (bag / "metadata.yaml").write_text("rosbag2_bagfile_information: {}\n", encoding="utf-8")
            (bag / "live-drive_0.mcap").write_bytes(b"MCAP0")
            receipt = publish_live_trace_bundle(root / "bundle", capture(), PROFILE, bag)
            self.assertEqual([], validate_retained_live_trace_bundle(root / "bundle", receipt.manifest_sha256, bag))
            (bag / "live-drive_0.mcap").write_bytes(b"MCAP1")
            self.assertIn("raw bag SHA-256 mismatch", validate_retained_live_trace_bundle(root / "bundle", receipt.manifest_sha256, bag))

            tampered = root / "tampered"
            shutil.copytree(bag, tampered)
            (tampered / "extra.mcap").write_bytes(b"MCAP")
            self.assertIn("raw bag files are not closed", validate_retained_live_trace_bundle(root / "bundle", receipt.manifest_sha256, tampered))


if __name__ == "__main__":
    unittest.main()
