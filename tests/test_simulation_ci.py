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
        self.assertIn('require_active_controller "arm_controller"', gate)
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
        self.assertNotIn("continue-on-error: true", workflow)


if __name__ == "__main__":
    unittest.main()
