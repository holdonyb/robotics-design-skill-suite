# Robotics Design Skill Suite

[简体中文](README.zh-CN.md)

An evidence-gated robotics design skill suite for Codex. It routes system design across CAD, STEP parts, DXF, URDF, SDF, SRDF, ROS 2 engineering, Gazebo simulation, structure-preserving visualization, traceable mission animation, patent-aware architecture, visual review, and validation.

This repository is a thin, auditable distribution. It owns the integration skill and installer; third-party skills are downloaded from full pinned commits in [`manifest.json`](manifest.json), not copied into this repository.

## Included skills

| Layer | Skills |
|---|---|
| System routing | `robotics-design` |
| Mechanical artifacts | `cad`, `step-parts`, `dxf`, `cad-viewer` |
| Robot descriptions | `urdf`, `sdf`, `srdf` |
| Software and simulation | `ros2-engineering-skills`, `ros2-sim` |

## Install

Requirements: Git and Python 3.11+.

```bash
git clone https://github.com/holdonyb/robotics-design-skill-suite.git
cd robotics-design-skill-suite
python scripts/install.py --dry-run
python scripts/install.py
```

The default destination is `${CODEX_HOME}/skills` when `CODEX_HOME` is set, otherwise `~/.codex/skills`. Override it explicitly when needed:

```bash
python scripts/install.py --dest /path/to/codex/skills
```

To generate a machine-local runtime overlay without putting host paths in the public skill, pass an existing Python executable:

```bash
python scripts/install.py --host-runtime-python /path/to/python3.12
```

This creates `references/host-runtime.md` only in the staged installation. The repository's runtime and source-lock documents remain portable.

The installer refuses to overwrite existing skill directories. Review or move old installations first. Start a new Codex task after installation so skill discovery refreshes.

## Use

```text
$robotics-design Design an indoor mobile manipulator from requirements through CAD, URDF, SDF, ROS 2, simulation, and validation.
```

You can also invoke an artifact owner directly:

```text
$urdf Review this robot description for frame, axis, limit, inertia, and consumer-load errors.
$sdf Build a Gazebo Harmonic world and identify every validation gate that was not run.
```

## Physical plausibility gate

Version 0.3.0 adds a closed, machine-readable design contract before nominal
simulation or training. It binds explicit-unit quantities to evidence, binds
components to explicit left/right drive and per-joint responsibilities, closes
each plug-in input to an expected physical dimension, checks artifact hashes,
owned URDF observations, and bounded declared-JSON observations, and emits deterministic diagnostics and signed
margins for drivetrain, battery/runtime, static stability, arm gravity/brake
holding, and conservative steady-state winding thermal duty.

```bash
python skills/robotics-design/scripts/validate_design_contract.py path/to/design-contract.json --report evidence.json
```

Exit `0` means only that the declared contract passes the implemented
analytical screens at its recorded evidence levels. Missing or placeholder
parts, stale evidence, invalid units, incomplete actuator/load paths, and
missing architecture-derived analysis coverage, failed or indeterminate analyses block promotion. Simulation cannot replace a
missing motor, reducer, bearing, driver, brake, power-protection element, or
unsupported continuous/thermal rating.

[`reference/mobile-manipulator`](reference/mobile-manipulator) is a
differential-drive plus six-axis-arm regression fixture with 35 critical fault
mutations. Most component ratings are engineering assumptions, not a build or
purchasing recommendation; its J2 bearing and reducer are hash-bound parsed
catalog candidates, not validated assemblies. Static arm load demand is also
screened back through declared motor/reducer transmissions, while motor curves,
life, and transient dynamics remain separate evidence gates. It intentionally remains
unpromoted until exact parts and stronger evidence replace every claim-driving
placeholder. See the
full [`physical-plausibility-contract.md`](skills/robotics-design/references/physical-plausibility-contract.md).

## Bounded design hypotheses

Version 0.4 adds deterministic finite design spaces, hard uncertainty and
counterexample search, visible Pareto fronts, owner-correct repair lineage, and
transactional evidence bundles. Every canonical resolved candidate runs through
the v0.3 contract and physical gate; content aliases share that exact evidence.
Candidate and stage budgets are hard limits.

```bash
python skills/robotics-design/scripts/generate_design_hypotheses.py reference/mobile-manipulator/hypothesis-space.json --out ../v040-reference --seed 20260813
```

