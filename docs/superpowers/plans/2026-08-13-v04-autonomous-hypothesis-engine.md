# Autonomous Hypothesis Engine v0.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and release a deterministic, bounded hypothesis engine that resolves finite robot design spaces into complete v0.3 contracts, evaluates uncertainty and counterexamples, ranks promotable candidates by visible Pareto fronts, and records owner-correct repair lineage.

**Architecture:** Add a focused `assurance.hypothesis` package beside the v0.3 kernel. Closed design-space input becomes immutable semantic overlays; resolved contracts always pass through `evaluate_contract`. Independent modules own canonical identity, schema, overlay resolution, scheduling/cache, uncertainty, Pareto objectives, repairs, and transactional evidence bundles.

**Tech Stack:** Python 3.11/3.12 standard library, JSON/SHA-256, `unittest`, existing v0.3 assurance APIs, GitHub Actions on Ubuntu/Windows.

---

## File structure

- `skills/robotics-design/scripts/assurance/hypothesis/model.py`: immutable candidate, lineage, stage, objective, and result records.
- `skills/robotics-design/scripts/assurance/hypothesis/canonical.py`: canonical JSON bytes, hashes, seeded ordering, and identifier derivation.
- `skills/robotics-design/scripts/assurance/hypothesis/schema.py`: closed hypothesis-space schema and file loading.
- `skills/robotics-design/scripts/assurance/hypothesis/overlay.py`: semantic target resolution, immutable operations, generation, and deduplication.
- `skills/robotics-design/scripts/assurance/hypothesis/scheduler.py`: stage registry, dependency order, budget accounting, and content-addressed cache.
- `skills/robotics-design/scripts/assurance/hypothesis/uncertainty.py`: discrete cases, sensitivity, distance, and counterexample selection.
- `skills/robotics-design/scripts/assurance/hypothesis/objectives.py`: scalar extraction and Pareto fronts.
- `skills/robotics-design/scripts/assurance/hypothesis/repair.py`: earliest-failure selection, ownership gate, child generation, and cycle prevention.
- `skills/robotics-design/scripts/assurance/hypothesis/bundle.py`: transactional bundle writing and validation.
- `skills/robotics-design/scripts/assurance/hypothesis/engine.py`: end-to-end orchestration.
- `skills/robotics-design/scripts/generate_design_hypotheses.py`: CLI boundary and exit codes.
- `reference/mobile-manipulator/hypothesis-space.json`: bounded public reference trade-off benchmark.
- `reference/mobile-manipulator/hypothesis-benchmark.md`: interpretation and nonclaims.
- `tests/test_hypothesis_*.py`: focused unit, integration, adversarial, and determinism tests.

### Task 1: Canonical records and deterministic identities

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/__init__.py`
- Create: `skills/robotics-design/scripts/assurance/hypothesis/model.py`
- Create: `skills/robotics-design/scripts/assurance/hypothesis/canonical.py`
- Test: `tests/test_hypothesis_model.py`

- [ ] **Step 1: Write failing canonical identity tests**

```python
def test_candidate_identity_ignores_mapping_order_but_includes_seed():
    left = candidate_id("0" * 64, {"motor": "a", "wheel": "b"}, 7)
    right = candidate_id("0" * 64, {"wheel": "b", "motor": "a"}, 7)
    assert left == right
    assert left != candidate_id("0" * 64, {"motor": "a", "wheel": "b"}, 8)
    assert left.startswith("candidate-") and len(left) == 34

def test_canonical_json_rejects_nonfinite_and_boolean_seed():
    with self.assertRaises(CanonicalError):
        canonical_bytes({"x": float("nan")})
    with self.assertRaises(CanonicalError):
        candidate_id("0" * 64, {}, True)
```

- [ ] **Step 2: Run the focused test and confirm missing-module failure**

Run: `python -m unittest tests.test_hypothesis_model -v`

Expected: import failure for `assurance.hypothesis`.

- [ ] **Step 3: Implement canonical primitives and immutable records**

```python
def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalError(str(exc)) from exc
    return (text + "\n").encode("utf-8")

def candidate_id(base_sha256: str, assignments: Mapping[str, str], seed: int,
                 parent_id: str | None = None,
                 repair_rule_id: str | None = None) -> str:
    if type(seed) is not int:
        raise CanonicalError("seed must be an integer")
    payload = {"base_sha256": base_sha256,
               "assignments": dict(sorted(assignments.items())),
               "seed": seed, "parent_id": parent_id,
               "repair_rule_id": repair_rule_id}
    return "candidate-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()[:24]
