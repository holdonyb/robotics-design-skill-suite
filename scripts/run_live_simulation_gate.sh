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
require_running() {
  local pid="$1"
  local log="$2"
  if ! kill -0 "$pid" 2>/dev/null; then
    cat "$log" >&2 || true
    return 1
  fi
}
wait_for_clock() {
  local pid="$1"
  local log="$2"
  local deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    require_running "$pid" "$log"
    if timeout 3s ros2 topic echo --once /clock > "$EVIDENCE/clock.txt" 2>> "$log"; then
      return 0
    fi
    sleep 1
  done
  cat "$log" >&2 || true
  return 1
}
require_active_controller() {
  local controller="$1"
  if ! grep -Eq "^${controller}[[:space:]].*active" "$EVIDENCE/controllers.txt"; then
    cat "$EVIDENCE/sim.log" >&2 || true
    return 1
  fi
}

set +u
source /opt/ros/jazzy/setup.bash
set -u
test "${ROS_DISTRO:-}" = "jazzy"
gz sim --versions > "$EVIDENCE/gazebo-versions.txt"
dpkg-query -W > "$EVIDENCE/dpkg-inventory.txt"
docker image inspect "${SIMULATION_IMAGE_REF:-unavailable}" > "$EVIDENCE/image-inspect.json" 2>/dev/null || true

run colcon --log-base "$WORKSPACE/log" build --base-paths "$WORKSPACE/src" --build-base "$WORKSPACE/build" --install-base "$WORKSPACE/install" --event-handlers console_direct+
set +u
source "$WORKSPACE/install/setup.bash"
set -u
run xacro "$WORKSPACE/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro" use_sim:=true > "$EVIDENCE/robot.urdf"
run colcon --log-base "$WORKSPACE/log" test --base-paths "$WORKSPACE/src" --build-base "$WORKSPACE/build" --install-base "$WORKSPACE/install"
run colcon test-result --test-result-base "$WORKSPACE/build" --verbose

# Exercise headless Gazebo, ros2_control, MoveIt, and Nav2 as consumers.  All
# launch processes are bounded and captured; absence of any consumer fails.
timeout 45s ros2 launch jx_mobile_manipulator_sim sim.launch.py > "$EVIDENCE/sim.log" 2>&1 & pids+=("$!")
wait_for_clock "${pids[0]}" "$EVIDENCE/sim.log"
ros2 node list | tee "$EVIDENCE/sim-nodes.txt"
ros2 control list_controllers | tee "$EVIDENCE/controllers.txt"
require_active_controller "joint_state_broadcaster"
require_active_controller "arm_controller"
require_active_controller "diff_drive_controller"
MOVE_GROUP_LAUNCH="$WORKSPACE/install/jx_mobile_manipulator_moveit_config/share/jx_mobile_manipulator_moveit_config/launch/move_group.launch.py"
run python3 - "$MOVE_GROUP_LAUNCH" > "$EVIDENCE/move_group-construction.log" 2>&1 <<'PY'
import runpy
import sys

launch_file = runpy.run_path(sys.argv[1])
launch_file["generate_launch_description"]()
PY
timeout 30s ros2 launch --debug jx_mobile_manipulator_moveit_config move_group.launch.py > "$EVIDENCE/move_group.log" 2>&1 & pids+=("$!")
timeout 30s ros2 launch jx_mobile_manipulator_nav navigation.launch.py > "$EVIDENCE/nav2.log" 2>&1 & pids+=("$!")
sleep 10
require_running "${pids[1]}" "$EVIDENCE/move_group.log"
require_running "${pids[2]}" "$EVIDENCE/nav2.log"
grep -q "You can start planning now!" "$EVIDENCE/move_group.log"
! grep -q "No geometry is associated to any robot links" "$EVIDENCE/move_group.log"
ros2 node list | tee "$EVIDENCE/consumer-nodes.txt"
grep -q move_group "$EVIDENCE/consumer-nodes.txt"
grep -Eq 'controller_server|planner_server' "$EVIDENCE/consumer-nodes.txt"
grep -Eq 'bt_navigator|behavior_server' "$EVIDENCE/consumer-nodes.txt"

run python3 "$ROOT/skills/robotics-design/scripts/validate_simulation_bundle.py" --reference-root "$REFERENCE" > "$EVIDENCE/portable-benchmark.json"
cp "$REFERENCE/simulation/environment-lock.json" "$EVIDENCE/environment-lock.json"
