# Robot Validation Gates

Record tool versions and distinguish PASS, FAIL, WARN, and NOT RUN.

| Layer | Minimum gate | Stronger evidence |
|---|---|---|
| Requirements | Numbered requirements/assumptions and owners | Reviewed verification matrix and interface control document |
| Budgets | Mass/CG/stability, energy/current, thermal, timing | Sensitivity, contingency, vendor curves, measured duty cycle |
| Physical plausibility | Hash-bound design contract, explicit SI quantities/evidence, complete component bindings, drivetrain/battery/stability/arm-gravity/thermal margins | Exact vendor curves, uncertainty sweeps, full dynamics/structure/thermal models, bench correlation |
| CAD | Valid solids, dimensions, datums, clearances, interference | STEP re-import, motion, mass properties, manufacturing review |
| URDF/xacro | Expansion/parser, connected tree, valid axes/limits/inertias | Consumer load, TF assertions, collision review, CAD drift test |
| SDF | Schema/bundled validation and resource resolution | `gz sdf --check`, stable load, sensors/plugins, real-time evidence |
| SRDF | Valid against exact URDF; legal groups/states | MoveIt load, IK/planning, sampled collision review |
| ROS 2 | Build/lint, interface/parameter validation | Lifecycle, QoS, timing, bag regression, fault injection |
| Integration | Repeatable launch, model/TF/controllers/bridges/topics visible | Scenario matrix, randomized starts, timeout/dropout/contact tests |
| Generated visualization | Exact deterministic target-pose references, source hashes, visible joint/interface landmarks, appearance-only changes | Independent side-by-side landmark review and valid promoted visual manifest |
| Mission animation | Versioned trajectory/contact trace, hashes, phase/load-case manifest, exact required moving joints | Numeric render-to-trajectory comparison, contact/load trace review, valid promoted mission manifest |
| Patent-aware architecture | Official publication/status sources, element-by-element claim chart, positive constraints and drift tests | Current family/file-wrapper review and qualified-counsel disposition for the exact design revision |
| Hardware | Current-limited power-up, E-stop/STO, timeout checks | Incremental commissioning, calibration, thermal/current logs |
| Field | Controlled acceptance tied to requirements | Payload/endurance/stability/braking/coverage and safety validation |

## Cross-artifact invariants

- names and topology agree across URDF, SRDF, controllers, launch, and MoveIt;
- dimensions, transforms, mesh scale, mass, inertia, and joint limits match their owners;
- handedness, axes, signs, units, and optical frames are explicit;
- sensor topic/frame/rate/noise contracts agree across model, bridge, ROS config, and consumers;
- controller command/state interfaces agree with description and hardware;
- generated robot images preserve deterministic topology, pose, joint count/axes, interfaces, and link proportions; required and observed landmark sets match exactly;
- mission animation frames sample the accepted trajectory exactly; phase contacts, required moving joints, load cases, and violation counts agree with the physics trace;
- patent-aware design constraints remain visible in requirements and owned artifacts, and automated drift tests reject reintroduction of prohibited claim combinations;
- safety and fault states exist in architecture, simulation, configuration, and commissioning procedures.
- each actuator has its own motor/reducer/bearing/driver binding and URDF transmission; each power, moving-cable, and claimed safety path has every mandatory role;
- each claim-driving quantity is explicitly supported by its selected evidence record, and every mirrored observation agrees with its owner within the declared tolerance.

## Evidence ladder

1. authored/generated;
2. syntax/schema valid;
3. actual consumer loads;
4. semantic assertions pass;
5. integrated simulation passes;
6. bench hardware measured;
7. field requirement verified;
8. certified or independently assessed.

A higher-level claim requires its own evidence.

Run analytical physical gates before nominal simulation or training. Simulation
cannot turn a missing component, stale source, invalid unit, failed continuous
rating, or failed thermal margin into a pass. Preserve the machine-readable
failure report and rerun it after repairing the owning record or artifact.

A plausible image is level 1 evidence at most until its deterministic sources, hashes, landmark review, and promotion manifest pass. Visual review does not replace kinematic, structural, thermal, electrical, manufacturing, or hardware evidence.

An animation is level 1 evidence until its source trajectory, physics/contact trace, hashes, phase invariants, numeric render comparison, and promotion manifest pass. Even a promoted simulation animation does not establish hardware performance.
