# Reference Load Envelope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive each reference-arm joint's continuous and brake-holding sizing requirement from hash-bound mass, centre-of-mass, joint-axis, and pose-envelope data, without relaxing the placeholder or hardware-authorization boundary.

**Architecture:** A strict `arm_load_envelope_v1` plug-in evaluates a serial URDF-style kinematic chain in each declared static posture and projects every downstream gravity moment onto every joint axis. Contract validation admits only closed, dimensioned inputs; the engine binds every reported rating to the exact motor/brake responsible for that actuator. The reference fixture receives an assumed, hash-bound mass/posture artifact but remains unpromotable until later supplier evidence exists.

**Tech Stack:** Python 3.11 standard library (`math`, `json`, `unittest`) and the existing `assurance` contract/engine/artifact model.

---

## File structure

- `skills/robotics-design/scripts/assurance/plugin_contracts.py` — strict structural/dimensional contract and coverage provider.
- `skills/robotics-design/scripts/assurance/analyses.py` — deterministic forward-kinematics/static-gravity evaluator.
- `skills/robotics-design/scripts/assurance/engine.py` — exact component rating-owner binding.
- `reference/mobile-manipulator/model/load-envelope.json` — closed assumed mass/COM and static-pose budget.
- `reference/mobile-manipulator/design-contract.json` — artifact hash, observed quantities, and analysis migration.
- `tests/test_assurance_analyses.py`, `tests/test_assurance_contract.py`, `tests/test_reference_robot.py` — numerical, closure, ownership, drift, and boundary regression coverage.

### Task 1: Define the closed envelope schema and coverage provider

**Files:**

- Modify: `skills/robotics-design/scripts/assurance/plugin_contracts.py`
- Modify: `tests/test_assurance_contract.py`

- [ ] **Step 1: Write the failing schema tests.** Create a numeric valid envelope fixture, then mutate it with an unknown field, a wrong quantity dimension, a duplicate joint ID, a missing rating record, a non-chain parent, and a load-case angle count different from `joint_order`. Assert each invokes `validate_plugin_inputs` with an actionable error.

```python
errors = validate_plugin_inputs("arm_load_envelope_v1", invalid, quantities, "analyses[0].inputs")
self.assertTrue(any("unknown fields" in error for error in errors))
self.assertTrue(any("expects dimension mass" in error for error in errors))
```

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_assurance_contract -v`. Expected: FAIL because `arm_load_envelope_v1` is not known.

- [ ] **Step 3: Implement strict recursive quantity validation.** Register the plug-in and require exactly `joint_order`, `joints`, `links`, `payload`, `load_cases`, `continuous_safety_factor`, `brake_safety_factor`, `rated_continuous_torque_nm`, and `brake_holding_torque_nm`. Require quantity references for all physical numeric fields: `length` for origins/COM, `angle` for RPY and positions, `acceleration` for gravity, `mass` for mass, `torque` for ratings, and `dimensionless` for safety factors. Validate unique IDs, exact order, a `base_link` rooted serial chain, exact link-child coverage, a known payload parent, three-element vector shape, nonempty cases, and exact rating coverage. Keep existing coverage unchanged in this task so the published reference remains green until its atomic migration in Task 4.

- [ ] **Step 4: Run GREEN.** Run `python -m unittest tests.test_assurance_contract -v`. Expected: PASS.

- [ ] **Step 5: Commit.** Stage exactly the two Task 1 files and commit `feat: define closed arm load-envelope inputs`.

### Task 2: Implement deterministic 3D static load-envelope evaluation

**Files:**

- Modify: `skills/robotics-design/scripts/assurance/analyses.py`
- Modify: `tests/test_assurance_analyses.py`

- [ ] **Step 1: Write numerical RED tests.** Use a two-joint planar fixture. A 2 kg point at x=1 m under `[0, 0, -9.80665]` must generate `19.6133 N m` around a Y-axis joint. Assert a 90-degree pose changes the result, deterministic case-ID ties, and mass monotonicity in a declared same-sign-moment posture. Add zero/non-unit axis, duplicate/disconnected ID, non-finite and finite-extreme fixtures; each must return diagnostics with no non-finite output or traceback.

```python
result = run_plugin("arm_load_envelope_v1", two_joint_inputs())
self.assertAlmostEqual(result.outputs["joints"][0]["maximum_gravity_torque_nm"], 19.6133)
self.assertEqual(result.outputs["joints"][0]["worst_case_id"], "LC-HORIZONTAL")
```

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_assurance_analyses -v`. Expected: FAIL because `run_plugin` has no `arm_load_envelope_v1` evaluator.

- [ ] **Step 3: Implement the solver.** Add finite-vector helpers and `_arm_load_envelope`. Apply each joint's fixed XYZ/RPY transform then axis-angle position to propagate frames. For every case, transform every downstream link COM and payload point, calculate the absolute axis moment and retain a deterministic maximum.

```python
torque = abs(dot(axis_world, cross(sub(point_world, joint_origin_world), scale(gravity, mass))))
continuous_required = maximum * continuous_safety_factor
brake_required = maximum * brake_safety_factor
```

