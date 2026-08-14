# v0.9 Task and Robustness Evidence Design

## Decision

v0.9 adds a local, fail-closed task-and-robustness evidence intake. It validates
the structure, integrity, traceability, and deterministic summary of future
task, fault, endurance, and simulation-to-real comparison submissions. It does
not operate a robot, acquire measurements, issue commands, infer a physical
result, or emit `task-validated` from self-authored local files.

The reference robot remains a vertical fixture. Its shipped v0.9 index is
empty, reports `awaiting_authorization`, and keeps every authorization and
physical-performance claim false.

## Why this boundary

Three designs were considered:

1. A task-score-only schema. This is compact but permits a hand-written score
   to hide failed trials, faults, and raw traces.
2. A generic experiment database. This would be broad but would have no
   bounded consumer or robot-specific safety semantics.
3. A closed task-evidence dossier linked to v0.3-v0.8 inputs. This makes every
   claimed trial, fault injection, endurance sample, comparison input, and
   calculation reviewable while keeping empirical claims outside local control.

v0.9 selects option 3.

## Scope

The release owns five layers:

```text
design contract + engineering freeze + accepted bench intake + commissioning
  -> closed task protocol and approved test envelope
  -> hash-bound raw trial, fault, endurance, and comparison traces
  -> deterministic aggregate, fault-disposition, and residual checks
  -> evidence-complete dossier or actionable blocking report
```

The dossier is a prerequisite for an externally witnessed task-validation
decision. It is never that decision.

## Input contract

`task-evidence-index.json` is canonical UTF-8 JSON with exactly one of two
closed roots:

- Empty intake: `schema_version`, `task_evidence_id`, `packages`.
- Populated intake: the empty fields plus hash-bound `design_contract`,
  `freeze_package`, `bench_index`, `commissioning_index`, and `task_protocol`.

Every bound file is a regular local non-symlink path below its index directory,
uses a forward-slash relative path, and carries an exact SHA-256. A path escape,
duplicate hash, noncanonical JSON, malformed nested collection, or read failure
is an invalid invocation (`2`), never a traceback.

All upstream bindings must resolve to the same design-contract SHA-256. The
freeze must be internally ready, every bench package must be accepted at
`bench-tested` and not fixture-only, and commissioning must contain every
recorded stage with no error or indeterminate finding. A source that is merely
nonempty or self-consistent does not clear an upstream blocker.

## Task protocol

The protocol is an independently hash-bound, closed schema-v1 record. It owns:

- an immutable task identifier and ordered phase identifiers;
- a bounded operating-envelope grid whose exact axes, SI units, and allowed
  values are declared before trials are evaluated;
- required repetitions for each envelope point and fault profile;
- task metrics with direction, finite threshold, explicit unit, and
  success/failure classification;
- declared fault profiles, each with a safe-state expectation and required
  recovery disposition;
- endurance sampling interval, maximum duration, and maximum sample count;
- comparison quantities and absolute/relative residual limits for simulation
  versus retained observation.

The protocol rejects nonfinite values, boolean numbers, duplicate identifiers,
unknown units, empty dimensions, undefined fault profiles, unbounded ranges,
and ambiguous success rules. It cannot be silently edited after traces are
recorded because the index binds its bytes.

## Package and trace model

Each package declares exactly one protocol envelope point and one trial kind:
`nominal`, `fault`, `endurance`, or `comparison`. It binds a local canonical
metadata record plus local raw CSV or JSON traces. A package has a unique ID;
raw hashes, trial IDs, and `(envelope, repetition, fault)` identities are
globally unique.

Nominal trials bind command, state, and task-observation traces. Every trace
has nonnegative strictly increasing nanosecond timestamps, bounded sample
count/bytes, finite SI values, and a terminal disposition. The evaluator checks
that required phases occur in order, commanded and observed speed/torque/energy
stay inside the protocol limit, watchdog state remains healthy, and an abort
is retained rather than deleted.

Fault trials additionally bind an injected fault profile, observed detection,
safe-state transition, recovery record, and post-test inspection. A fault
cannot be counted as passed merely because its nominal task metric passes;
its required safe state and recovery disposition must match the protocol.

Endurance packages bind evenly sampled health data. Gaps, duplicates, early
termination without an abort record, nonfinite values, or a sample count beyond
the declared bound reject the package. The evaluator calculates only declared
health trends and threshold crossings; it does not extrapolate lifetime.

Comparison packages bind a simulation trace receipt and an observed trace with
the same protocol point. The evaluator performs deterministic time-aligned
residual calculations over named quantities. It retains raw residual values,
coverage, and the worst error. Missing alignment, mismatched units, or a
residual over the predeclared bound blocks evidence completeness.

## Deterministic dossier result

The result is an immutable `TaskEvidenceReport` containing sorted findings,
protocol hash, coverage counts, per-metric aggregate statistics, fault
dispositions, endurance summaries, and comparison residuals. Valid statuses
are:

- `awaiting_authorization`: empty intake or complete syntax with a missing
  externally authorized record;
- `rejected`: schema, integrity, coverage, limit, fault, or residual error;
- `evidence_complete`: all locally verifiable requirements are met.

The status is derived from findings, never supplied by a caller. Reports always
serialize `procurement_authorized: false`, `motion_authorized: false`, and
`task_validated: false`. There is no local API state that can return true for
those fields.

`evidence_complete` means only that the retained dossier agrees with the
declared protocol. An actual task-validation conclusion needs an external
authority record, controlled site, qualified operators/observers, reachable
E-stop, independent retention/attestation, and a qualified review. Those are
outside this repository and must not be generated to make a test pass.

## Validator behavior

The public command is:

```bash
python skills/robotics-design/scripts/validate_task_evidence.py \
  --index reference/mobile-manipulator/task-evidence/task-evidence-index.json
```

Exit `0` means an `evidence_complete` local dossier; exit `1` means a valid
input with missing authorization, failed trials, or indeterminate evidence;
exit `2` means malformed, tampered, path-unsafe, or unreadable input. The CLI
outputs canonical JSON to stdout and a concise `ERROR:` diagnostic to stderr
on exit `2`; it never prints a traceback for user input.

## Testing and release gates

Tests must be test-first and cover:

- canonical root/path/hash/symlink/duplicate/malformed-nested attacks;
- design/freeze/bench/commissioning binding mismatch and self-consistent
  rejected upstream evidence;
- protocol unit, finite-value, closed-schema, axis, repetition, and threshold
  attacks;
- trace timestamp/order/limit/abort/fault/recovery/endurance/residual attacks;
- deterministic ordering/statistics across input permutations;
- no mutable report fields, no forged status, and no true authorization or
  `task_validated` field;
- empty reference behavior, public hygiene, full cross-platform suite,
  distribution validation, installer dry run, compile check, and diff check.

The Jazzy/Harmonic consumer gate remains a required release check but does not
convert any synthetic or local evidence package into a physical claim.

## Non-goals

v0.9 does not select suppliers, place an order, configure a physical safety
controller, control hardware, run a robot, certify a system, predict lifetime,
or replace a qualified safety/engineering review. It does not create fake raw
traces, calibration records, external authority, or independent attestation.
