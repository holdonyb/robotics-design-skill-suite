# v0.7 Bench Evidence Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept only hash-bound, calibration-backed raw bench records and retain an explicit no-motion/no-procurement boundary.

**Architecture:** Create a pure local `assurance.bench_evidence` validator that parses canonical package metadata and bounded CSV raw data. It has no serial, network, ROS, actuator, or file-generation interface. The reference intake index remains empty and reports no bench evidence.

**Tech Stack:** Python standard library CSV/JSON/SHA-256/date handling; existing canonical JSON helpers.

---

### Task 1: TDD bench package records

- [ ] Add `tests/test_bench_evidence.py` for a complete fixture, raw-file hash drift, unsafe path/symlink, exact CSV headers, finite/monotonic samples, calibration dates, explicit component/claim edges, and authorization denial.
- [ ] Verify RED with `python -m unittest tests.test_bench_evidence -v`.
- [ ] Create `assurance/bench_evidence.py` with bounded canonical input/CSV validation and immutable result serialization.
- [ ] Run focused plus calibration/contract suites and commit `feat: validate bench evidence intake`.

### Task 2: Reference intake and CLI

- [ ] Add an empty reference intake manifest and raw-data README that forbids invented measurements.
- [ ] Add `validate_bench_evidence.py` and CLI tests for accepted synthetic fixture, empty reference `awaiting_authorization`, invalid input exit 2, report overwrite refusal, and no traceback.
- [ ] Add bilingual documentation and skill routing; run full suite, distribution validation, installer dry-run, compilation and diff check.
- [ ] Commit `feat: add reference bench evidence intake`.

### Task 3: Release

- [ ] Add v0.7 audit/version/hygiene test retaining `bench_tested` provenance boundaries.
- [ ] Push candidate PR, verify Linux/Windows CI and Jazzy/Harmonic gate, merge, tag and release only after all are green.
