# Robot Mission Animation Contract

Use this contract for any video or interactive sequence that claims to show the designed robot executing a real task.

## Single-source rule

CAD/URDF/SDF or an equivalent deterministic multibody model owns topology. One versioned trajectory owns robot pose over time. A physics/contact trace owns contact state and calculated loads. The renderer consumes these artifacts without solving or rewriting motion.

**Never keyframe robot joint poses by hand.** Camera, exposure and lighting may be authored independently. If a robot pose is wrong, repair the model, planner, controller or trajectory and regenerate the animation.

## Required task definition

For every shot, define:

- mission objective, initial and terminal state;
- named task phases and transition guards;
- active base/root frame and contact state for every gripper, foot, wheel, tool and fixture;
- commanded joint order, axes, limits and exact trajectory sampling rate;
- payload, gravity, external wrench, friction/contact assumptions and load-case IDs;
- collision pairs, clearance limits, speed/acceleration/jerk/torque limits and abort conditions;
- expected moving joints. For a seven-axis inchworm transfer, include J4 whenever the planned geometry requires central elbow motion; a visually static J4 cannot pass by implication;
- camera plan separated from robot-state generation.

## Motion pipeline

1. Validate topology, frames, root reversal and interface identity.
2. Plan or prescribe the path in joint/configuration space with task constraints.
3. Time-parameterize within position, velocity, acceleration, jerk and actuator limits.
4. Simulate or calculate contacts, controller tracking and loads at the evidence level claimed.
5. Reject any frame with limit, collision, contact-state, anchoring or load-case violations.
6. Export one immutable trajectory and trace. Hash both.
7. Drive CAD/GLB/renderer transforms directly from the accepted samples. Do not recreate the motion in the render tool.
8. Render engineering review views first: fixed camera, visible joints/interfaces, axes/contact overlays and frame/time labels.
9. Render cinematic views only after the engineering cut passes. Image generation may create appearance plates or non-contact environment elements; it may not generate or interpolate robot motion.
10. Validate `scripts/validate_mission_animation_manifest.py` before promotion.

## Inchworm safety invariants

- At least one end is `hard_lock` whenever the robot is not externally restrained.
- The releasing end cannot unload until the receiving end has mechanical lock confirmation and the modeled load transfer is complete.
- Electrical source selection is not proof of mechanical anchoring.
- Root switching changes kinematic/control semantics without teleporting world poses.
- Dual-anchor phases solve closed-chain consistency and interface reactions; they are not two independent fixed-base arms.

## Review views and acceptance

Provide a fixed wide shot, one joint/axis diagnostic view, one interface/contact close-up and the final cinematic cut. Compare joint positions sampled from the animation against the trajectory numerically, not by eye. Report maximum pose deviation, joint/velocity/torque margins, minimum clearance, contact transitions, constraint residuals, dropped frames and any visual post-processing.

An MP4 proves that frames were rendered. It does not prove dynamics, structural margins, contact fidelity, controllability, environmental qualification or flight readiness unless the corresponding trace and higher-level evidence exist.

## Manifest minimum

The manifest records hashes for the source model, trajectory, physics trace and rendered animation; canonical joint order; required and observed moving joints; task phases with contact state and load-case IDs; zero-count topology, limit, collision and unconstrained-dual-release violations; physics-trace disposition; and independent review notes.
