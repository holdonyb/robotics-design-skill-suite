# Component Mass Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a selected component's catalog mass from being omitted or double-counted in the URDF and arm load-envelope model that supports a physical claim.

**Architecture:** Add a closed `component_mass_closure_v1` analysis that maps every declared component mass contribution to one named URDF/load-envelope link and verifies exact per-link mass closure: `link_mass = structural_residual_mass + sum(component_masses)`. Each mass input is a typed quantity, is owned by its declared component or the link's structural owner, and a verified/qualified component's mass must equal its source-bound catalog limit. The analysis only validates bookkeeping; it does not infer placement, inertia, mounting, or suitability.

**Tech Stack:** Python 3.11+, standard-library `unittest`, schema-v1 JSON design contracts, deterministic SHA-256-bound artifacts.

---

### Task 1: Define the closed mass-closure input contract

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/plugin_contracts.py`
- Test: `tests/test_assurance_contract.py`

- [ ] **Step 1: Write failing shape and dimension tests**

Add `valid_component_mass_closure_inputs()` with one link record:

```python
{
    "links": [{
        "id": "arm_link_2",
        "link_mass_kg": "quantity:Q-LINK-MASS",
        "structural_residual_mass_kg": "quantity:Q-STRUCTURAL-MASS",
        "components": [{
            "id": "CMP-BRAKE-J2",
            "mass_kg": "quantity:Q-BRAKE-MASS",
        }],
    }]
}
```

Assert `validate_plugin_inputs()` rejects a duplicate component id, an unknown field, a missing link field, a bare number, and a `mass_kg` quantity with `current` dimension.

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```powershell
python -m unittest tests.test_assurance_contract.AssuranceContractTests.test_component_mass_closure_requires_closed_mass_records -v
```

Expected: FAIL because `component_mass_closure_v1` is not a known plug-in or its nested records are not validated.

- [ ] **Step 3: Implement closed schema validation**

In `plugin_contracts.py`, add `component_mass_closure_v1` to `KNOWN_PLUGINS` and route it to a dedicated validator. Require a non-empty `links` list of exactly `{id,link_mass_kg,structural_residual_mass_kg,components}` records. Require every component record to contain exactly `{id,mass_kg}`. Require all link and component ids to be non-empty and unique within the analysis and all three quantity references to use `mass` dimension.

- [ ] **Step 4: Run focused contract tests and observe GREEN**

Run:

```powershell
python -m unittest tests.test_assurance_contract -v
```

Expected: PASS.

### Task 2: Implement deterministic mass-closure analysis

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/analyses.py`
- Test: `tests/test_assurance_analyses.py`

- [ ] **Step 1: Write failing calculation and negative-margin tests**

Call `run_plugin("component_mass_closure_v1", ...)` with one 10 kg link, 2 kg structural residual, and 3 kg/5 kg components. Assert the output has `component_mass_kg == 8`, `closure_margin_kg == 0`, and passes. Change link mass to 9 kg and assert `PHY.MASS.CLOSURE`. Supply a non-finite mass and assert an actionable input diagnostic without traceback.

- [ ] **Step 2: Run the focused analysis test and observe RED**

Run:

```powershell
python -m unittest tests.test_assurance_analyses.AssuranceAnalysisTests.test_component_mass_closure_detects_omission_and_double_count -v
```

Expected: FAIL because the plug-in does not exist.

- [ ] **Step 3: Implement the analysis**

Add a `component_mass_closure_v1` plug-in with version `1`. Validate records as mappings with finite non-negative values. For each link calculate:

```python
component_mass = sum(component["mass_kg"] for component in link["components"])
expected_link_mass = link["structural_residual_mass_kg"] + component_mass
closure_margin = link["link_mass_kg"] - expected_link_mass
```

Publish the three masses and margin for every link. Emit `PHY.MASS.CLOSURE` when `abs(closure_margin) > 1e-9`; emit stable domain/type diagnostics for malformed or non-finite records. Do not silently absorb a residual error into the structural term.

- [ ] **Step 4: Run focused analysis and regression suites**

Run:

```powershell
python -m unittest tests.test_assurance_analyses tests.test_assurance_contract -v
```

Expected: PASS.

### Task 3: Bind mass records to exact component ownership and catalog limits

**Files:**
- Modify: `skills/robotics-design/scripts/assurance/contract.py`
- Modify: `skills/robotics-design/scripts/assurance/engine.py`
- Test: `tests/test_assurance_contract.py`
- Test: `tests/test_assurance_engine.py`

- [ ] **Step 1: Write failing ownership tests**

Create two components bound to `actuator:joint_2` and `actuator:joint_3`, each with a mass quantity. Reference the J3 mass from the J2 closure record and assert `PHY.MASS.OWNER`. Mark the J2 component as `verified_part`, declare its `mass` limit, then reference a different J2-owned quantity and assert `PHY.MASS.LIMIT`. Remove the declared `mass` limit from the verified component and assert contract validation rejects the mass contribution.

- [ ] **Step 2: Run focused ownership tests and observe RED**

Run:

```powershell
python -m unittest tests.test_assurance_contract.AssuranceContractTests.test_component_mass_closure_binds_exact_component_mass -v
```