```

Define frozen dataclasses `CandidateDecision`, `CandidateLineage`,
`StageSpec`, `StageResult`, and `HypothesisResult`; validate identifiers and
expose `to_dict()` methods returning only canonical JSON values.

- [ ] **Step 4: Run model tests**

Run: `python -m unittest tests.test_hypothesis_model -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis tests/test_hypothesis_model.py
git commit -m "feat: add deterministic hypothesis records"
```

### Task 2: Closed design-space schema and budgets

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/schema.py`
- Test: `tests/test_hypothesis_schema.py`

- [ ] **Step 1: Write failing valid/invalid schema tests**

```python
def minimal_space(base_hash: str) -> dict[str, Any]:
    return {"schema_version": 1, "space_id": "drive-tradeoff",
            "base_contract": {"path": "design-contract.json", "sha256": base_hash},
            "max_candidates": 4,
            "axes": [{"id": "wheel", "choices": [
                {"id": "small", "operations": [{"target": "quantity:Q-WHEEL.value",
                                                   "value": {"value": 0.1, "unit": "m"}}]},
                {"id": "large", "operations": [{"target": "quantity:Q-WHEEL.value",
                                                   "value": {"value": 0.2, "unit": "m"}}]}]}],
            "uncertainties": [], "objectives": [], "repair_rules": [],
            "evaluation": {"max_stage_evaluations": 32,
                           "stages": ["contract_v1", "physical_v030"]}}

def test_unknown_fields_and_product_over_budget_are_errors():
    data = minimal_space("0" * 64)
    data["secret"] = True
    assert "root has unknown fields: secret" in validate_space(data)
    data = minimal_space("0" * 64)
    data["max_candidates"] = 1
    assert any("Cartesian product 2 exceeds max_candidates 1" in e
               for e in validate_space(data))
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_schema -v`

Expected: missing `schema` module or validation symbols.

- [ ] **Step 3: Implement schema v1**

Implement exact root/record field allowlists from the design spec, identifier
and SHA-256 checks, typed semantic target parsing, unique IDs, operation target
deduplication, integer budget bounds, and pre-generation Cartesian product
calculation. Reuse `to_si()` to close quantity values. `load_space(Path)` must
catch JSON, UTF-8, I/O, duplicate-key, non-finite, oversized-integer, and
recursion failures as actionable errors without traceback.

- [ ] **Step 4: Add adversarial type/table tests and run**

Cover Boolean schema/budgets, `None`, arrays in scalar fields, duplicate IDs,
empty choices, escaping base paths, forbidden targets such as requirements and
analyses, extra nested fields, NaN/infinity, and 309-digit integers.

Run: `python -m unittest tests.test_hypothesis_schema -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/schema.py tests/test_hypothesis_schema.py
git commit -m "feat: validate bounded hypothesis spaces"
```

### Task 3: Semantic overlays, generation, and deduplication

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/overlay.py`
- Test: `tests/test_hypothesis_overlay.py`

- [ ] **Step 1: Write failing generation tests**

```python
def test_axes_resolve_in_canonical_order_and_deduplicate_contracts():
    candidates = generate_candidates(space, base_contract, seed=11)
    assert [c.decision.assignments for c in candidates] == [
        {"motor": "a", "wheel": "large"},
        {"motor": "a", "wheel": "small"},
        {"motor": "b", "wheel": "large"},
        {"motor": "b", "wheel": "small"},
    ]
    assert candidates[1].resolved_contract["candidate_id"] == candidates[1].candidate_id
    assert any(candidate.alias_of is not None for candidate in candidates)

