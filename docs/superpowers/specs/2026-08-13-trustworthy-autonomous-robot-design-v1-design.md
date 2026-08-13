# Trustworthy Autonomous Robot Design v1.0

## Status and decision

This specification defines the release train from the published `v0.2.0` suite
to `v1.0`. The reference system is an indoor mobile manipulator with a
differential-drive base and a six-axis arm. One versioned design contract, one
component ledger, and one evidence graph follow that robot from requirements
through analysis, generated artifacts, simulation, bench tests, and controlled
hardware trials.

The selected strategy is a vertical reference implementation. We will prove
each platform capability on the reference robot before generalizing it. We will
not build a broad schema platform with no physical consumer, and we will not
generate large numbers of candidates before the assurance kernel can reject
physically impossible ones.

The release sequence is gate-driven rather than date-driven:

1. `v0.3`: Physical Plausibility Kernel.
2. `v0.4`: Autonomous Hypothesis Engine.
3. `v0.5`: Simulation, Training, and Ecosystem Integration.
4. `v0.6`: reference-robot engineering freeze and procurement package.
5. `v0.7`: component characterization and bench evidence.
6. `v0.8`: integrated low-energy commissioning.
7. `v0.9`: task, fault, endurance, and sim-to-real validation.
8. `v1.0`: reproducible public delivery with bounded claims.

## Execution policy

The agent owns reversible in-scope technical decisions, architecture choices,
research routing, implementation details, testing, branch management, pull
requests, and already-authorized public releases. Routine work does not pause
for user approval. When evidence invalidates an earlier decision, the agent
records the reason and chooses the smallest technically sound correction.

This autonomy does not authorize purchases, fabrication orders, paid services,
shipping, access to a facility, or physical robot motion. Those actions require
the necessary account authority, budget, equipment, site control, and explicit
motion authorization. Real motion also requires a bounded area, reachable
emergency stop, named observers, speed/torque/power limits, command timeout,
and an approved test card. Missing external authority is reported as a release
dependency; it is never hidden by relabeling simulation as hardware evidence.

## Product objective

The suite will turn a robot request into a traceable sequence:

```text
requirements
  -> explicit assumptions and acceptance criteria
  -> architecture and component hypotheses
  -> conservative analytical rejection
  -> owned CAD/URDF/SDF/SRDF/ROS artifacts
  -> cross-artifact consistency checks
  -> calibrated simulation and counterexample search
  -> training where training is justified
  -> bench characterization
  -> controlled hardware commissioning
  -> task and fault evidence
  -> bounded promotion report
```

The product is not a robot-certification system. It is a design-assurance and
evidence-orchestration system that refuses unsupported completion claims and
produces reviewable inputs for qualified mechanical, electrical, controls,
safety, manufacturing, and certification professionals.

## Reference mission

The reference robot demonstrates an indoor material-handling mission:

1. start from a charging or service station;
2. navigate through a bounded indoor route;
3. stop and localize at a work zone;
4. perceive and pick a bounded payload from a shelf or fixture;
5. place the payload into a destination fixture;
6. recover from defined perception, localization, command, contact, and power
   faults;
7. return to a safe state and, when enabled, dock.

Exact payload, reach, route, slope, floor friction, speed, accuracy, duty cycle,
and endurance targets are not implied by this document. `v0.3` must capture
them as versioned requirements or numbered assumptions with owner, confidence,
validation method, and decision deadline. A candidate cannot be promoted while
an unresolved assumption can reverse component selection or safety design.

## System architecture

### 1. Contract registry

Versioned machine-readable contracts define:

- requirements, environments, hazards, tasks, and acceptance criteria;
- assumptions and uncertainty distributions;
- quantities, SI units, owners, source artifacts, and allowed mirrors;
- interfaces, frames, datums, joints, transmissions, electrical nets, thermal
  paths, communication links, and safety functions;
- candidate status, analysis obligations, evidence requirements, and release
  gates.

Every mirrored value records its owner and source locator. A validator reports
missing ownership, incompatible units, stale source hashes, and divergent
mirrors. Schemas are append-only within a minor release and use explicit
migrations across incompatible versions.

