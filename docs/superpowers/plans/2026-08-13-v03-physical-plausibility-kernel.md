# v0.3 Physical Plausibility Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and release a deterministic, standard-library physical-plausibility kernel that rejects incomplete or contradictory mobile-manipulator designs before simulation or generation claims can be promoted.

**Architecture:** A small `assurance` package inside the installed `robotics-design` skill validates a versioned JSON contract, normalizes SI quantities, infers mandatory component roles, runs bounded physical-analysis plug-ins, compares normalized artifact observations, and emits a deterministic evidence report. A checked-in reference mobile manipulator and a mutation corpus prove that critical omissions and nonphysical values fail closed.

**Tech Stack:** Python 3.11+ standard library, JSON/JSON Schema-like project contracts, XML parsing for URDF observations, `unittest`, existing transactional installer and GitHub Actions matrix.

---

## File map

- `skills/robotics-design/scripts/assurance/model.py`: result, diagnostic, evidence and report dataclasses.
- `skills/robotics-design/scripts/assurance/units.py`: explicit supported SI-unit conversions; no implicit unit guessing.
- `skills/robotics-design/scripts/assurance/contract.py`: contract parsing and structural/semantic validation.
- `skills/robotics-design/scripts/assurance/ledger.py`: component-ledger validation and required-role inference.
- `skills/robotics-design/scripts/assurance/analyses.py`: plug-in protocol and first drivetrain, power, stability and arm checks.
- `skills/robotics-design/scripts/assurance/artifacts.py`: normalized URDF and declared-artifact observations.
- `skills/robotics-design/scripts/assurance/engine.py`: deterministic orchestration, stale evidence and promotion decision.
- `skills/robotics-design/scripts/validate_design_contract.py`: user-facing CLI.
- `skills/robotics-design/references/physical-plausibility-contract.md`: behavior, formulas, validity domains and claim boundaries.
- `reference/mobile-manipulator/`: reference contract, minimal URDF observations and fault mutations.
- `tests/test_assurance_*.py`: focused tests by responsibility.

### Task 1: Preserve and classify active-local experiments

**Files:**
- Create: `docs/research/2026-08-13-active-local-delta.md`
- Test: `tests/test_public_hygiene.py`

- [ ] **Step 1: Capture the read-only delta inventory**

Run:

```powershell
$activeSkill = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex/skills/robotics-design'
git diff --no-index --name-status -- skills/robotics-design $activeSkill
git diff --no-index -- skills/robotics-design (Join-Path $activeSkill 'scripts/test_review_contracts.py')
```

Expected: 17 changed, added, removed, or generated paths; neither installed copy changes.

- [ ] **Step 2: Write the classification record**

The record must list every path in one of these dispositions:

```text
promote_with_tests | superseded_by_v020_review_fix | host_only | generated_drop
```

It must identify `test_review_contracts.py` as candidate behavior evidence,
`__pycache__`/`*.pyc` as `generated_drop`, missing `runtime.md` as local drift,
and validator differences as superseded unless an individual test proves a
new behavior not already present in `a77044a`.

- [ ] **Step 3: Add a hygiene assertion**

Add to `PublicHygieneTests`:

```python
def test_local_delta_record_has_no_unresolved_disposition(self):
    record = (ROOT / "docs/research/2026-08-13-active-local-delta.md").read_text(encoding="utf-8")
    self.assertNotIn("unclassified", record.lower())
    for disposition in (
        "promote_with_tests",
        "superseded_by_v020_review_fix",
        "host_only",
        "generated_drop",
    ):
        self.assertIn(disposition, record)
```

- [ ] **Step 4: Run the focused test**

Run: `python -m unittest tests.test_public_hygiene -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add docs/research/2026-08-13-active-local-delta.md tests/test_public_hygiene.py
git commit -m "docs: classify active robotics skill delta"
```

### Task 2: Define deterministic diagnostics and evidence levels