def test_requirement_analysis_and_artifact_mutations_are_impossible():
    for target in ("requirement:REQ-X.statement", "analysis:AN-X.inputs",
                   "artifact:robot.sha256"):
        with self.assertRaises(OverlayError):
            apply_operation(base_contract, {"target": target, "value": None})
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_overlay -v`

- [ ] **Step 3: Implement immutable semantic operations**

Use `copy.deepcopy`. Resolve quantities/components/evidence by unique ID rather
than array index. Quantity operations may replace only `value` or `tolerance`.
Component/evidence operations replace the complete record and require the same
ID. Architecture operations replace one allowed list. After all operations,
set the derived candidate ID, call `validate_contract`, compute the resolution
hash with candidate ID omitted, and create canonical alias records.

- [ ] **Step 4: Run overlay and v0.3 contract tests**

Run: `python -m unittest tests.test_hypothesis_overlay tests.test_assurance_contract -v`

Expected: all pass and the base object remains byte-equivalent to its pre-run
copy.

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/overlay.py tests/test_hypothesis_overlay.py
git commit -m "feat: resolve immutable robot design overlays"
```

### Task 4: Staged scheduler and content-addressed cache

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/scheduler.py`
- Test: `tests/test_hypothesis_scheduler.py`

- [ ] **Step 1: Write failing dependency/cache tests**

```python
def test_physical_stage_always_calls_v030_gate_and_cache_key_binds_tool_version():
    first = scheduler.evaluate(candidate, cache)
    assert gate_spy.call_count == 1
    second = scheduler.evaluate(candidate, cache)
    assert gate_spy.call_count == 1
    scheduler.tool_versions["assurance_kernel"] = "0.3.1"
    scheduler.evaluate(candidate, cache)
    assert gate_spy.call_count == 2

def test_blocking_contract_stage_prevents_physical_stage():
    result = scheduler.evaluate(invalid_candidate, cache)
    assert result.stages[0].name == "contract_v1"
    assert result.stages[0].status == "blocked"
    assert all(stage.name != "physical_v030" for stage in result.stages)
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_scheduler -v`

- [ ] **Step 3: Implement registry, topological order, budget, and cache**

Define only the five specified stages. Reject unknown stages, dependency cycles,
and evaluation counts beyond `max_stage_evaluations`. Build keys from canonical
candidate/stage/dependency/tool payloads. Validate cached payload key and hash;
write new entries through a sibling temporary file plus `Path.replace()`.
`physical_v030` writes a temporary canonical contract and calls
`evaluate_contract`, preserving the returned report and schema errors.

- [ ] **Step 4: Run scheduler, engine, and CLI-boundary tests**

Run: `python -m unittest tests.test_hypothesis_scheduler tests.test_assurance_engine -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/scheduler.py tests/test_hypothesis_scheduler.py
git commit -m "feat: schedule and cache hypothesis evaluations"
```

### Task 5: Uncertainty, sensitivity, and counterexamples

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/uncertainty.py`
- Test: `tests/test_hypothesis_uncertainty.py`

- [ ] **Step 1: Write failing deterministic-case tests**

```python
def test_same_seed_reproduces_order_and_different_seed_preserves_case_set():
    a = ordered_cases(candidate_id, uncertainties, seed=5)
    b = ordered_cases(candidate_id, uncertainties, seed=5)
    c = ordered_cases(candidate_id, uncertainties, seed=6)
    assert a == b
    assert set(map(case_id, a)) == set(map(case_id, c))
    assert a[0].nominal and c[0].nominal

def test_smallest_hard_counterexample_blocks_candidate():
    result = search_counterexample(cases, evaluate)
    assert result.blocking
    assert result.case.values == {"quantity:Q-SLOPE.value": {"value": 8, "unit": "deg"}}
    assert result.diagnostic_codes == ["PHY.STABILITY.MARGIN"]
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_uncertainty -v`

- [ ] **Step 3: Implement bounded cases**

Generate nominal plus declared discrete cases, refuse products over the stage
budget, use SHA-256 seeded permutation after nominal, normalize distance using
the maximum declared SI deviation per uncertainty, and tie-break by case ID.
Sensitivity records objective deltas and newly blocking diagnostics. Hard
counterexamples block; soft cases remain explicit risk records.

- [ ] **Step 4: Run tests including non-finite and budget attacks**

Run: `python -m unittest tests.test_hypothesis_uncertainty -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/uncertainty.py tests/test_hypothesis_uncertainty.py
git commit -m "feat: search bounded hypothesis counterexamples"
```