### 2. Component and BOM ledger

The ledger distinguishes four states:

- `verified_part`: exact manufacturer identity and source document;
- `qualified_substitute`: bounded equivalent with reviewed differences;
- `engineering_placeholder`: explicit envelope and uncertainty, not orderable;
- `missing`: required component not represented.

Records cover at least motors, reducers, bearings, shafts, couplings, brakes,
drivers, contactors, protection, battery cells/packs, BMS, chargers, converters,
compute, networks, sensors, cables, connectors, cable management, cooling,
fasteners, structural materials, wheels, tires, end effectors, and guarding.
Each record includes source provenance, operating limits, derating conditions,
mass and envelope, interfaces, lifecycle state, and the exact claims supported
by its evidence. Generated part numbers and unverified catalog values fail
closed.

The BOM completeness gate uses the architecture and energy/control paths to
infer required roles. A joint with effort capability but no motor/transmission,
a battery with no protection or current path, a brake claim with no brake
component, or a moving cable with no routing/strain-relief owner is an error.

### 3. Evidence graph

Claims, artifacts, analyses, tests, and source documents are content-addressed
nodes. Typed edges record `owns`, `derived_from`, `mirrors`, `checks`,
`calibrates`, `invalidates`, and `supports`. Evidence levels are ordered but not
interchangeable:

```text
assumed < generated < parsed < calculated < simulated < bench-tested
        < integrated-hardware-tested < task-validated < certified
```

A higher label is legal only when the required evidence node and its promotion
gate exist. Changing an upstream hash makes dependent evidence stale. The graph
must explain both why a claim is currently supported and what invalidated a
failed candidate.

### 4. Analysis plug-ins

Each analysis plug-in has declared input contracts, units, validity domain,
uncertainty treatment, output claims, diagnostic codes, and reference tests.
Plug-ins never silently repair their inputs. They return pass, fail, or
indeterminate; `indeterminate` cannot satisfy a release gate.

The initial analysis families are:

- dimensional and unit consistency;
- completeness of mechanical, electrical, control, thermal, and safety paths;
- differential-drive traction, slope, acceleration, braking, wheel load, and
  tip/stability margins;
- motor speed-torque operating points, gear ratio, efficiency, continuous and
  peak duty, reflected inertia, backdrivability, regenerative energy, and
  thermal derating;
- manipulator gravity and dynamic joint loads, payload/reach envelopes,
  reducer and bearing load limits, brake holding, backlash/accuracy budget,
  singularity, workspace, self-collision, and base reaction loads;
- battery energy, peak/continuous power, current, voltage drop, BMS limits,
  converter headroom, state-of-charge and temperature derating;
- structural load paths, interface loads, conservative factors, deflection and
  modal obligations, with FEA required only when first-order bounds are
  insufficient;
- compute, communication, latency, update-rate, watchdog, timeout, and degraded
  state budgets;
- sensor field of view, occlusion, range, rate, accuracy, calibration and
  environmental operating envelope;
- cable bend, sweep, strain relief, current, voltage and thermal envelopes;
- task-phase contact, payload, energy, thermal, and stability budgets.

Analytical checks are conservative screening tools, not substitutes for
manufacturer limits, detailed analysis, test, or certification.

### 5. Artifact adapters

Adapters read or generate owned artifacts without changing ownership rules:

- CAD/STEP owns geometry, datums, packaging and derived mass properties;
- the component ledger owns selected component identity and catalog evidence;
- URDF/xacro owns the robot kinematic tree, frames, joints, transmissions,
  limits and consumer inertials;
- SDF owns world, simulator physics, contact, sensors and simulator plug-ins;
- SRDF owns planning groups, semantic poses and collision exceptions;
- ROS 2 configuration owns hardware interfaces, controllers, lifecycle,
  QoS, navigation, perception and deployment parameters;
- the evidence graph owns promotion status and claim boundaries.

Adapters produce normalized observations. The assurance kernel compares those
observations against the contract; it does not trust successful parsing,
generation, spawning, building or rendering as semantic validation.

