import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.live_trace import (  # noqa: E402
    LiveTraceError,
    normalize_records,
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
    def test_normalizer_accepts_only_the_live_gate_ros_topics(self):
        records = [
            {"topic": "/clock", "type": "rosgraph_msgs/msg/Clock", "timestamp_ns": 0, "message": {"clock": {"sec": 0, "nanosec": 0}}},
            {"topic": "/clock", "type": "rosgraph_msgs/msg/Clock", "timestamp_ns": 1_000_000_000, "message": {"clock": {"sec": 1, "nanosec": 0}}},
            {"topic": "/clock", "type": "rosgraph_msgs/msg/Clock", "timestamp_ns": 2_000_000_000, "message": {"clock": {"sec": 2, "nanosec": 0}}},
            {"topic": "/joint_states", "type": "sensor_msgs/msg/JointState", "timestamp_ns": 0, "message": {"header": {"stamp": {"sec": 0, "nanosec": 0}}, "name": ["left_wheel_joint", "right_wheel_joint", "joint_1"], "position": [0.0, 0.0, 0.0]}},
            {"topic": "/joint_states", "type": "sensor_msgs/msg/JointState", "timestamp_ns": 2_000_000_000, "message": {"header": {"stamp": {"sec": 2, "nanosec": 0}}, "name": ["left_wheel_joint", "right_wheel_joint", "joint_1"], "position": [1.0, 1.0, 0.0]}},
            {"topic": "/diff_drive_controller/odom", "type": "nav_msgs/msg/Odometry", "timestamp_ns": 0, "message": {"header": {"stamp": {"sec": 0, "nanosec": 0}}, "pose": {"pose": {"position": {"x": 0.0, "y": 0.0}, "orientation": {"z": 0.0, "w": 1.0}}}}},
            {"topic": "/diff_drive_controller/odom", "type": "nav_msgs/msg/Odometry", "timestamp_ns": 2_000_000_000, "message": {"header": {"stamp": {"sec": 2, "nanosec": 0}}, "pose": {"pose": {"position": {"x": 0.15, "y": 0.0}, "orientation": {"z": 0.0, "w": 1.0}}}}},
            {"topic": "/diff_drive_controller/cmd_vel", "type": "geometry_msgs/msg/TwistStamped", "timestamp_ns": 500_000_000, "message": {"header": {"stamp": {"sec": 0, "nanosec": 500_000_000}}, "twist": {"linear": {"x": 0.1}, "angular": {"z": 0.0}}}},
            {"topic": "/diff_drive_controller/cmd_vel", "type": "geometry_msgs/msg/TwistStamped", "timestamp_ns": 1_500_000_000, "message": {"header": {"stamp": {"sec": 1, "nanosec": 500_000_000}}, "twist": {"linear": {"x": 0.1}, "angular": {"z": 0.0}}}},
        ]
        normalized = normalize_records(records)
        self.assertEqual(capture(), normalized)
        invalid = list(records)
        invalid[0] = dict(invalid[0], topic="/rogue")
        with self.assertRaisesRegex(LiveTraceError, "unknown topic"):
            normalize_records(invalid)
        invalid = list(records)
        invalid[3] = dict(invalid[3], message={"name": [], "position": []})
        with self.assertRaisesRegex(LiveTraceError, "header"):
            normalize_records(invalid)

    def test_runtime_adapter_uses_rosbag_deserialization_only_at_linux_boundary(self):
        source = (ROOT / "scripts" / "validate_live_simulation_trace.py").read_text(encoding="utf-8")
        for token in ("rosbag2_py.SequentialReader", "deserialize_message", "get_message", 'storage_id="mcap"', "publish_live_trace_bundle", "validate_retained_live_trace_bundle"):
            self.assertIn(token, source)
        self.assertIn('topic == "/diff_drive_controller/odom"', source)
        self.assertNotIn('topic == "/odom"', source)

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
            (bag / "live-drive_0.mcap").write_bytes(b"\x89MCAP0\r\ntrace\x89MCAP0\r\n")
            receipt = publish_live_trace_bundle(root / "bundle", capture(), PROFILE, bag)
            self.assertEqual([], validate_retained_live_trace_bundle(root / "bundle", receipt.manifest_sha256, bag))
            (bag / "live-drive_0.mcap").write_bytes(b"\x89MCAP0\r\nchanged\x89MCAP0\r\n")
            self.assertIn("raw bag SHA-256 mismatch", validate_retained_live_trace_bundle(root / "bundle", receipt.manifest_sha256, bag))

            tampered = root / "tampered"
            shutil.copytree(bag, tampered)
            (tampered / "extra.mcap").write_bytes(b"\x89MCAP0\r\nextra\x89MCAP0\r\n")
            self.assertIn("raw bag files are not closed", validate_retained_live_trace_bundle(root / "bundle", receipt.manifest_sha256, tampered))

    def test_raw_bag_rejects_a_non_mcap_payload_even_with_a_valid_suffix(self):
        with tempfile.TemporaryDirectory() as raw:
            bag = Path(raw) / "live-drive"
            bag.mkdir()
            (bag / "metadata.yaml").write_text("rosbag2_bagfile_information: {}\n", encoding="utf-8")
            (bag / "live-drive_0.mcap").write_bytes(b"not an mcap")
            with self.assertRaisesRegex(LiveTraceError, "MCAP signature"):
                publish_live_trace_bundle(Path(raw) / "bundle", capture(), PROFILE, bag)


if __name__ == "__main__":
    unittest.main()
