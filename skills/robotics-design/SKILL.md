---
name: robotics-design
description: Use when designing or changing robot systems, mobile robots, manipulators, robot mechanisms, CAD or STEP geometry, URDF or xacro, SDF, SRDF, ROS 2, Gazebo, kinematics, dynamics, sensors, actuators, controls, simulation, commissioning, or robot work spanning multiple engineering layers.
---

# Robotics Design

## Overview

Route robot work through an evidence-gated system workflow. Produce a traceable chain from requirements and assumptions to owned artifacts, consumer checks, simulation evidence, and bounded hardware claims.

## Start Here

1. Recover project constraints, existing artifacts, target consumers, and validation commands.
2. Read `references/design-contract.md`; establish requirements, assumptions, quantity ownership, and acceptance evidence before interface-driving geometry or code.
3. Load each required sub-skill from the router before editing its artifact.
4. Run the relevant gates in `references/validation-gates.md`.
5. Use `references/authority-map.md` for method selection, `references/runtime.md` for environment setup, and `references/source-lock.md` for supply-chain review.

## Capability Router

| Work | Required sub-skill | Boundary |
|---|---|---|
| Requirements, architecture, budgets, tradeoffs, verification | `$robotics-design` | Maintain one design contract and verification matrix. |
| Parametric parts, assemblies, brackets, enclosures, STEP, collision geometry | `$cad` | CAD owns geometry and controlled datums. |
| Purchasable motors, servos, bearings, fasteners, electronics | `$step-parts`, then `$cad` | Record exact identity and source; otherwise use a documented envelope. |
| DXF profiles, panels, drawings, cut layouts | `$dxf`; also `$cad` when derived from 3D | Keep 2D output linked to owning geometry. |
| Visual review of STEP, URDF, SDF, SRDF, DXF, GLB, STL, 3MF | `$cad-viewer` | Return review evidence or report viewer failure. |
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
6. Validate syntax/schema, semantics, cross-artifact invariants, consumer loading, integrated simulation, then hardware. A generator, build, or launch alone is not proof of correctness.
7. Repair the owning artifact, regenerate explicit dependents, and rerun failed plus regression gates:

`spec -> model -> simulate/test -> collect trace -> diagnose earliest violated contract -> minimal repair -> rerun -> promote verified pattern`

## Hard Gates

- Never present assumed dimensions, inertias, limits, payloads, friction, or test evidence as measured fact.
- Never claim certification, functional safety, human-safe operation, braking, endurance, payload, or stability without the required analysis and physical evidence.
- Navigation lidar and depth cameras are not protective safety devices unless the exact components and architecture are certified for that role.
- Before real robot motion, require explicit authorization, a bounded test area, reachable emergency stop, power/torque/speed limits, observer roles, command timeout, and staged commissioning. Simulation never authorizes hardware motion.
- Preserve failed reports and traces. An unresolved failed gate is an open risk.

## Completion Contract

Report artifacts and owners, assumptions, exact validation evidence, drift checks, skipped gates, remaining risks, and the boundary between generated, parsed, consumer-loaded, simulated, bench-measured, field-verified, and certified claims.
