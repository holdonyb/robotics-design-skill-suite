import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SimulationCiTests(unittest.TestCase):
    def test_live_gate_declares_pinned_linux_consumers_and_mandatory_evidence(self):
        dockerfile = (ROOT / "reference/mobile-manipulator/simulation/Dockerfile.jazzy-harmonic").read_text(encoding="utf-8")
        lock = (ROOT / "reference/mobile-manipulator/simulation/environment-lock.json").read_text(encoding="utf-8")
        gate = (ROOT / "scripts/run_live_simulation_gate.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/simulation.yml").read_text(encoding="utf-8")
        self.assertIn("ubuntu:24.04@sha256:", dockerfile)
        self.assertIn("ros-jazzy", dockerfile)
        self.assertIn("gz-harmonic", dockerfile)
        self.assertIn("build-essential", dockerfile)
        self.assertIn("ros-jazzy-joint-trajectory-controller", dockerfile)
        self.assertIn("ros-jazzy-rosbag2-storage-mcap", dockerfile)
        self.assertIn('"image_digest"', lock)
        self.assertNotIn(":latest", dockerfile + workflow)
        for token in ("xacro", "colcon test", "gz sim", "ros2_control", "move_group", "nav2", "timeout", "trap", "validate_simulation_bundle.py", "kill -0", "joint_state_broadcaster", "arm_controller", "diff_drive_controller"):
            self.assertIn(token, gate)
        self.assertLess(gate.index("source /opt/ros/jazzy/setup.bash"), gate.index('test "${ROS_DISTRO:-}" = "jazzy"'))
        self.assertIn('"$WORKSPACE/build"', gate)
        self.assertIn('"$WORKSPACE/install"', gate)
        self.assertIn('"$WORKSPACE/log"', gate)
        self.assertIn('colcon --log-base "$WORKSPACE/log" build', gate)
        self.assertIn('colcon --log-base "$WORKSPACE/log" test', gate)
        self.assertIn('cat "$log" >&2', gate)
        self.assertIn("wait_for_clock()", gate)
        self.assertIn('timeout 3s ros2 topic echo --once /clock', gate)
        self.assertIn('wait_for_clock "${pids[0]}"', gate)
        self.assertIn("wait_for_active_controllers()", gate)
        self.assertIn('wait_for_active_controllers "${pids[0]}"', gate)
        self.assertNotIn("sleep 12", gate)
        self.assertIn('require_active_controller "arm_controller"', gate)
        self.assertIn("runpy.run_path", gate)
        self.assertIn("generate_launch_description", gate)
        self.assertIn('ros2 launch --debug jx_mobile_manipulator_moveit_config move_group.launch.py', gate)
        self.assertIn('require_running "${pids[1]}" "$EVIDENCE/move_group.log"', gate)
        self.assertIn('grep -q "You can start planning now!" "$EVIDENCE/move_group.log"', gate)
        self.assertIn('! grep -q "No geometry is associated to any robot links" "$EVIDENCE/move_group.log"', gate)
        self.assertIn('require_running "${pids[2]}" "$EVIDENCE/nav2.log"', gate)
        self.assertIn("bt_navigator|behavior_server", gate)
        self.assertLess(
            gate.index("run colcon --log-base"),
            gate.index('source "$WORKSPACE/install/setup.bash"'),
        )
        self.assertLess(
            gate.index('source "$WORKSPACE/install/setup.bash"'),
            gate.index("run xacro"),
        )
        self.assertIn("if: always()", workflow)
        self.assertIn("upload-artifact", workflow)
        self.assertIn("include-hidden-files: true", workflow)
        self.assertNotIn("continue-on-error: true", workflow)
        self.assertNotIn("--network=host", workflow)
        self.assertIn("--network=none", workflow)
        self.assertIn("ROS_DOMAIN_ID=139", workflow)
        self.assertIn("ROS_LOCALHOST_ONLY=1", workflow)
        self.assertIn('test "${ROS_DOMAIN_ID:-}" = "139"', gate)
        self.assertIn('test "${ROS_LOCALHOST_ONLY:-}" = "1"', gate)

    def test_live_gate_retains_a_bounded_controller_trace_not_a_synthetic_substitute(self):
        gate = (ROOT / "scripts/run_live_simulation_gate.sh").read_text(encoding="utf-8")
        for token in (
            'ros2 bag record --storage mcap --output "$EVIDENCE/live-drive"',
            "/clock", "/joint_states", "/diff_drive_controller/odom", "/diff_drive_controller/cmd_vel",
            'timeout 5s ros2 topic pub -r 10 /diff_drive_controller/cmd_vel geometry_msgs/msg/TwistStamped',
            "x: 0.10", "z: 0.20", "--require-turning", "validate_live_simulation_trace.py",
            '"$EVIDENCE/live-trace-bundle"',
        ):
            self.assertIn(token, gate)
        self.assertLess(gate.index("wait_for_active_controllers"), gate.index("ros2 bag record --storage mcap"))
        self.assertLess(gate.index("ros2 bag record --storage mcap"), gate.index("validate_live_simulation_trace.py"))
        self.assertIn("Subscribed to topic '/diff_drive_controller/odom'", gate)
        self.assertIn("wait_for_recorded_topics", gate)
        self.assertLess(gate.index("wait_for_recorded_topics \"$RECORDER_PID\""), gate.index("sleep 2"))


if __name__ == "__main__":
    unittest.main()
