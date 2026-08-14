# v0.9 Task and Robustness Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed offline intake for future task, fault, endurance, and sim-to-real evidence without granting hardware or task-validation claims.

**Architecture:** `assurance.task_evidence` owns immutable report records, a closed task protocol, and bounded package evaluation. The CLI hash-binds and revalidates v0.3-v0.8 prerequisites before producing a deterministic local dossier.

**Tech Stack:** Python 3.11+, stdlib `dataclasses`, `csv`, `hashlib`, `statistics`, `pathlib`; current canonical JSON and upstream assurance evaluators; `unittest`.

---

### Task 1: Immutable task-evidence model

**Files:** Create `skills/robotics-design/scripts/assurance/task_evidence/__init__.py`, `skills/robotics-design/scripts/assurance/task_evidence/model.py`, and `tests/test_task_evidence_model.py`.

- [ ] **Step 1: Write the failing test**

```python
finding = TaskEvidenceFinding("TASK.MISSING", "indeterminate", "packages", "missing")
report = TaskEvidenceReport("task-reference", "awaiting_authorization", (finding,), (), (), ())
self.assertFalse(report.task_validated)
with self.assertRaisesRegex(ValueError, "derived"):
    TaskEvidenceReport("task-reference", "evidence_complete", (finding,), (), (), ())
```

- [ ] **Step 2: Verify RED** — run `python -m unittest tests.test_task_evidence_model -v`; expect `ModuleNotFoundError`.

- [ ] **Step 3: Implement the model**

```python
@dataclass(frozen=True)
class TaskEvidenceReport:
    task_evidence_id: str
    status: str
    findings: tuple[TaskEvidenceFinding, ...]
    metric_summaries: tuple[MetricSummary, ...]
    fault_dispositions: tuple[FaultDisposition, ...]
    comparison_residuals: tuple[ComparisonResidual, ...]
    procurement_authorized: bool = False
    motion_authorized: bool = False
    task_validated: bool = False
```

Require immutable tuples, finite summaries, stable IDs, and a derived status: error → `rejected`, indeterminate → `awaiting_authorization`, otherwise `evidence_complete`. Reject any true authorization/task-validation input and sort every serialized collection.

- [ ] **Step 4: Verify GREEN** — run the focused test; expect all pass.
- [ ] **Step 5: Commit** — `git add skills/robotics-design/scripts/assurance/task_evidence tests/test_task_evidence_model.py; git commit -m "feat: add task evidence model"`.

### Task 2: Closed task protocol

**Files:** Create `skills/robotics-design/scripts/assurance/task_evidence/protocol.py` and `tests/test_task_evidence_protocol.py`.

- [ ] **Step 1: Write the failing test**

```python
protocol = valid_protocol()
protocol["metrics"][0]["threshold"] = float("nan")
self.assertIn("TASK.PROTOCOL_METRIC_INVALID", codes(validate_task_protocol(protocol)))
protocol = valid_protocol()
protocol["envelope"][0]["values"] = [0.1, 0.1]
self.assertIn("TASK.PROTOCOL_ENVELOPE_INVALID", codes(validate_task_protocol(protocol)))
```

- [ ] **Step 2: Verify RED** — run `python -m unittest tests.test_task_evidence_protocol -v`; expect missing API failure.
- [ ] **Step 3: Implement `validate_task_protocol(data)`** — accept only the schema-v1 root with `task_id`, ordered `phases`, finite explicit-unit envelope axes, `repetitions`, metrics, fault definitions, endurance bound, and comparison limits. Reject boolean/nonfinite numbers, duplicate IDs/axis values, unsupported units, empty dimensions, undefined faults, non-positive bounds, and ambiguous success direction. Return a frozen normalized protocol plus sorted actionable findings.
- [ ] **Step 4: Verify GREEN** — run focused test; expect valid normalization and invalid findings without traceback.
- [ ] **Step 5: Commit** — `git add skills/robotics-design/scripts/assurance/task_evidence/protocol.py tests/test_task_evidence_protocol.py; git commit -m "feat: validate closed task protocols"`.

