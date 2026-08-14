# Live Trace Turning Design

## Decision

Extend the retained Jazzy/Harmonic controller trace from straight-only motion to one bounded forward-left arc: `linear.x = 0.10 m/s`, `angular.z = 0.20 rad/s`, published for the existing two-second recording window in the isolated container. This remains a simulated controller/odometry consistency check, never a task, calibration, safety, or hardware claim.

## Evidence model

Joint state and odometry retain their ROS header simulation times; command samples retain bag receive times because the bounded publisher emits a zero header timestamp. The dynamics crosscheck derives wheel rates from joint-state time and computes observed travel as the sum of consecutive odometry XY chord lengths. It accumulates normalized consecutive yaw deltas, so an accepted turn may cross the `-pi`/`pi` representation boundary without becoming a false large rotation.

Both portable integrations must independently agree with the odometry path length and unwrapped yaw under the existing simulation-only tolerances. The CLI gets an explicit `--require-turning` mode for the CI gate: a positive angular command and a matching nontrivial observed yaw are both mandatory. Generic retained-trace validation remains capable of checking a straight trace, but the shipped live gate must invoke the stricter mode.

## Rejection and verification

Malformed timestamps, zero/contradictory turning command, zero/opposite measured yaw, nonfinite samples, backend disagreement, or either backend's odometry error reject the capture. Portable tests cover curved path length rather than endpoint chord, wrapped yaw, and required-turn failures. The isolated CI artifact must contain a passed `dynamics_crosscheck` with nonzero observed yaw while retaining the raw MCAP hash and `hardware_promotable:false` firewall.
