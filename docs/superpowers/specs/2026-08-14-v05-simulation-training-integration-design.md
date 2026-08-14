# v0.5 Simulation, Training, and Ecosystem Integration

## Status and decision

This specification refines the v0.5 contract in the trustworthy autonomous
robot design v1.0 design. It begins from released v0.4.0 and uses the same
differential-drive plus six-axis-arm reference robot.

The selected architecture is a container-first vertical reference slice. The
public repository keeps portable contracts, generators, reference packages,
traces, and static validators. A digest-pinned Ubuntu 24.04 environment runs
ROS 2 Jazzy, Gazebo Harmonic, ros2_control, Nav2, and MoveIt consumer gates on
Linux. Windows continues to validate schemas, hashes, ownership, generated
artifacts, traces, and replay without claiming a live simulator.

This is preferred to three rejected approaches:

1. A Gazebo-only demo would be quick but would not close artifact ownership,
   replay, calibration, training, or promotion boundaries.
2. A broad simulator abstraction before a working reference would create
   interfaces with no evidence-bearing consumer.
3. Treating placeholders as accepted hardware would enable simulation but
   invalidate the physical evidence model.

The reference remains unpromoted for procurement and hardware. v0.5 introduces
an explicit `simulation_admitted` state for a complete, analytically passing,
hard-uncertainty-clean model whose remaining blockers are bounded engineering
placeholders. That state permits simulation and training research only. It can
never imply `hardware_promotable`.

## Evidence levels and promotion firewall

The cumulative levels are:

```text
generated
  -> parsed
  -> calculated
  -> simulation_admitted
  -> simulated
  -> calibrated_simulation
  -> bench_tested
  -> integrated_hardware_tested
  -> task_validated
  -> certified (external authority only)
```

`simulation_admitted` requires:

- the v0.3 contract and all applicable analyses are valid;
- all numerical physical analyses pass;
- all hard uncertainty cases are clean;
- no missing component role, missing load path, stale artifact, unsupported
  unit, or unknown safety requirement remains;
- every remaining blocker is exactly an `engineering_placeholder` evidence
  deficiency and is listed in the admission receipt;
- every simulator artifact is hash-bound to the resolved candidate.

It does not require vendor-authenticated parts because simulation may be used
to compare bounded hypotheses before procurement. A simulation-admitted model
is ineligible for purchasing, fabrication, hardware motion, hardware
promotion, or task-performance claims.

Training outputs are always derived evidence. A policy record carries the
training adapter, code/environment hashes, objective, observation/action
schema, safety shield, training seeds, held-out evaluation seeds, baseline,
and evaluation results. No reward, success rate, or simulator result may set a
hardware evidence level or remove a physical/BOM blocker.

## Owned artifacts and consumers

The reference robot adds a generated ROS 2 workspace under
`reference/mobile-manipulator/ros2_ws/src`:

| Package | Owner | Required consumers |
|---|---|---|
| `jx_mobile_manipulator_description` | design contract and generator sources | xacro, robot_state_publisher, URDF parser, Gazebo spawn, MoveIt model |
| `jx_mobile_manipulator_sim` | simulation contract | Gazebo Harmonic, ros_gz bridge, ros2_control controller manager |
| `jx_mobile_manipulator_moveit_config` | SRDF/planning ledger | MoveIt model load, planning-scene smoke test |
| `jx_mobile_manipulator_nav` | navigation contract | Nav2 configuration load and bounded nominal scenario |
| `jx_mobile_manipulator_scenarios` | scenario registry | headless runner, trace recorder, replay validator |

Generator source owns URDF/xacro, SDF, SRDF, controller configuration, bridge
configuration, RViz configuration, worlds, launch files, and scenario records.
Generated files are never edited independently. A release artifact manifest
binds every source and output SHA-256, normalized joint/frame/interface sets,
consumer, generator version, and candidate contract hash.