### Task 6: Objective extraction and visible Pareto fronts

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/objectives.py`
- Test: `tests/test_hypothesis_objectives.py`

- [ ] **Step 1: Write failing dominance tests**

```python
def test_pareto_front_has_no_hidden_scalarization():
    vectors = {"light": {"mass": 10.0, "runtime": 100.0},
               "long": {"mass": 12.0, "runtime": 140.0},
               "dominated": {"mass": 13.0, "runtime": 90.0}}
    result = pareto_fronts(vectors, {"mass": "minimize", "runtime": "maximize"})
    assert result.fronts[0] == ["light", "long"]
    assert result.dominance_edges == [
        {"dominant": "light", "dominated": "dominated"},
        {"dominant": "long", "dominated": "dominated"},
    ]
    assert "score" not in json.dumps(result.to_dict())

def test_blocked_or_missing_objective_candidate_is_not_pareto_accepted():
    assert extract_vector(blocked_candidate).eligible is False
    assert extract_vector(candidate_with_nan).eligible is False
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_objectives -v`

- [ ] **Step 3: Implement the four source types and fronts**

Resolve quantities through `to_si`, analysis records by `analysis_id` and dotted
output path, minimum evidence through `EvidenceLevel`, and blocking diagnostic
count from the physical report. Require finite non-Boolean scalars. Sort IDs,
emit pairwise edges and non-dominated fronts, and expose raw deltas only.

- [ ] **Step 4: Run objective and report determinism tests**

Run: `python -m unittest tests.test_hypothesis_objectives tests.test_assurance_model -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/objectives.py tests/test_hypothesis_objectives.py
git commit -m "feat: rank robot hypotheses by Pareto fronts"
```

### Task 7: Owner-correct repair lineage

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/repair.py`
- Test: `tests/test_hypothesis_repair.py`

- [ ] **Step 1: Write failing repair ownership tests**

```python
def test_repair_changes_failed_owner_and_creates_child():
    child, trace = repair(parent, diagnostic, rule, seen_hashes=set())
    assert child.parent_id == parent.candidate_id
    assert child.candidate_id != parent.candidate_id
    assert trace.trigger_code == diagnostic.code
    assert trace.owner == "component:CMP-MOTOR-R"
    assert trace.before_hash != trace.after_hash

def test_controller_tuning_cannot_repair_motor_rating_failure():
    with self.assertRaisesRegex(RepairError, "outside diagnostic owner"):
        repair(parent, motor_diagnostic, controller_rule, seen_hashes=set())
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_repair -v`

- [ ] **Step 3: Implement earliest failure and ownership gate**

Sort blocking diagnostics by stage, code, path, and message. Resolve the owner
from the failing quantity/component/path and permit only its quantity values,
the exact component, or that component's source evidence. Apply rules in rule-ID
order, enforce per-rule/global depth, reject immutable targets and seen
resolution hashes, create child decision/lineage, and list failed plus
downstream stages for rerun.

- [ ] **Step 4: Add cycle, no-rule, max-count, and deterministic-selection tests**

Run: `python -m unittest tests.test_hypothesis_repair -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/repair.py tests/test_hypothesis_repair.py
git commit -m "feat: retain owner-correct hypothesis repairs"
```

### Task 8: End-to-end engine, transactional bundle, and validator

**Files:**
- Create: `skills/robotics-design/scripts/assurance/hypothesis/bundle.py`
- Create: `skills/robotics-design/scripts/assurance/hypothesis/engine.py`
- Test: `tests/test_hypothesis_engine.py`
- Test: `tests/test_hypothesis_bundle.py`

- [ ] **Step 1: Write failing end-to-end tests**

```python
def test_same_space_and_seed_produce_byte_identical_bundles():
    run_space(space_path, out_a, seed=42)
    run_space(space_path, out_b, seed=42)
    assert tree_hash(out_a) == tree_hash(out_b)

def test_every_index_file_is_hash_bound_and_tamper_is_rejected():
    run_space(space_path, output, seed=42)
    assert validate_bundle(output) == []
    report = next(output.glob("candidates/*/physical-report.json"))
    report.write_text("{}\n", encoding="utf-8")
    assert any("stale bundle file" in error for error in validate_bundle(output))
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_engine tests.test_hypothesis_bundle -v`

- [ ] **Step 3: Implement orchestration and transactional publication**

Load and hash the space/base, generate/deduplicate, evaluate nominal and
uncertainty cases, apply bounded repairs, extract objectives, compute fronts,
and form `HypothesisResult`. Write to a sibling `.hypothesis-txn-<uuid>`
directory, validate every canonical file/hash/path, then atomically rename to
the requested absent output. On failure, remove only the verified transaction
directory. `--force` uses a sibling backup and restores it on publication
failure.

