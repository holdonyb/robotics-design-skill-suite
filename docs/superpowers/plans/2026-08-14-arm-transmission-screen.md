# Arm Transmission Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the static arm load-envelope gate so every declared arm joint proves that its motor-side continuous torque, reducer ratio and reducer efficiency can produce the already screened output-side continuous demand.

**Architecture:** Keep `arm_load_envelope_v1` as the authoritative gravity model. Add three closed per-joint quantity-record collections to its inputs: motor continuous torque, reducer ratio, and reducer efficiency. The plug-in computes motor-side continuous demand from the existing safety-factored output demand; the contract validator requires each record to belong to the exact actuator motor or reducer, preventing a rating from another joint from satisfying the check.

**Tech Stack:** Python 3.11+, standard-library `unittest`, JSON schema-v1 contract, deterministic SHA-256 bound artifacts.

---

### Task 1: Define the closed transmission input contract

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/plugin_contracts.py`
- Test: `tests/test_assurance_contract.py`

- [ ] **Step 1: Add a failing input-shape and dimension test**

Extend `valid_load_envelope_inputs()` with the expected three record collections, then remove one `reducer_efficiency` record and change a `motor_continuous_torque_nm` reference to a mass quantity. Assert `validate_plugin_inputs()` returns errors stating that every joint must be covered and that torque is required.

- [ ] **Step 2: Run the focused contract test and observe RED**

Run: `python -m unittest tests.test_assurance_contract.AssuranceContractTests.test_arm_load_envelope_rejects_shape_identity_and_dimension_errors -v`

Expected: FAIL because the current closed input schema rejects the new collections or accepts missing motor transmission coverage.

- [ ] **Step 3: Implement closed record validation**

Add `motor_continuous_torque_nm`, `reducer_gear_ratio`, and `reducer_efficiency` to `ARM_LOAD_ENVELOPE_FIELDS`. Reuse `_load_envelope_rating_records()` with expected dimensions `torque` and `dimensionless`; rename the helper parameter from a fixed torque assumption to an explicit `dimension` argument. Require exactly one `{id,value}` record for each `joint_order` entry and reject unknown fields, duplicate IDs, missing entries, unknown quantities, and dimension mismatches.

- [ ] **Step 4: Run focused contract tests and observe GREEN**

Run: `python -m unittest tests.test_assurance_contract -v`

Expected: PASS.

### Task 2: Compute motor-side continuous demand in the analytical gate

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/analyses.py`
- Test: `tests/test_assurance_analyses.py`

- [ ] **Step 1: Add failing calculation and fault tests**

Add a test using one joint with output demand `29.41995 N*m`, ratio `10`, efficiency `0.8`, and motor continuous rating `4 N*m`. Assert output contains `motor_continuous_required_torque_nm == 3.67749375`, `motor_continuous_margin_nm == 0.32250625`, and passes. Lower the motor rating to `3 N*m`; assert `PHY.ARM.MOTOR_CONTINUOUS_TORQUE`. Set efficiency to zero; assert `PHY.ARM.TRANSMISSION_DOMAIN` instead of a traceback.

- [ ] **Step 2: Run the focused analysis tests and observe RED**

Run: `python -m unittest tests.test_assurance_analyses.AssuranceAnalysisTests.test_arm_load_envelope_calculates_pose_dependent_static_torque -v`

Expected: FAIL because transmission outputs and diagnostics do not exist.

- [ ] **Step 3: Implement numerical transmission screening**

Parse all three record collections as finite positive numbers. Require `ratio > 0` and `0 < efficiency <= 1`. For every joint compute `motor_required = continuous_required / ratio / efficiency` and `motor_margin = motor_rating - motor_required`. Reject non-finite derived values as `PHY.NUMERIC.OVERFLOW`; emit `PHY.ARM.MOTOR_CONTINUOUS_TORQUE` only when the signed motor margin is negative. Preserve the existing reducer output and brake checks, and add both motor values to each joint output.

- [ ] **Step 4: Run focused analyses and regression suite**

Run: `python -m unittest tests.test_assurance_analyses tests.test_assurance_contract -v`

Expected: PASS.

