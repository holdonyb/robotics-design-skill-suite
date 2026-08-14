# v0.8 Commissioning Evidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline, fail-closed commissioning-evidence validator that prepares future low-energy hardware trials without controlling hardware or claiming completed commissioning.

**Architecture:** A small `assurance.commissioning` package owns immutable result records and canonical package/trace validation. A CLI binds a commissioning index to the current design, engineering-freeze, and bench-evidence packages, then aggregates deterministic phase findings. The reference contains only an exact empty index, so it remains explicitly awaiting external authorization.

**Tech Stack:** Python 3.11 standard library, existing canonical JSON/SHA-256 helpers, unittest, existing public distribution validator.

---

### Task 1: Immutable commissioning result model

**Files:**
- Create: `skills/robotics-design/scripts/assurance/commissioning/__init__.py`
- Create: `skills/robotics-design/scripts/assurance/commissioning/model.py`
- Create: `tests/test_commissioning_model.py`

- [ ] **Step 1: Write failing immutable-record tests**

```python
from assurance.commissioning.model import CommissioningFinding, CommissioningReport

finding = CommissioningFinding("COMM.AUTHORIZATION_REQUIRED", "indeterminate", "phases", "external authority is required")
report = CommissioningReport("commissioning-reference", "awaiting_authorization", (finding,), None)
self.assertFalse(report.procurement_authorized)
self.assertFalse(report.motion_authorized)
self.assertEqual("awaiting_authorization", report.to_dict()["status"])
with self.assertRaisesRegex(ValueError, "authorization"):
    CommissioningReport("commissioning-reference", "ready", (), None, motion_authorized=True)
```

- [ ] **Step 2: Run the focused model test and verify RED**

Run: `python -m unittest tests.test_commissioning_model -v`

Expected: `ModuleNotFoundError: No module named 'assurance.commissioning'`.

- [ ] **Step 3: Implement closed immutable model records**

```python
@dataclass(frozen=True)
class CommissioningReport:
    commissioning_id: str
    status: str
    findings: tuple[CommissioningFinding, ...]
    highest_validated_phase: str | None
    procurement_authorized: bool = False
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.commissioning_id, "commissioning_id")
        if self.status not in {"ready", "rejected", "awaiting_authorization"}:
            raise ValueError("invalid commissioning status")
        if self.procurement_authorized or self.motion_authorized:
            raise ValueError("authorization flags must always be false")
```

`CommissioningFinding` contains `code`, `severity`, `path`, and `message`.
Its constructor rejects an empty/non-identifier code, a severity outside
`info|warning|error|indeterminate`, and empty path/message. Its `to_dict()`
returns exactly those fields. `CommissioningReport.to_dict()` always emits both
authorization flags as `false`, sorts findings by `(code, path, message,
severity)`, and never emits `integrated-hardware-tested`.

- [ ] **Step 4: Run focused model test and verify GREEN**

Run: `python -m unittest tests.test_commissioning_model -v`

Expected: all immutable, bad-status, invalid-finding, and authorization-firewall tests pass.

- [ ] **Step 5: Commit the model boundary**

```bash
git add skills/robotics-design/scripts/assurance/commissioning tests/test_commissioning_model.py
git commit -m "feat: add commissioning evidence model"
```

### Task 2: Closed commissioning schema and phase evaluator

**Files:**
- Create: `skills/robotics-design/scripts/assurance/commissioning/evaluator.py`
- Create: `tests/test_commissioning_evaluator.py`
- Modify: `skills/robotics-design/scripts/assurance/commissioning/__init__.py`

- [ ] **Step 1: Write failing phase-order and safety-trace tests**

```python
report = evaluate_commissioning_package(root, package)
self.assertEqual("rejected", report.status)
self.assertIn("COMM.PHASE_ORDER", {item.code for item in report.findings})

package["phases"][1]["stop_trace"] = None
report = evaluate_commissioning_package(root, package)
self.assertIn("COMM.STOP_TRACE_REQUIRED", {item.code for item in report.findings})
```

The test helper writes canonical local JSON with fields exactly matching:

```python
ROOT_EMPTY = {"schema_version", "commissioning_id", "phases"}
ROOT_POPULATED = ROOT_EMPTY | {"design_contract", "freeze_package", "bench_index"}
PHASE = {
    "phase", "status", "test_card_id", "authority_record_id", "roles",
    "area_id", "estop_id", "limits", "watchdog_timeout_ns",
    "abort_criteria", "command_trace", "state_trace", "stop_trace",
    "inspection_record",
}
LIMITS = {"energy_j", "speed_m_s", "torque_nm"}
BOUND_FILE = {"path", "sha256"}
```