### Task 3: Bounded task-package evaluator

**Files:** Create `skills/robotics-design/scripts/assurance/task_evidence/evaluator.py` and `tests/test_task_evidence_evaluator.py`.

- [ ] **Step 1: Write the failing test**

```python
result = evaluate_task_packages(root, valid_protocol(), [nominal_package(root)])
self.assertEqual("evidence_complete", result.status)
bad = nominal_package(root)
bad["state_trace"] = bind_json(root, "traces/state.json", {"schema_version": 1, "events": [[], []]})
self.assertIn("TASK.TRACE_INVALID", codes(evaluate_task_packages(root, valid_protocol(), [bad])))
```

- [ ] **Step 2: Verify RED** — run `python -m unittest tests.test_task_evidence_evaluator -v`; expect missing evaluator failure.
- [ ] **Step 3: Implement `evaluate_task_packages(root, protocol, packages)`** — verify closed package fields, regular local non-symlink hash-bound files, canonical traces, global unique package/raw/trial identities, strict nonnegative timestamps, bounded bytes/samples, finite SI values, phase order, terminal disposition, watchdog, and task limits. Always guard nested event use with an object check after validation so invalid nested values become findings, not `AttributeError`.
- [ ] **Step 4: Add kind-specific RED/GREEN cases**

```python
fault["observed_safe_state"] = "moving"
self.assertIn("TASK.FAULT_SAFE_STATE", codes(evaluate_task_packages(root, protocol, [fault])))
endurance["samples"][1]["timestamp_ns"] = endurance["samples"][0]["timestamp_ns"]
self.assertIn("TASK.ENDURANCE_TIMESTAMPS", codes(evaluate_task_packages(root, protocol, [endurance])))
comparison["observed_values"][0]["value"] = 3.0
self.assertIn("TASK.COMPARISON_RESIDUAL", codes(evaluate_task_packages(root, protocol, [comparison])))
```

Require fault safe-state/recovery records, even endurance sampling without unsupported lifetime extrapolation, and deterministic time-aligned residuals with retained worst error.

- [ ] **Step 5: Verify and commit** — run evaluator tests after each slice, then `git add skills/robotics-design/scripts/assurance/task_evidence/evaluator.py tests/test_task_evidence_evaluator.py; git commit -m "feat: evaluate bounded task evidence"`.

### Task 4: Coverage and aggregate gate

**Files:** Modify `skills/robotics-design/scripts/assurance/task_evidence/evaluator.py` and `tests/test_task_evidence_evaluator.py`.

- [ ] **Step 1: Write the failing test**

```python
result = evaluate_task_packages(root, protocol_with_repetitions(2), [one_nominal_trial(root)])
self.assertIn("TASK.REPETITION_MISSING", codes(result))
forward = evaluate_task_packages(root, protocol, [trial_a, trial_b])
reverse = evaluate_task_packages(root, protocol, [trial_b, trial_a])
self.assertEqual(forward.to_dict(), reverse.to_dict())
```

- [ ] **Step 2: Verify RED** — run the evaluator test; expect coverage/order assertion failure.
- [ ] **Step 3: Implement coverage/statistics** — require every declared envelope/fault/repetition identity once, retain aborted/failed records, sort samples, and calculate only count/min/max/arithmetic mean plus explicit threshold result. Never average away failures or extrapolate endurance into lifetime.
- [ ] **Step 4: Verify and commit** — run evaluator test; then commit `feat: gate task evidence coverage`.

### Task 5: Upstream-bound public CLI

**Files:** Create `skills/robotics-design/scripts/validate_task_evidence.py` and `tests/test_task_evidence_cli.py`.

- [ ] **Step 1: Write the failing test**

