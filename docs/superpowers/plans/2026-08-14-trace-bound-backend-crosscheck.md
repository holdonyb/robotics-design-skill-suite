# Trace-Bound Backend Crosscheck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind every portable primary/independent backend comparison to its receipt-validated replay trace and fail closed on missing or disagreeing evidence.

**Architecture:** `validate_simulation_bundle.py` turns every `SimulationResult` returned by trace replay into one closed dynamics input and serializable crosscheck record. The existing two independent calculations remain unchanged; the benchmark owns evidence binding and aggregation.

**Tech Stack:** Python 3.11/3.12 standard library, JSON/SHA-256, `unittest`, existing simulation trace and backend APIs.

---

## File structure

- `skills/robotics-design/scripts/validate_simulation_bundle.py`: closed conversion, per-replay execution, deterministic aggregation, and nonzero outcome gate.
- `tests/test_reference_simulation.py`: public benchmark binding and fail-closed integration regressions.

### Task 1: Bind every replay

**Files:**
- Modify: `tests/test_reference_simulation.py`
- Modify: `skills/robotics-design/scripts/validate_simulation_bundle.py`

- [x] **Step 1: Write the failing test**

```python
report = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")
records = report["backend_crosschecks"]
self.assertEqual(10, len(records))
self.assertEqual(
    [(item["scenario_id"], item["trace_sha256"]) for item in report["replays"]],
    [(item["scenario_id"], item["trace_sha256"]) for item in records],
)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_crosschecks_bind_every_replay -v`

Expected: FAIL because `backend_crosschecks` is absent.

- [x] **Step 3: Write minimal implementation**

```python
for replay in sorted(replayed, key=lambda item: item.scenario_id):
    input_data = _backend_input(replay)
    primary = evaluate_trace_kinematics(input_data)
    independent = evaluate_independent_dynamics(input_data)
    comparison = compare_backends(primary, independent, _BACKEND_TOLERANCES)
    records.append(_crosscheck_record(replay, primary, independent, comparison))
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_crosschecks_bind_every_replay -v`

Expected: PASS.

### Task 2: Reject malformed replay evidence before evaluation

**Files:**
- Modify: `tests/test_reference_simulation.py`
- Modify: `skills/robotics-design/scripts/validate_simulation_bundle.py`

- [x] **Step 1: Write the failing test**

```python
replay = run_reference_benchmark(ROOT / "reference" / "mobile-manipulator")["replays"][0]
replay["samples"][1]["state"].pop("left_wheel_rad_s")
with self.assertRaisesRegex(BenchmarkError, "wheel state"):
    _backend_input(replay)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_rejects_missing_replayed_wheel_state -v`

Expected: FAIL because the malformed state leaks or reaches a backend.

- [x] **Step 3: Write minimal implementation**

```python
def _backend_input(replay: dict[str, Any]) -> dict[str, object]:
    identity = {field: replay[field] for field in ("scenario_id", "trace_sha256", "model_sha256", "trajectory_sha256")}
    for field in ("trace_sha256", "model_sha256", "trajectory_sha256"):
        validate_sha256(identity[field], f"replay.{field}")
    left = [sample["state"]["left_wheel_rad_s"] for sample in replay["samples"]]
    right = [sample["state"]["right_wheel_rad_s"] for sample in replay["samples"]]
    if any(not math.isfinite(float(value)) for value in left + right):
        raise BenchmarkError("replayed trace wheel state must contain finite numbers")
    return {"model_sha256": identity["model_sha256"], "trajectory_sha256": identity["trajectory_sha256"], "units": "si", "timestamps_ns": [sample["timestamp_ns"] for sample in replay["samples"]], "left_wheel_rad_s": left, "right_wheel_rad_s": right, "wheel_radius_m": 0.1, "wheel_separation_m": 0.5, "wheel_speed_limit_rad_s": 2.0, "mass_kg": 100.0, "slope_rad": 0.0, "brake_deceleration_m_s2": 1.0, "joint_final_rad": replay["samples"][-1]["positions"], "joint_target_rad": [0.0] * len(replay["joint_order"]), "joint_error_limit_rad": 0.01}
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_reference_simulation -v`

Expected: PASS.

### Task 3: Aggregate failed comparison evidence

**Files:**
- Modify: `tests/test_reference_simulation.py`
- Modify: `skills/robotics-design/scripts/validate_simulation_bundle.py`

- [x] **Step 1: Write the regression test**

```python
report = run_reference_benchmark(
    ROOT / "reference" / "mobile-manipulator", force_failed_scenario=True
)
self.assertEqual("failed", report["independent_backend"]["status"])
self.assertEqual("failed", report["backend_crosschecks"][0]["status"])
```

- [x] **Step 2: Run focused simulation regressions**

Run: `python -m unittest tests.test_reference_simulation.ReferenceSimulationTests.test_backend_disagreement_blocks_benchmark -v`

Expected: PASS with both aggregate and scenario-01 crosscheck failed.

- [x] **Step 3: Aggregate all per-scenario records**

```python
status = "passed" if all(record["status"] == "passed" for record in records) else "failed"
report["independent_backend"] = {"status": status, "evidence_level": "calculated", "crosscheck_count": len(records)}
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_reference_simulation tests.test_simulation_backend tests.test_simulation_cli -v`

Expected: PASS.

### Task 4: Verify and publish

**Files:**
- Modify: `docs/superpowers/specs/2026-08-14-trace-bound-backend-crosscheck-design.md`
- Modify: `docs/superpowers/plans/2026-08-14-trace-bound-backend-crosscheck.md`

- [x] **Step 1: Run release verification**

Run: `python -m unittest discover -s tests -v`; `python scripts/validate.py`; `python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1.1-release-contract.json`; `python scripts/install.py --dry-run`; `python -m compileall -q scripts tests skills/robotics-design/scripts`; `git diff --check`

Verified: 495 unit tests, distribution validation, v1.1 release delivery validation, installer dry-run, compilation, and diff check passed locally.

- [x] **Step 2: Commit and open draft pull request**

```bash
git add docs/superpowers/specs/2026-08-14-trace-bound-backend-crosscheck-design.md docs/superpowers/plans/2026-08-14-trace-bound-backend-crosscheck.md tests/test_reference_simulation.py skills/robotics-design/scripts/validate_simulation_bundle.py
git commit -m "feat: bind simulation backend checks to replay traces"
git push -u origin agent/trace-bound-backend-crosscheck
gh pr create --draft --base main --head agent/trace-bound-backend-crosscheck --title "feat: bind simulation backend checks to replay traces"
```
