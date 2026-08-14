# Hardware Authority Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind recorded commissioning phases to explicit external authority
records without granting a software-side hardware authorization.

**Architecture:** `commissioning/authority.py` loads one canonical, bounded
record and validates its scope against a phase. The commissioning evaluator
requires the hash-bound record for recorded phases and the CLI provides the
already-bound design hash. Reports remain authorization-negative.

**Tech Stack:** Python standard library, canonical JSON loader, `unittest`.

---

### Task 1: Authority record validator

**Files:**
- Create: `skills/robotics-design/scripts/assurance/commissioning/authority.py`
- Create: `tests/test_commissioning_authority.py`

- [ ] Write tests for canonical closed records and each scope mismatch.
- [ ] Run the focused test and observe missing-module failure.
- [ ] Implement canonical bound-file loading, field/date/finite validation,
  and phase/design/scope cross-binding.
- [ ] Run the focused test green.

### Task 2: Commissioning integration

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/commissioning/evaluator.py`
- Modify: `tests/test_commissioning_evaluator.py`
- Modify: `tests/test_commissioning_cli.py`

- [ ] Require `execution_date` and `authority_record` for recorded phases.
- [ ] Pass the known design hash from the populated CLI intake into the
  evaluator and reject a record bound to another design.
- [ ] Preserve empty-reference behavior and immutable false authorization
  fields.
- [ ] Run focused commissioning suites green.

### Task 3: Public route and full verification

**Files:**
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `tests/test_robotics_design_behavior.py`

- [ ] Document the externally attested, non-authorizing intake before real
  motion in the router.
- [ ] Add a behavior regression for the route and non-authority boundary.
- [ ] Run full suite, distribution validation, installer dry-run, compile, and
  diff check.
- [ ] Commit with `feat: bind commissioning records to external authority`.
