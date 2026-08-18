# Simulation Evidence Contract

## Admission

Simulation begins only with a closed `SimulationAdmission` receipt. It binds a
canonical resolved candidate and physical/hypothesis reports. The reference
fixture is admitted only when every analytical screen passes and its sole
remaining blocker is the explicit component-placeholder code. Admission always
sets `hardware_promotable` to `false`.

## Portable trace evidence

Scenario registries contain exactly ten bounded, deterministic records with
model, trajectory, environment, seed, faults, metric contract, stop condition,
and joint order. A trace bundle has canonical files plus an external manifest
receipt. Replay verifies the receipt, source closure, timestamps, sample count,
joint width, fixed sample period, stop time, and recomputes metrics without
trusting a stored verdict.

The portable reference fixture currently uses a zero-joint target convention.
Its trace schema does not carry a target vector, so `final_joint_error` means
the maximum absolute final joint position, not a general nonzero-trajectory
tracking-error claim. A future nonzero-target scenario must add a target-vector
evidence field before using this metric for tracking conclusions.

## Backend and calibration boundary

A trace-primary kinematics calculation is compared to an independent planar
dynamics adapter over declared validity domains and metric intervals. They may
share strict input validation, but each must recompute every reported metric
from the receipt-validated trace; neither result may call or reuse the other's
metrics. Their bounded planar metrics include conservative worst-direction
downslope braking and gravity force, so mass and slope cannot be inert inputs.
A passing comparison is calculated evidence, not a higher-fidelity or
live-simulator claim. Calibration stays `simulated` for synthetic data; only declared bench or
integrated-hardware data can produce `calibrated_simulation`, and that still
does not authorize hardware motion.

## Training boundary

Training contracts close observation/action schemas, SI frames and rates,
reward/constraints, episode/step/time/memory caps, distinct train/evaluation
seeds, uncertainty-owned randomization, held-out faults, baseline reward, and
physical blockers. Each case binds one unique receipt-validated replay result
and its compiled scenario; its seed and exact fault identity must match the
declared case. Serialized replay dictionaries are never accepted as evaluation
input. The callback receives only the trace-native final joint/wheel observation
and may return only the bounded base action; it cannot report reward,
displacement, or joint error. Visible `wheel_progress` and `wheel_effort`
weights and the hard joint-error gate are recomputed from replay samples, and
the retained metric must agree with that recomputation. The returned record
binds consumed trace hashes, is always `simulated` and `not_justified`, and has
no hardware-promotion field. A required failed replay prevents score production
rather than permitting a partial policy result.

## Live consumer and hardware boundary

The portable command is:

```bash
python scripts/validate_simulation_bundle.py --reference-root reference/mobile-manipulator
```

It is synthetic replay. The separate Linux Jazzy/Harmonic gate must actually
build and load ROS 2, Gazebo, ros2_control, MoveIt, and Nav2 and retain logs.
Neither gate proves a physical robot safe or authorizes motion. That requires
exact parts and evidence, approved venue and operators, reachable E-stop,
bounded energy/speed/torque, command timeouts, and staged commissioning.