### 6. Candidate and hypothesis engine

A candidate is a versioned graph of architecture decisions, component choices,
parameters, assumptions and expected evidence. Candidate generation operates
within declared design spaces; it cannot invent vendor performance or expand a
requirement silently.

The engine uses a staged evaluation budget:

1. schema, units, mandatory-role and source checks;
2. conservative algebraic bounds;
3. kinematic, collision and quasi-static checks;
4. dynamic, electrical and thermal simulation;
5. parameter sweep, sensitivity and uncertainty propagation;
6. adversarial search for the smallest environment or fault perturbation that
   violates a requirement;
7. multi-objective ranking with visible trade-offs and no hidden scalar score;
8. detailed simulation or training only for surviving candidates.

Every rejected candidate keeps its earliest violated contract, inputs, tool
version and trace. The repair loop changes the owning decision and reruns the
failed and dependent gates. It does not tune downstream controllers to conceal
an invalid actuator, geometry, mass or power choice.

### 7. Simulation and training harness

The primary integration target through `v0.5` is ROS 2 Jazzy with Gazebo
Harmonic because both have long-lived support windows suitable for a stable
baseline. Simulator interfaces remain replaceable so independent backends can
cross-check sensitive results. The ROS control boundary uses declared
`ros2_control` hardware, state and command interfaces; MoveIt consumes the
validated robot model and planning scene rather than becoming a geometry owner.

Scenario packages define initial state, environment, random variables, task
phases, faults, stop conditions, metrics and artifact hashes. Required scenario
families include nominal navigation/manipulation, low friction, slope, payload
variation, localization loss, sensor dropout, delayed/stale commands, network
loss, low power, thermal derating, collision/contact, joint saturation,
controller failure and emergency transition.

Training is admitted only when the policy objective, observation/action space,
safety envelope, baseline controller, deterministic seed handling, evaluation
set and deployment boundary are explicit. Training and evaluation seeds are
separate. Domain randomization ranges come from the uncertainty registry or
measured system-identification evidence, not arbitrary visual variety.

### 8. Hardware evidence path

Hardware promotion is staged:

1. document and source inspection;
2. unpowered dimensional, assembly, wiring and continuity checks;
3. protected power-up with motion inhibited;
4. individual component and joint characterization at bounded energy;
5. base and arm restricted motion in separated test modes;
6. integrated low-speed motion with reachable emergency stop;
7. injected timeout, communication, sensor and power faults;
8. bounded reference mission;
9. repeatability, endurance and post-test inspection.

Each test card names hazards, roles, equipment, preconditions, limits, abort
criteria, expected traces and evidence retention. Failed tests remain evidence
and invalidate dependent promotion claims until the owning issue is repaired.

## Release contracts

### v0.3 — Physical Plausibility Kernel

Deliverables:

- classify the 17-path active-local delta and promote only tested behavior;
- versioned requirement, assumption, ownership, component/BOM and evidence
  schemas;
- deterministic unit handling and report format;
- reference-robot contract with explicit unresolved assumptions;
- first component ledger and mandatory-role inference;
- drivetrain, manipulator, battery/power, stability, thermal-duty and
  cross-artifact validators;
- synthetic and reference-based fault corpus;
- behavior evaluations that reject unsupported physical claims;
- bilingual documentation, migration tooling and a public release.

Exit gate:

- 100% of curated critical faults are rejected;
- no critical fault is converted to a warning;
- reports are deterministic across supported platforms;
- every promoted physical claim has an owner, source and evidence level;
- the reference candidate passes the defined analytical gates or remains
  explicitly unpromoted with actionable failures.

### v0.4 — Autonomous Hypothesis Engine

Deliverables:

- bounded candidate/design-space schema;
- candidate generation, deduplication and lineage;
- staged evaluation scheduler and cache keyed by inputs/tool versions;
- parameter sweep, sensitivity, uncertainty and counterexample interfaces;
- visible Pareto ranking across mass, cost, endurance, performance, risk and
  evidence completeness;
- ASPIRE-style repair loop with regression selection;
- benchmark comparing accepted, rejected and repaired candidates;
- public release with reproducible seeds and traces.

