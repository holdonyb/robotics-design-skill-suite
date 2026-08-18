# Trace-First Simulation Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind portable training and independent dynamics checks to the same receipt-validated replay traces, with no callback-reported outcome fields.

**Architecture:** A small pure replay-feature module owns trace decoding and metrics.  Training maps every required evaluation case to a replay, derives observations and reward from it, and keeps its existing physical/hardware firewall.  The benchmark uses the same feature record to feed both portable dynamics backends.

**Tech Stack:** Python 3.11+ standard library, canonical JSON, existing simulation trace/backend contracts, unittest.

---

## File map

- `skills/robotics-design/scripts/assurance/simulation/replay_features.py`:
  closed replay decoding and immutable trace-native features.
- `skills/robotics-design/scripts/assurance/simulation/training.py`:
  trace assignment validation and policy evaluation without outcome claims.
- `skills/robotics-design/scripts/validate_simulation_bundle.py`:
  reference trace assignment and shared backend input construction.
- `reference/mobile-manipulator/simulation/training-contract.json`:
  visible trace-native reward terms.
- `tests/test_simulation_training.py` and `tests/test_reference_simulation.py`:
  policy-boundary and end-to-end regressions.
- `release/v1.1-release-contract.json`, `PROJECT_STATUS.md`:
  regenerated release binding and current checkpoint.

### Task 1: Close replay feature extraction

- [ ] Write focused tests that pass a replay with finite uniform samples and
  assert its trace identity, signed wheel travel, effort, final joint error,
  and final observation; assert rejection of malformed state, duplicate metric,
  irregular timestamps, non-finite wheel rates, and non-passed replay status.
- [ ] Run `python -m unittest tests.test_simulation_training tests.test_reference_simulation -v` and observe the missing feature API.
- [ ] Add `replay_features.py` with a frozen `ReplayFeatures` record and one
  `extract_replay_features(replay)` function.  Recompute values from samples,
  reject ambiguous mappings, and serialize sorted canonical values.
- [ ] Run the focused tests and commit `feat: derive bounded features from replay traces`.

### Task 2: Make policy evaluation trace-derived

- [ ] Change training tests so callbacks return only `linear_m_s` and
  `angular_rad_s`, and give each train/evaluation/held-out case an explicit
  replay assignment.  Add attacks for a removed self-reported joint error,
  trace-derived joint-limit failure, duplicate/missing assignments, and a
  callback attempting an unused reward claim.
- [ ] Run `python -m unittest tests.test_simulation_training -v` and observe
  the old outcome API fail the new tests.
- [ ] Update `training.py`: validate exact case assignments, derive callback
  observations and hard joint-error checks from `ReplayFeatures`, calculate
  `wheel_progress` and `wheel_effort` reward terms from features, and bind the
  sorted trace hashes in `PolicyResult` identity/serialization.
- [ ] Update the reference training contract and run
  `python -m unittest tests.test_simulation_training tests.test_simulation_trace -v`.
- [ ] Commit `feat: score policy evaluation from replayed traces`.

### Task 3: Share receipt-bound input with dynamics and reference benchmark

- [ ] Add reference tests that assert every training assignment names a unique
  replay hash and that altering a replayed wheel sample changes both the
  backend input and trace-derived training features.
- [ ] Run `python -m unittest tests.test_reference_simulation -v` and observe
  the old benchmark lacks trace-bound training assignments.
- [ ] Replace duplicated replay parsing in `_backend_input`, build deterministic
  benchmark assignments from compiled scenarios, and pass all replays to
  `_training_result`.  Preserve simulated/not-justified status and the hardware
  firewall.
- [ ] Run focused tests, full unittest discovery, distribution validation,
  release-contract validation, installer dry run, compileall, and diff check.
- [ ] Regenerate `release/v1.1-release-contract.json`, update
  `PROJECT_STATUS.md`, commit `feat: bind simulation evaluation to replay traces`,
  obtain independent read-only review, then publish a PR and merge only after
  CI passes.

## Plan self-review

Every score and hard joint-error check has a receipt-bound input owner; callbacks
only emit actions.  The shared extractor gives training and both dynamics
calculations one input path.  No task creates a hardware claim or changes the
admission firewall.
