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

Never leave two co-equal sources of truth.

## Interface record

For each mechanical, electrical, data, safety, or software interface, record provider, consumer, datum/frame, connector/API, units, sign, rate, tolerances, limits, version, failure behavior, acceptance evidence, and change owner.

Every acceptance claim maps to a requirement ID, artifact version, command or procedure, captured evidence, and disposition. “Looks right,” “builds,” and “spawns” are observations, not acceptance criteria.