Exit `0` means at least one candidate is accepted, `1` means the bounded run
completed with none accepted, and `2` means invalid input or a fail-closed
execution/publication error. Preserve the printed `manifest_sha256` outside the
bundle. `pareto.json` is promotion-scoped; `screening-pareto.json` is an
explicitly non-promoting comparison for analytically passing placeholder-only
candidates. This calculated evidence does not prove simulation or hardware performance.
See [`hypothesis-engine-contract.md`](skills/robotics-design/references/hypothesis-engine-contract.md)
and the public [`hypothesis benchmark`](reference/mobile-manipulator/hypothesis-benchmark.md).

## Simulation, replay, and training boundary

Version 0.5 adds a closed simulation-admission receipt, ten deterministic
reference scenarios, canonical trace bundles with external receipts,
separate trace-primary and independent planar-dynamics cross-check, bounded calibration, and a
simulation-only policy callback boundary.

```bash
python skills/robotics-design/scripts/validate_simulation_bundle.py \
  --reference-root reference/mobile-manipulator
```

Exit `0` is a valid portable synthetic replay with every scenario passing; `1`
is a valid benchmark containing a failed or indeterminate scenario; `2` is
invalid/tampered input or a fail-closed execution error. The result is not a
live Gazebo run and does not authorize hardware promotion. The separate
Linux Jazzy/Harmonic workflow is the consumer-load gate for Gazebo,
ros2_control, MoveIt, and Nav2; it retains logs and package inventory even on
failure. The v0.5 candidate passed two retained consumer-gate runs at
`ced7dc3`; this is integration evidence only, not hardware promotion. See the
[`simulation benchmark`](reference/mobile-manipulator/simulation-benchmark.md).

## Engineering-freeze boundary

The v0.6 engineering-freeze gate records hash-bound supplier snapshots,
controlled-artifact references, hazards, safety-function links, verification
items, inspection items, and planned hardware test cards. It is an input to a
future engineering review, never a purchase, fabrication, energization, or
motion authorization.

```bash
python skills/robotics-design/scripts/validate_engineering_freeze.py \
  --package reference/mobile-manipulator/engineering-freeze/freeze-package.json
```

Exit `0` means a complete review package; `1` means valid input with open
engineering gaps; `2` means malformed or tampered input. Both
`procurement_authorized` and `motion_authorized` are always `false`. The
reference package intentionally exits `1` because it has no selected supplier
parts, controlled drawings, or authorized hardware test conditions.

## Raw bench-evidence intake

v0.7 accepts future component measurements only when they include an original
local CSV, hash, exact units/columns and timestamps, instrument-calibration
snapshot, approved recording card, site/operator metadata, and explicit
component/claim edges.

```bash
python skills/robotics-design/scripts/validate_bench_evidence.py \
  --index reference/mobile-manipulator/bench-evidence/intake-index.json
```

The empty reference index exits `1` with `awaiting_authorization`; it is not a
bench result. Validation has no device interface and never authorizes
purchasing, energization, or motion.

## Commissioning-evidence intake

v1.1 strengthens future controlled low-energy commissioning submissions. A
populated package must bind the design contract, engineering-freeze package,
bench intake, ordered commissioning stages, bounded command/state/stop traces,
post-test inspection records, and an `external_human_attestation` record
covering the exact design, phase, date, site, area, reachable emergency stop,
roles, limits, and watchdog timeout.

```bash
python skills/robotics-design/scripts/validate_commissioning_evidence.py \
  --index reference/mobile-manipulator/commissioning/commissioning-index.json
```

The shipped reference index has no records and exits `1` with
`awaiting_authorization`. The validator never connects to or controls a device;
even a complete local submission leaves procurement and motion authorization
false and is not an integrated-hardware-tested claim.

The attestation is retained evidence, not a local permission source: it never
authorizes procurement, energization, or robot motion. Actual action still
requires the responsible people, controlled site, and emergency-stop decision
at execution time. See
[`hardware-authority-contract.md`](skills/robotics-design/references/hardware-authority-contract.md).

## Task and robustness evidence intake

Published v0.9 accepts future hash-bound task, fault, endurance, and
simulation-to-observation dossiers only after re-running the contract, freeze,
bench, and commissioning gates. It derives metric summaries, fault
dispositions, and residual summaries locally; it never marks a task validated.

```bash
python skills/robotics-design/scripts/validate_task_evidence.py \
  --index reference/mobile-manipulator/task-evidence/task-evidence-index.json
```

