# Live Simulation Trace Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain a receipt-bound command-and-response trace from the pinned Jazzy/Harmonic live gate while preserving the simulation-only hardware firewall.

**Architecture:** A portable `live_trace` module validates closed primitive records and publishes a canonical evidence bundle that names and hashes raw rosbag files. A Linux-only `rosbag2_py` adapter extracts the four recorded ROS topics into those primitives; the existing live gate records one bounded simulated drive and invokes that adapter after Gazebo/controller startup.

**Tech Stack:** Python 3.11 standard library for portable validation; ROS 2 Jazzy `rclpy`, `rosbag2_py`, MCAP storage, and Bash only in the Linux consumer gate.

---

## File map

- `skills/robotics-design/scripts/assurance/simulation/live_trace.py`: closed primitive-record validation, raw-file hashing, canonical bundle publication, and retained-bundle revalidation.
- `scripts/validate_live_simulation_trace.py`: Jazzy-only rosbag deserializer that converts MCAP messages to the module's primitive input.
- `scripts/run_live_simulation_gate.sh`: bounded simulated command, recorder lifecycle, and invocation of the runtime adapter.
- `tests/test_simulation_live_trace.py`: pure validator and tamper regressions.
- `tests/test_simulation_ci.py`: static live-gate contract regression.

### Task 1: Closed live-trace evidence module

**Files:** Create `skills/robotics-design/scripts/assurance/simulation/live_trace.py` and `tests/test_simulation_live_trace.py`; modify `skills/robotics-design/scripts/assurance/simulation/__init__.py`.

- [ ] **Step 1: Write the failing pure validation tests.** Build a valid primitive capture containing exactly `clock_ns`, `joint_samples`, `odom_samples`, and `command_samples`. Require a passed `live_simulation_trace` at evidence level `simulated`, with `hardware_promotable: false` and positive forward displacement. Cover unknown series, timestamp reversal, NaN, an over-limit command, missing `left_wheel_joint`, and zero displacement.

- [ ] **Step 2: Verify RED.** Run `python -m unittest tests.test_simulation_live_trace -v`. Expect `ModuleNotFoundError: assurance.simulation.live_trace`.

- [ ] **Step 3: Implement closed normalization.** Add `LiveTraceError`, `validate_live_capture(capture, profile)`, `publish_live_trace_bundle(output, capture, profile, raw_bag)`, and `validate_retained_live_trace_bundle(bundle, receipt, raw_bag)`. Permit only the four primitive keys, cap each series at 10,000 samples, require strictly increasing nonnegative integer timestamps, finite scalars, the two drive-joint names, an in-limit nonzero forward command, and at least 0.01 m x displacement. Derive the hardware firewall. Hash only regular `metadata.yaml` plus exactly one regular `.mcap` below `raw_bag`; reject symlinks, extra files, or a raw file above 64 MiB. Publish canonical `index.json`, `provenance.json`, `trace.json`, and `validation.json` through `write_bundle_with_receipt`; provenance records every raw relative path, byte count, and SHA-256 but no binary is copied into the JSON bundle.

- [ ] **Step 4: Verify publication and tamper behavior.** Publish from a temporary valid raw bag, validate with its receipt, modify the MCAP byte, and require a stale-hash error. Run `python -m unittest tests.test_simulation_live_trace tests.test_simulation_trace -v`; all tests pass.

- [ ] **Step 5: Commit.** Stage the module, its export, and focused tests with message `feat: validate receipt-bound live simulation traces`.

### Task 2: Linux rosbag2 extraction boundary

**Files:** Create `scripts/validate_live_simulation_trace.py`; modify `tests/test_simulation_live_trace.py`.