**Files:**
- Create: `skills/robotics-design/scripts/assurance/__init__.py`
- Create: `skills/robotics-design/scripts/assurance/model.py`
- Test: `tests/test_assurance_model.py`

- [ ] **Step 1: Write failing model tests**

```python
from assurance.model import Diagnostic, EvidenceLevel, Report


def test_evidence_levels_are_ordered_but_certified_is_not_inferred():
    assert EvidenceLevel.CALCULATED < EvidenceLevel.SIMULATED
    assert EvidenceLevel.SIMULATED < EvidenceLevel.BENCH_TESTED


def test_report_is_deterministic_and_fails_on_error_or_indeterminate():
    report = Report("candidate-a")
    report.add(Diagnostic("BOM.MISSING", "error", "components", "missing reducer"))
    report.add(Diagnostic("PHY.UNKNOWN", "indeterminate", "analyses.arm", "no inertia"))
    assert report.promotable is False
    assert report.to_dict()["diagnostics"][0]["code"] == "BOM.MISSING"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_model -v`

Expected: FAIL because `assurance` does not exist.

- [ ] **Step 3: Implement the model**

Use string-valued `IntEnum` ordering only through an explicit rank map:

```python
class EvidenceLevel(str, Enum):
    ASSUMED = "assumed"
    GENERATED = "generated"
    PARSED = "parsed"
    CALCULATED = "calculated"
    SIMULATED = "simulated"
    BENCH_TESTED = "bench-tested"
    INTEGRATED_HARDWARE_TESTED = "integrated-hardware-tested"
    TASK_VALIDATED = "task-validated"
    CERTIFIED = "certified"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, EvidenceLevel):
            return NotImplemented
        return list(EvidenceLevel).index(self) < list(EvidenceLevel).index(other)
```

`Diagnostic` is a frozen dataclass with `code`, `severity`, `path`, `message`
and optional `evidence_ids`. `Report.add()` stores diagnostics; `to_dict()`
sorts them by `(code, path, message)`. `promotable` is false for any `error` or
`indeterminate` severity.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_model -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance tests/test_assurance_model.py
git commit -m "feat: add deterministic assurance evidence model"
```

### Task 3: Add explicit SI quantity handling

**Files:**
- Create: `skills/robotics-design/scripts/assurance/units.py`
- Test: `tests/test_assurance_units.py`

- [ ] **Step 1: Write failing unit tests**

```python
from assurance.units import QuantityError, to_si


def test_supported_units_convert_explicitly():
    assert to_si({"value": 120, "unit": "rpm"}, "angular_velocity") == pytest.approx(12.566370614359172)
    assert to_si({"value": 250, "unit": "mm"}, "length") == 0.25


def test_dimension_mismatch_and_bare_number_fail_closed():
    with pytest.raises(QuantityError, match="expected torque"):
        to_si({"value": 5, "unit": "kg"}, "torque")
    with pytest.raises(QuantityError, match="object with value and unit"):
        to_si(5, "torque")
```

Use `unittest.TestCase` and `assertAlmostEqual` instead of importing pytest in
the committed test, preserving the standard-library runtime.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_units -v`

Expected: FAIL because `assurance.units` does not exist.

- [ ] **Step 3: Implement the bounded unit table**

Support only the dimensions required by v0.3: length, mass, time, angle,
angular velocity, force, torque, power, energy, voltage, current, temperature,
inertia, speed, acceleration and dimensionless ratio. Use exact factor/offset
tuples such as:

```python
UNITS = {
    "m": ("length", 1.0, 0.0),
    "mm": ("length", 1e-3, 0.0),
    "kg": ("mass", 1.0, 0.0),
    "rad/s": ("angular_velocity", 1.0, 0.0),
    "rpm": ("angular_velocity", 2.0 * math.pi / 60.0, 0.0),
    "N": ("force", 1.0, 0.0),
    "N*m": ("torque", 1.0, 0.0),
    "W": ("power", 1.0, 0.0),
    "Wh": ("energy", 3600.0, 0.0),
    "V": ("voltage", 1.0, 0.0),
    "A": ("current", 1.0, 0.0),
    "degC": ("temperature", 1.0, 273.15),
    "kg*m^2": ("inertia", 1.0, 0.0),
}
```

