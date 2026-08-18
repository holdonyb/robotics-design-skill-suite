# Trusted Policy Trace Design

## Decision

Training and backend evaluation will consume a `trusted_policy_trace_v1`
bundle, not an arbitrary trace bundle.  Its authority is rooted in a
hash-bound reference scenario registry and an external registry receipt that
is supplied by the benchmark owner, never by the policy callback or a caller
choosing a local directory.

Each trace embeds a canonical policy digest and the complete sampled action
sequence.  A bounded deterministic runner generates state samples from those
actions.  Replay recomputes the trajectory outcome and reward inputs, then
checks that the trace action sequence and policy digest equal the evaluation
request.  Therefore an action that is merely in range cannot receive another
policy's successful trace or reward.

## Trust chain

```text
approved scenarios.json SHA-256 + external registry receipt
  -> compiled scenario identity
  -> policy digest + canonical action sequence
  -> runner-generated trace bundle + external trace receipt
  -> replayed outcome, reward, backend crosscheck
```

`TrustedScenarioRegistry` contains an exact registry file path, SHA-256,
external receipt, model/trajectory/environment hashes, and all ten compiled
scenario IDs.  It is loaded once by the benchmark, validates the external
receipt before any assignment, and becomes the sole authority allowed to issue
trace assignments.  A trace assignment names the registry receipt, scenario
ID, policy digest, trace bundle path, and trace receipt.  A mismatched registry,
scenario, policy, action digest, bundle, or receipt is an error.

## Causal runner

The portable reference runner is deliberately narrow.  It accepts only the
declared base action at every fixed sample tick and emits wheel rates,
zero-target joint positions, and the canonical action record.  It is not a
claim of Gazebo fidelity or policy training convergence.  It proves the
evaluation plumbing: the reward and safety metrics are generated from the
specific bounded action sequence, not supplied by a callback or borrowed from
another trace.

The existing Jazzy/Harmonic runner can later issue the same trace format after
actual controller execution.  Its Linux receipt must still validate against
the same registry and policy/action identity.

## Replay and metrics

Trace JSON gains closed fields `policy_sha256` and `actions`; every action has
an integer timestamp, `linear_m_s`, and `angular_rad_s`.  Replay verifies the
action grid, hard action bounds supplied by the trusted evaluation contract,
and exact correspondence with the state timestamps.  For the current reference
fixture, final joint error is explicitly zero-target-only and is recomputed as
`max(abs(final_position))`; non-zero trajectory targets require a future schema
revision with explicit target samples.

Reward uses only replayed action/state values.  `wheel_progress` is signed
base-wheel travel and `wheel_effort` is the integrated wheel-rate-squared
proxy.  Both are tied to a trace whose policy/action identity has been checked.

## Runtime closure and claims

The v1.1 delivery profile must bind the entire source closure needed to load
the registry, publish/replay the trace, derive features, evaluate training,
perform backend comparison, admission, calibration, and bundle validation.
The closure is tested by tampering every listed runtime source in a copied
repository and requiring release validation to fail.

All resulting records remain `simulated/not_justified`; no policy, trace,
registry, reward, or backend agreement authorizes procurement, controller
activation, hardware motion, or a hardware-performance claim.