- [ ] **Step 1: Write adapter boundary tests.** Test mapping-only `normalize_records(records)` using message-shaped mappings. It accepts only `/clock`, `/joint_states`, `/odom`, and `/diff_drive_controller/cmd_vel`, maps each to the Task 1 series, and rejects an unknown topic, unexpected ROS type, missing header/pose/twist field, or empty input. Add static assertions that the CLI imports `rosbag2_py.SequentialReader`, `deserialize_message`, and `get_message`, opens MCAP, and calls publication plus retained-bundle validation.

- [ ] **Step 2: Verify RED.** Run `python -m unittest tests.test_simulation_live_trace -v`; expect missing adapter functions or script assertions.

- [ ] **Step 3: Implement the runtime adapter.** Keep ROS imports inside the CLI so Windows never needs ROS packages. The CLI opens its supplied MCAP directory using `StorageOptions(..., storage_id="mcap")`, rejects an unclosed topic/type inventory, deserializes each message with its registered type, and converts bag timestamps to integer nanoseconds. It loads the receipt-bound profile from `validate_simulation_bundle._load_backend_profile`, publishes evidence, validates it against the raw bag once, prints a canonical receipt, and exits nonzero for every malformed/runtime boundary.

- [ ] **Step 4: Verify portable isolation.** Run `python -m unittest tests.test_simulation_live_trace tests.test_reference_simulation -v`; all tests pass without importing ROS on Windows.

- [ ] **Step 5: Commit.** Stage CLI, module changes, and tests with message `feat: extract live ROS simulation trace evidence`.

### Task 3: Bounded live-Gazebo capture gate

**Files:** Modify `scripts/run_live_simulation_gate.sh` and `tests/test_simulation_ci.py`; modify `reference/mobile-manipulator/simulation/Dockerfile.jazzy-harmonic` only if an asserted runtime dependency is absent.

- [ ] **Step 1: Write static gate RED assertions.** Require `ros2 bag record --storage mcap` to name exactly `/clock`, `/joint_states`, `/odom`, and `/diff_drive_controller/cmd_vel`; require a two-second 10 Hz `TwistStamped` publication with `linear.x: 0.10` and zero angular velocity; require recorder PID cleanup; and require the runtime validator to write a retained evidence bundle before artifact upload. Reject a synthetic trace or an un-namespaced `/cmd_vel`.

- [ ] **Step 2: Verify RED.** Run `python -m unittest tests.test_simulation_ci -v`; expect the new assertions to fail.

- [ ] **Step 3: Implement lifecycle and bounded command.** After `wait_for_active_controllers`, start the recorder under a 30-second timeout and add its PID to cleanup; publish only the declared `TwistStamped` command at 10 Hz for two seconds; wait one settling second; stop/wait the recorder; invoke `validate_live_simulation_trace.py --reference-root "$REFERENCE" --bag "$EVIDENCE/live-drive" --out "$EVIDENCE/live-trace-bundle"`. Preserve all current Gazebo, MoveIt, Nav2, timeout, and liveness checks.

- [ ] **Step 4: Validate release and live CI.** Run `python -m unittest discover -s tests -v`, `python scripts/validate.py`, the release validator, installer dry-run, compileall, and diff-check. Regenerate `release/v1.1-release-contract.json` if bound files changed. Push a draft PR; require full Windows/Linux matrix plus Jazzy/Harmonic; inspect the retained artifact for MCAP, canonical trace bundle, and receipt.

- [ ] **Step 5: Commit.** Stage the gate, static tests, needed environment declaration, and generated release contract with message `ci: retain bounded live Gazebo trace evidence`.

## Plan self-review

- Scope is limited to live-trace provenance; it does not add task validation, calibration, policy promotion, or real-hardware behavior.
- Task 1 binds raw files to canonical output, Task 2 proves runtime decoding instead of trusting a stored verdict, and Task 3 makes live CI the producer.
- The only motion command targets the existing Dockerized Gazebo controller and remains within the parsed ROS profile; every output stays simulation-only.
- Portable adversarial tests, release checks, and the independent live CI job cover distinct failure boundaries.