- [ ] **Step 4: Add collision, path escape, stale cache, extra file, and rollback tests**

Run: `python -m unittest tests.test_hypothesis_engine tests.test_hypothesis_bundle -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/assurance/hypothesis/bundle.py skills/robotics-design/scripts/assurance/hypothesis/engine.py tests/test_hypothesis_engine.py tests/test_hypothesis_bundle.py
git commit -m "feat: emit reproducible hypothesis evidence bundles"
```

### Task 9: CLI and fail-closed exit codes

**Files:**
- Create: `skills/robotics-design/scripts/generate_design_hypotheses.py`
- Test: `tests/test_hypothesis_cli.py`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_exit_codes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        assert run_cli(promotable_space, root / "ok").returncode == 0
        assert run_cli(rejected_space, root / "rejected").returncode == 1
        assert run_cli(invalid_space, root / "invalid").returncode == 2
        assert run_cli(promotable_space, root / "ok").returncode == 2
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_cli -v`

- [ ] **Step 3: Implement argparse and last-resort boundary**

Accept `space`, `--out`, `--seed`, and `--force`. Reject Boolean/invalid seeds,
existing outputs without force, and output paths inside source inputs. Catch
unexpected exceptions at the CLI boundary, print one actionable error without
traceback, and return 2. Print counts/fronts/bundle path on success and earliest
blocking diagnostic when no candidate is accepted.

- [ ] **Step 4: Run CLI and malformed-input tests**

Run: `python -m unittest tests.test_hypothesis_cli tests.test_hypothesis_schema -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design/scripts/generate_design_hypotheses.py tests/test_hypothesis_cli.py
git commit -m "feat: add bounded robot hypothesis CLI"
```

### Task 10: Reference trade-off and repair benchmark

**Files:**
- Create: `reference/mobile-manipulator/hypothesis-space.json`
- Create: `reference/mobile-manipulator/hypothesis-benchmark.md`
- Create: `reference/mobile-manipulator/hypothesis-expected.json`
- Test: `tests/test_hypothesis_reference.py`

- [ ] **Step 1: Write failing reference benchmark tests**

```python
def test_reference_tradeoff_improves_runtime_without_new_hard_failure():
    result = run_reference_space(seed=20260813)
    baseline = next(candidate for candidate in result.candidates
                    if candidate.lineage.assignments["energy"] == "baseline")
    improved = result.best_visible("runtime")
    assert improved.objectives["runtime"] > baseline.objectives["runtime"]
    assert improved.new_blocking_codes_relative_to(baseline) == []
    assert improved.accepted is False
    assert improved.blocking_codes == ["BOM.PLACEHOLDER_BLOCKS_CLAIM"]

def test_injected_wrong_right_motor_rating_traces_and_repairs_owner():
    trace = result.repair_trace("wrong-right-rating")
    assert trace.owner == "component:CMP-TRACTION-MOTOR-R"
    assert trace.trigger_code in {"PHY.ANALYSIS.RATING_OWNER", "PHY.DRIVE.PEAK_TORQUE"}
    assert "controller" not in json.dumps(trace.to_dict()).lower()
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_hypothesis_reference -v`

- [ ] **Step 3: Add a finite public space**

Use exact quantity IDs from the v0.3 reference. Include battery usable-energy,
continuous power, wheel radius, and right-motor rating choices; slope/payload
hard uncertainties; objectives for runtime, peak motor demand, stability
margin, and blocking count; and an owner-correct right-motor repair. Set exact
budgets so the full candidate/case count is known before execution.

- [ ] **Step 4: Generate and hash expected benchmark evidence**

Run:

```powershell
python skills/robotics-design/scripts/generate_design_hypotheses.py reference/mobile-manipulator/hypothesis-space.json --out .tmp-install/v040-reference --seed 20260813
python -m unittest tests.test_hypothesis_reference tests.test_reference_robot -v
```

Expected: the CLI returns 1 because placeholders remain; all trade-off,
counterexample, repair, determinism, and 32 legacy fault assertions pass.

- [ ] **Step 5: Commit**

```powershell
git add reference/mobile-manipulator tests/test_hypothesis_reference.py
git commit -m "test: add mobile manipulator hypothesis benchmark"
```

### Task 11: Skill routing, schema docs, and behavior tests

**Files:**
- Modify: `skills/robotics-design/SKILL.md`
- Create: `skills/robotics-design/references/hypothesis-engine-contract.md`
- Modify: `skills/robotics-design/references/validation-gates.md`
- Modify: `skills/robotics-design/references/design-contract.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Test: `tests/test_robotics_design_behavior.py`
- Test: `tests/test_public_hygiene.py`

