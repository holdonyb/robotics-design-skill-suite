# Live Trace Dynamics Crosscheck Design

## Decision

A retained live Gazebo trace is accepted only when receipt-bound wheel motion, the two portable dynamics calculations, and Gazebo odometry agree within declared simulation-only tolerances. A simulator producing plausible odometry from geometry or controller parameters that no longer match the bound profile therefore fails closed.

## Derived input

The pure validator consumes the existing closed capture and profile. It extracts named left/right wheel positions, rejects missing, reordered, or duplicate drive joints, and derives piecewise-constant wheel rates from deltas and bag timestamps. Initial/final odometry supplies an independently observed displacement and yaw. SHA-256 over canonical commands is the trajectory identity; the workspace receipt is the model identity.

Both existing dynamics implementations consume this input. Their interval comparison must pass, then each integrated distance/yaw must agree with observed odometry using 0.05 m plus 10% distance tolerance and 0.10 rad yaw tolerance. Those tolerances are simulation crosscheck bounds, never performance, calibration, or hardware claims.

## Evidence and rejection

The record stores profile sources, command identity, backend outputs, observed odometry, tolerances, and a derived passed or failed status. Malformed series, nonfinite data, speed violation, backend error, or disagreement rejects the capture. It is stored under dynamics_crosscheck in validation.json, required by retained-bundle validation, remains simulated, and can never change hardware_promotable.

## Verification

Portable tests cover matching straight motion, missing/reordered wheels, speed violations, odometry disagreement, and receipt tampering. Isolated Jazzy/Harmonic CI must retain a passed crosscheck beside raw MCAP. The existing no-network container, ROS domain 139, and localhost-only boundary remain mandatory.