`status` is exactly one of `planned`, `recorded`, or `aborted`. A planned
phase has all trace/inspection fields set to `null`; recorded and aborted
phases bind all four `BOUND_FILE` records. An aborted phase remains valid input
but emits blocking output and prevents all following phases from passing.

- [ ] **Step 2: Run focused evaluator test and verify RED**

Run: `python -m unittest tests.test_commissioning_evaluator -v`

Expected: import failure because `evaluate_commissioning_package` is not implemented.

- [ ] **Step 3: Implement closed, bounded phase evaluation**

```python
_PHASES = (
    "unpowered_inspection", "protected_power", "isolated_joint",
    "separated_base_arm", "integrated_low_energy",
)

def evaluate_commissioning_package(root: Path, package: object) -> CommissioningReport:
    # validate exact root/record sets; return stable findings, never tracebacks
    # require each phase prefix exactly once and block every dependent phase
    # after a planned, aborted, rejected, or missing predecessor
```

Require a planned phase to contain no traces and a recorded/aborted phase to contain all
four hash-bound records. Validate regular non-symlink paths (including every
parent component), SHA-256, maximum
one MiB JSON traces, maximum 10,000 events, integer nanosecond timestamps,
finite numeric values, monotonically increasing trace time, unique IDs, at
least two unique roles, nonempty area/E-stop/authority/card IDs, positive
finite limits, and nonempty abort criteria. Reject command or observed motion
in `unpowered_inspection` and `protected_power`; require both `emergency_stop`
and `command_timeout` safe-state events for motion-capable recorded phases;
require a post-test inspection disposition. Preserve aborted/rejected evidence
as blocking findings rather than dropping it.

- [ ] **Step 4: Add adversarial evaluator coverage**

```python
for mutate, code in (
    (lambda p: p["phases"].pop(0), "COMM.PHASE_ORDER"),
    (lambda p: p["phases"][2]["limits"].update(speed_m_s=float("nan")), "COMM.LIMIT_INVALID"),
    (lambda p: p["phases"][2]["roles"].__setitem__(1, "operator"), "COMM.ROLES_INVALID"),
):
    with self.subTest(code=code):
        self.assertIn(code, finding_codes(evaluate_commissioning_package(root, mutate(package))))
```

Also cover malformed nested containers, duplicate phase/trace IDs, traversal,
symlink parents, altered hash, irregular timestamps, limit violations, missing
E-stop/timeout transitions, motion during inhibition, missing post inspection,
fixture-only input, abort retention, and deterministic sorted findings.

- [ ] **Step 5: Run evaluator tests and verify GREEN**

Run: `python -m unittest tests.test_commissioning_model tests.test_commissioning_evaluator -v`

Expected: all happy-path, planned, adversarial, and no-traceback tests pass.

- [ ] **Step 6: Commit evaluator behavior**

```bash
git add skills/robotics-design/scripts/assurance/commissioning tests/test_commissioning_evaluator.py
git commit -m "feat: validate commissioning phase evidence"
```

### Task 3: Hash-bound upstream intake CLI

**Files:**
- Create: `skills/robotics-design/scripts/validate_commissioning_evidence.py`
- Create: `tests/test_commissioning_cli.py`

- [ ] **Step 1: Write failing empty-index, upstream-drift, and fixture tests**

```python
result = run_cli(REFERENCE_INDEX)
self.assertEqual(1, result.returncode)
self.assertIn('"status":"awaiting_authorization"', result.stdout)
self.assertIn('"motion_authorized":false', result.stdout)

result = run_cli(tampered_index)
self.assertEqual(2, result.returncode)
self.assertNotIn("Traceback", result.stderr)
```

- [ ] **Step 2: Run focused CLI test and verify RED**

Run: `python -m unittest tests.test_commissioning_cli -v`

Expected: missing CLI and reference-index failures.

- [ ] **Step 3: Implement hash-bound upstream loading**

```python
def main(argv: list[str] | None = None) -> int:
    # Canonical index only: exact empty root is ROOT_EMPTY; nonempty phase list
    # uses ROOT_POPULATED = ROOT_EMPTY | {design_contract, freeze_package,
    # bench_index}. Empty reference omits bindings and reports awaiting_authorization.
    # populated records load the design with load_contract, re-evaluate the
    # freeze via evaluate_engineering_freeze, require a canonical closed bench
    # index, and bind each byte SHA-256 before phase evaluation.
```

