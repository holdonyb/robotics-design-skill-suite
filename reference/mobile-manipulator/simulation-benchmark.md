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
logs and environment inventory. GitHub Actions runs `31754134659` and
`31754138979` both passed at commit `ced7dc3`. The retained artifact
`simulation-evidence-ced7dc3bdc8280370420ab2437199b02a7e1ade8` has SHA-256
`f83e27da5cb0f9832e8f58f43b83e9f8af6469b2319d5a0298a4b58a40493c41`.
It records active joint-state, arm-trajectory, and differential-drive
controllers; MoveIt planning readiness; and Nav2 controller, planner, behavior,
and BT nodes. This consumer-load evidence is still not a task-execution,
calibration, or hardware result.

## Hardware boundary

All claim-driving components remain engineering placeholders. Neither the
portable benchmark nor any future simulation gate may convert that blocker into
bench-tested, integrated-hardware-tested, task-validated, certified, or motion
authorization evidence.
