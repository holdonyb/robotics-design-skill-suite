# Isolated Policy Artifact Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate the public reference policy from a SHA-bound declarative artifact in a fresh worker process rather than an in-process callback.

**Architecture:** A closed affine-tanh artifact loader derives the actual policy SHA-256. A stdlib worker evaluates one canonical observation per process request. Training owns the trace/reward/firewall and uses only verified worker actions.

**Tech Stack:** Python 3.11 standard library, canonical JSON, subprocess, unittest.

---

### Task 1: Closed policy artifact loader

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/policy_artifact.py`
- Create: `tests/test_simulation_policy_artifact.py`

- [ ] **Step 1: Write failing loader tests**

```python
artifact = load_policy_artifact(path)
self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact.sha256)
with self.assertRaisesRegex(PolicyArtifactError, "canonical|weights"):
    load_policy_artifact(malformed_path)
```

- [ ] **Step 2: Run the focused test**

Run: `python -m unittest tests.test_simulation_policy_artifact -v`

Expected: import failure for `policy_artifact`.

- [ ] **Step 3: Implement the closed loader**

```python
@dataclass(frozen=True)
class PolicyArtifact:
    policy_id: str
    sha256: str
    payload: MappingProxyType

def load_policy_artifact(path: str | Path) -> PolicyArtifact:
    # reject symlinks/oversize/noncanonical JSON; validate exact affine_tanh_v1 fields
```

- [ ] **Step 4: Re-run focused tests**

Run: `python -m unittest tests.test_simulation_policy_artifact -v`

Expected: PASS.

### Task 2: One-request worker protocol

**Files:**
- Create: `skills/robotics-design/scripts/assurance/simulation/policy_worker.py`
- Create: `skills/robotics-design/scripts/assurance/simulation/policy_backend.py`
- Modify: `tests/test_simulation_policy_artifact.py`

- [ ] **Step 1: Add red worker tests**

```python
action = evaluate_artifact_action(artifact, observation, timeout_s=1.0)
self.assertLessEqual(abs(action["linear_m_s"]), 1.0)
with self.assertRaisesRegex(PolicyBackendError, "timeout|response"):
    evaluate_artifact_action(bad_artifact, observation, timeout_s=0.01)
```

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest tests.test_simulation_policy_artifact -v`

Expected: import failure for `policy_backend`.

- [ ] **Step 3: Implement stdlib worker and parent**

```python
completed = subprocess.run(
    [sys.executable, str(WORKER), "--once"], input=request, text=True,
    cwd=empty_dir, env={}, timeout=timeout_s, capture_output=True, check=False,
)
```

- [ ] **Step 4: Re-run focused tests**

Run: `python -m unittest tests.test_simulation_policy_artifact -v`

Expected: PASS.

### Task 3: Migrate reference training

**Files:**
- Create: `reference/mobile-manipulator/simulation/policies/baseline-affine.json`
- Modify: `reference/mobile-manipulator/simulation/training-contract.json`
- Modify: `skills/robotics-design/scripts/assurance/simulation/training.py`
- Modify: `skills/robotics-design/scripts/validate_simulation_bundle.py`
- Modify: `tests/test_simulation_training.py`
- Modify: `tests/test_reference_simulation.py`

- [ ] **Step 1: Add failing artifact-evaluation tests**

```python
result = evaluate_policy_artifact(contract, artifact_path, physical, context)
self.assertEqual("simulated", result.evidence_level)
with self.assertRaisesRegex(TrainingError, "artifact_sha256"):
    evaluate_policy_artifact(wrong_digest_contract, artifact_path, physical, context)
```

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest tests.test_simulation_training tests.test_reference_simulation -v`

Expected: failure because artifact evaluation is unavailable.

- [ ] **Step 3: Implement migration**

```python
artifact = load_policy_artifact(artifact_path)
if checked_contract["artifact_sha256"] != artifact.sha256:
    raise TrainingError("training contract artifact_sha256 does not match policy artifact")
action = evaluate_artifact_action(artifact, observation, timeout_s=remaining_timeout)
```

- [ ] **Step 4: Re-run focused tests**

Run: `python -m unittest tests.test_simulation_training tests.test_reference_simulation -v`

Expected: PASS.

### Task 4: Bind delivery and validate

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/simulation/__init__.py`
- Modify: `skills/robotics-design/scripts/assurance/release/evaluator.py`
- Modify: `tests/test_release_delivery_evaluator.py`
- Modify: `release/v1.1-release-contract.json`

- [ ] **Step 1: Add a release-binding red test**

```python
for path in ("policy_artifact.py", "policy_backend.py", "policy_worker.py", "baseline-affine.json"):
    self.assertIn(path, required_paths_for("v1.1.0"))
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m unittest tests.test_release_delivery_evaluator -v`

Expected: missing new runtime path.

- [ ] **Step 3: Bind files and regenerate contract**

Run: `python skills/robotics-design/scripts/generate_release_delivery_contract.py --root . --release-id v1.1.0 --out release/v1.1-release-contract.json`

- [ ] **Step 4: Run final verification and commit**

Run: `python -m unittest discover -s tests -q && python scripts/validate.py && python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1.1-release-contract.json && python scripts/install.py --dry-run && python -m compileall -q scripts tests skills/robotics-design/scripts && git diff --check`

Expected: all commands pass.

Commit: `feat: isolate reference policy artifact evaluation`