Expected: FAIL because component mass has no role-approved limit and the engine does not validate closure ownership.

- [ ] **Step 3: Implement component mass binding**

Add optional `mass: mass` to every physical role's allowed limits in `ROLE_LIMIT_DIMENSIONS`. Extend the mass-closure engine diagnostics so `components[].mass_kg` must be owned by `component:<id>`, the component id must exist exactly once, and verified/qualified components must expose the same quantity as their `mass` catalog limit. Require `structural_residual_mass_kg` to be owned by the actual URDF artifact (`artifact:robot-model`) or `project:system`; never permit it to be component-owned. Give missing/ambiguous/foreign component mappings `PHY.MASS.OWNER` and verified catalog mismatches `PHY.MASS.LIMIT`.

- [ ] **Step 4: Run contract and engine suites**

Run:

```powershell
python -m unittest tests.test_assurance_contract tests.test_assurance_engine -v
```

Expected: PASS.

### Task 4: Migrate the reference J2 brake as a deliberate unbound candidate

**Files:**
- Create: `reference/mobile-manipulator/component-mass-closure.json`
- Modify: `reference/mobile-manipulator/design-contract.json`
- Modify: `reference/mobile-manipulator/assumptions.json`
- Modify: `tests/test_reference_robot.py`
- Modify: `reference/mobile-manipulator/hypothesis-space.json`
- Modify: `reference/mobile-manipulator/hypothesis-expected.json`
- Modify: `reference/mobile-manipulator/engineering-freeze/freeze-package.json`
- Modify: `reference/mobile-manipulator/simulation/artifact-manifest.json`
- Modify: `reference/mobile-manipulator/simulation/ros-workspace-manifest.json`
- Modify: `release/v1.1-release-contract.json`

- [ ] **Step 1: Write a failing reference closure test**

Add a test asserting the J2 mass-closure analysis exists, reports exact closure for every declared link, and does **not** claim a BFK458-20 mass contribution while `CMP-BRAKE-J2` is an engineering placeholder. In the plug-in regression fixture, inject a 19.3 kg component mass without increasing its link mass and assert `PHY.MASS.CLOSURE`. Do not create a reference fault that edits an unconsumed candidate snapshot.

- [ ] **Step 2: Run the focused reference test and observe RED**

Run:

```powershell
python -m unittest tests.test_reference_robot.ReferenceRobotTests.test_component_mass_closure_blocks_unmodelled_brake_mass -v
```

Expected: FAIL because the reference has no component mass-closure artifact or fault.

- [ ] **Step 3: Add an explicit mass budget without selecting the brake**

Create a hash-bound `component-mass-closure.json` that accounts only for quantities already present in the current URDF/load-envelope model. Keep the BFK458-20 catalog mass in its unbound candidate snapshot and do not add it as a component contribution. Add an explicit `EV-COMPONENT-MASS-CLOSURE` evidence edge, declared JSON observations for the consumed link masses, and a `component_mass_closure_v1` analysis. Ensure the reference report stays non-promotable because all original placeholders remain visible; do not alter status or component state.

- [ ] **Step 4: Regenerate every dependent receipt**

Run the hypothesis generator with seed `20260813`; update `hypothesis-expected.json`; update freeze, simulation, ROS-workspace and release manifests using their existing deterministic scripts. Verify the release receipt's hash-bound source list includes the new artifact and that the generated bundle validators pass.

- [ ] **Step 5: Run end-to-end verification**

Run:

```powershell
$env:PYTHONPATH='skills/robotics-design/scripts'
python -m compileall -q scripts tests skills/robotics-design/scripts reference/mobile-manipulator/model
python -m unittest discover -s tests -q
python scripts/validate.py
python scripts/install.py --dry-run
git diff --check
```

Expected: all tests pass; distribution and installer validate; the reference contract exits `1` only for `BOM.PLACEHOLDER_BLOCKS_CLAIM`; no purchase, power, motion or hardware claim is created.

### Task 5: Publish the mass-accounting boundary

**Files:**
- Modify: `skills/robotics-design/references/physical-plausibility-contract.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Create: `docs/research/2026-08-14-component-mass-closure-audit.md`

- [ ] **Step 1: Document the scope and exclusions**

Document the exact equality check and the rule that a source-bound component mass must be mapped or explicitly excluded before its assembly can be evaluated. State that this does not infer datum, centre of mass, inertia, fastener load, structural stiffness, wiring mass, contact, suitability, procurement or hardware authorization.

- [ ] **Step 2: Publish only after full CI**

Commit the plan's files with `feat: close component mass accounting`, push `agent/component-mass-closure`, open a draft pull request, wait for all checks including `jazzy-harmonic-live`, and merge only if every check passes.

## Self-review

The feature does not silently turn supplier-candidate values into reference-model values. It detects both omitted component mass and double counting with an explicit residual, keeps every mass typed and owner-bound, and requires a parsed catalog value only when a component is already declared verified or qualified. It remains a bookkeeping and analytical gate: actual placement, inertia, braking, structural reaction, CAD fit, procurement, energization and motion each require their own evidence and authority.
