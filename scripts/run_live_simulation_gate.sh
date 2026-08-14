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
wait_for_active_controllers() {
  local pid="$1"
  local log="$2"
  local deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    require_running "$pid" "$log"
    if ros2 control list_controllers > "$EVIDENCE/controllers.txt" 2>> "$log" \
      && grep -Eq '^joint_state_broadcaster[[:space:]].*active' "$EVIDENCE/controllers.txt" \
      && grep -Eq '^arm_controller[[:space:]].*active' "$EVIDENCE/controllers.txt" \
      && grep -Eq '^diff_drive_controller[[:space:]].*active' "$EVIDENCE/controllers.txt"; then
      return 0
    fi
    sleep 1
  done
  cat "$log" >&2 || true
  return 1
}
wait_for_recorded_topics() {
  local pid="$1"
  local log="$2"
  local deadline=$((SECONDS + 15))
  while (( SECONDS < deadline )); do
    require_running "$pid" "$log"
    if grep -q "Subscribed to topic '/clock'" "$log" \
      && grep -q "Subscribed to topic '/joint_states'" "$log" \
      && grep -q "Subscribed to topic '/diff_drive_controller/odom'" "$log" \
      && grep -q "Subscribed to topic '/diff_drive_controller/cmd_vel'" "$log"; then
      return 0
    fi
    sleep 1
  done
  cat "$log" >&2 || true
  return 1
}

set +u
source /opt/ros/jazzy/setup.bash
set -u
test "${ROS_DISTRO:-}" = "jazzy"
test "${ROS_DOMAIN_ID:-}" = "139"
test "${ROS_LOCALHOST_ONLY:-}" = "1"
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
wait_for_active_controllers "${pids[0]}" "$EVIDENCE/sim.log"
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

# Retain one bounded response from the running Gazebo controller.  This command
# targets only the Dockerized simulation namespace; its profile limit is 0.4 m/s.
timeout 30s ros2 bag record --storage mcap --output "$EVIDENCE/live-drive" /clock /joint_states /diff_drive_controller/odom /diff_drive_controller/cmd_vel > "$EVIDENCE/live-record.log" 2>&1 & pids+=("$!")
RECORDER_PID="${pids[${#pids[@]}-1]}"
timeout 5s ros2 topic pub -r 10 /diff_drive_controller/cmd_vel geometry_msgs/msg/TwistStamped "{twist: {linear: {x: 0.10}, angular: {z: 0.0}}}" > "$EVIDENCE/live-command.log" 2>&1 & pids+=("$!")
COMMAND_PID="${pids[${#pids[@]}-1]}"
wait_for_recorded_topics "$RECORDER_PID" "$EVIDENCE/live-record.log"
sleep 2
require_running "$RECORDER_PID" "$EVIDENCE/live-record.log"
kill "$COMMAND_PID" 2>/dev/null || true
wait "$COMMAND_PID" || true
kill "$RECORDER_PID"
wait "$RECORDER_PID" || true
run python3 "$ROOT/scripts/validate_live_simulation_trace.py" --reference-root "$REFERENCE" --bag "$EVIDENCE/live-drive" --out "$EVIDENCE/live-trace-bundle" > "$EVIDENCE/live-trace-receipt.json"

run python3 "$ROOT/skills/robotics-design/scripts/validate_simulation_bundle.py" --reference-root "$REFERENCE" > "$EVIDENCE/portable-benchmark.json"
cp "$REFERENCE/simulation/environment-lock.json" "$EVIDENCE/environment-lock.json"
