# Arm motor–reducer transmission screen audit

Date: 2026-08-14

`arm_load_envelope_v1` now preserves its existing static gravity calculation at
the reducer output and separately computes the motor-side continuous demand:

```text
motor_continuous_required = output_continuous_required / gear_ratio / efficiency
```

Every result is a signed margin against the motor's declared continuous torque.
The input contract is closed: every arm joint must supply exactly one motor
rating, reducer ratio, and reducer efficiency record. The assurance engine
requires them to be owned by the unique motor or reducer bound to that same
joint. A verified motor capacity or reducer ratio must also be the exact
catalog-bound component limit; an explicitly assumed reducer efficiency may be
used only as a conservative analysis input and remains visible at the assumed
evidence level.

The reference J2 ratio stays bound to the Harmonic Drive CSG-40-100-2UH
snapshot. J2's motor rating and reducer efficiency, along with the other arm
motor and efficiency inputs, remain engineering assumptions. The added fault
sets the J2 motor rating to 1 N*m and must produce
`PHY.ARM.MOTOR_CONTINUOUS_TORQUE`.

This is a static continuous torque transfer screen only. It does not establish
motor torque-speed curves, current control, winding temperature, reducer life,
backlash, coupling or adapter fit, brake behavior, transient dynamics, CAD
collision clearance, procurement suitability, energization, or permission for
hardware motion.
