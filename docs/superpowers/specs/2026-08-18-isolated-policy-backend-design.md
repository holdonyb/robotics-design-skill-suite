# Isolated Policy Artifact Backend

## Decision

Portable reference evaluation will add `policy_artifact_v1` rather than treating
an arbitrary in-process Python callable as an authenticated policy.  The first
supported artifact is a closed affine-plus-tanh controller over the reference
robot's six joint positions and two wheel-rate observations.  Its SHA-256 is
the canonical artifact bytes, and the training contract must name that exact
digest.

The evaluator launches a fresh stdlib-only worker process for each bounded
action request.  It sends the already verified canonical artifact object and
canonical observation over standard input, imposes the contract-derived timeout,
accepts one closed canonical action response, and retains no worker state.  The
worker process is an execution boundary that prevents ordinary callback code
from mutating evaluator modules, registry objects, geometry, reward logic, or
trace publishing state.

This is process separation, not a claim of a hostile-code sandbox.  The initial
artifact format is deliberately declarative and has no imports, executable file
paths, shell commands, network access, or dynamic language expressions.  A
future native/model backend needs a separately reviewed container or OS sandbox
and must not reuse the `policy_artifact_v1` evidence level.

## Artifact contract

`policy_artifact_v1` is canonical UTF-8 JSON with exactly:

```json
{
  "schema_version": 1,
  "kind": "affine_tanh_v1",
  "policy_id": "policy-reference-baseline",
  "observation_order": ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6", "left_wheel_rad_s", "right_wheel_rad_s"],
  "linear": {"bias": 0.2, "weights": [0, 0, 0, 0, 0, 0, 0, 0]},
  "angular": {"bias": 0, "weights": [0, 0, 0, 0, 0, 0, 0, 0]}
}
```

All numeric values are finite and bounded.  The action is `tanh(bias + dot(weights,
observation))`, so the protocol cannot emit a nonfinite result.  The parent
still applies the training contract's hard linear/angular bounds after replay.

The artifact contains no self-reported digest.  `load_policy_artifact(path)`
requires canonical bytes, rejects symlinks and oversized files, validates the
closed schema, and derives the SHA-256.  `evaluate_policy_artifact` rejects a
contract whose `artifact_sha256` differs from that derived digest.  Every
per-case trace digest includes this actual artifact digest, the case, and the
full action sequence.

## Worker protocol

The parent invokes the repository-owned worker script directly with the host
Python executable, an empty temporary working directory, a scrubbed environment,
and a per-request timeout capped by the remaining declared wall-time.  One
request and one response are JSON lines:

```text
{"artifact":{...},"observation":{"joint_rad":[...],"left_wheel_rad_s":0,"right_wheel_rad_s":0}}
{"linear_m_s":0.1973753202,"angular_rad_s":0}
```

Any extra stdout line, stderr output, noncanonical JSON, malformed result,
timeout, nonzero exit, or artifact/observation mismatch is a fail-closed
`PolicyBackendError`.  The worker cannot author a trace, receipt, promotion, or
score.  The evaluator remains the sole owner of profile loading, fault
disposition, deterministic runner state, reward, and hardware firewall.

## Migration and evidence boundary

`evaluate_policy` remains a test-only trusted-callback compatibility path until
all callers migrate.  The public reference benchmark migrates to
`evaluate_policy_artifact` and uses a retained baseline artifact under
`reference/mobile-manipulator/simulation/policies/`.  The release profile binds
the worker, loader, artifact, updated training contract, and evaluator.

Results remain `simulated/not_justified`.  This backend neither trains a neural
policy nor proves Gazebo fidelity, task success, safe control, bench behavior,
or hardware performance.
