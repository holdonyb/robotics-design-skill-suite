# v0.5 Simulation, Training, and Ecosystem Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver and publicly release a reproducible v0.5 reference simulation, replay, calibration, and training-boundary pipeline without promoting placeholder components or simulated results to hardware evidence.

**Architecture:** Add a portable simulation-assurance kernel and generated reference ROS workspace, then exercise the same closed contracts in a digest-pinned ROS 2 Jazzy/Gazebo Harmonic Linux job. Each layer emits canonical, hash-bound records; a strict evidence lattice and policy firewall separate analytical screening, simulation admission, simulated/calibrated evidence, and future hardware levels.

**Tech Stack:** Python 3.11/3.12 standard library, JSON, XML/xacro/SDF/SRDF, ROS 2 Jazzy, Gazebo Harmonic, ros2_control, ros_gz, Nav2, MoveIt 2, rosbag2/MCAP, Docker/GitHub Actions.

---

## File map

- `skills/robotics-design/scripts/assurance/simulation/model.py`: frozen simulation IDs, evidence levels, artifact/scenario/environment/trace records.
- `skills/robotics-design/scripts/assurance/simulation/schema.py`: closed bounded JSON loaders and field diagnostics.
- `skills/robotics-design/scripts/assurance/simulation/admission.py`: v0.3/v0.4 report to `simulation_admitted` decision and hardware firewall.
- `skills/robotics-design/scripts/assurance/simulation/artifacts.py`: generated artifact manifest, normalized observations, source/output drift checks.
- `skills/robotics-design/scripts/assurance/simulation/scenario.py`: scenario compilation, fault schedule, metric and stop-condition contracts.
- `skills/robotics-design/scripts/assurance/simulation/trace.py`: canonical trace bundle, manifest, replay, tolerances, resource limits.
- `skills/robotics-design/scripts/assurance/simulation/backend.py`: backend protocol and independent deterministic dynamics adapter.
- `skills/robotics-design/scripts/assurance/simulation/calibration.py`: dataset manifest, bounded fit, residual evaluation, calibration promotion.
- `skills/robotics-design/scripts/assurance/simulation/training.py`: training/domain-randomization schemas, callback boundary, held-out evaluation, promotion firewall.
- `skills/robotics-design/scripts/validate_simulation_bundle.py`: fail-closed CLI.
- `reference/mobile-manipulator/model/`: deterministic geometry inputs and STEP/robot-description generators.
- `reference/mobile-manipulator/ros2_ws/src/`: generated description, simulation, MoveIt, Nav2, and scenario packages.
- `reference/mobile-manipulator/simulation/`: environment lock, admission/scenario/trajectory/calibration/training records and expected evidence.
- `.github/workflows/simulation.yml`: Linux live consumer/build/scenario/replay gate.
- `tests/test_simulation_*.py`: portable model, schema, admission, artifact, scenario, trace, backend, calibration, training, CLI, and reference regressions.

### Task 1: Closed simulation evidence model

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/__init__.py`
- Create: `skills/robotics-design/scripts/assurance/simulation/model.py`
- Create: `tests/test_simulation_model.py`

- [ ] **Step 1: Write failing model tests**

Test frozen records for `EnvironmentLock`, `ArtifactRecord`, `SimulationAdmission`, `ScenarioSpec`, `TrajectoryRecord`, `TraceSample`, `MetricResult`, and `SimulationResult`. Require identifier patterns, lowercase SHA-256, finite scalars, integer nanoseconds, closed status/evidence enums, unique sorted collections, immutable nested JSON, and canonical `to_dict()` output. Include recursive containers, booleans-as-integers, non-UTF-8-surrogate strings, duplicate joints, invalid evidence jumps, and 10,000-sample bounded behavior.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_model -v`

Expected: `ModuleNotFoundError: assurance.simulation`.

- [ ] **Step 3: Implement the minimal records**

Reuse `assurance.hypothesis.canonical` helpers. Define exact enums:

```python
EVIDENCE_LEVELS = (
    "generated", "parsed", "calculated", "simulation_admitted",
    "simulated", "calibrated_simulation", "bench_tested",
    "integrated_hardware_tested", "task_validated", "certified",
)
```

All constructors validate and freeze; all serializations sort keys and ordered identity fields.

- [ ] **Step 4: Run focused and existing model tests**