The geometry authority is a deterministic reference-model generator. It owns
named frames, joint datums, primitive collision/visual envelopes, sensor and
tool interfaces, and a reviewable STEP assembly generated from the same
dimensions. v0.5 geometry is an interface and simulation model, not a released
manufacturing definition. URDF/xacro, SDF, SRDF, STEP, and renders must bind to
the same geometry-input hash. Mass and inertia remain owned by the physical
contract; CAD volume may not silently overwrite them. Meshes are optional and
cannot replace primitive collision geometry in CI.

The same accepted trajectory record drives controller replay, scenario
evaluation, trace comparison, and mission/communication rendering. Renders may
change camera and appearance only; robot transforms come from the trajectory
and contact trace.

## Primary Linux environment

The environment target is Ubuntu 24.04, ROS 2 Jazzy, and Gazebo Harmonic. The
release records an immutable container digest plus the resolved versions of at
least:

- ROS 2 distribution and `ros-core`/desktop packages;
- Gazebo Sim, SDFormat, physics engine, and renderer;
- `ros_gz`, `gz_ros2_control`, `ros2_control`, and controllers;
- Nav2, MoveIt, xacro, robot_state_publisher, and rosbag2;
- Python and colcon.

The environment lock is invalid if it uses only floating tags. CI may build a
Dockerfile from pinned apt repository keys and package versions, but the
published evidence must record the resulting image digest. Every live command
sources `/opt/ros/jazzy/setup.bash` and the built workspace in the same shell.

The headless live gate performs:

1. environment inventory;
2. package discovery proving reuse of standard packages;
3. xacro expansion and URDF/SDF/SRDF checks;
4. colcon build and tests;
5. Gazebo server startup with stale-process prevention;
6. model spawn and level/rest check;
7. controller and target topic/interface inventory;
8. nominal trajectory replay;
9. bounded fault scenarios;
10. structured trace publication and replay verification;
11. clean shutdown and retained logs.

## Scenario, trace, and replay contract

A scenario is closed JSON with bounded sizes and explicit units. It declares:

- scenario ID/version and mission phase;
- model, world, controller, environment, and trajectory hashes;
- initial state and deterministic seed;
- physics engine, solver, time step, real-time factor limit, and duration;
- parameter overrides and their owning uncertainty IDs;
- scheduled faults and recovery/abort expectations;
- required topics, TF edges, controller states, contacts, and sample rates;
- stop conditions, metrics, thresholds, and evidence classification.

The first v0.5 scenario set is deliberately bounded:

- nominal base rest and straight drive;
- nominal six-axis joint trajectory;
- low friction and bounded slope;
- payload variation;
- stale command timeout;
- localization/sensor dropout;
- low-power/thermal-derating state transition;
- joint saturation;
- controller failure and emergency transition;
- collision/contact abort.

A trace bundle contains canonical metadata and immutable raw or normalized
series. Samples use integer nanoseconds and the declared canonical joint order.
It records commands, states, odometry, TF, contacts, faults, controller state,
stop reason, and metrics. The manifest binds every file and contains no
wall-clock-dependent identity fields. Replay checks event order, invariants,
sample bounds, final state, metric recomputation, and exact hash closure.

Nondeterministic engine fields are compared using declared absolute/relative
tolerances. The same seed must reproduce the same normalized verdict and metric
interval; raw floating-point bytes need not be identical unless the engine
guarantees it. A changed model, environment, solver, step, trajectory, or
calibration invalidates prior simulation evidence.

## Second dynamics backend

The second backend is an independent deterministic planar/kinematic adapter,
not a claim of equivalent simulator fidelity. It independently calculates:

- differential-drive forward kinematics and straight/yaw trajectory;
- wheel/joint limit conformance;
- commanded versus integrated base displacement;
- simplified stopping and slope demand within its declared validity domain;
- arm joint trajectory limit and final-state agreement.

It consumes the same normalized scenario and trajectory and emits the same
metric record shape. Cross-backend comparison has per-metric tolerances and
validity domains. Disagreement blocks the affected simulation claim and
preserves both outputs; it is never averaged away.

## Calibration and system identification