Reject booleans, NaN, infinity, unknown units and dimension mismatches with a
field-specific `QuantityError`.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_units -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/units.py tests/test_assurance_units.py
git commit -m "feat: normalize assurance quantities to SI"
```

### Task 4: Validate the v0.3 design contract

**Files:**
- Create: `skills/robotics-design/scripts/assurance/contract.py`
- Create: `skills/robotics-design/scripts/assurance/schema.md`
- Test: `tests/test_assurance_contract.py`

- [ ] **Step 1: Write failing contract tests**

Build a minimal valid object with `schema_version`, `candidate_id`,
`requirements`, `assumptions`, `quantities`, `components`, `architecture`,
`artifacts`, `analyses`, and `evidence`. Assert that duplicate IDs, boolean
schema versions, unknown owner references, unsupported evidence promotion,
missing source locators and bare physical numbers produce actionable errors.

```python
errors = validate_contract(valid_contract())
self.assertEqual(errors, [])
bad = valid_contract()
bad["quantities"][0]["owner"] = "artifact:missing"
self.assertIn("quantities[0].owner references unknown owner", validate_contract(bad))
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_contract -v`

Expected: FAIL because `validate_contract` is missing.

- [ ] **Step 3: Implement structural and reference validation**

Expose:

```python
def validate_contract(data: Any) -> list[str]: ...
def load_contract(path: Path) -> tuple[dict[str, Any] | None, list[str]]: ...
```

Require schema version `1`, non-empty stable IDs, unique IDs per collection,
explicit quantity objects, known owners, source/evidence references, closed
severity/status vocabularies, SHA-256 file records for artifact evidence, and
no `certified` level unless `authority` and `certificate_id` are non-empty.
Sort errors lexically before return.

- [ ] **Step 4: Document the exact schema**

`schema.md` must define every required/optional field, unit object, ID syntax,
reference syntax, evidence level, lifecycle state and forward-compatibility
rule. It must state that unknown fields are rejected within schema version 1.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_contract -v`

Expected: PASS, including malformed-type cases without traceback.

- [ ] **Step 6: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/contract.py skills/robotics-design/scripts/assurance/schema.md tests/test_assurance_contract.py
git commit -m "feat: validate versioned robot design contracts"
```

### Task 5: Infer and validate the component/BOM ledger

**Files:**
- Create: `skills/robotics-design/scripts/assurance/ledger.py`
- Test: `tests/test_assurance_ledger.py`

- [ ] **Step 1: Write failing mandatory-role tests**

Cover these graph rules:

```python
{
  "differential_drive": ["traction_motor", "reducer", "wheel", "bearing", "motor_driver"],
  "actuated_revolute_joint": ["motor", "reducer", "bearing", "motor_driver"],
  "battery_powered": ["battery", "bms", "main_protection", "contactor", "dc_converter"],
  "claimed_holding_brake": ["brake"],
  "moving_cable": ["cable", "connector", "strain_relief", "cable_management"],
}
```

Assert missing reducer, BMS and strain relief are errors; engineering
placeholders are allowed only when no promoted physical claim depends on them;
verified parts require manufacturer, part number, source URL, source date and
operating-limit records.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_ledger -v`

Expected: FAIL because `assurance.ledger` does not exist.

- [ ] **Step 3: Implement role inference**

Expose:

```python
def required_roles(architecture: dict[str, Any]) -> dict[str, set[str]]: ...
def validate_ledger(contract: dict[str, Any]) -> list[Diagnostic]: ...
```

