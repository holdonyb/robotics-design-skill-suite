# Project Status

## Purpose

This repository distributes an evidence-gated robotics-design skill suite. It
owns the integration contract, physical-assurance runtime, reference robot,
tests, and transactional installer while locking third-party CAD, robot
description, ROS 2, and simulation skills to audited commits.

## Live State

- Public release: `v0.3.0`, annotated tag and GitHub Release at merged `main`
  commit `a728e29`.
- v0.3 pull request: `#2`, merged after Ubuntu/Windows × Python 3.11/3.12
  checks passed.
- v1 architecture and autonomy boundary: `0e03e58`.
- v0.3 implementation plan: `f0ca0a0`, with portable command fix `ccc1697`.
- Physical-assurance implementation: `b975a3e` through `501fbd5`.
- Local-delta classification: `b2c5b95`; no active installed skill was
  overwritten during classification or implementation.
- Third-party source locks remain unchanged from `v0.2.0`.

## v0.3 Released Capability

The release adds a closed schema-v1 design contract and deterministic
physical evidence report with:

- explicit SI-normalized quantities, single ownership, evidence source and
  level, hash binding, quantity-to-evidence support edges, and plug-in-specific
  expected dimensions for flat and nested analysis inputs;
- architecture-derived component roles and exact responsibility bindings for
  separate left/right drive units, battery power, every arm actuator, moving
  cables, and a holding-brake function, including driven-wheel cardinality;
- verified-part identity requirements and fail-closed handling for missing or
  claim-driving `engineering_placeholder` components, with URL/date/hash-bound
  parsed `component_catalog_v1` source snapshots, non-empty claim edges, and
  closed role-specific component limits;
- safe URDF observations for mass, joint semantics/limits, and transmissions,
  bounded declared-JSON observations for other exporters, plus owned-value
  drift, checkout-stable hashes, and stale-artifact detection;
- conservative `drivetrain_v1`, `battery_v1`, `stability_v1`,
  `arm_gravity_v1`, and `thermal_duty_v1` analytical plug-ins with required
  reciprocal architecture/requirement coverage, exact rating ownership,
  exact rating-to-component-limit equality, strict plug-in scope types,
  per-drive/per-actuator thermal coverage, finite derived outputs, explicit
  downhill braking noncoverage, and worst-direction static-slope projection;
- deterministic JSON reporting and CLI exit codes: `0` promotable, `1`
  physical failure/indeterminate, `2` invalid invocation or contract;
- a differential-drive plus six-axis-arm reference fixture with 32 critical
  fault mutations, including slope-induced support-boundary violation.

The reference candidate intentionally remains unpromoted. All 49 component
records are engineering placeholders supporting the physical requirement. Its
13 analysis instances across five plug-in families use separate left/right
drive ratings, six per-joint motor/brake paths, and eight motor-specific thermal
checks. Successful calculations mean only that the declared regression
assumptions satisfy the implemented conservative equations.

## Latest Verified Evidence

On 2026-08-13, at implementation commit `501fbd5` and merged release commit
`a728e29`:

- Python 3.11 full repository suite: 132/132 passed;
- bundled Python 3.12.13 full repository suite: 132/132 passed;
- `scripts/validate.py`: 10 skills and 3 pinned sources valid;
- `scripts/install.py --dry-run`: complete 10-skill plan with no writes;
- reference physical CLI: exit `1` as designed, report emitted, only
  `BOM.PLACEHOLDER_BLOCKS_CLAIM` diagnostics;
- `git diff --check`: clean;
- a clean Windows checkout with `core.autocrlf=true` retained LF bytes for
  hash-bound URDF/JSON evidence, produced the expected reference CLI result,
  and passed the complete reference-robot tests;
- fresh pinned-source network install artifact: 10 skills installed into a new
  ignored destination with a generated Python 3.12 host overlay and the exact
  `units.py` hash from `501fbd5`;
- official skill validator using UTF-8 mode: 10/10 installed skills valid;
- fresh install retained 9/9 upstream-license copies and contained zero
  `__pycache__`, `.pyc`, `.pyo`, or transaction-residue paths.
- pull-request and annotated-tag CI each passed all four Ubuntu/Windows ×
  Python 3.11/3.12 jobs;
- annotated tag `v0.3.0` resolves to `a728e29`, and the public tag
  `manifest.json` blob matches the local tag blob exactly;
- GitHub Release `v0.3.0` is public, non-draft, and non-prerelease;
- the active local `robotics-design` skill was refreshed from the verified
  release staging artifact; its validator and core hash check passed. The prior
  skill remains in ignored reversible backup storage.

Independent adversarial reviews exposed vacuous analysis coverage,
cross-responsibility rating reuse, missing per-motor thermal coverage, and
forgeable verified-part provenance, oversized numeric inputs, and open nested
catalog fields and open typed quantity objects; commits through `501fbd5`
remediate those findings with
semantic catalog parsing, exact limit binding, bounded integers, and recursive
closed schemas. Final independent adversarial review of `833b0b9` found no
Critical, Important, or Minor issues and returned Ready to merge: Yes.

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
report with all 13 analysis instances passing.

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

Start v0.4 in an isolated branch: implement bounded design hypotheses,
parameter/uncertainty sets, deterministic expansion and pruning, counterexample
search, repair traces, and reproducible evidence bundles on top of the v0.3
physical gate.

## Durable Design Sources

- `docs/superpowers/specs/2026-08-13-trustworthy-autonomous-robot-design-v1-design.md`
- `docs/superpowers/plans/2026-08-13-v03-physical-plausibility-kernel.md`
- `skills/robotics-design/references/physical-plausibility-contract.md`
- `skills/robotics-design/scripts/assurance/schema.md`
- `reference/mobile-manipulator/README.md`