Reject a populated package unless the design contract is valid, the freeze
package remains not hardware-authorizing, and the bench index is canonical.
Do not infer that a valid bench CSV, simulated trace, or a claimed authority
record proves a completed hardware phase. Serialize only canonical bytes.
Return `0` only for an internally complete record, `1` for planned/blocked/
awaiting inputs, and `2` for malformed or tampered input.

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run: `python -m unittest tests.test_commissioning_cli tests.test_bench_evidence_cli tests.test_engineering_freeze_cli -v`

Expected: complete tests pass; reference exit is `1`; bad inputs exit `2`
without a traceback.

- [ ] **Step 5: Commit the CLI boundary**

```bash
git add skills/robotics-design/scripts/validate_commissioning_evidence.py tests/test_commissioning_cli.py
git commit -m "feat: bind commissioning intake evidence"
```

### Task 4: Reference intake, public routing, and release tests

**Files:**
- Create: `reference/mobile-manipulator/commissioning/commissioning-index.json`
- Create: `reference/mobile-manipulator/commissioning/raw/README.md`
- Create: `tests/test_reference_commissioning.py`
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `manifest.json`
- Modify: `tests/test_public_hygiene.py`
- Create: `docs/releases/v0.8-completion-audit.md`

- [ ] **Step 1: Write failing reference and hygiene tests**

```python
result = subprocess.run([sys.executable, str(CLI), "--index", str(INDEX)], capture_output=True, text=True)
self.assertEqual(1, result.returncode)
self.assertIn('"status":"awaiting_authorization"', result.stdout)
self.assertNotIn("integrated-hardware-tested", result.stdout)
```

Assert the reference readme forbids generated, simulated, copied, hand-edited,
or fabricated commissioning records; assert README/Chinese README/skill route
the validator and retain the explicit no-command/no-motion boundary.

- [ ] **Step 2: Run reference tests and verify RED**

Run: `python -m unittest tests.test_reference_commissioning tests.test_public_hygiene -v`

Expected: reference path, routing text, and manifest version failures.

- [ ] **Step 3: Add empty reference package and bilingual route**

```json
{"commissioning_id":"commissioning-reference","phases":[],"schema_version":1}
```

Set the suite version to `0.8.0`. Document that a completed validator output is
not a motion permit or integrated-hardware claim, and the reference intentionally
awaits authority and real retained records.

- [ ] **Step 4: Add release audit and verify focused tests**

Run: `python -m unittest tests.test_reference_commissioning tests.test_public_hygiene tests.test_commissioning_cli -v`

Expected: reference/hygiene/CLI tests pass and no shipped file presents a
fabricated commissioning result.

- [ ] **Step 5: Commit release surface**

```bash
git add reference/mobile-manipulator/commissioning skills/robotics-design/SKILL.md README.md README.zh-CN.md manifest.json tests/test_reference_commissioning.py tests/test_public_hygiene.py docs/releases/v0.8-completion-audit.md
git commit -m "release: prepare v0.8 commissioning evidence gate"
```

### Task 5: Full verification and public release

**Files:**
- Modify: `PROJECT_STATUS.md`

- [ ] **Step 1: Run full local verification**

Run:

```bash
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
python -m compileall -q scripts tests skills/robotics-design/scripts
git diff --check
python skills/robotics-design/scripts/validate_commissioning_evidence.py --index reference/mobile-manipulator/commissioning/commissioning-index.json
```

Expected: full suite, distribution validation, installer dry-run, compile, and
diff checks pass; reference CLI exits `1` with `awaiting_authorization` and
both authorization flags false.

- [ ] **Step 2: Commit verified candidate status**

```bash
git add PROJECT_STATUS.md docs/releases/v0.8-completion-audit.md
git commit -m "docs: record v0.8 candidate evidence"
```

- [ ] **Step 3: Publish through gated GitHub flow**

```bash
git push -u origin feature/v080-commissioning
gh pr create --base main --head feature/v080-commissioning --title "feat: add v0.8 commissioning evidence gate"
```

Merge only after Ubuntu/Windows Python 3.11/3.12, clean-install, and
Jazzy/Harmonic consumer checks pass. Then verify the merge commit CI, annotate
and push `v0.8.0`, create a non-draft GitHub Release, and update
`PROJECT_STATUS.md` with exact release/CI IDs in a separately reviewed docs
commit.