Diagnostics use stable codes: `BOM.MISSING_ROLE`, `BOM.UNVERIFIED_PART`,
`BOM.DUPLICATE_ID`, `BOM.UNBOUND_INTERFACE`, and `BOM.PLACEHOLDER_BLOCKS_CLAIM`.
Sort by code/path/message.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_ledger -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/ledger.py tests/test_assurance_ledger.py
git commit -m "feat: enforce physical component completeness"
```

### Task 6: Implement conservative physical-analysis plug-ins

**Files:**
- Create: `skills/robotics-design/scripts/assurance/analyses.py`
- Test: `tests/test_assurance_analyses.py`

- [ ] **Step 1: Write failing golden and metamorphic tests**

Test independently calculated fixtures for:

- wheel force and wheel/motor torque on level ground and slope;
- motor speed after gear ratio and drivetrain efficiency;
- continuous versus peak torque/duty checks;
- battery peak power/current and usable-energy runtime;
- static tip margin from projected center of mass and support polygon;
- arm gravity torque `sum(m_i * g * horizontal_lever_i)` per joint;
- brake holding torque with declared safety factor.

Metamorphic assertions must include: increasing payload cannot reduce required
torque; reducing efficiency cannot reduce motor demand; increasing slope cannot
increase tip margin; reducing usable battery energy cannot increase endurance.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_analyses -v`

Expected: FAIL because analysis functions are missing.

- [ ] **Step 3: Implement the plug-in contract**

```python
@dataclass(frozen=True)
class AnalysisPlugin:
    name: str
    version: str
    required_inputs: tuple[str, ...]
    run: Callable[[dict[str, float]], AnalysisResult]
```

Implement `drivetrain_v1`, `battery_v1`, `stability_v1`, and
`arm_gravity_v1`. Each result includes normalized inputs, calculated outputs,
validity assumptions, margins, diagnostic codes and evidence level
`calculated`. Missing required inputs yield `indeterminate`; zero/negative
efficiency, mass, radius, ratio or capacity yield errors, never division
tracebacks.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_analyses -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/analyses.py tests/test_assurance_analyses.py
git commit -m "feat: add conservative robot physical analyses"
```

### Task 7: Parse artifact observations and detect drift

**Files:**
- Create: `skills/robotics-design/scripts/assurance/artifacts.py`
- Test: `tests/test_assurance_artifacts.py`

- [ ] **Step 1: Write failing URDF and drift tests**

Use temporary UTF-8 URDF files to assert extraction of link masses/inertias,
joint parent/child/type/axis/origin/limits and transmissions. Add declared JSON
observations for CAD/BOM/SDF/SRDF/ROS configuration. Assert mismatched mass,
joint limit, missing transmission, unknown component binding and duplicate
owner produce stable `DRIFT.*` diagnostics.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_artifacts -v`

Expected: FAIL because artifact adapters do not exist.

- [ ] **Step 3: Implement safe observation adapters**

Expose:

```python
def observe_urdf(path: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]: ...
def compare_observations(contract: dict[str, Any], observations: dict[str, Any]) -> list[Diagnostic]: ...
```

Use `xml.etree.ElementTree`; reject DTD/entity declarations before parsing.
Never resolve external content. Parse numeric vectors with exact cardinality
and finite values. Comparison tolerances come only from the owning quantity's
contract record; absence of tolerance requires exact equality.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_artifacts -v`

Expected: PASS, including malformed XML and non-finite values without traceback.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/artifacts.py tests/test_assurance_artifacts.py
git commit -m "feat: detect robot artifact ownership drift"
```

### Task 8: Orchestrate validation and emit an evidence report

**Files:**
- Create: `skills/robotics-design/scripts/assurance/engine.py`
- Create: `skills/robotics-design/scripts/validate_design_contract.py`
- Test: `tests/test_assurance_engine.py`

- [ ] **Step 1: Write failing end-to-end tests**