Run: `python -m unittest tests.test_simulation_model tests.test_hypothesis_model tests.test_assurance_model -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation tests/test_simulation_model.py
git commit -m "feat: add closed simulation evidence model"
```

### Task 2: Simulation contract schema and admission firewall

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/schema.py`
- Create: `skills/robotics-design/scripts/assurance/simulation/admission.py`
- Create: `tests/test_simulation_schema.py`
- Create: `tests/test_simulation_admission.py`

- [ ] **Step 1: Write schema and admission RED tests**

Cover duplicate-key JSON, invalid UTF-8, unknown fields, depth/item/byte bounds, units, hashes, engine parameters, calibration status, scenario budgets, and path traversal. Admission cases must prove:

```python
decision = evaluate_simulation_admission(physical_report, hypothesis_report)
self.assertEqual(decision.status, "simulation_admitted")
self.assertFalse(decision.hardware_promotable)
self.assertEqual(set(decision.remaining_blockers), {"BOM.PLACEHOLDER_BLOCKS_CLAIM"})
```

Reject failed/indeterminate analyses, hard counterexamples, missing roles/load paths, stale artifacts, unknown safety requirements, non-placeholder blockers, report/candidate/hash mismatch, and any attempt to set hardware evidence.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_schema tests.test_simulation_admission -v`

Expected: missing modules/functions.

- [ ] **Step 3: Implement closed loaders and admission**

Use duplicate-detecting JSON loading and explicit maximums. Admission consumes immutable report mappings, recomputes canonical hashes, inventories every diagnostic, allows only the exact placeholder code family, and emits a canonical receipt. Hardware promotion is a derived constant `False`, not caller input.

- [ ] **Step 4: Verify focused plus v0.3/v0.4 gates**

Run: `python -m unittest tests.test_simulation_schema tests.test_simulation_admission tests.test_assurance_engine tests.test_hypothesis_engine -v`

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation/schema.py skills/robotics-design/scripts/assurance/simulation/admission.py tests/test_simulation_schema.py tests/test_simulation_admission.py
git commit -m "feat: gate simulation admission without hardware promotion"
```

### Task 3: Manifest-bound artifact generation and drift validation

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/artifacts.py`
- Create: `reference/mobile-manipulator/model/geometry.json`
- Create: `reference/mobile-manipulator/model/generate_reference_model.py`
- Create: `reference/mobile-manipulator/simulation/artifact-manifest.json`
- Create: `tests/test_simulation_artifacts.py`

- [ ] **Step 1: Write failing artifact tests**

Assert one geometry-input SHA binds STEP, URDF/xacro, SDF, SRDF, controller YAML, bridge YAML, RViz, and package files. Validate normalized robot name, links, joints, axes, limits, frames, ros2_control interfaces, MoveIt group/TCP, SDF plugins/sensors, source/output hashes, exact file set, LF text, no symlinks/extra files, and mass/inertia equality with the physical contract. Inject wrong joint sign, missing transmission, stale STEP, broad disabled collision, missing `/clock`, hand-edited generated file, and mesh-only collision.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_artifacts -v`

- [ ] **Step 3: Implement generator and manifest validator**

Generate deterministic primitive geometry and a reviewable STEP assembly from `geometry.json`; generate ROS artifacts from the same named dimensions. Do not derive physical masses from CAD volumes. Emit canonical manifest only after every output validates.

- [ ] **Step 4: Regenerate twice and compare trees**

Run:

```bash
python reference/mobile-manipulator/model/generate_reference_model.py --out .tmp-install/model-a
python reference/mobile-manipulator/model/generate_reference_model.py --out .tmp-install/model-b
python -m unittest tests.test_simulation_artifacts -v
```

Expected: byte-identical generated trees and all tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation/artifacts.py reference/mobile-manipulator/model reference/mobile-manipulator/simulation tests/test_simulation_artifacts.py
git commit -m "feat: bind reference simulator artifacts to one model"
```

### Task 4: Reference ROS 2 packages and portable consumer checks

**Files:**
- Create: `reference/mobile-manipulator/ros2_ws/src/jx_mobile_manipulator_description/**`
- Create: `reference/mobile-manipulator/ros2_ws/src/jx_mobile_manipulator_sim/**`
- Create: `reference/mobile-manipulator/ros2_ws/src/jx_mobile_manipulator_moveit_config/**`
- Create: `reference/mobile-manipulator/ros2_ws/src/jx_mobile_manipulator_nav/**`
- Create: `reference/mobile-manipulator/ros2_ws/src/jx_mobile_manipulator_scenarios/**`
- Create: `tests/test_reference_ros_workspace.py`

