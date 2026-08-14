# v1.1 Release Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the hardware-authority intake as v1.1.0 while preserving exact, independent verification of the published v1.0.0 delivery.

**Architecture:** Release contracts remain canonical and hash-bound. The evaluator selects a closed release profile from the contract's `release_id`; v1.0.0 retains its original binding allow-list and manifest requirement, while v1.1.0 adds the authority entry points and requires manifest version 1.1.0. The distribution validator selects v1.1.0 only after the new contract is generated.

**Tech Stack:** Python standard library, canonical JSON, SHA-256, `unittest`, GitHub release checks.

---

### Task 1: Add closed dual-release profiles

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/release/schema.py`
- Modify: `skills/robotics-design/scripts/assurance/release/model.py`
- Modify: `skills/robotics-design/scripts/assurance/release/evaluator.py`
- Modify: `tests/test_release_delivery_model.py`
- Modify: `tests/test_release_delivery_evaluator.py`

- [x] **Step 1: Write red regressions for both accepted identifiers and a rejected unknown identifier.**

```python
self.assertEqual("v1.1.0", load_release_contract(path).release_id)
with self.assertRaisesRegex(ReleaseSchemaError, "release_id"):
    load_release_contract(unknown_path)
```

- [x] **Step 2: Run the release model tests and observe v1.1.0 rejection.**

Run: `python -m unittest tests.test_release_delivery_model -v`
Expected: FAIL because the v1.0-only schema rejects `v1.1.0`.

- [x] **Step 3: Implement immutable profiles keyed by exact release ID.**

```python
RELEASE_PROFILES = {
    "v1.0.0": ReleaseProfile("1.0.0", V100_REQUIRED_PATHS),
    "v1.1.0": ReleaseProfile("1.1.0", V110_REQUIRED_PATHS),
}
```

Keep `REQUIRED_PATHS` as the v1.0 compatibility alias. Make the evaluator compare binding sets and `manifest.json` against the loaded profile, not a global current version.

- [x] **Step 4: Run the focused model/evaluator suites.**

Run: `python -m unittest tests.test_release_delivery_model tests.test_release_delivery_evaluator -v`
Expected: PASS, including a v1.0 contract over a 1.0 candidate and a v1.1 contract over a 1.1 candidate.

### Task 2: Bind the complete authority delivery surface in v1.1

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/release/evaluator.py`
- Modify: `skills/robotics-design/scripts/generate_release_delivery_contract.py`
- Modify: `tests/test_release_delivery_cli.py`
- Create: `release/v1.1-release-contract.json`

- [x] **Step 1: Write red CLI tests for explicit v1.1 generation and stale authority artifacts.**

```python
created = self.run_cli(GENERATOR, "--root", root, "--release-id", "v1.1.0", "--out", contract)
self.assertEqual(0, created.returncode, created.stderr)
(root / "skills/robotics-design/scripts/assurance/commissioning/authority.py").write_text("tampered")
self.assertEqual(1, self.run_cli(CLI, "--root", root, "--contract", contract).returncode)
```

- [x] **Step 2: Run the release CLI test and observe unsupported `--release-id` or absent v1.1 bindings.**

Run: `python -m unittest tests.test_release_delivery_cli -v`
Expected: FAIL.

- [x] **Step 3: Generate v1.1 only from its profile.**

The v1.1 binding set must include existing public entry points plus:

```text
skills/robotics-design/references/hardware-authority-contract.md
skills/robotics-design/scripts/assurance/commissioning/authority.py
skills/robotics-design/scripts/assurance/commissioning/evaluator.py
```

Require `--release-id` to be a known profile, retain no-overwrite and safe-path rules, and serialize the requested ID verbatim in canonical JSON.

- [x] **Step 4: Change `manifest.json` to `1.1.0`, create the contract, and prove tamper failure.**

Run: `python skills/robotics-design/scripts/generate_release_delivery_contract.py --root . --release-id v1.1.0 --out release/v1.1-release-contract.json`
Expected: exit 0 and one canonical new contract; the original `release/v1-release-contract.json` remains unchanged.

- [x] **Step 5: Run focused release suites.**

Run: `python -m unittest tests.test_release_delivery_model tests.test_release_delivery_evaluator tests.test_release_delivery_cli -v`
Expected: PASS.

### Task 3: Route normal distribution validation through v1.1

**Files:**
- Modify: `scripts/validate.py`
- Modify: `tests/test_robotics_design_behavior.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Create: `docs/releases/v1.1-authority-intake-audit.md`

- [x] **Step 1: Write a failing distribution regression that expects the v1.1 contract path and authority reference.**

```python
self.assertIn("v1.1-release-contract.json", validate_source)
self.assertIn("hardware-authority-contract.md", skill_source)
```

- [x] **Step 2: Update the public version and documentation without implying hardware approval.**

Every public statement must retain: the authority record is evidence-only, hardware claims remain false, and procurement/energization/motion require separate real-world approval.

- [x] **Step 3: Verify all release boundaries before publication.**

Run:
`python scripts/validate.py; python scripts/install.py --dry-run; python -m compileall -q scripts tests skills/robotics-design/scripts; git diff --check`

Expected: every command exits 0. Confirm the old v1.0 contract remains byte-identical to the public tag's contract.

### Task 4: Full verification and publication handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-08-14-hardware-authority-intake.md`
- Modify: `PROJECT_STATUS.md` only if the new release contract does not bind it; otherwise add status only after the tag as an unbound publication record.

- [x] **Step 1: Mark completed plan steps only after their named checks pass.**

- [x] **Step 2: Run the full suite on supported Python runtimes.**

Run: `python -m unittest discover -s tests -v`
Expected: PASS with no skipped security-boundary regressions.

- [x] **Step 3: Commit reviewable changes and complete a pre-landing code review before tagging.**

Commit: `git commit -m "feat: add v1.1 hardware authority intake"`

- [ ] **Step 4: Publish only after GitHub CI and simulation gates pass.**

Create annotated `v1.1.0` at the reviewed main commit and a non-prerelease GitHub Release. Do not purchase, energize, or move hardware as part of this release.