Exit gate:

- candidates never bypass v0.3 physical gates;
- identical inputs and seeds reproduce candidate identities and reports;
- injected design flaws are traced to the earliest violated owner;
- at least one reference design trade-off is improved without regressing any
  hard requirement;
- uncertainty and counterexample results affect promotion, not presentation
  only.

### v0.5 — Simulation, Training, and Ecosystem Integration

Deliverables:

- audited updates to the ROS 2 and CAD-generation dependencies;
- repeatable Linux ROS 2 Jazzy/Gazebo Harmonic environment;
- reference CAD, URDF/xacro, SDF, SRDF, ros2_control, navigation, MoveIt and
  task packages;
- scenario/fault harness, structured traces and replay;
- second-backend adapter for selected dynamics cross-checks;
- system-identification and simulator-calibration contracts;
- training adapter, domain-randomization registry and held-out evaluation;
- Windows static/contract CI and Linux live simulation CI;
- public release with pinned environments and artifacts.

Exit gate:

- the same accepted model and trajectory drive engineering evidence and
  communication renders;
- target consumers load every artifact and cross-artifact gates remain green;
- nominal and fault scenarios are repeatable in CI;
- simulation claims include engine/version/parameters and calibration status;
- trained policies cannot cross the hardware promotion boundary.

### v0.6 — Engineering freeze

Deliverables include supplier-level BOM, controlled drawings and CAD, assembly,
wiring and protection design, thermal plan, manufacturing/inspection plan,
hazard log, safety-function requirements, verification matrix, procurement
alternatives, lead-time and obsolescence risks, and a hardware test plan.

Exit requires an independently reviewable package with no missing critical
component role and no unresolved assumption that can reverse the architecture.
This gate prepares purchasing decisions but does not authorize a purchase.

### v0.7 — Component and bench evidence

Characterize the actual motors, reducers, brakes, drivers, battery/power path,
sensors, networks and thermal behavior used by the reference build. Feed
measured curves and uncertainty back into the ledger, analyses and simulators.

Exit requires reproducible raw data, calibration records, safe test limits,
model-fit residuals and explicit disposition of every failed or anomalous test.

### v0.8 — Integrated commissioning

Assemble the reference robot, validate unpowered and protected-power states,
bring up hardware interfaces, verify limits/watchdogs/stop paths, and execute
separated then integrated low-energy motion.

Exit requires successful emergency and timeout transitions, bounded base and
arm motion, traceable command/state data, post-test inspection and no open
critical safety defect. Passing v0.8 is not a task-performance claim.

### v0.9 — Task and robustness validation

Execute the reference mission across the approved operating envelope, repeat
fault scenarios, measure repeatability and endurance, quantify simulation-to-
hardware gaps, and update uncertainty and maintenance models.

Exit requires predefined task metrics, sufficient repetitions, retained raw
evidence, root-cause disposition of failures and regression replay on the
software/simulation side. Certification remains a separate external activity.

### v1.0 — Reproducible delivery

The public release includes:

- installable skills and pinned third-party provenance;
- schema, migration, validator and analysis APIs;
- reference-robot source artifacts and artifact manifest;
- component ledger with public-source and measured-evidence boundaries;
- candidate/hypothesis and scenario benchmark suites;
- CI, simulator images or environment locks, replayable traces and reports;
- hardware build, inspection, commissioning and test documentation that can be
  published without leaking private or restricted data;
- behavior evaluations and adversarial fault corpus;
- English and Chinese user, developer and evidence-boundary documentation;
- release notes that distinguish calculated, simulated, bench-tested,
  integrated-hardware-tested, task-validated and certified claims.

`v1.0` cannot ship with an open critical fault, a stale promoted artifact, an
unreproducible critical result, or a hardware claim supported only by generated
or simulated evidence.

## Failure handling

- Invalid types, units, missing values and unavailable sources produce field-
  specific diagnostics, never tracebacks as user-facing validation output.
- Unknown or unsupported evidence is `indeterminate`, not a pass.
- Network or vendor-source failure preserves the last verified record and marks
  freshness; it never substitutes generated specifications.