- [ ] **Step 1: Write static consumer RED tests**

Check package.xml format/dependencies, CMake/install rules, launch syntax, xacro expansion inputs, exact controller joints/interfaces, Jazzy `TwistStamped` expectations, use_sim_time, `/clock`, resource/plugin paths, front/rear caster support, sensor world plugins, TF ownership, SRDF group/TCP, MoveIt/Nav2 config references, RViz displays for all sensors, and absence of hardware plugins/ports.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_reference_ros_workspace -v`

- [ ] **Step 3: Generate minimal auditable packages**

Use standard ROS packages and configuration; custom code is limited to scenario orchestration. Split description, sim, planning, nav, and scenarios so each consumer can load independently.

- [ ] **Step 4: Run portable checks**

Run: `python -m unittest tests.test_reference_ros_workspace tests.test_simulation_artifacts -v`

- [ ] **Step 5: Commit**

```bash
git add reference/mobile-manipulator/ros2_ws tests/test_reference_ros_workspace.py
git commit -m "feat: add reference ROS 2 simulation workspace"
```

### Task 5: Scenario compilation, trace bundle, and deterministic replay

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/scenario.py`
- Create: `skills/robotics-design/scripts/assurance/simulation/trace.py`
- Create: `reference/mobile-manipulator/simulation/scenarios.json`
- Create: `reference/mobile-manipulator/simulation/trajectory.json`
- Create: `tests/test_simulation_scenario.py`
- Create: `tests/test_simulation_trace.py`

- [ ] **Step 1: Write scenario/trace RED tests**

Test the ten bounded scenarios, canonical seed ordering, integer-nanosecond samples, monotonic time, exact joint order, scheduled fault uniqueness, metric units, stop reason, file/hash closure, replay event order, sample/rate/byte budgets, tolerance behavior, raw versus normalized identity, tamper/extra/symlink rejection, and rollback on publication failure.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_scenario tests.test_simulation_trace -v`

- [ ] **Step 3: Implement compiler and replay validator**

Compile registry entries into immutable scenario specs. Publish bundles transactionally with canonical JSON plus one LF. Replay recomputes metrics and invariants; it never trusts stored verdicts.

- [ ] **Step 4: Verify repeatability and tamper corpus**

Run: `python -m unittest tests.test_simulation_scenario tests.test_simulation_trace -v`

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation/scenario.py skills/robotics-design/scripts/assurance/simulation/trace.py reference/mobile-manipulator/simulation tests/test_simulation_scenario.py tests/test_simulation_trace.py
git commit -m "feat: compile and replay bounded simulation traces"
```

### Task 6: Independent dynamics adapter and cross-backend comparison

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/backend.py`
- Create: `tests/test_simulation_backend.py`

- [ ] **Step 1: Write backend RED tests**

Use textbook-independent fixtures for differential-drive straight/yaw motion, stopping/slope demand, wheel/joint limits, arm final state, invalid time grids, nonfinite/extreme values, reverse/braking validity, mismatched model/trajectory hashes, per-metric tolerance, domain exclusion, and disagreement blocking.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_backend -v`

- [ ] **Step 3: Implement protocol and deterministic adapter**

The adapter consumes normalized SI records and returns metric intervals with validity domains. `compare_backends()` retains both outputs and returns `passed`, `failed`, or `indeterminate`; it never averages results.

- [ ] **Step 4: Verify focused plus physical metamorphic tests**

Run: `python -m unittest tests.test_simulation_backend tests.test_assurance_analyses -v`

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation/backend.py tests/test_simulation_backend.py
git commit -m "feat: cross-check simulation with independent dynamics"
```

### Task 7: Calibration and system-identification contracts

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/calibration.py`
- Create: `reference/mobile-manipulator/simulation/calibration-synthetic.json`
- Create: `tests/test_simulation_calibration.py`

- [ ] **Step 1: Write calibration RED tests**