```python
result = run_cli(empty_index())
self.assertEqual(1, result.returncode)
self.assertIn('"status":"awaiting_authorization"', result.stdout)
result = run_cli(index_with_rejected_commissioning())
self.assertIn("TASK.COMMISSIONING_REQUIRED", result.stdout)
```

- [ ] **Step 2: Verify RED** — run `python -m unittest tests.test_task_evidence_cli -v`; expect missing script.
- [ ] **Step 3: Implement CLI** — close empty/populated roots, safely bind every path/hash, require one contract SHA across design/freeze/bench/commissioning, run existing upstream validators rather than merely checking nonempty files, evaluate the protocol/packages, and append indeterminate upstream findings. Emit canonical JSON and return `0` only for `evidence_complete`, `1` otherwise, `2` only for malformed/tampered/path-unsafe/read failures with one `ERROR:` line and no traceback.
- [ ] **Step 4: Verify and commit** — run CLI tests including symlink/path/hash/upstream mismatch attacks and `task_validated:false`; commit `feat: bind task evidence intake`.

### Task 6: Reference and public routing

**Files:** Create `reference/mobile-manipulator/task-evidence/task-evidence-index.json`, `reference/mobile-manipulator/task-evidence/raw/README.md`, and `tests/test_reference_task_evidence.py`; modify `README.md`, `README.zh-CN.md`, `skills/robotics-design/SKILL.md`, `manifest.json`, `PROJECT_STATUS.md`, `docs/releases/v0.9-completion-audit.md`, `tests/test_manifest.py`, and `tests/test_public_hygiene.py`.

- [ ] **Step 1: Write the failing test**

```python
result = subprocess.run([sys.executable, str(CLI), "--index", str(INDEX)], capture_output=True, text=True)
self.assertEqual(1, result.returncode)
self.assertFalse(json.loads(result.stdout)["task_validated"])
self.assertIn("fabricated", (INDEX.parent / "raw" / "README.md").read_text().lower())
```

- [ ] **Step 2: Verify RED** — run reference/public/manifest tests; expect missing reference/routing failure.
- [ ] **Step 3: Implement public artifacts** — create exact canonical empty index `{"packages":[],"schema_version":1,"task_evidence_id":"task-evidence-reference"}`, state command and `0/1/2` behavior in both languages, preserve no-device/no-task-validation text, and bump version only at candidate freeze with actual evidence in the audit.
- [ ] **Step 4: Verify and commit** — run focused reference/public/manifest tests; commit `release: prepare v0.9 task evidence gate`.

### Task 7: Candidate and release verification

**Files:** Modify `docs/releases/v0.9-completion-audit.md` and `PROJECT_STATUS.md` with observed outputs only.

- [ ] **Step 1: Run complete local evidence**

```bash
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
python -m compileall -q scripts tests skills/robotics-design/scripts
git diff --check origin/main...HEAD
python skills/robotics-design/scripts/validate_task_evidence.py --index reference/mobile-manipulator/task-evidence/task-evidence-index.json
```

Expected: all checks pass; reference exits `1` with `awaiting_authorization` and all claim fields false.

- [ ] **Step 2: Publish exact candidate** — commit audit evidence, push `feature/v090-task-evidence`, open a draft PR, and require reviewed-head PR CI, Windows/Linux matrices, fresh-install, and Jazzy/Harmonic gate before merge.
- [ ] **Step 3: Publish exact release** — merge only after gates pass, tag the exact main merge as annotated `v0.9.0`, wait for main/tag CI, create GitHub Release, and land a separate post-release documentation PR with real IDs.

## Plan self-review

- Tasks 1-6 cover every v0.9 design boundary; Task 7 covers evidence and publication.
- `TaskEvidenceReport`, `validate_task_protocol`, `evaluate_task_packages`, and `validate_task_evidence.py` are defined before their later use.
- Each implementation task contains a RED test, expected command, GREEN verification, and commit boundary; no task invents hardware or physical evidence.
