# Trace-Bound Backend Crosscheck Design

## Decision

The portable simulation benchmark will perform its primary/independent dynamics comparison for every receipt-validated replay, using data derived from that replay rather than a handwritten dynamics fixture. A backend result is evidence only for the exact `(scenario_id, model_sha256, trajectory_sha256, trace_sha256)` it consumed.

## Data flow

`replay_trace_bundle` remains the trust boundary for a trace receipt. The benchmark converts each returned `SimulationResult` to a closed backend input containing its timestamps, wheel-state series, final joint positions, model hash, and trajectory hash. Conversion rejects missing, nonnumeric, or nonfinite wheel state before either backend is called.

The primary kinematic implementation and independent planar-dynamics implementation consume the same derived input. Their comparison is retained only when metric intervals overlap within explicit, metric-specific tolerances. The benchmark emits one inspectable backend record per scenario, including scenario id, trace hash, consumed model/trajectory hashes, both statuses, comparison status, and comparison metrics. Adapter failure, hash mismatch, or comparison failure makes the benchmark a valid nonzero result rather than silently omitting the crosscheck.

The static parameters needed by the bounded planar model (wheel geometry, mass, slope, braking, and joint target/limit) remain explicitly declared in one closed benchmark profile. They are reported as a calculated, portable synthetic check; this creates no Gazebo or hardware claim.

## Invariants

- Every replayed scenario has a backend record in deterministic scenario-id order.
- A record's hashes and final joint state originate from the exact replay result.
- `trace_sha256` prevents a report from relabeling dynamics evidence as belonging to another receipt.
- Malformed wheel state raises `BenchmarkError`; neither backend sees a partial trace.
- Backend disagreement fails the benchmark even when replay metrics passed.
- The existing hardware firewall remains: `hardware_promotable` is always false.

## Verification

Focused tests prove per-replay binding, missing-wheel fail-closed behavior, and a real primary/independent disagreement. Existing backend unit tests establish the adapters use distinct integration methods. The full suite, release validator, distribution validation, and installer dry-run remain release gates.