Cover dataset hashes, evidence levels, SI units, sample/split bounds, distinct train/evaluation indices, bounded parameters, deterministic fitting, residual recomputation, overfit/poor held-out rejection, nonfinite data, singular inputs, artifact drift, synthetic self-fit, and the rule that only eligible bench/hardware data can produce `calibrated_simulation`.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_calibration -v`

- [ ] **Step 3: Implement bounded fit and promotion logic**

Use a small deterministic least-squares/grid fit implemented with finite checked arithmetic. Synthetic/reference records remain `simulated` even when residuals pass; attach `pipeline_test_only`.

- [ ] **Step 4: Verify**

Run: `python -m unittest tests.test_simulation_calibration tests.test_simulation_backend -v`

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation/calibration.py reference/mobile-manipulator/simulation/calibration-synthetic.json tests/test_simulation_calibration.py
git commit -m "feat: fit bounded simulator calibration records"
```

### Task 8: Training adapter, domain randomization, and policy firewall

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/training.py`
- Create: `reference/mobile-manipulator/simulation/training-contract.json`
- Create: `tests/test_simulation_training.py`

- [ ] **Step 1: Write training RED tests**

Test closed observation/action schemas, frames/units/rates, visible reward weights, hard constraints, episode/step/time/memory/artifact budgets, distinct train/eval seeds, stable policy ID, uncertainty-owned randomization, out-of-range distributions, callback exceptions/timeouts/NaN/malformed output, baseline comparison, held-out faults, `not_justified`, and attempts to mutate physical report/evidence/hardware promotion.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_training -v`

- [ ] **Step 3: Implement finite adapter and firewall**

Callbacks receive deep-thawed copies and return validated records. Policy results are always `simulated`; the result serializer has no hardware-promotion field and preserves physical blockers verbatim.

- [ ] **Step 4: Verify**

Run: `python -m unittest tests.test_simulation_training tests.test_simulation_admission -v`

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/assurance/simulation/training.py reference/mobile-manipulator/simulation/training-contract.json tests/test_simulation_training.py
git commit -m "feat: enforce bounded training promotion firewall"
```

### Task 9: Validation CLI and end-to-end portable reference benchmark

**Files:**
- Create: `skills/robotics-design/scripts/validate_simulation_bundle.py`
- Create: `tests/test_simulation_cli.py`
- Create: `tests/test_reference_simulation.py`
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `skills/robotics-design/references/validation-gates.md`
- Create: `skills/robotics-design/references/simulation-evidence-contract.md`

- [ ] **Step 1: Write CLI/reference RED tests**

Assert exit `0` valid simulated bundle, `1` valid but failed/indeterminate scenario, `2` invalid input/tamper/resource/publication error; no traceback. The reference benchmark must be simulation-admitted but not hardware-promotable, compile ten scenarios, replay deterministic synthetic traces, cross-check the independent backend, run synthetic calibration without upgrading evidence, and retain training firewall results.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_cli tests.test_reference_simulation -v`

- [ ] **Step 3: Implement CLI/router/docs**

Catch decoding, schema, execution, overflow, timeout, filesystem, and serialization boundaries. Route simulation/training requests through physical/hypothesis admission before consumer work.

- [ ] **Step 4: Run full portable suite on Python 3.11 and 3.12**

Run:

```bash
python -m unittest discover -s tests -v
<python3.12> -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
```

- [ ] **Step 5: Commit**

```bash
git add skills/robotics-design/scripts/validate_simulation_bundle.py skills/robotics-design/SKILL.md skills/robotics-design/references tests/test_simulation_cli.py tests/test_reference_simulation.py
git commit -m "feat: validate simulation evidence end to end"
```

### Task 10: Digest-pinned Linux live simulation CI

**Files:**
- Create: `reference/mobile-manipulator/simulation/Dockerfile.jazzy-harmonic`
- Create: `reference/mobile-manipulator/simulation/environment-lock.json`
- Create: `scripts/run_live_simulation_gate.sh`
- Create: `.github/workflows/simulation.yml`
- Create: `tests/test_simulation_ci.py`

- [ ] **Step 1: Write CI contract RED tests**