System-identification records distinguish synthetic, simulated, bench, and
hardware datasets. A dataset manifest binds source files, units, sampling,
sensor calibration, preprocessing, excluded samples, and evidence level.

A calibration contract declares parameters, priors/bounds, objective,
optimizer, train/evaluation split, seeds, residual metrics, acceptance limits,
and the simulator/environment hashes. v0.5 supplies deterministic fitting and
residual evaluation on synthetic/reference traces only. Those tests prove the
calibration machinery, not reference hardware fidelity.

`calibrated_simulation` requires an eligible bench or hardware dataset and
accepted held-out residuals. Synthetic self-fit remains `simulated` and is
labelled as a pipeline test.

## Training adapter and domain randomization

The training interface is backend-neutral and finite:

- closed observation/action schemas with units, frames, bounds, and rates;
- explicit baseline controller and fallback action;
- objective/reward terms with visible weights and hard constraints;
- maximum episodes, steps, wall time, memory, and artifact bytes;
- separate training and held-out evaluation seeds;
- deterministic policy ID from adapter, environment, model, schema, and seed
  hashes;
- callback boundary that converts crashes, NaN, timeouts, and malformed output
  into failed evidence.

Domain randomization is a registry of uncertainty-owned ranges and
distributions. Every range references an existing design uncertainty or an
eligible identification result. Arbitrary appearance randomization cannot
change physical parameters. Training is optional: if a conventional controller
meets the task, the benchmark records `not_justified` rather than training for
its own sake.

Held-out evaluation always includes the baseline, nominal cases, hard boundary
cases, and registered faults. Policy evaluation may qualify a policy for more
simulation. It cannot authorize hardware loading, controller activation, or
motion.

## Dependency audit

Every third-party update is reviewed as source, not accepted because it is
newer. The audit records old/new commits, release/license changes, skill
frontmatter and executable-script differences, security/reproducibility
effects, behavioral regressions, and selected disposition.

At design time the latest observed commits were:

- `earthtojake/text-to-cad@9068fdb4d08487590030beefde5630da09c0f97b`;
- `dbwls99706/ros2-engineering-skills@2048e1bccf787a79044f140bc6bff4f57ce184f5`;
- `BaraaLazkani/ros2-sim-skill@97cd3cec17b89b28c577a001285bcace35ec2374`.

The first two differ from v0.4 pins and require bounded diff review and install
regression before any manifest change. The third is already current.

## CI and release gates

Windows and ordinary Linux matrix jobs run all portable validation. A separate
Linux live-simulation workflow uses the pinned environment and uploads:

- environment inventory and image digest;
- build/test logs;
- consumer-load report;
- normalized trace bundles and replay results;
- cross-backend comparison;
- calibration and training-boundary reports.

Live CI fails on missing target consumers, stale hashes, an unrepeatable
normalized verdict, nonfinite data, unbounded output, orphan process, policy
promotion, or a fault scenario that does not reach its declared safe outcome.

v0.5 release requires:

- all generated reference artifacts are manifest-bound and load in their
  target consumer;
- the same trajectory identity reaches controller replay and rendering;
- nominal and fault scenarios reproduce their normalized verdicts in fresh CI;
- every simulation claim records engine/version/parameters/calibration status;
- the second backend agrees within declared domains or disagreement blocks;
- synthetic calibration is not represented as hardware calibration;
- trained policies cannot alter hardware evidence or promotion;
- fresh installation, independent adversarial review, public PR, matrix/live
  CI, merge, annotated tag, GitHub Release, public verification, and controlled
  local integration-skill refresh all pass.

## Explicit nonclaims

- A successful spawn is not proof of dynamics, control quality, safety, or
  manufacturability.
- Gazebo is not physical truth and the second adapter is not high fidelity.
- Synthetic calibration proves only the pipeline.
- Training reward is not task, safety, or hardware evidence.
- Placeholder components remain placeholders after any amount of simulation.
- No v0.5 action authorizes purchasing, fabrication, or real robot motion.