- [ ] **Step 1: Write failing routing assertions**

```python
def test_multi_candidate_requests_route_through_hypothesis_contract(self):
    skill = read("skills/robotics-design/SKILL.md")
    assert "hypothesis-engine-contract.md" in skill
    assert "generate_design_hypotheses.py" in skill
    assert "Never rank a candidate that bypassed the physical contract" in skill
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_robotics_design_behavior tests.test_public_hygiene -v`

- [ ] **Step 3: Document operational contract and nonclaims**

Document schema, CLI, stages, uncertainty, Pareto, repairs, bundle validation,
exit codes, reference benchmark, and the exact boundary between calculated
hypothesis evidence and future simulation/hardware evidence. Add bilingual
quick-start commands. Route multi-concept, optimization, sweep, robustness, and
repair requests through the v0.4 contract after requirements and before v0.5
simulation.

- [ ] **Step 4: Run docs/behavior tests**

Run: `python -m unittest tests.test_robotics_design_behavior tests.test_public_hygiene -v`

- [ ] **Step 5: Commit**

```powershell
git add skills/robotics-design README.md README.zh-CN.md tests/test_robotics_design_behavior.py tests/test_public_hygiene.py
git commit -m "docs: route design exploration through hypothesis assurance"
```

### Task 12: Version, cross-platform verification, review, and v0.4 release

**Files:**
- Modify: `manifest.json`
- Modify: `PROJECT_STATUS.md`
- Modify: `.github/workflows/ci.yml` only if the existing matrix does not run all new tests

- [ ] **Step 1: Set version `0.4.0` and durable status**

Record exact commits, candidate/case/repair counts, benchmark result, known
nonclaims, and v0.5 next action. Do not claim simulation or hardware evidence.

- [ ] **Step 2: Run fresh verification on both Python versions**

```powershell
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
py -3.12 -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
git diff --check v0.3.0..HEAD
```

Expected: zero failures, 10 valid skills, 3 pinned sources, complete dry run,
and a clean diff.

- [ ] **Step 3: Perform fresh install and reproducibility checks**

Install to a new ignored path with the Python 3.12 overlay. Require 10/10
official skill validation, 9/9 upstream licenses, zero bytecode/transaction
residue, matching hypothesis-engine hashes, and byte-identical reference
bundles on Python 3.11 and 3.12.

- [ ] **Step 4: Request independent adversarial review**

Probe schema types, product/budget overflow, target escape, requirement or gate
mutation, hash replacement, candidate collisions, cache poisoning, seed
nondeterminism, uncertainty downgrade, Pareto inclusion of failed candidates,
repair ownership/cycles, bundle path escape/tamper, CLI tracebacks, and all v0.3
fault regressions. Resolve every Critical and Important finding.

- [ ] **Step 5: Publish PR and wait for CI**

Push `feature/v040-hypothesis-engine`, open a draft PR, require Ubuntu/Windows ×
Python 3.11/3.12 green, mark ready, and merge. Rerun the complete suite on the
merged commit.

- [ ] **Step 6: Tag, release, verify, and refresh local skill**

Create annotated `v0.4.0`, publish release notes with exact gates/benchmarks/
nonclaims, wait for tag CI, verify public tag and manifest hashes, then refresh
only the local `robotics-design` skill from a validated staged install while
retaining a reversible backup.

- [ ] **Step 7: Commit**

```powershell
git add manifest.json PROJECT_STATUS.md .github/workflows/ci.yml
git commit -m "chore: prepare autonomous hypothesis engine v0.4.0"
```

## Completion audit

Before declaring v0.4 complete, map every v0.4 deliverable and exit gate in
`2026-08-13-trustworthy-autonomous-robot-design-v1-design.md` to a file, test,
command, PR check, bundle hash, benchmark record, or public release. Missing or
indirect evidence keeps v0.4 open. Completing v0.4 advances the v1 goal and
starts v0.5; it does not complete or narrow the v1 goal.
