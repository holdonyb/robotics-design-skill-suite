---
name: robotics-design
description: Use when designing or changing robot systems, mobile robots, manipulators, robot mechanisms, multi-concept exploration, parameter sweeps, robustness, repair, mission animation, patent-aware architecture, product or task renders, CAD or STEP geometry, URDF or xacro, SDF, SRDF, ROS 2, Gazebo, kinematics, dynamics, sensors, actuators, controls, simulation, commissioning, or robot work spanning multiple engineering layers.
---

# Robotics Design

## Overview

Route robot work through an evidence-gated system workflow. Produce a traceable chain from requirements and assumptions to owned artifacts, consumer checks, simulation evidence, and bounded hardware claims.

## Start Here

1. Recover project constraints, existing artifacts, target consumers, and validation commands.
2. Read `references/design-contract.md`; establish requirements, assumptions, quantity ownership, and acceptance evidence before interface-driving geometry or code.
3. Read `references/physical-plausibility-contract.md` before selecting components or claiming physical feasibility; create the machine-readable contract and run its analytical gate before simulation or training.
4. For multi-concept generation, optimization, a parameter sweep, robustness search, counterexample search, or repair, read `references/hypothesis-engine-contract.md`; run `scripts/generate_design_hypotheses.py` after the physical contract and before simulation.
5. For simulation admission, deterministic trace replay, calibration, or bounded training callbacks, read `references/simulation-evidence-contract.md`; run `scripts/validate_simulation_bundle.py` before making any simulated claim.
6. For a supplier review, engineering freeze, procurement package, controlled drawing, wiring/protection, hazard log, inspection plan, or planned hardware test card, run `scripts/validate_engineering_freeze.py`; its result never authorizes procurement or motion.
7. For real component bench evidence, validate raw local data, instrument calibration, and an approved recording card with `scripts/validate_bench_evidence.py`; absent raw evidence is never a measurement.
8. For a future controlled commissioning submission, validate only retained local records with `scripts/validate_commissioning_evidence.py`; it never authorizes procurement, energization, or motion.
9. For any generated product, task, concept, or marketing image of the robot, read `references/visualization-contract.md` before creating references or prompts.
10. For a task, product, or demonstration animation, read `references/mission-animation-contract.md` before creating trajectories, keyframes, renders, or video.
11. For patent study, design-around, freedom-to-operate screening, or competitor-inspired mechanisms, read `references/patent-design-around.md` before freezing topology or interfaces.
12. Load each required sub-skill from the router before editing its artifact.
13. Run the relevant gates in `references/validation-gates.md`.
14. Use `references/authority-map.md` for method selection, `references/runtime.md` for environment setup, and `references/source-lock.md` for supply-chain review.
15. If `references/host-runtime.md` exists, read it for this installation's runtime executable and destination; never copy those host values into project artifacts.

## Capability Router

| Work | Required sub-skill | Boundary |
|---|---|---|
| Requirements, architecture, budgets, tradeoffs, verification | `$robotics-design` | Maintain one design contract and verification matrix. |
| Multi-concept generation, parameter sweep, optimization, robustness, counterexample search, repair | `references/hypothesis-engine-contract.md`, then `$robotics-design` | Resolve finite overlays through the physical gate; publish bounded uncertainty, Pareto, and repair evidence before simulation. |
| Simulation admission, trace replay, calibration, bounded training | `references/simulation-evidence-contract.md`, then `$ros2-sim` when a live consumer is requested | Portable replay remains `simulated`; live ROS/Gazebo consumer evidence and hardware authorization are separate gates. |
| Supplier review, engineering freeze, controlled drawings, wiring, hazards, inspection, planned hardware cards | `$robotics-design` then `scripts/validate_engineering_freeze.py` | Hash-bound documents can support engineering review only; procurement and motion are always denied. |
| Component characterization, raw bench data, instrument calibration | `$robotics-design` then `scripts/validate_bench_evidence.py` | Only original hash-bound local measurements may claim `bench-tested`; validation never controls equipment. |
| Future commissioning records, protected power-up, restricted motion, stop/timeout traces | `$robotics-design` then `scripts/validate_commissioning_evidence.py` | Offline validation accepts only bounded local records; it never authorizes or controls hardware. |
| Parametric parts, assemblies, brackets, enclosures, STEP, collision geometry | `$cad` | CAD owns geometry and controlled datums. |
| Purchasable motors, servos, reducers, bearings, brakes, drivers, batteries, electronics | `references/physical-plausibility-contract.md`, then `$step-parts` and `$cad` | Bind exact parts to architecture responsibilities and verify ratings; otherwise retain an unpromoted engineering placeholder. |
| DXF profiles, panels, drawings, cut layouts | `$dxf`; also `$cad` when derived from 3D | Keep 2D output linked to owning geometry. |
| Visual review of STEP, URDF, SDF, SRDF, DXF, GLB, STL, 3MF | `$cad-viewer` | Return review evidence or report viewer failure. |
| Photorealistic, product, task, concept, or marketing robot renders | Deterministic CAD/URDF/SDF owner, then `$imagegen` when available | The deterministic model owns topology and pose; image generation may change appearance and environment only. |
| Mission, operation, assembly, docking, crawling, driving, or manipulation animation | Deterministic robot model and trajectory owner; `$sdf`/`$ros2-sim` when physics is claimed | One trajectory and contact-state trace must drive every robot frame; validate `scripts/validate_mission_animation_manifest.py` before promotion. |
| Patent study, competitor-inspired design, design-around, or FTO screening | `$deep-research`, then `$robotics-design` | Map live claim elements to explicit architecture constraints; preserve official sources and the qualified-counsel boundary. |
| Links, joints, frames, limits, inertials, meshes, xacro/URDF | `$urdf` | URDF owns physical robot structure. |
| Gazebo/libsdformat models, worlds, sensors, plugins, physics | `$sdf` | SDF owns simulation and world semantics. |
| MoveIt groups, end effectors, semantic poses, collision exclusions | `$srdf` | Start from the exact valid URDF; SRDF owns planning semantics. |
| ROS 2 packages, QoS, lifecycle, realtime, ros2_control, Nav2, MoveIt, perception | `$ros2-engineering-skills` | Run its validators manually in Codex. |
| ROS 2 Jazzy + Gazebo Harmonic integration | `$ros2-sim` plus artifact owners | Preflight the Linux environment before promising live simulation. |

