# Reference Load Envelope and Component-Selection Readiness Design

## Purpose

Turn the reference mobile manipulator's arm from a generic, manually entered
``5 kg × 1 m`` gravity check into a bounded, reproducible load-envelope
calculation.  The result is an engineering requirement for each joint's
continuous and brake-holding capability.  It is deliberately **not** a vendor
part selection, purchasing instruction, hardware authorization, or proof of
hardware performance.

## Problem and decision

The existing `arm_gravity_v1` analysis accepts independent mass/lever pairs
for each joint.  The reference fixture currently gives every joint a single
payload load and the same provisional 100 N m ratings.  That has two
unacceptable properties for selection work: link/tool/cable mass is absent,
and a change in the model can leave the manual levers unchanged.

The new `arm_load_envelope_v1` plug-in will calculate static gravity torque
from a closed serial-chain description for named URDF joints and links.  Each
load case supplies joint positions, gravity, and a payload attachment point.
For every joint, the plug-in will form the posed joint frame, transform each
downstream link centre of mass and payload point, and calculate the absolute
axis moment:

```
tau = abs(dot(axis_world, cross(point_world - joint_origin_world, mass * gravity_world)))
```

The reported required continuous and brake holding torques are the maximum
over declared cases times their separately declared safety factors.  The
plug-in reports a worst-case case ID per joint and compares those requirements
with the declared provisional component limits.  This is a static sizing
screen only: acceleration, gearbox life, bearing life, shock, backlash,
electronics, cable loads, thermal transients, and collision loads remain
separate mandatory analyses before any selection can be promoted.

## Closed input contract

`arm_load_envelope_v1` receives only a closed object with these fields:

```json
{
  "joint_order": ["joint_1"],
  "joints": [{"id": "joint_1", "parent": "base_link", "child": "arm_link_1",
              "origin_xyz_m": ["quantity:Q-J1-OX", "quantity:Q-J1-OY", "quantity:Q-J1-OZ"],
              "origin_rpy_rad": ["quantity:Q-J1-R", "quantity:Q-J1-P", "quantity:Q-J1-Y"],
              "axis_xyz": ["quantity:Q-J1-AX", "quantity:Q-J1-AY", "quantity:Q-J1-AZ"]}],
  "links": [{"id": "arm_link_1", "mass_kg": "quantity:Q-L1-MASS",
             "com_xyz_m": ["quantity:Q-L1-COM-X", "quantity:Q-L1-COM-Y", "quantity:Q-L1-COM-Z"]}],
  "payload": {"mass_kg": "quantity:Q-PAYLOAD", "parent": "arm_link_1",
              "origin_xyz_m": ["quantity:Q-PAYLOAD-X", "quantity:Q-PAYLOAD-Y", "quantity:Q-PAYLOAD-Z"]},
  "load_cases": [{"id": "LC-HORIZONTAL", "joint_positions_rad": ["quantity:Q-LC-H-J1"],
                  "gravity_xyz_m_s2": ["quantity:Q-GX", "quantity:Q-GY", "quantity:Q-GZ"]}],
  "continuous_safety_factor": "quantity:Q-ARM-CONTINUOUS-SF",
  "brake_safety_factor": "quantity:Q-ARM-BRAKE-SF",
  "rated_continuous_torque_nm": [{"id": "joint_1", "value": "quantity:Q-ARM-CONTINUOUS-TORQUE-J1"}],
  "brake_holding_torque_nm": [{"id": "joint_1", "value": "quantity:Q-BRAKE-HOLDING-TORQUE-J1"}]
}
```

All repeated IDs are unique and exactly cover `joint_order`; the joint graph is
one acyclic chain rooted at `base_link`; links exactly cover the joint children;
the payload parent is a known child link or `tool0`; all numeric inputs are
finite quantity references with explicit dimensions.  Joint axes must be
unit-length within a tight tolerance.  A load case supplies exactly one angle
per joint, has a non-zero finite gravity vector, and its ID is unique.  Empty
or unknown fields, disconnected graphs, duplicate IDs, non-finite values, and
dimension mismatch are invalid rather than interpreted permissively.

## Model binding

The reference contract will add `model/geometry.json` as a hash-bound
`declared_json` artifact and record a distinct assumed load-envelope evidence
source.  New contract quantities for link mass, link COM, joint origin and
axis, and payload attachment will carry observations from the URDF or the
declared geometry record.  Thus changing a source model without regenerating
the contract produces a drift diagnostic before this plug-in can be trusted.

The initial reference envelope uses explicit, conservative engineering mass
budgets for each link/tool/cable group and a small finite set of named static
postures.  Those values are assumptions and will be visibly reported as such;
they are not CAD-derived or vendor-certified.  The generator may emit the
reference contract quantities from the same model source, but it must never
silently rewrite a hash-bound contract in validation.

## Result and promotion boundary

The analysis output contains per-case, per-joint torques; maximum gravity
torque; worst-case case ID; continuous/brake requirements; declared-rating
margins; and validity assumptions.  The solver sums signed axis moments before
taking their magnitude, rather than summing magnitudes.  Its monotonicity test
therefore uses a declared posture where the added downstream mass has the same
moment sign as the baseline load; a generic monotonic claim across cancelling
geometry would be physically false.

`reference/mobile-manipulator` remains intentionally unpromotable.  Its
motors, reducers, brakes, bearings, drivers, and power equipment remain
`engineering_placeholder`; no requirement calculated here may be presented as
a selected part rating.  A later, separate supplier-selection increment may
only replace a placeholder with a `verified_part` or a bounded
`qualified_substitute` after official, hash-bound catalogue/datasheet evidence
and all applicable drivetrain, thermal, mechanical, electrical, and safety
analyses pass.

## Verification

Tests will cover exact input closure and dimensional validation, serial-chain
and axis errors, known analytical torque fixtures, pose-dependent worst cases,
mass monotonicity, URDF/geometry drift, report determinism, and preservation of
the reference fixture's placeholder-blocked promotion result.  The complete
suite, distribution validator, installer dry-run, and a clean diff check are
release gates for this increment.