The shipped reference index is intentionally empty and exits `1` with
`awaiting_authorization`. Local evidence validation never authorizes
procurement, energization, motion, or an empirical task-performance claim.

## v1.1 reproducible public delivery

Version 1.1 binds the expanded public software and evidence surface to a
canonical release contract while retaining the published v1.0 contract for
historical verification. Verify the current delivery and intentionally empty
reference hardware intakes with:

```bash
python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1.1-release-contract.json
```

This command verifies public software and evidence delivery; it does not
validate physical robot performance or authorize hardware.

## Structure-preserving robot renders

Version 0.2.0 prevents image generation from silently changing a robot's mechanism. CAD, URDF, SDF, or an equivalent deterministic model must own topology and pose. A generated image may change materials, surface finish, color, lighting, background, and non-contact environment context only.

Set the exact task pose upstream, render deterministic references with visible joint and interface landmarks, then use image-to-image for the appearance pass. A render is promotable only when its source hashes and exact landmark set pass the visual manifest gate:

```bash
python skills/robotics-design/scripts/validate_visual_manifest.py path/to/visual_manifest.json
```

See [`visualization-contract.md`](skills/robotics-design/references/visualization-contract.md) for the full contract. A plausible-looking image or disclaimer is not evidence that topology, axes, interfaces, or pose are correct.

## Traceable mission animation

Mission animation uses one deterministic model, one accepted trajectory, and one physics/contact trace. Robot joint transforms may not be hand-keyframed for engineering evidence. Every promoted animation records source hashes, canonical joint order, required moving joints, task phases, contact states, load cases, violation counts, and independent review evidence.

```bash
python skills/robotics-design/scripts/validate_mission_animation_manifest.py path/to/mission_manifest.json
```

See [`mission-animation-contract.md`](skills/robotics-design/references/mission-animation-contract.md). A rendered video proves frames exist; it does not by itself prove dynamics, contact fidelity, controllability, or hardware performance.

## Patent-aware architecture

Patent study and competitor-inspired design route through source research and an element-by-element claim chart before architecture is frozen. Selected distinctions become positive design requirements, prohibited combinations, owned artifacts, and drift tests. This is an engineering design-around screen, not a legal opinion or FTO conclusion; qualified counsel owns legal disposition.

See [`patent-design-around.md`](skills/robotics-design/references/patent-design-around.md) for the evidence hierarchy, claim-chart schema, review package, and counsel boundary.

## Optional CAD runtime

Installing skills does not mutate Python environments. CAD generation needs an isolated Python 3.12+ environment; DXF also needs `ezdxf`.

```bash
python3.12 -m venv .venv-robotics-design
.venv-robotics-design/bin/python -m pip install -e ~/.codex/skills/cad/scripts/packages/cadpy ezdxf
```

On Windows, use the environment's `Scripts/python.exe`. See [`runtime.md`](skills/robotics-design/references/runtime.md) for platform notes.

## Verification

```bash
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
```

Tests cover manifest integrity, pinned commits, transactional installation, host overlays, bytecode exclusion, license preservation, Codex frontmatter normalization, collision refusal, ZIP traversal protection, public-data hygiene, physical contract/schema/units/evidence/component bindings, deterministic analysis reports, bounded hypotheses, uncertainty/counterexamples, Pareto fronts, repair ownership, manifest-bound bundles, the reference benchmark, URDF drift, 35 critical physical faults, visual source hashes and landmark promotion, mission trajectory/contact traceability, and patent-aware routing boundaries.

## Claim boundary

This suite improves engineering workflow; it does not certify a robot or provide a legal opinion. Generated or simulated artifacts do not prove payload, stability, braking distance, endurance, field reliability, human-safe operation, or regulatory compliance. Patent-aware controls do not establish non-infringement or freedom to operate. Real robot motion requires explicit authorization, a bounded test area, reachable emergency stop, power/torque/speed limits, command timeouts, and staged commissioning.

ROS 2 live simulation requires a suitable Linux environment with ROS 2 Jazzy and Gazebo Harmonic. Always run the installed `ros2-sim/scripts/env_check.sh` before promising live results.

## Supply chain and licenses

Exact sources are locked in [`manifest.json`](manifest.json) and summarized in [`source-lock.md`](skills/robotics-design/references/source-lock.md). The installer downloads HTTPS archives at full commit hashes and places the upstream license in every installed third-party skill.

Original repository content is MIT licensed. Third-party components retain their own licenses; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md). Source updates require audit, tests, and updated provenance rather than changing a commit alone.
