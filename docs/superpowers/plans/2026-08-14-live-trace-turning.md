# Live Trace Turning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require the retained isolated live simulation trace to exercise and validate nonzero yaw as well as forward motion.

**Architecture:** Keep the pure trace validator independent of ROS. It will derive odometry path length and unwrapped yaw from closed primitive samples, then apply an explicit turning requirement only when the runtime CLI requests it. The shell gate sends one bounded arc command and invokes that strict CLI mode.

**Tech Stack:** Python 3 standard library, existing assurance simulation backends, ROS 2 Jazzy CLI, Gazebo Harmonic CI.

---

### Task 1: Curved odometry semantics

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/simulation/live_trace.py`
- Test: `tests/test_simulation_live_trace.py`

- [ ] **Step 1: Write failing curved-trace tests.** Construct three odometry samples along a radius-0.5 m, 0.4-rad arc and assert observed distance is approximately 0.2 m (not the 0.1987 m endpoint chord), observed yaw is 0.4 rad, and a `3.13 -> -3.13` pair contributes a small positive wrapped delta.
- [ ] **Step 2: Run the focused test.** Run `python -m unittest tests.test_simulation_live_trace.LiveTraceTests.test_live_wheel_trace_crosschecks_bound_profile_against_odometry -v`; expect failure because the current code uses only the endpoint vector and yaw subtraction.
- [ ] **Step 3: Implement closed path and yaw accumulation.** Sum finite consecutive XY distances, normalize each yaw delta into `[-pi, pi]`, and use the accumulated values for both primary and independent odometry comparisons.
- [ ] **Step 4: Verify focused regression.** Run `python -m unittest tests.test_simulation_live_trace tests.test_simulation_backend -v`; expect all tests to pass.

### Task 2: Require the shipped gate to turn

**Files:**
- Modify: `scripts/validate_live_simulation_trace.py`
- Modify: `scripts/run_live_simulation_gate.sh`
- Modify: `tests/test_simulation_live_trace.py`
- Modify: `tests/test_simulation_ci.py`

- [ ] **Step 1: Write failing CLI/source tests.** Require a `--require-turning` boolean CLI option, a call that rejects zero/opposite command/yaw when enabled, and gate source containing `angular: {z: 0.20}` plus `--require-turning`.
- [ ] **Step 2: Run focused tests.** Run `python -m unittest tests.test_simulation_live_trace tests.test_simulation_ci -v`; expect failure because neither strict option nor arc command exists.
- [ ] **Step 3: Implement minimal strict mode.** After closed capture validation, require a positive angular command above `0.05 rad/s`, observed yaw above `0.05 rad`, and the same sign. Preserve generic straight-trace behavior when the flag is absent. Change only the isolated shell command to the declared bounded arc and pass the flag.
- [ ] **Step 4: Verify focused regression.** Run `python -m unittest tests.test_simulation_live_trace tests.test_simulation_ci -v`; expect all tests to pass.

### Task 3: Release evidence and live validation

**Files:**
- Modify: `release/v1.1-release-contract.json`

- [ ] **Step 1: Re-sign release contract.** Run `python skills/robotics-design/scripts/generate_release_delivery_contract.py --root . --release-id v1.1.0 --out release/v1.1-release-contract.next.json`, then atomically replace the v1.1 contract.
- [ ] **Step 2: Run release-quality checks.** Run `python -m unittest discover -s tests -v`, `python scripts/validate.py`, `python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1.1-release-contract.json`, `python scripts/install.py --dry-run`, `python -m compileall -q scripts tests skills/robotics-design/scripts`, and `git diff --check`.
- [ ] **Step 3: Commit, independently review, and use a draft PR.** Commit `feat: require turning live trace evidence`, request read-only review, push, create draft PR, and require the isolated Jazzy/Harmonic run.
- [ ] **Step 4: Inspect the retained artifact before merge.** Confirm raw MCAP inventory, a passed receipt-bound crosscheck, nonzero observed yaw, and `hardware_promotable:false`; merge only after all PR checks and review are clean.
