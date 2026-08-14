# v0.6 Engineering Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a hash-bound, fail-closed engineering-freeze package that records procurement and future-hardware prerequisites while authorizing neither procurement nor motion.

**Architecture:** Add a bounded `assurance.engineering_freeze` layer beside the physical and simulation kernels. It validates canonical manifests, supplier snapshots, artifact hashes, hazards, safety functions, verification links, and planned test cards. Its result is deterministic and both authorization flags are always false.

**Tech Stack:** Python 3.11/3.12 standard library, canonical JSON/SHA-256, existing assurance canonical helpers, GitHub Actions.

---

### Task 1: Closed records and canonical inputs

**Files:** Create `skills/robotics-design/scripts/assurance/engineering_freeze/{__init__,model,schema}.py`; create `tests/test_engineering_freeze_model.py`.

- [ ] Write tests that reject duplicate keys, noncanonical JSON, non-UTF-8, unsafe paths, nonfinite data, and either authorization flag being true.
- [ ] Run `python -m unittest tests.test_engineering_freeze_model -v` and observe missing-module RED.
- [ ] Implement frozen findings/reports, bounded canonical loading, and sorted canonical serialization.
- [ ] Re-run the focused suite and commit `feat: add closed engineering freeze records`.

### Task 2: Supplier-snapshot contract

**Files:** Create `skills/robotics-design/scripts/assurance/engineering_freeze/suppliers.py`, `tests/test_engineering_freeze_suppliers.py`, and `reference/mobile-manipulator/engineering-freeze/{supplier-manifest.json,supplier-snapshots/README.md}`.

- [ ] Test exact identity, URL/date, local regular snapshot, SHA-256, reviewed typed limits, component and requirement edges, stale/tampered files, and a complete synthetic fixture that still grants no authorization.
- [ ] Run the focused test RED, then implement offline-only hash-bound validation (never fetch supplier URLs).
- [ ] Re-run supplier, ledger, and contract suites; commit `feat: validate supplier snapshot manifests`.

### Task 3: Freeze package evaluator

**Files:** Create `skills/robotics-design/scripts/assurance/engineering_freeze/evaluator.py`, `tests/test_engineering_freeze_evaluator.py`, and `reference/mobile-manipulator/engineering-freeze/freeze-package.json`.

- [ ] Test closed graph records, duplicate IDs, hash drift, unresolved critical hazards, missing drawings/wiring/inspection/verification links, safety paths without test cards, invalid post-control risk, and planned hardware-card preconditions.
- [ ] Run the focused test RED, then implement deterministic evaluator and literal false authorization flags.
- [ ] Re-run the freeze suite; commit `feat: evaluate engineering freeze packages`.

### Task 4: Reference gate and documentation

**Files:** Create reference `drawings`, `wiring`, `hazards`, `verification`, `inspection`, and `test-cards` README artifacts; create `skills/robotics-design/scripts/validate_engineering_freeze.py` and `tests/test_engineering_freeze_cli.py`; modify `SKILL.md`, `README.md`, and `README.zh-CN.md`.

- [ ] Test CLI exit 0 for complete synthetic fixtures, exit 1 for the valid-but-open reference package, exit 2 for malformed input, canonical reports, and no traceback.
- [ ] Implement the CLI and bounded documentation. Every reference artifact must state its missing evidence and no-purchase/no-motion condition.
- [ ] Run `python -m unittest discover -s tests -v`, `python scripts/validate.py`, `python scripts/install.py --dry-run`, `python -m compileall -q scripts tests skills/robotics-design/scripts`, and `git diff --check`; commit `feat: add reference engineering freeze gate`.

### Task 5: v0.6 release

**Files:** Create `docs/releases/v0.6-completion-audit.md`; modify `PROJECT_STATUS.md`, `manifest.json`, `tests/test_manifest.py`, and `tests/test_public_hygiene.py`.

- [ ] Add failing hygiene assertions for `procurement_authorized: false` and `motion_authorized: false`, then update the version/audit only after candidate gates pass.
- [ ] Push an isolated PR; validate retained cross-platform and Linux CI evidence; merge, annotate `v0.6.0`, publish the release, and verify tag CI.
- [ ] Do not represent the freeze package as vendor approval, purchasing approval, fabrication authorization, hardware safety, energization, or motion authority.