Assert that a valid temporary contract emits byte-identical JSON on two runs,
that changing an artifact after its evidence hash creates
`EVIDENCE.STALE_ARTIFACT`, that any error/indeterminate blocks promotion, and
that CLI errors are actionable lines without traceback.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_assurance_engine -v`

Expected: FAIL because the engine and CLI do not exist.

- [ ] **Step 3: Implement the orchestration order**

`evaluate_contract(path)` must execute in this fixed order:

```text
load/shape -> references/hashes -> ledger -> observations/drift
-> analyses -> evidence dependencies -> promotion decision
```

The report includes schema version, candidate ID, contract SHA-256, tool
versions, normalized analysis inputs/outputs, sorted diagnostics, evidence
coverage and `promotable`. JSON serialization uses `sort_keys=True`,
`separators=(",", ":")`, UTF-8 and one trailing newline.

- [ ] **Step 4: Implement the CLI**

```text
validate_design_contract.py CONTRACT [--report REPORT.json]
```

Exit `0` only when promotable; exit `1` for a valid evaluation that fails or is
indeterminate; exit `2` for CLI/path/JSON/schema-loading errors. Never overwrite
an existing report unless `--force` is passed.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_assurance_engine -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/engine.py skills/robotics-design/scripts/validate_design_contract.py tests/test_assurance_engine.py
git commit -m "feat: emit physical plausibility evidence reports"
```

### Task 9: Add the reference mobile manipulator and critical-fault corpus

**Files:**
- Create: `reference/mobile-manipulator/design-contract.json`
- Create: `reference/mobile-manipulator/robot.urdf`
- Create: `reference/mobile-manipulator/README.md`
- Create: `reference/mobile-manipulator/faults/*.json`
- Create: `tests/test_reference_robot.py`

- [ ] **Step 1: Define the reference fixture without invented claims**

The fixture uses explicit `engineering_placeholder` components and numbered
assumptions for payload, speed, slope, friction, reach, duty, temperature and
endurance. It is expected to be `unpromoted` until verified parts replace every
claim-driving placeholder. The README must state that values are regression
fixtures, not a build recommendation or measured performance.

- [ ] **Step 2: Write the mutation harness test**

Each fault file contains `id`, `critical`, `mutation`, and
`expected_diagnostic`. The harness deep-copies the baseline contract, applies
the JSON-pointer-like mutation, evaluates it, and requires the expected stable
code. Initial critical faults cover missing motor, reducer, bearing, brake,
driver, BMS, protection, contactor, cable management, negative mass, zero wheel
radius, efficiency over one, insufficient continuous torque, overspeed,
insufficient battery current/power/energy, center of mass outside support,
arm gravity overload, stale artifact hash, mass drift and joint-limit drift.

- [ ] **Step 3: Run and verify RED against missing fixtures**

Run: `python -m unittest tests.test_reference_robot -v`

Expected: FAIL because reference files do not exist.

- [ ] **Step 4: Add baseline and mutations**

Every critical fault must fail with its expected diagnostic. The baseline may
remain non-promotable only for the explicit placeholder diagnostics documented
in its README; it must have no structural, unit, reference, arithmetic or drift
errors.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_reference_robot -v`

Expected: PASS with all critical faults rejected and zero false promotions.

- [ ] **Step 6: Commit**

```powershell
git add reference/mobile-manipulator tests/test_reference_robot.py
git commit -m "test: add mobile manipulator physical fault corpus"
```

### Task 10: Route skill behavior and document the physical gate

**Files:**
- Create: `skills/robotics-design/references/physical-plausibility-contract.md`
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `skills/robotics-design/references/design-contract.md`
- Modify: `skills/robotics-design/references/validation-gates.md`
- Modify: `skills/robotics-design/references/authority-map.md`
- Modify: `scripts/validate.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Test: `tests/test_robotics_design_behavior.py`
- Test: `tests/test_public_hygiene.py`

- [ ] **Step 1: Write failing routing tests**

