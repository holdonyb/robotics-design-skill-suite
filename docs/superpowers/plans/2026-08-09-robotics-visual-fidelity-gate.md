# Robotics Visual Fidelity Gate v0.2.0 Implementation Plan

> Execute with the `executing-plans` workflow in the isolated `feature/v020-visual-fidelity` worktree.

**Goal:** Prevent generative robot renders from changing the authoritative mechanism, pose, joints, interfaces, or link proportions.

**Architecture:** Add a concise visualization contract to the robotics-design skill and enforce promoted assets with a dependency-free JSON manifest validator. Keep CAD/URDF/SDF authoritative and restrict image generation to an image-to-image appearance pass.

## Task 1: Lock the failure into RED tests

**Files:**

- Create `tests/test_visual_manifest.py`
- Create `tests/test_robotics_design_behavior.py`

**Steps:**

1. Test a valid promoted visual manifest.
2. Test rejection for a missing landmark.
3. Test rejection when `pose` is allowed to change.
4. Test rejection after a source hash is tampered.
5. Test that the skill routes robot renders to a visualization contract and forbids generative reposing.
6. Run only the new tests and confirm they fail because the validator/reference/clauses do not exist.

## Task 2: Implement the executable visual gate

**Files:**

- Create `skills/robotics-design/scripts/validate_visual_manifest.py`

**Steps:**

1. Parse a JSON manifest using the Python standard library.
2. Validate schema, status, unique landmark lists, source paths, and SHA-256 hashes.
3. Enforce the allowed appearance-only change vocabulary.
4. Require the full forbidden structural-change vocabulary.
5. Require exact landmark equality and review metadata for promoted assets.
6. Return exit code 0 only for a valid manifest and print actionable errors otherwise.
7. Run the manifest tests to GREEN.

## Task 3: Add the skill-level contract

**Files:**

- Create `skills/robotics-design/references/visualization-contract.md`
- Modify `skills/robotics-design/SKILL.md`
- Modify `skills/robotics-design/references/design-contract.md`
- Modify `skills/robotics-design/references/validation-gates.md`
- Modify `skills/robotics-design/references/source-lock.md`
- Modify `skills/robotics-design/references/runtime.md` if validator usage needs clarification

**Steps:**

1. Define deterministic topology/pose ownership and the no-generative-kinematics rule.
2. Define the reference-view, landmark, image-to-image, review, and promotion workflow.
3. Add the visualization route and hard gates to the main skill.
4. Add visual quantities and invariant ownership to the design contract.
5. Add visual fidelity to cross-artifact validation and source-lock updates.
6. Run the behavior tests to GREEN.

## Task 4: Update distribution metadata and validation

**Files:**

- Modify `manifest.json`
- Modify `agents/openai.yaml`
- Modify `README.md`
- Modify `README.zh-CN.md`
- Modify `scripts/validate.py`
- Modify `tests/test_manifest.py`

**Steps:**

1. Bump the suite version to 0.2.0.
2. Document the visual-fidelity gate and validator entry point.
3. Require the new reference and validator in distribution validation.
4. Run focused metadata tests.

## Task 5: Verify and review

**Steps:**

1. Run all repository unit tests.
2. Run `scripts/validate.py`.
3. Compile Python sources.
4. Run the system skill validator against `skills/robotics-design`.
5. Inspect the diff for consistency, public hygiene, and unintended changes.
6. Commit the verified change on `feature/v020-visual-fidelity`.

## Task 6: Deploy to the installed skill

**Steps:**

1. Preserve installed host-specific runtime and source-lock adaptations.
2. Sync the new reference, validator, and equivalent main-skill clauses into the installed `robotics-design` skill directory.
3. Run the same skill and manifest validations against the installed copy.
4. Report the commit, validation evidence, and installed paths.