- Analysis disagreement preserves both results and blocks the affected claim
  until validity domains and assumptions are resolved.
- Simulation divergence, instability or nondeterminism retains traces and
  blocks promotion.
- Hardware aborts preserve the pre-test card, commands, states, faults and
  operator disposition without automatically retrying motion.

## Verification strategy

Verification layers are cumulative:

1. schema, unit and migration tests;
2. property and metamorphic tests for physical equations;
3. published textbook/manufacturer examples where licensing permits;
4. golden reference calculations with independent implementations;
5. adversarial fault corpus and malformed inputs;
6. cross-artifact fixtures and drift injection;
7. simulator consumer loads and deterministic scenario replay;
8. cross-backend comparisons with declared tolerances;
9. bench calibration and model residual checks;
10. controlled hardware task/fault tests;
11. independent review before every public minor release.

Coverage metrics include critical-fault recall, false promotion count,
diagnostic localization, evidence coverage, stale-dependency detection,
reproducibility, scenario pass/fail stability, sim-to-bench residuals and
sim-to-hardware residuals. A high line-coverage number does not replace these
metrics.

## Safety and standards profile

The project keeps a version-locked standards profile appropriate to the
intended market and application. As of this specification, official sources
identify:

- [ISO 12100:2010](https://www.iso.org/standard/51528.html) for machinery risk
  assessment and reduction; ISO reports it remains current but under revision;
- [ISO 10218-1:2025 and ISO 10218-2:2025](https://www.iso.org/ics/25.040.30/x/)
  for industrial robots and applications/cells;
- [ISO 3691-4:2023](https://www.iso.org/standard/83545.html) for driverless
  industrial trucks and their systems, including AMR examples;
- [ISO 13849-1:2023](https://www.iso.org/standard/73481.html) for the design and
  integration methodology of safety-related parts of control systems;
- the applicable functional-safety, electrical, battery, EMC, radio, fire,
  machinery and regional requirements selected by qualified reviewers for the
  final architecture and site.

The profile records applicability and verification obligations but does not
copy restricted standards text or claim conformity. Standards are rechecked at
the engineering-freeze and v1.0 gates because revisions are already in
progress.

The software baseline initially targets
[ROS 2 Jazzy](https://docs.ros.org/en/jazzy/Releases.html), supported through
May 2029, and [Gazebo Harmonic](https://gazebosim.org/docs/harmonic/releases/),
an LTS release through September 2028. The
[ros2_control architecture](https://control.ros.org/jazzy/doc/ros2_control/doc/index.html)
provides the hardware/controller boundary, while
[MoveIt 2](https://moveit.picknik.ai/humble/index.html) consumes robot and
planning-scene models for manipulation. Exact dependency commits and container
images remain locked in release manifests.

## Project organization and publication

The existing thin distribution remains the public suite. New modules are kept
small and independently testable: contracts, component ledger, evidence graph,
analyses, adapters, candidate engine, scenarios, reference robot and report
generation. The reference robot may become a separate repository only when its
generated artifacts or simulation dependencies would make the skill
distribution unauditable; until then, its schemas and minimal fixtures live
with the suite.

Every minor release uses an isolated branch, tests before and after merge,
independent review, public PR, cross-platform CI, fresh installation, official
skill validation, signed or annotated tag, release notes and a durable
`PROJECT_STATUS.md` handoff. Installed local copies are outputs, never the only
source of reusable behavior.

## Explicit non-goals and claim boundary

- No automatic certification, legal conformity decision, patent clearance or
  functional-safety approval.
- No invented vendor parts, measurements, test results or safety performance.
- No requirement that one simulator be treated as physical truth.
- No unrestricted search over unsafe or unmanufacturable designs.
- No autonomous purchase, fabrication order or real robot motion.
- No promotion from attractive CAD, animation, training reward or successful
  simulator runs alone.

The final completion report must state which parts of the objective are
generated, parsed, calculated, simulated, bench-tested, integrated-hardware-
tested, task-validated and externally certified. Anything without direct
evidence remains explicitly open.