Require Ubuntu 24.04/Jazzy/Harmonic, immutable base/image digest recording, pinned package inventory, source commands, environment check, package discovery, xacro/SDF/SRDF/colcon tests, headless Gazebo, stale-process cleanup, spawn level check, ros2_control/MoveIt/Nav2 consumer inventories, all scenarios, trace replay, cross-backend report, clean shutdown, timeouts, and uploaded evidence. Reject floating-only image tags and workflows that mark missing MoveIt/Nav2 as success.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_simulation_ci -v`

- [ ] **Step 3: Implement environment and live gate**

Pin every resolvable dependency; record the built image digest and actual dpkg/ROS/Gazebo inventory at runtime. Use headless server mode and explicit process cleanup. Upload bounded evidence even on failed scenarios using a final collection step, but keep the job failed.

- [ ] **Step 4: Run workflow and repair until live evidence passes**

Push the branch, inspect every failed step, add a failing regression before each code/config correction, and retain the successful run ID plus artifact hashes.

- [ ] **Step 5: Commit**

```bash
git add reference/mobile-manipulator/simulation scripts/run_live_simulation_gate.sh .github/workflows/simulation.yml tests/test_simulation_ci.py
git commit -m "ci: run pinned Jazzy Harmonic simulation gate"
```

### Task 11: Dependency audit, benchmark, bilingual documentation

**Files:**
- Create: `docs/research/2026-08-14-v05-dependency-audit.md`
- Create: `reference/mobile-manipulator/simulation-benchmark.md`
- Create: `docs/releases/v0.5-completion-audit.md`
- Modify: `manifest.json` only for independently approved dependency updates
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `PROJECT_STATUS.md`
- Modify: `tests/test_public_hygiene.py`

- [ ] **Step 1: Audit source deltas before updating pins**

Diff v0.4 pins against the candidate commits. Record executable/frontmatter/license changes, new network/process behavior, compatibility, tests, and `upgrade` or `retain` disposition. Never change a pin solely because it is newer.

- [ ] **Step 2: Write documentation RED tests**

Require bilingual quick start, exact evidence levels, environment/run IDs, scenario counts, trace/manifest receipts, dependency dispositions, live/static gate distinction, and simulation/training/hardware nonclaims.

- [ ] **Step 3: Write benchmark and completion audit**

Report actual run results only. The benchmark distinguishes portable synthetic replay from Gazebo live evidence and records every skipped consumer or unresolved discrepancy.

- [ ] **Step 4: Run public hygiene and full suites**

Run: `python -m unittest tests.test_public_hygiene tests.test_robotics_design_behavior -v` plus both full Python versions, validate, dry-run, compileall, and diff-check.

- [ ] **Step 5: Commit**

```bash
git add docs reference/mobile-manipulator/simulation-benchmark.md README.md README.zh-CN.md PROJECT_STATUS.md manifest.json tests/test_public_hygiene.py
git commit -m "docs: prepare v0.5 simulation release"
```

### Task 12: Independent review and public v0.5 release

**Files:**
- Modify: release evidence documents only when each external gate becomes true.

- [ ] **Step 1: Run independent whole-release review**

Require no unresolved Critical or Important findings. Reproduce tamper, policy-promotion, stale-artifact, nondeterminism, malformed trace, missing-consumer, and simulator-disagreement attacks.

- [ ] **Step 2: Fresh installation and dual-version/cross-platform verification**

Require 10/10 skills, per-skill pinned-source licenses, official validation, exact local-skill hashes, Python 3.11/3.12, Windows/Linux portable matrix, live Linux simulation, clean residues, and reproducible reference receipts.

- [ ] **Step 3: Public PR and CI**

Open a draft PR, wait for every portable and live job, fix failures with RED regressions, update evidence to the exact successful head/run, obtain final approval, and mark ready.

- [ ] **Step 4: Merge, tag, release, and public verification**

Verify merged tree, rerun main gates, create annotated `v0.5.0`, wait tag gates, publish bounded release notes, verify tag target/manifest/release/artifacts, and retain run IDs/hashes.

- [ ] **Step 5: Controlled local refresh and close audit**

Stage the public tag with skill-installer, generate the host overlay, run official validation and compileall, back up and atomically replace only `robotics-design`, record recovery path without publishing private host paths, merge a post-release audit PR, and advance `PROJECT_STATUS.md` to v0.6.

## Plan self-review

- Spec coverage: all v0.5 deliverables and exit gates map to Tasks 1-12.
- Promotion boundary: Tasks 2, 7, 8, 9, and 12 independently test that simulation/training cannot create hardware evidence.
- Consumer evidence: Tasks 3, 4, 9, and 10 separate portable structure checks from live ROS/Gazebo/MoveIt/Nav2 loads.
- Reproducibility: Tasks 3, 5, 6, 7, 8, 10, and 12 bind seeds, versions, environment/model/trajectory hashes, normalized verdicts, and retained artifacts.
- No placeholders: every planned behavior has an owner, test file, command, and commit boundary; real run IDs/digests are recorded only after execution.
