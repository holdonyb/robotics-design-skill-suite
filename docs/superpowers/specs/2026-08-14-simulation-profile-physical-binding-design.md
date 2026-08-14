# Simulation Profile Physical Binding Design

## Decision

The portable backend's physical profile will no longer use handwritten wheel
geometry, mass, speed, or deceleration constants. It will extract its bounded
level-ground values from the receipt-validated ROS workspace consumed by the
live gate.

## Sources and extraction

The profile loader first verifies `simulation/ros-workspace-manifest.json` with
its external receipt. It then reads only three declared consumers:

- the description xacro: only top-level actual link, wheel-macro invocation,
  and joint declarations are eligible; unexpanded macro/conditional bodies are
  ignored. From those declarations it extracts left/right wheel radius,
  wheel-joint lateral origins, and numeric simulator inertial mass;
- `controllers.yaml`: wheel radius and separation, which must exactly agree
  with the xacro geometry;
- Nav2 velocity-smoother settings: positive linear limit and braking magnitude.

After verifying the external workspace receipt, the loader takes a byte snapshot
of the manifest and each consumed file, verifies every snapshot SHA-256 against
that manifest, and parses only those retained bytes. The loader calculates total simulator mass by summing numeric declared inertial
mass records, calculates wheel separation from the two wheel-joint origins, and
calculates maximum wheel rate as `max_linear_m_s / wheel_radius_m`. It rejects
missing, duplicated, nonfinite, nonpositive, or mismatched values before a
backend runs. The profile retains the existing explicit level-ground scope and
has evidence level `parsed`; it is not a vendor or physical test claim.

## Evidence binding

Every backend crosscheck will include a `profile` object containing the exact
ROS workspace receipt, the three consumed relative paths and their observed
SHA-256 values, and the normalized calculated values. This prevents a benchmark
report from silently using a physical profile from a different ROS workspace.

## Verification

Tests will establish the reference values (0.15 m radius, 0.68 m separation,
140.2 kg simulator mass, 0.8 m/s² braking and 0.4/0.15 rad/s wheel limit), reject
xacro/controller disagreement and tampering after a self-rehashed local manifest,
ensure that an unexpanded xacro macro cannot supply a profile, reject a source
replaced after manifest validation, and ensure every crosscheck reports the profile receipt. Full release validation
will re-sign all affected reference and release receipts.
