# Reference Mobile Manipulator Simulation Benchmark

## Portable result

Run from the repository root:

```bash
python skills/robotics-design/scripts/validate_simulation_bundle.py \
  --reference-root reference/mobile-manipulator
```

The benchmark first re-evaluates the physical contract. It admits the reference
only because its remaining blocker inventory is exactly
`BOM.PLACEHOLDER_BLOCKS_CLAIM`; the admission receipt has
`hardware_promotable: false`. It then compiles and replays ten canonical
synthetic scenarios, compares two deterministic planar dynamics calculations,
fits only the synthetic calibration dataset, and evaluates the bounded training
callback firewall.

The expected portable result is ten passed replays, a passed independent-backend
comparison, `simulated` calibration evidence, and a `simulated` /
`not_justified` training record. `--force-failed-scenario` deliberately produces
a valid failed benchmark and exit code 1. Invalid or tampered inputs exit 2.

## Evidence interpretation

This is portable synthetic replay, not live Gazebo evidence. It proves that the
closed contracts, receipts, metric recomputation, resource bounds, and no-
hardware-promotion boundary compose deterministically on supported Python.

The separate Linux Jazzy/Harmonic gate builds the ROS workspace, runs headless
Gazebo, checks ros2_control, MoveIt, and Nav2 consumer presence, and uploads its
logs and environment inventory. Until that job has a retained successful run,
there is no live-consumer claim.

## Hardware boundary

All claim-driving components remain engineering placeholders. Neither the
portable benchmark nor any future simulation gate may convert that blocker into
bench-tested, integrated-hardware-tested, task-validated, certified, or motion
authorization evidence.
