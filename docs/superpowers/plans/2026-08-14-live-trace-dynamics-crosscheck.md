# Live Trace Dynamics Crosscheck Implementation Plan

Goal: reject a retained live Gazebo trace whose wheel motion and odometry do not agree with the receipt-bound physical profile.

Architecture: extend the pure live-trace module with a closed adapter from named wheel positions to the existing primary and independent planar backends. Retain the result in the canonical bundle and require it before runtime publication.

## Task 1: Pure wheel and odometry crosscheck

Files: modify skills/robotics-design/scripts/assurance/simulation/live_trace.py and tests/test_simulation_live_trace.py.

- [ ] Write failing tests for matching wheel position and odometry, missing/reordered wheels, excess wheel speed, and a 0.2 m odometry mismatch.
- [ ] Run python -m unittest tests.test_simulation_live_trace -v and observe the missing crosscheck function.
- [ ] Implement crosscheck_live_dynamics: derive rates from wheel position deltas, bind model to workspace receipt and trajectory to canonical command SHA, run both existing backends, and compare their base distance/yaw against odometry with 0.05 m plus 10 percent and 0.10 rad tolerances.
- [ ] Run python -m unittest tests.test_simulation_live_trace tests.test_simulation_backend -v; commit feat: cross-check live trace dynamics.

## Task 2: Evidence publication

Files: modify scripts/validate_live_simulation_trace.py, tests/test_simulation_live_trace.py, and regenerate release/v1.1-release-contract.json.

- [ ] Write a failing test requiring a passed dynamics_crosscheck in validation.json and a CLI call before publication; a rehashed missing field must fail retained validation.
- [ ] Implement fail-closed publication and exact retained validation without changing simulated or hardware firewall semantics.
- [ ] Run full unittest discovery, distribution validation, release validator, installer dry run, compileall, and diff-check. Push a draft PR, require isolated Jazzy/Harmonic CI and inspect its retained receipt before merging.

## Plan self-review

This joins evidence already derived from one MCAP; it does not claim simulator fidelity or hardware behavior. Missing or disagreeing data blocks evidence rather than weakening the check.
