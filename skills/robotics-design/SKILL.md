---
name: robotics-design
description: Use when designing or changing robot systems, mobile robots, manipulators, robot mechanisms, mission animation, patent-aware architecture, product or task renders, CAD or STEP geometry, URDF or xacro, SDF, SRDF, ROS 2, Gazebo, kinematics, dynamics, sensors, actuators, controls, simulation, commissioning, or robot work spanning multiple engineering layers.
---

# Robotics Design

## Overview

Route robot work through an evidence-gated system workflow. Produce a traceable chain from requirements and assumptions to owned artifacts, consumer checks, simulation evidence, and bounded hardware claims.

## Start Here

1. Recover project constraints, existing artifacts, target consumers, and validation commands.
2. Read `references/design-contract.md`; establish requirements, assumptions, quantity ownership, and acceptance evidence before interface-driving geometry or code.
3. For any generated product, task, concept, or marketing image of the robot, read `references/visualization-contract.md` before creating references or prompts.
4. For a task, product, or demonstration animation, read `references/mission-animation-contract.md` before creating trajectories, keyframes, renders, or video.
5. For patent study, design-around, freedom-to-operate screening, or competitor-inspired mechanisms, read `references/patent-design-around.md` before freezing topology or interfaces.
6. Load each required sub-skill from the router before editing its artifact.
7. Run the relevant gates in `references/validation-gates.md`.
8. Use `references/authority-map.md` for method selection, `references/runtime.md` for environment setup, and `references/source-lock.md` for supply-chain review.

## Capability Router

| Work | Required sub-skill | Boundary |
|---|---|---|
| Requirements, architecture, budgets, tradeoffs, verification | `$robotics-design` | Maintain one design contract and verification matrix. |
| Parametric parts, assemblies, brackets, enclosures, STEP, collision geometry | `$cad` | CAD owns geometry and controlled datums. |
| Purchasable motors, servos, bearings, fasteners, electronics | `$step-parts`, then `$cad` | Record exact identity and source; otherwise use a documented envelope. |
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
4. Freeze envelopes, datums, support polygon, swept volumes, interfaces, and budgets before detail CAD.
5. Derive URDF frames and joints from controlled datums. Add SDF and SRDF semantics only after upstream contracts exist. Integrate ROS 2 against named, versioned interfaces.
6. When a communication render is required, pose the authoritative deterministic model, render visible joint/interface references, perform an appearance-only image-to-image pass, then validate its visual manifest before promotion.
7. When a mission animation is required, plan and validate one trajectory/contact trace, then render robot transforms directly from its accepted samples.
8. Validate syntax/schema, semantics, cross-artifact invariants, consumer loading, integrated simulation, then hardware. A generator, build, launch, or plausible-looking image alone is not proof of correctness.
9. Repair the owning artifact, regenerate explicit dependents, and rerun failed plus regression gates:

`spec -> model -> simulate/test -> collect trace -> diagnose earliest violated contract -> minimal repair -> rerun -> promote verified pattern`

## Hard Gates

- Never present assumed dimensions, inertias, limits, payloads, friction, or test evidence as measured fact.
- Never claim certification, functional safety, human-safe operation, braking, endurance, payload, or stability without the required analysis and physical evidence.
- Navigation lidar and depth cameras are not protective safety devices unless the exact components and architecture are certified for that role.
- Never ask a generative model to articulate, repose, unfold, or reconfigure a robot. Change the pose in CAD, URDF, SDF, or an equivalent deterministic source and render a new reference.
- Never promote a generated robot image unless its required and observed joint/interface landmark sets match exactly and its visual manifest passes. A disclaimer does not make a structurally wrong robot image acceptable.
- Never keyframe robot joint poses by hand for mission evidence. Camera and lighting may be authored separately, but robot transforms must come from the accepted trajectory and contact-state trace.
- Never claim that a cosmetic change, renamed joint, reordered drawing, or single omitted feature avoids a patent. Record claim elements, equivalents risk, status uncertainty, and architecture constraints; reserve FTO conclusions for qualified counsel.
- Before real robot motion, require explicit authorization, a bounded test area, reachable emergency stop, power/torque/speed limits, observer roles, command timeout, and staged commissioning. Simulation never authorizes hardware motion.
- Preserve failed reports and traces. An unresolved failed gate is an open risk.

## Completion Contract

Report artifacts and owners, assumptions, exact validation evidence, drift checks, skipped gates, remaining risks, visual manifest status when renders are included, mission-animation manifest status and trajectory identity when motion is included, patent claim-map status and legal-review boundary when patent constraints affected architecture, and the boundary between generated, parsed, consumer-loaded, simulated, bench-measured, field-verified, and certified claims.
