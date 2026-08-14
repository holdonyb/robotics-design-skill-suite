# Simulation Profile Physical Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive the portable simulation dynamics profile from receipt-bound ROS workspace artifacts instead of handwritten constants.

**Architecture:** The benchmark verifies the external ROS workspace receipt, extracts a closed normalized profile from xacro/controller/Nav2 files, and passes it to both independent dynamics implementations. Each crosscheck retains profile source hashes and calculated values.

**Tech Stack:** Python 3.11/3.12 standard library, XML parsing, bounded text parsing, SHA-256, `unittest`, existing ROS workspace manifest validator.

---

## File structure

- `skills/robotics-design/scripts/validate_simulation_bundle.py`: receipt-bound profile loader and backend input integration.
- `tests/test_reference_simulation.py`: reference values, per-crosscheck profile provenance, and tamper regressions.
- `reference/mobile-manipulator/simulation/ros-workspace-manifest.json`: regenerated only if a source fixture changes.
- `release/v1.1-release-contract.json`: regenerated after the bound benchmark changes.

### Task 1: Establish profile extraction contract

**Files:**
- Modify: `tests/test_reference_simulation.py`

- [x] **Step 1: Write failing reference-profile test**

```python
profile = _load_backend_profile(ROOT / "reference" / "mobile-manipulator")
self.assertEqual(0.15, profile["wheel_radius_m"])
self.assertEqual(0.68, profile["wheel_separation_m"])
self.assertEqual(140.2, profile["mass_kg"])
self.assertEqual(0.8, profile["brake_deceleration_m_s2"])
self.assertAlmostEqual(0.4 / 0.15, profile["wheel_speed_limit_rad_s"])
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_profile_is_extracted_from_bound_ros_workspace -v`

Expected: FAIL because `_load_backend_profile` is absent.

- [x] **Step 3: Implement minimal closed extraction**

```python
errors = validate_ros_workspace_manifest(root, manifest_path, _ROS_WORKSPACE_RECEIPT)
if errors:
    raise BenchmarkError("ROS workspace is not receipt-valid: " + "; ".join(errors))
profile = _parse_xacro_and_consumer_configs(root)
if profile["wheel_radius_m"] != profile["controller_wheel_radius_m"]:
    raise BenchmarkError("controller and xacro wheel radius disagree")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_profile_is_extracted_from_bound_ros_workspace -v`

Expected: PASS.

### Task 2: Bind profile to every backend record

**Files:**
- Modify: `tests/test_reference_simulation.py`
- Modify: `skills/robotics-design/scripts/validate_simulation_bundle.py`

- [x] **Step 1: Write profile-provenance regression**

```python
report = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")
record = report["backend_crosschecks"][0]
self.assertEqual("parsed", record["profile"]["evidence_level"])
self.assertEqual("fe325213ea6081a8bb35a5c7651b7183678bb62d8a2baf26cf267a896aba4db1", record["profile"]["workspace_manifest_sha256"])
self.assertEqual(0.15, record["profile"]["wheel_radius_m"])
```

- [x] **Step 2: Run focused profile regressions**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_crosschecks_report_bound_physical_profile -v`

Expected: FAIL because backend records have no profile.

- [x] **Step 3: Implement backend-input and record binding**

```python
profile = _load_backend_profile(root)
crosschecks = [_crosscheck_record(replay, profile) for replay in replayed]
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_reference_simulation -v`

Expected: PASS.

### Task 3: Reject source drift and verify release

**Files:**
- Modify: `tests/test_reference_simulation.py`
- Modify: `skills/robotics-design/scripts/validate_simulation_bundle.py`
- Modify: `release/v1.1-release-contract.json`

- [x] **Step 1: Write tamper regression**

```python
with tempfile.TemporaryDirectory() as raw:
    copied = Path(raw) / "reference"
    shutil.copytree(ROOT / "reference" / "mobile-manipulator", copied)
    controllers = copied / "ros2_ws/src/jx_mobile_manipulator_sim/config/controllers.yaml"
    controllers.write_text(controllers.read_text(encoding="utf-8").replace("wheel_radius: 0.15", "wheel_radius: 0.14"), encoding="utf-8")
    with self.assertRaisesRegex(BenchmarkError, "receipt-valid"):
        _load_backend_profile(copied)
```

- [x] **Step 2: Run focused tamper regression**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_profile_rejects_workspace_source_drift -v`

Expected: FAIL because no profile loader verifies the workspace receipt.

- [x] **Step 3: Run generation and release commands**

Run: `python skills/robotics-design/scripts/generate_release_delivery_contract.py --root . --release-id v1.1.0 --out release/v1.1-release-contract.next.json`; atomically replace `release/v1.1-release-contract.json`; `python -m unittest discover -s tests -v`; `python scripts/validate.py`; `python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1.1-release-contract.json`; `python scripts/install.py --dry-run`; `python -m compileall -q scripts tests skills/robotics-design/scripts`; `git diff --check`.

- [x] **Step 4: Commit and open a draft pull request**

```bash
git add skills/robotics-design/scripts/validate_simulation_bundle.py tests/test_reference_simulation.py release/v1.1-release-contract.json docs/superpowers/specs/2026-08-14-simulation-profile-physical-binding-design.md docs/superpowers/plans/2026-08-14-simulation-profile-physical-binding.md
git commit -m "feat: bind simulation profile to ROS artifacts"
git push -u origin agent/simulation-profile-physical-binding
gh pr create --draft --base main --head agent/simulation-profile-physical-binding --title "feat: bind simulation profile to ROS artifacts"
```
