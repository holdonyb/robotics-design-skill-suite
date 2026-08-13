# Project Status

## Purpose

This repository distributes an evidence-gated robotics-design skill suite. It
owns the integration contract, physical-assurance runtime, reference robot,
tests, and transactional installer while locking third-party CAD, robot
description, ROS 2, and simulation skills to audited commits.

## Live State

- Public release: `v0.2.0` on `main` at `d41de54`.
- Active release-candidate branch: `feature/v030-physical-plausibility`.
- Candidate manifest version: `0.3.0`; it is not a public release until review,
  CI, merge, tag, and GitHub Release complete.
- v1 architecture and autonomy boundary: `0e03e58`.
- v0.3 implementation plan: `f0ca0a0`, with portable command fix `ccc1697`.
- Physical-assurance implementation: `b975a3e` through `aaf8f6b`.
- Local-delta classification: `b2c5b95`; no active installed skill was
  overwritten during classification or implementation.
- Third-party source locks remain unchanged from `v0.2.0`.

## v0.3 Candidate Capability

The candidate adds a closed schema-v1 design contract and deterministic
physical evidence report with:

- explicit SI-normalized quantities, single ownership, evidence source and
  level, hash binding, and quantity-to-evidence support edges;
- architecture-derived component roles and exact responsibility bindings for
  differential drive, battery power, every arm actuator, moving cables, and a
  holding-brake function;
- verified-part identity requirements and fail-closed handling for missing or
  claim-driving `engineering_placeholder` components;
- safe URDF observations for mass, joint semantics/limits, and transmissions,
  plus owned-value drift and stale-artifact detection;
- conservative `drivetrain_v1`, `battery_v1`, `stability_v1`,
  `arm_gravity_v1`, and `thermal_duty_v1` analytical plug-ins;
- deterministic JSON reporting and CLI exit codes: `0` promotable, `1`
  physical failure/indeterminate, `2` invalid invocation or contract;
- a differential-drive plus six-axis-arm reference fixture with 32 critical
  fault mutations, including slope-induced support-boundary violation.

The reference candidate intentionally remains unpromoted. All 39 component
records are engineering placeholders supporting the physical requirement; its
successful calculations mean only that the declared regression assumptions
satisfy the implemented conservative equations.

## Latest Verified Evidence

On 2026-08-13, at release-candidate commit `b411b2d`:

- Python 3.11 full repository suite: 103/103 passed;
- Python 3.12.12 full repository suite: 103/103 passed;
- focused routing and public-hygiene suite: 18/18 passed;
- `scripts/validate.py`: 10 skills and 3 pinned sources valid;
- `scripts/install.py --dry-run`: complete 10-skill plan with no writes;
- reference physical CLI: exit `1` as designed, report emitted, only
  `BOM.PLACEHOLDER_BLOCKS_CLAIM` diagnostics;
- `git diff --check`: clean.
- fresh pinned-source network install: 10 skills installed into a new ignored
  destination with a generated Python 3.12 host overlay;
- official skill validator using UTF-8 mode: 10/10 installed skills valid;
- fresh install retained 9/9 upstream-license copies and contained zero
  `__pycache__`, `.pyc`, `.pyo`, or transaction-residue paths.

Independent adversarial review, GitHub CI, merge, tag, and release evidence are
still pending and must not be reported as complete.

## Run and Validate

```powershell
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
python skills/robotics-design/scripts/validate_design_contract.py reference/mobile-manipulator/design-contract.json --report evidence.json
```

The final command is expected to exit `1` because the reference uses
claim-driving placeholders. It must still produce a deterministic evidence
report with all five analyses passing.

## Claim Boundary and Open Engineering Risks

- Scalar drivetrain efficiency and operating-point torque checks do not
  replace motor curves, traction, braking, gearbox life, or transient dynamics.
- Battery current/runtime checks do not cover cell sag, aging, balancing,
  regenerative acceptance, cable drop, fault energy, or protection clearing.
- Rectangular static support margin does not prove dynamic stability.
- Arm gravity and brake checks do not cover full inverse dynamics, reflected
  inertia, impacts, fatigue, bearing life, or structural deflection.
- The thermal plug-in is a steady-state winding screen, not a transient thermal
  network or bench correlation.
- Structural strength, collision/contact fidelity, workspace, braking,
  controllability, manufacturability, reliability, human safety, and
  certification remain unverified.
- The Windows host has no live ROS 2 Jazzy/Gazebo Harmonic regression
  environment. Simulation claims require a suitable Linux runner.
- No real robot motion is authorized by this candidate. Hardware work requires
  the exact hardware and site, bounded energy, reachable emergency stop,
  qualified operators, explicit motion authorization, and retained raw data.

## Roadmap

1. Finish v0.3 dual-version verification, fresh install, adversarial review,
   CI, release, and controlled local-skill refresh.
2. v0.4: generate bounded design hypotheses, parameter sweeps, uncertainty
   sets, dominance/pruning rules, counterexample search, and repair traces.
3. v0.5: connect accepted candidates to CAD/URDF/SDF/SRDF/ROS 2 consumers,
   Linux Gazebo/MoveIt scenario regression, training backends, calibration,
   domain randomization, and reproducible evidence bundles.
4. v0.6-v0.9: add motor/gearbox curves, braking/traction, dynamic stability,
   structure/fatigue, transient thermal/electrical models, collision/workspace,
   control and safety fault injection, bench plans, and system identification.
5. v1.0: demonstrate the complete requirement-to-hypothesis-to-analysis-to-
   simulation/training-to-bounded-hardware evidence chain on the reference
   mobile manipulator. Real-hardware claims remain dependent on approved parts,
   site, operators, and safe test authority.

## Next Action

Run the fresh Python 3.11/3.12 matrix and network installation, then request an
independent adversarial review against `v0.2.0`. Resolve all Critical and
Important findings before publishing the v0.3 pull request.

## Durable Design Sources

- `docs/superpowers/specs/2026-08-13-trustworthy-autonomous-robot-design-v1-design.md`
- `docs/superpowers/plans/2026-08-13-v03-physical-plausibility-kernel.md`
- `skills/robotics-design/references/physical-plausibility-contract.md`
- `skills/robotics-design/scripts/assurance/schema.md`
- `reference/mobile-manipulator/README.md`
