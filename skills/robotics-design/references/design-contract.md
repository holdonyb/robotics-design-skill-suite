# Robot Design Contract

Create this contract in the target project before changing interface-driving geometry, descriptions, controls, or simulation semantics.

## Requirements

| ID | Requirement | Value/range | Source | Priority | Verification | Owner | Status |
|---|---|---|---|---|---|---|---|

Cover environment, hazards, envelope, payload/reach, motion, accuracy, duty cycle, power, thermal, compute, sensing, actuation, safety, interfaces, serviceability, manufacturing, cost, schedule, and target versions.

## Assumptions

| ID | Provisional value | Rationale | Confidence | Affected artifacts | Validation | Owner | Deadline | Change trigger |
|---|---|---|---|---|---|---|---|---|

Label assumptions in calculations and generated artifacts. A changed interface-driving assumption reopens dependent gates.

## Quantity ownership

| Quantity | Owner | Mirrored in | Convention | Drift check |
|---|---|---|---|---|
| Geometry, envelopes, datums | CAD source | URDF/SDF/meshes | mm in CAD, m in robot formats | bounds, datum transform, mesh scale |
| Topology, frames, joint axes/origins | URDF source | SRDF/SDF/controllers | REP conventions, radians | graph/name equality and TF assertions |
| Joint limits | URDF source | ros2_control/MoveIt/SDF | SI units | set equality or documented narrowing |
| Mass and inertia | declared project owner | URDF/SDF/control model | kg, kg m^2 | numeric comparison and plausibility |
| Planning semantics | SRDF source | MoveIt config | named semantics | MoveIt load and collision sampling |
| Simulator physics/sensors/plugins | SDF source | launch/bridge | versioned SDF | load, topic, frame, rate, plugin checks |
| Controller/hardware parameters | ROS config | launch/adapters | SI units, explicit rates | lifecycle and interface assertions |
| Communication-render topology and task pose | CAD/URDF/SDF deterministic source | reference renders and visual manifest | canonical joint names and exact joint values | source hashes and joint/interface landmark equality |
| Render appearance and environment | approved shot brief | image-generation prompt and output | allowed-change vocabulary | side-by-side review and manifest validation |
| Mission robot pose over time | accepted trajectory | renderer, animation, controller replay | canonical joint order and sample time | trajectory hash and sampled joint equality |
| Mission contact state and calculated loads | physics/contact trace | animation overlays and review report | named phases and load-case IDs | trace hash, transition, residual, and violation checks |

Never leave two co-equal sources of truth.

## Machine-readable physical contract

When the design includes physical motion, loads, power, heat, stability, or a
component choice, instantiate the closed JSON contract described in
`physical-plausibility-contract.md` and `../scripts/assurance/schema.md`.
Every quantity needs an explicit unit, owner, evidence source, and evidence
level. Every component needs an exact architecture binding; global BOM role
presence is insufficient for a multi-axis robot. Hash-bound observations link
owned values back to CAD/URDF/SDF/SRDF/ROS/BOM artifacts and expose drift.

Run the physical contract validator before promoting a candidate to simulation
or training. A failed or indeterminate result reopens dependent geometry,
component, control, simulation, and procurement decisions.

## Interface record

For each mechanical, electrical, data, safety, or software interface, record provider, consumer, datum/frame, connector/API, units, sign, rate, tolerances, limits, version, failure behavior, acceptance evidence, and change owner.

Every acceptance claim maps to a requirement ID, artifact version, command or procedure, captured evidence, and disposition. “Looks right,” “builds,” and “spawns” are observations, not acceptance criteria.

## Visual invariant record

Before generating a robot image, record the authoritative model and pose, required joint/interface landmarks, link proportions that must remain identifiable, interface/tool attachment state, allowed appearance changes, forbidden structural changes, source hashes, reviewer, and promotion state. A pose request changes the deterministic model first; it is never delegated to an image model.

## Mission animation invariant record

Before rendering robot task motion, record the authoritative model, immutable trajectory and physics/contact trace; canonical joint order; required moving joints; task phases and guards; contact states; load-case IDs; position, velocity, acceleration, jerk and torque limits; collision and clearance checks; source hashes; independent reviewer; and promotion state. The renderer samples the accepted trajectory and never owns robot joint motion.

## Patent-aware architecture constraints

When patent or competitor evidence affects the design, record the reviewed publication and family/status sources, claim-chart revision, literal and equivalents risks, selected distinguishing principles, positive design requirements, prohibited combinations, owned artifacts, drift tests, review territory, and qualified-counsel questions. A design change that touches one of these constraints reopens the claim chart and its dependent gates.