Require the router to read the physical contract before selecting components or
claiming feasibility; forbid promoting joints without motor/transmission/load
paths; require analytical gates before simulation/training; require explicit
evidence level and failure report. Require the distribution validator to find
the new reference and CLI.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_robotics_design_behavior tests.test_public_hygiene -v`

Expected: FAIL on missing v0.3 clauses and files.

- [ ] **Step 3: Write the physical-plausibility contract**

Document inputs, mandatory roles, formulas used by each plug-in, SI units,
validity domains, evidence levels, fault codes, conservative-screening limits,
promotion rules and examples of incomplete drive, arm and power paths. State
that catalog values require exact part provenance and that simulation cannot
replace missing components or unsupported continuous/thermal capability.

- [ ] **Step 4: Update routing and bilingual user documentation**

Add the exact command:

```powershell
python skills/robotics-design/scripts/validate_design_contract.py path/to/design-contract.json --report evidence.json
```

Explain that the checked-in reference is a regression fixture, and describe
what v0.3 proves and does not prove.

- [ ] **Step 5: Run focused and distribution validation**

```powershell
python -m unittest tests.test_robotics_design_behavior tests.test_public_hygiene -v
python scripts/validate.py
python scripts/install.py --dry-run
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```powershell
git add skills/robotics-design scripts/validate.py README.md README.zh-CN.md tests
git commit -m "docs: route robot designs through physical assurance"
```

### Task 11: Version, release evidence, and independent review

**Files:**
- Modify: `manifest.json`
- Modify: `PROJECT_STATUS.md`
- Modify: `.github/workflows/ci.yml` if reference CLI coverage is absent
- Test: entire repository

- [ ] **Step 1: Set the suite version to `0.3.0` and update status**

Record the exact implementation commit IDs after those commits exist. State which
analyses are implemented, which remain future work, fault-corpus counts,
reference candidate promotion state, and the next v0.4 action. Do not claim
hardware evidence.

- [ ] **Step 2: Run fresh dual-version verification**

```powershell
py -3.11 -m compileall -q scripts tests skills/robotics-design/scripts
py -3.11 -m unittest discover -s tests -v
py -3.11 scripts/validate.py
py -V:Astral/CPython3.12.12 -m unittest discover -s tests -v
git diff --check v0.2.0..HEAD
```

Expected: zero failures and clean diff check.

- [ ] **Step 3: Perform a fresh network installation**

Install into a new ignored destination with the Python 3.12 host overlay. Run
the official skill validator with `python -X utf8`, count 10 skills and 9
upstream licenses, and assert zero `__pycache__`, `.pyc`, `.pyo`, or transaction
residue.

- [ ] **Step 4: Request independent adversarial review**

Review against `v0.2.0`, specifically probing malformed types, NaN/infinity,
path escape, hash replacement, missing mandatory components, unit mismatch,
analysis-domain violations, baseline false promotion and each critical-fault
mutation. Resolve every Critical/Important finding and rerun all evidence.

- [ ] **Step 5: Publish through PR and CI**

Push the feature branch, open a draft PR, wait for Ubuntu/Windows × Python
3.11/3.12, mark ready, merge only when green, and rerun the complete suite on
merged `main`.

- [ ] **Step 6: Tag and release `v0.3.0`**

Create an annotated tag and GitHub Release whose notes list implemented gates,
fault-corpus results, reference candidate evidence state and explicit nonclaims.
Wait for tag CI and verify public tag/release hashes.

- [ ] **Step 7: Commit release preparation**

```powershell
git add manifest.json PROJECT_STATUS.md .github/workflows/ci.yml
git commit -m "chore: prepare physical plausibility kernel v0.3.0"
```

## v0.3 completion audit

Before declaring v0.3 complete, map each `v0.3` deliverable and exit gate in
`2026-08-13-trustworthy-autonomous-robot-design-v1-design.md` to a file, test,
command, PR check, installation artifact or public release. Missing or indirect
evidence keeps the release open. Completion of v0.3 advances the active v1.0
goal; it does not complete or narrow that goal.
