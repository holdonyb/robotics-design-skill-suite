# v0.5 Dependency Audit

Date: 2026-08-14

## Scope and disposition

No third-party skill pin was changed for v0.5. The existing pinned sources in
`manifest.json` continue to be the installable suite boundary. The v0.5 work
adds only first-party Python, reference data, and an optional Linux consumer
container definition.

| Dependency area | Disposition | Reason |
|---|---|---|
| Existing skill pins | retain | No independently reviewed upstream delta is required for the v0.5 evidence model. |
| Ubuntu base image | digest-pinned | The live gate records the Ubuntu 24.04 image index digest in both the Dockerfile and `environment-lock.json`. |
| ROS 2 / Gazebo / MoveIt / Nav2 packages | runtime inventory | Package names are declared for Jazzy/Harmonic consumer validation; the gate retains actual `dpkg-query` output rather than presenting the Dockerfile as a resolved package lock. |
| Python portable kernel | standard library | Portable schema, replay, calibration, and training-boundary tests require no new Python package. |

## Evidence boundary

The portable benchmark is a synthetic trace-replay and independent-dynamics
check. It is not a Gazebo execution result. The Linux gate is the separate
place where ROS 2 Jazzy, Gazebo Harmonic, ros2_control, MoveIt, and Nav2 must
actually load and where logs and package inventory are retained.

The Docker base digest was checked against the Ubuntu official-image listing on
2026-08-14. It is intentionally an immutable reference in source; a future
refresh requires a new audit, updated lock, consumer run, and review.

## Nonclaims

Neither a pinned container nor a passing simulation proves a physical robot is
safe, calibrated, compliant, or authorized to move. Exact hardware parts,
controlled site procedures, emergency stop, bounded energy, and retained raw
measurements remain v1 evidence prerequisites.
