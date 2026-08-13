#!/usr/bin/env bash
# Headless ROS 2 Jazzy / Gazebo Harmonic consumer gate.  This is Linux-only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REFERENCE="$ROOT/reference/mobile-manipulator"
WORKSPACE="$REFERENCE/ros2_ws"
EVIDENCE="${SIMULATION_EVIDENCE_DIR:-$ROOT/.simulation-evidence}"
mkdir -p "$EVIDENCE"

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait "${pids[@]:-}" 2>/dev/null || true
  pkill -f 'gz sim|ros2 launch|move_group|nav2' 2>/dev/null || true
}
trap cleanup EXIT INT TERM
run() { timeout --preserve-status 90s "$@"; }

set +u
source /opt/ros/jazzy/setup.bash
set -u
test "${ROS_DISTRO:-}" = "jazzy"
gz sim --versions > "$EVIDENCE/gazebo-versions.txt"
dpkg-query -W > "$EVIDENCE/dpkg-inventory.txt"
docker image inspect "${SIMULATION_IMAGE_REF:-unavailable}" > "$EVIDENCE/image-inspect.json" 2>/dev/null || true

run colcon build --base-paths "$WORKSPACE/src" --event-handlers console_direct+
set +u
source "$WORKSPACE/install/setup.bash"
set -u
run xacro "$WORKSPACE/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro" use_sim:=true > "$EVIDENCE/robot.urdf"
run colcon test --base-paths "$WORKSPACE/src"
run colcon test-result --verbose

# Exercise headless Gazebo, ros2_control, MoveIt, and Nav2 as consumers.  All
# launch processes are bounded and captured; absence of any consumer fails.
timeout 45s ros2 launch jx_mobile_manipulator_sim sim.launch.py > "$EVIDENCE/sim.log" 2>&1 & pids+=("$!")
sleep 12
kill -0 "${pids[0]}"
ros2 node list | tee "$EVIDENCE/sim-nodes.txt"
ros2 topic echo --once /clock | tee "$EVIDENCE/clock.txt"
ros2 control list_controllers | tee "$EVIDENCE/controllers.txt"
grep -Eq 'joint_state_broadcaster.*active' "$EVIDENCE/controllers.txt"
grep -Eq 'arm_controller.*active' "$EVIDENCE/controllers.txt"
grep -Eq 'diff_drive_controller.*active' "$EVIDENCE/controllers.txt"
timeout 30s ros2 launch jx_mobile_manipulator_moveit_config move_group.launch.py > "$EVIDENCE/move_group.log" 2>&1 & pids+=("$!")
timeout 30s ros2 launch jx_mobile_manipulator_nav navigation.launch.py > "$EVIDENCE/nav2.log" 2>&1 & pids+=("$!")
sleep 10
ros2 node list | tee "$EVIDENCE/consumer-nodes.txt"
grep -q move_group "$EVIDENCE/consumer-nodes.txt"
grep -Eq 'controller_server|planner_server' "$EVIDENCE/consumer-nodes.txt"

run python3 "$ROOT/skills/robotics-design/scripts/validate_simulation_bundle.py" --reference-root "$REFERENCE" > "$EVIDENCE/portable-benchmark.json"
cp "$REFERENCE/simulation/environment-lock.json" "$EVIDENCE/environment-lock.json"