If a required sub-skill is unavailable, name the missing capability and continue only with a bounded fallback. Never replace deterministic generators or validators with prose silently.

## System Workflow

1. Separate requirements into environment/hazards, envelope/workspace, payload/reach, motion/accuracy, duty cycle, power/thermal/compute, sensing/actuation, safety, interfaces, serviceability, and target versions.
2. Turn missing interface-driving numbers into numbered assumptions with confidence, affected artifacts, owner, validation method, deadline, and change trigger.
3. Assign one source of truth per quantity. Downstream mirrors must record their source and drift check.
4. Bind every declared actuator, power path, moving cable, and safety function to complete component records. A joint is not physically complete merely because it exists in URDF.
5. Run `python skills/robotics-design/scripts/validate_design_contract.py path/to/design-contract.json --report evidence.json`; preserve its evidence level, signed margins, and failure report.
6. When several concepts, sweeps, robustness cases, or repairs are requested, run the closed bounded hypothesis space and preserve its manifest receipt. Never rank a candidate that bypassed the physical contract.
7. Before a simulation or training claim, create a simulation-admission receipt, compile closed scenarios, bind traces to an external receipt, and recompute metrics on replay. Treat portable synthetic replay, live ROS/Gazebo consumer execution, calibration, and hardware measurements as different evidence levels.
8. Freeze envelopes, datums, support polygon, swept volumes, interfaces, and budgets before detail CAD.
9. Derive URDF frames and joints from controlled datums. Add SDF and SRDF semantics only after upstream contracts and applicable analytical physical gates pass. Integrate ROS 2 against named, versioned interfaces.
10. When a communication render is required, pose the authoritative deterministic model, render visible joint/interface references, perform an appearance-only image-to-image pass, then validate its visual manifest before promotion.
11. When a mission animation is required, plan and validate one trajectory/contact trace, then render robot transforms directly from its accepted samples.
12. Validate syntax/schema, semantics, cross-artifact invariants, consumer loading, integrated simulation, then hardware. A generator, build, launch, or plausible-looking image alone is not proof of correctness.
13. Repair the owning artifact, regenerate explicit dependents, and rerun failed plus regression gates:

`spec -> model -> simulate/test -> collect trace -> diagnose earliest violated contract -> minimal repair -> rerun -> promote verified pattern`

## Hard Gates

- Never present assumed dimensions, inertias, limits, payloads, friction, or test evidence as measured fact.
- Never promote a declared actuator without explicitly bound motor, reducer, bearing, motor driver, interfaces, ratings, provenance, and load path. Simulation cannot supply a missing component.
- Never begin nominal simulation or training promotion while an applicable analytical physical gate is failed or indeterminate. Fault-injection runs must preserve the upstream failure.
- Never turn simulated, calibrated-simulation, or training output into a hardware claim. Training callbacks have no actuator interface; real motion still requires explicit human authorization and safety controls.
- Never rank a candidate that bypassed the physical contract. Hard uncertainty, incomplete objectives, failed ownership, or non-finite values block Pareto eligibility; analytical screening remains separate from promotion.
- Never claim certification, functional safety, human-safe operation, braking, endurance, payload, or stability without the required analysis and physical evidence.
- Navigation lidar and depth cameras are not protective safety devices unless the exact components and architecture are certified for that role.
- Never ask a generative model to articulate, repose, unfold, or reconfigure a robot. Change the pose in CAD, URDF, SDF, or an equivalent deterministic source and render a new reference.
- Never promote a generated robot image unless its required and observed joint/interface landmark sets match exactly and its visual manifest passes. A disclaimer does not make a structurally wrong robot image acceptable.
- Never keyframe robot joint poses by hand for mission evidence. Camera and lighting may be authored separately, but robot transforms must come from the accepted trajectory and contact-state trace.
- Never claim that a cosmetic change, renamed joint, reordered drawing, or single omitted feature avoids a patent. Record claim elements, equivalents risk, status uncertainty, and architecture constraints; reserve FTO conclusions for qualified counsel.
- Before real robot motion, require explicit authorization, a bounded test area, reachable emergency stop, power/torque/speed limits, observer roles, command timeout, and staged commissioning. Simulation never authorizes hardware motion.
- Preserve failed reports and traces. An unresolved failed gate is an open risk.

## Completion Contract

Report artifacts and owners, assumptions, component/load-path completeness, exact validation evidence, evidence level, signed analytical margins, the physical failure report, drift checks, skipped gates, remaining risks, visual manifest status when renders are included, mission-animation manifest status and trajectory identity when motion is included, patent claim-map status and legal-review boundary when patent constraints affected architecture, and the boundary between assumed, generated, parsed, calculated, simulated, bench-tested, integrated-hardware-tested, task-validated, and certified claims.
