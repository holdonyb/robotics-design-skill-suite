# v1.0 Publication Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve observed v1.0 publication evidence on the default branch
without modifying the hash-bound v1.0 release artifacts.

**Architecture:** A new, post-release Markdown record links every observed
external gate. A focused public-hygiene test locks its factual and
non-hardware boundary. The existing release validator remains unchanged and
proves that the immutable release contract was not rewritten.

**Tech Stack:** Markdown, Python standard-library `unittest`, existing
distribution and release validators.

---

### Task 1: Specify publication-record expectations

**Files:**
- Modify: `tests/test_public_hygiene.py`

- [ ] **Step 1: Write the failing public-hygiene test**

```python
def test_v100_publication_record_reports_observed_gates_without_hardware_claims(self):
    record = (ROOT / "docs/releases/v1.0-publication-record.md").read_text(encoding="utf-8")
    for phrase in (
        "v1.0.0",
        "01c3740687016dd34c830e024ece062b7158c26f",
        "31770183229",
        "31770180308",
        "31770543928",
        "31770543942",
        "31770864137",
        "hardware_claims: false",
        "not a hardware-validation claim",
    ):
        self.assertIn(phrase, record)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest tests.test_public_hygiene.PublicHygieneTests.test_v100_publication_record_reports_observed_gates_without_hardware_claims -v`

Expected: FAIL because the record does not exist.

### Task 2: Add the immutable-release-safe record

**Files:**
- Create: `docs/releases/v1.0-publication-record.md`

- [ ] **Step 1: Add the record**

Include the tag, exact commit, PR #15, both reviewed-head simulation runs,
main CI, main simulation, tag CI, and release URL. State that the file is a
post-release record, that the candidate audit remains unchanged, and that no
hardware evidence or authority is implied.

- [ ] **Step 2: Run focused verification**

Run: `python -m unittest tests.test_public_hygiene.PublicHygieneTests.test_v100_publication_record_reports_observed_gates_without_hardware_claims -v`

Expected: PASS.

### Task 3: Preserve release integrity

**Files:**
- Verify only: `PROJECT_STATUS.md`
- Verify only: `docs/releases/v1.0-completion-audit.md`
- Verify only: `release/v1-release-contract.json`

- [ ] **Step 1: Verify immutable inputs were not changed**

Run: `git diff --exit-code origin/main -- PROJECT_STATUS.md docs/releases/v1.0-completion-audit.md release/v1-release-contract.json`

Expected: exit code 0.

- [ ] **Step 2: Run release and distribution validators**

Run: `python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1-release-contract.json; python scripts/validate.py; git diff --check origin/main...HEAD`

Expected: release report `status: passed`, distribution validation passes, and
the diff check is clean.

- [ ] **Step 3: Commit**

Run: `git add docs/releases/v1.0-publication-record.md tests/test_public_hygiene.py docs/superpowers/specs/2026-08-14-v10-publication-record-design.md docs/superpowers/plans/2026-08-14-v10-publication-record.md; git commit -m "docs: record v1 publication evidence"`
