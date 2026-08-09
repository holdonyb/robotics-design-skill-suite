# Project Status

## Purpose

This repository distributes an auditable robotics-design routing skill plus pinned third-party CAD, robot-description, ROS 2, and simulation skills. It defines artifact ownership, evidence gates, and bounded engineering claims without treating generated or simulated output as certification.

## Verified Current State

- Suite version: `0.2.0`.
- Active branch: `feature/v020-visual-fidelity`.
- Visual-fidelity implementation commit: `2c7ff34`.
- On 2026-08-09, all 25 repository tests passed.
- On 2026-08-09, distribution validation, Python compilation, installer dry-run, and the system skill validator passed.
- Robot visualization now requires deterministic topology/pose ownership, appearance-only image generation, exact joint/interface landmark equality, source hashes, and a promoted visual manifest.

## Active Work

The 0.2.0 implementation is complete and verified on its feature branch. It has not been merged to the base branch or published from this repository.

## Run

This is a skill distribution rather than a long-running application. Preview the installation plan with:

```powershell
python scripts/install.py --dry-run
```

## Validate

```powershell
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
```

Validate an individual robot render manifest with:

```powershell
python skills/robotics-design/scripts/validate_visual_manifest.py path/to/visual_manifest.json
```

## Known Risks

- The manifest gate proves declared source integrity, authorized change categories, and reviewed landmark equality; it does not perform automatic pixel-level joint recognition.
- Visual promotion still needs a reviewer who can identify every required joint and interface without inference.
- The suite does not establish flight readiness, structural margins, thermal closure, radiation tolerance, functional safety, or certification.

## Next Smallest Action

Review commit `2c7ff34`, then choose whether to merge the feature branch or publish it through the repository's normal release workflow.

## Evidence

- `skills/robotics-design/references/visualization-contract.md`: topology/pose authority and promotion contract.
- `skills/robotics-design/scripts/validate_visual_manifest.py`: executable visual manifest gate.
- `tests/test_visual_manifest.py`: source-hash, allowed-change, landmark, and review regressions.
- `tests/test_robotics_design_behavior.py`: routing and no-generative-kinematics behavior regressions.
