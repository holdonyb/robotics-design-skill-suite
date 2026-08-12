# Project Status

## Purpose

This repository distributes an auditable robotics-design routing skill plus pinned third-party CAD, robot-description, ROS 2, and simulation skills. It defines artifact ownership, executable evidence gates, and bounded engineering claims without treating generated or simulated output as certification.

## Verified Current State

- Suite version: `0.2.0`.
- Active branch: `feature/v020-visual-fidelity`.
- Visual-fidelity implementation: `2c7ff34`.
- Mission-animation evidence gate: `804e2d7`.
- Patent-aware architecture gate: `1a319a1`.
- Portable host-runtime overlay: `b7fb670`.
- On 2026-08-12, all 40 repository tests passed.
- On 2026-08-12, distribution validation and `git diff --check` passed.
- Third-party source locks are unchanged from 0.1.0.

Version 0.2.0 now requires:

- deterministic topology and pose plus an exact visual manifest for generated robot renders;
- one hashed trajectory and physics/contact trace plus a valid mission manifest for task animation;
- official-source claim-element mapping, positive architecture constraints, drift tests, and a qualified-counsel boundary for patent-aware design;
- generated host overlays for machine paths instead of tracked host-specific source edits.

## Active Work

The portable recovery implementation is complete on the feature branch. It still requires a fresh real network installation, official validation of all ten installed skills, independent code review, pull-request CI, merge, and public `v0.2.0` release.

## Run

Preview the portable installation:

```powershell
python scripts/install.py --dry-run
```

Preview an installation with a generated host-runtime overlay:

```powershell
python scripts/install.py --dry-run --host-runtime-python /path/to/python3.12
```

## Validate

```powershell
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
```

Validate promoted communication artifacts with:

```powershell
python skills/robotics-design/scripts/validate_visual_manifest.py path/to/visual_manifest.json
python skills/robotics-design/scripts/validate_mission_animation_manifest.py path/to/mission_manifest.json
```

## Known Risks

- The visual manifest validates declared hashes, change categories, landmark equality, and review metadata; it does not perform automatic pixel-level landmark recognition.
- The mission manifest validates traceability and declared invariants; it does not independently recompute trajectory limits, collision, contacts, or loads from raw simulation data.
- Patent-aware controls are an engineering workflow, not a legal opinion or freedom-to-operate conclusion.
- A generated `host-runtime.md` intentionally contains local paths in the installed tree. It must never be committed or treated as public provenance.
- The suite still lacks a live ROS 2 Jazzy and Gazebo Harmonic regression environment on this Windows host.

## Upstream Drift

- `earthtojake/text-to-cad` is 29 commits ahead of the lock and has released 0.4.5. The change spans roughly 300 files and replaces `cadpy` with `cadgen`; treat it as a compatibility migration, not a commit bump.
- `dbwls99706/ros2-engineering-skills` is 6 commits ahead at 1.3.0. Its provenance, system-diagnostics, navigation actuation-onset, and end-to-end stop-path guidance should be audited in a focused update.
- `BaraaLazkani/ros2-sim-skill` remains at the locked head.

## Upgrade Roadmap

1. **Release 0.2.0:** finish real-install evidence, review, CI, release, and a controlled local refresh.
2. **ROS 2 provenance and safety:** update the ROS 2 skill to 1.3.0, preserve Codex frontmatter normalization, and add stop-path/provenance behavior tests.
3. **Executable system contract:** add a versioned project design-contract schema and cross-artifact validator for owned dimensions, frames, joint limits, masses, interfaces, and acceptance evidence.
4. **`cadgen` migration:** build a compatibility matrix for CAD, viewer, DXF, URDF, SDF, and SRDF workflows; migrate the isolated runtime only after real artifact parity passes.
5. **Simulation benchmark harness:** establish Linux ROS 2 Jazzy/Gazebo Harmonic CI or a reproducible remote runner with launch, TF, controller, contact, timeout, and fault-injection scenarios.
6. **Skill behavior evaluations:** add repeatable pressure cases that measure whether agents preserve artifact ownership, reject unsupported claims, repair upstream sources, and report skipped gates.

## Next Smallest Action

Run the real installation and official skill validators from the current feature head, then request independent code review before publishing the branch.

## Evidence

- `docs/superpowers/specs/2026-08-12-portable-workflow-recovery-design.md`
- `docs/superpowers/plans/2026-08-12-portable-workflow-recovery.md`
- `skills/robotics-design/references/visualization-contract.md`
- `skills/robotics-design/references/mission-animation-contract.md`
- `skills/robotics-design/references/patent-design-around.md`
- `tests/test_visual_manifest.py`
- `tests/test_mission_animation_manifest.py`
- `tests/test_robotics_design_behavior.py`
- `tests/test_install.py`
