# Trace-First Simulation Evaluation Design

## Decision

The portable v0.5 evaluator will stop accepting outcome fields from a policy
callback.  A callback may produce only a bounded base action.  Reward terms,
hard joint-error checks, and motion features are derived from receipt-validated
simulation trace samples by a single pure extractor.

The existing independent dynamics crosscheck will consume the same extractor
output.  It remains a simulation-only consistency check: neither a passing
replay, a policy score, nor agreement between portable backends changes
`hardware_promotable`, removes an analytical blocker, or authorizes motion.

## Why this boundary

Three alternatives were considered.

1. Keep callback-reported `mean_reward` and `final_joint_error_rad`.  This is
   compact but lets an untrusted callback create a passing score disconnected
   from the exercised trace.
2. Add an opaque generic simulator interface.  That would hide the actual
   trace and make receipt/provenance validation optional.
3. Use a closed replay-feature adapter as the only outcome source.  This is
   selected because its input is already receipt-validated, bounded, and
   replayable on Windows and Linux.

## Architecture

`assurance.simulation.replay_features` owns one immutable `ReplayFeatures`
record.  It accepts only a replay result returned by `replay_trace_bundle` and
recomputes, with strict finite/time-series checks:

- trace/model/trajectory provenance;
- canonical joint order and final replayed joint error;
- elapsed time and per-wheel signed travel;
- wheel-effort proxy from the sampled wheel-rate series; and
- the final trace-native observation for policy evaluation.

The adapter rejects a malformed result, missing wheel state, non-finite value,
wrong-width sample, non-monotonic timestamp, duplicated metric, or a replay
whose status is not `passed`.  It does not accept a caller-provided score.

`evaluate_policy` receives a closed sequence of trace assignments, one for
every deterministic train, evaluation, and held-out case.  It derives each
observation from that assigned replay, calls the policy only for the two base
action fields, and enforces the action limits.  `final_joint_error_rad` leaves
the callback API; the hard constraint uses the trace-derived value.  Visible
reward weights apply to trace-derived signed wheel progress and wheel-effort,
not to a callback claim.  The result binds all consumed trace hashes and stays
`simulated/not_justified`.

`validate_simulation_bundle.py` assigns each compiled replay explicitly to
one evaluation case.  The backend adapter imports the shared feature extractor
instead of independently re-parsing `samples`, so a crosscheck record and a
training record name the identical trace receipt.  The current synthetic traces
remain an evaluator-pipeline fixture, not evidence that a policy caused their
motion; that limitation is represented by `not_justified`.

## Error handling and compatibility

All public boundaries raise `TrainingError` or `BenchmarkError` with an
actionable field name; no malformed mapping may escape as `KeyError`,
`TypeError`, or a traceback.  The training-contract schema changes from the
ambiguous `progress`/`energy` weights to
`wheel_progress`/`wheel_effort`; the reference contract is regenerated with
the same visible baseline semantics.  There is intentionally no compatibility
fallback for legacy callback outcome fields because silently accepting them
would retain the trust boundary being removed.

## Verification

Focused tests must prove that a high callback claim cannot improve reward,
that trace joint error blocks a policy even when its action is in bounds, that
reordered/missing/non-finite samples fail closed, and that backend and training
both bind every replayed trace hash.  The reference benchmark must keep ten
passed replays, ten passed crosschecks, a simulated/not-justified training
record, and `hardware_promotable: false`.