Sum signed axis moments before taking magnitude, then emit per-joint maximum torque, worst-case ID, requirements, and signed margins. Emit `PHY.ARM.CONTINUOUS_TORQUE` / `PHY.ARM.BRAKE_HOLDING` for negative margins and fail closed for invalid or numerically overflowing input. Register version `"1"`; assumptions state static gravity only and exclude dynamic, life, thermal, safety and hardware conclusions.

- [ ] **Step 4: Run GREEN.** Run `python -m unittest tests.test_assurance_analyses -v`. Expected: PASS.

- [ ] **Step 5: Commit.** Stage the evaluator and numerical tests and commit `feat: calculate arm static load envelopes`.

### Task 3: Bind new rating records to exact components

**Files:**

- Modify: `skills/robotics-design/scripts/assurance/engine.py`
- Modify: `tests/test_assurance_contract.py`

- [ ] **Step 1: Write owner-binding RED tests.** Build valid envelopes whose J2 continuous rating comes from J1's motor, whose brake rating comes from an unbound brake, and whose verified component omits the rating in `limits`. Assert `PHY.ANALYSIS.RATING_OWNER` or `PHY.ANALYSIS.RATING_LIMIT`.

```python
report, errors = evaluate_contract(contract_path)
self.assertEqual(errors, [])
self.assertIn("PHY.ANALYSIS.RATING_OWNER", {item.code for item in report.diagnostics})
```

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_assurance_contract -v`. Expected: FAIL because `engine.py` only checks nested `arm_gravity_v1` ratings.

- [ ] **Step 3: Implement exact records iteration.** For `arm_load_envelope_v1`, iterate both rating lists keyed by `id`; pass their `value` fields through existing `check_owner` logic using `actuator:<id>`, role `arm_motor`/limit `continuous_torque`, then role `brake`/limit `holding_torque`. Keep legacy checks and do not convert assumed values to catalogue evidence.

- [ ] **Step 4: Run GREEN.** Run `python -m unittest tests.test_assurance_contract -v`. Expected: PASS, including old arm-gravity ownership regression.

- [ ] **Step 5: Commit.** Stage the engine and contract tests and commit `feat: bind load-envelope ratings to actuators`.

### Task 4: Bind the reference fixture to a mass/posture envelope

**Files:**

- Create: `reference/mobile-manipulator/model/load-envelope.json`
- Modify: `reference/mobile-manipulator/design-contract.json`
- Modify: `tests/test_reference_robot.py`

- [ ] **Step 1: Write reference RED tests.** Require a hash-bound `declared_json` artifact named `load-envelope-model`, distinct assumed `EV-LOAD-ENVELOPE` evidence, six ordered joint records, two or more cases, and `AN-ARM-LOAD-ENVELOPE` coverage of all actuators. Mutate source hash and observed URDF mass; both must block evaluation. Increase one downstream mass and assert J2 maximum gravity torque cannot decline. Retain `report.promotable is False` and only `BOM.PLACEHOLDER_BLOCKS_CLAIM` in nominal diagnostics.

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_reference_robot -v`. Expected: FAIL because there is neither artifact nor new analysis.

- [ ] **Step 3: Create data and migrate contract.** Create canonical `load-envelope.json` with `schema_version`, `purpose`, the six-joint order, link/tool/cable mass/COM budget, and two named static cases. Add artifact SHA, assumed `EV-LOAD-ENVELOPE` supports, explicit-unit quantities, and observations from `robot-model` where available. Bind envelope budget and case values to the declared JSON artifact. In the same atomic change, replace architecture-required arm coverage with `arm_load_envelope_v1` and replace `AN-ARM-GRAVITY` with `AN-ARM-LOAD-ENVELOPE`; do not alter component states or assert selected-parts evidence.

- [ ] **Step 4: Run GREEN and inspect gate.** Run `python -m unittest tests.test_reference_robot -v` then `python skills/robotics-design/scripts/validate_design_contract.py reference/mobile-manipulator/design-contract.json --report .tmp-load-envelope-report.json`. Expected: tests pass; direct gate exits `1` only because placeholders block promotion; report contains calculated `arm_load_envelope_v1`. Inspect then remove temporary output.

- [ ] **Step 5: Commit.** Stage the reference artifact, contract and tests and commit `feat: bind reference arm to load envelope`.

### Task 5: Finalize scope record and verify distribution

**Files:**

- Modify: `docs/superpowers/specs/2026-08-14-reference-load-envelope-design.md`
- Modify: `docs/superpowers/plans/2026-08-14-reference-load-envelope.md`

- [ ] **Step 1: Record exact result and limitation.** Add report SHA and per-joint maximum-torque summary, label sources as assumed model budgets, and state no vendor selection, purchase, fabrication, energization or motion occurred.

- [ ] **Step 2: Run release-quality verification.** Run `python -m compileall -q scripts tests skills/robotics-design/scripts`, `python -m unittest discover -s tests -v`, `python scripts/validate.py`, `python scripts/install.py --dry-run`, and `git diff --check origin/main...HEAD`. Expected: all pass except reference gate's intentional placeholder exit `1`; diff check has no output. Verify the v1.1 release contract if none of its bound inputs changed.

- [ ] **Step 3: Commit and publish software-only review branch.** Commit docs as `docs: record reference load-envelope boundary`, push `feat/reference-load-envelope`, open a PR that states static/calculated scope, evidence level, tests and unchanged hardware boundary, then merge only after CI and simulator gates pass. Do not create vendor orders, fabrication work, or physical action.