### Task 3: Bind every reference arm joint to its exact motor and reducer roles

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/contract.py`
- Modify: `tests/test_assurance_contract.py`
- Modify: `reference/mobile-manipulator/design-contract.json`
- Modify: `tests/test_reference_robot.py`

- [ ] **Step 1: Add failing exact-owner tests**

Build a two-actuator contract where each output rating and ratio is reducer-owned, each motor rating is motor-owned, and brakes are brake-owned. Swap the J2 motor torque reference with J1 or the J2 ratio reference with J1; assert `PHY.ANALYSIS.RATING_OWNER`. Add a reference test asserting all six motor and reducer records exactly cover the six arm joints and that J2’s source-bound ratio is used.

- [ ] **Step 2: Run owner tests and observe RED**

Run: `python -m unittest tests.test_assurance_contract.AssuranceContractTests.test_arm_load_envelope_output_ratings_bind_to_the_named_reducers -v`

Expected: FAIL because owner validation does not yet cover motor, ratio, or efficiency records.

- [ ] **Step 3: Implement owner mapping and reference quantities**

Extend `_analysis_rating_owner_diagnostics()` so `motor_continuous_torque_nm` must be owned by the exact bound role `motor`, and `reducer_gear_ratio`/`reducer_efficiency` by the exact bound `reducer`. Add one source-backed-or-assumed typed quantity per joint for each new collection. Keep J2’s `Q-ARM-GEAR-RATIO-J2` as the parsed Harmonic Drive value; any unsourced motor or efficiency values remain explicitly assumed and cannot elevate promotion. Reference all three collections from `AN-ARM-LOAD-ENVELOPE` in joint order.

- [ ] **Step 4: Run contract and reference tests**

Run: `python -m unittest tests.test_assurance_contract tests.test_reference_robot -v`

Expected: PASS; reference remains unpromotable only due existing BOM placeholders.

### Task 4: Add adversarial regression and regenerate bound dependents

**Files:**
- Create: `reference/mobile-manipulator/faults/35-motor-continuous-torque-overload.json`
- Modify: `tests/test_reference_robot.py`
- Modify: `reference/mobile-manipulator/hypothesis-space.json`
- Modify: `reference/mobile-manipulator/hypothesis-expected.json`
- Modify: `reference/mobile-manipulator/engineering-freeze/freeze-package.json`
- Modify: `reference/mobile-manipulator/simulation/artifact-manifest.json`
- Modify: `reference/mobile-manipulator/simulation/ros-workspace-manifest.json`
- Modify: `tests/test_simulation_artifacts.py`
- Modify: `tests/test_reference_ros_workspace.py`
- Modify: `release/v1.1-release-contract.json`

- [ ] **Step 1: Add a failing reference fault test**

Add `motor-continuous-torque-overload` to the exact critical-fault set and count. The mutation sets J2 motor continuous torque to `1 N*m`; expected diagnostic is `PHY.ARM.MOTOR_CONTINUOUS_TORQUE`.

- [ ] **Step 2: Run the fault test and observe RED**

Run: `python -m unittest tests.test_reference_robot.ReferenceRobotTests.test_all_critical_faults_are_rejected_by_expected_gate -v`

Expected: FAIL because the new fault does not exist or the analytical gate has not yet produced the diagnostic.

- [ ] **Step 3: Regenerate every hash-bound dependent**

Run the hypothesis generator with seed `20260813`, copy its manifest receipt/fronts into `hypothesis-expected.json`, update the freeze hash with raw LF bytes, regenerate model and ROS manifests, and replace their test receipts. Regenerate the release contract through a new temporary file, validate it, then atomically replace the old contract. Add the new fault only after the gate catches it.

- [ ] **Step 4: Run end-to-end verification**

Run:

```powershell
$env:PYTHONPATH='skills/robotics-design/scripts'
python -m compileall -q scripts tests skills/robotics-design/scripts reference/mobile-manipulator/model
python -m unittest discover -s tests -q
python scripts/validate.py
python scripts/install.py --dry-run
git diff --check
```

Expected: all tests pass; distribution and installation pass; the reference contract exits `1` with only `BOM.PLACEHOLDER_BLOCKS_CLAIM`; no promotion or hardware claim is created.

### Task 5: Publish the bounded analytical upgrade

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Create: `docs/research/2026-08-14-arm-transmission-screen-audit.md`

- [ ] **Step 1: Document the calculation boundary**

State the exact formula `motor_required = output_continuous_required / ratio / efficiency`, that it is a static continuous screen, and that motor speed, torque curves, transient dynamics, coupling, thermal network, life, brake, CAD fit, procurement and hardware authorization remain separate gates.

- [ ] **Step 2: Commit and publish after CI**

Commit only the plan’s files with `feat: screen arm motor-reducer transmission`, push an `agent/arm-transmission-screen` branch, open a draft pull request, wait for all required CI including `jazzy-harmonic-live`, then merge only if every check passes.

## Self-review

Each new physical value is a typed quantity and every value is either exact component-owned parsed evidence or explicitly assumed. The output torque stays owned by the reducer, motor torque by the motor, and efficiency/ratio by the reducer. The calculation cannot cause promotion because placeholder components, assumed inputs, and unresolved motor provenance remain visible. No task authorizes purchase, power, motion, or claims beyond a calculated static screening result.
