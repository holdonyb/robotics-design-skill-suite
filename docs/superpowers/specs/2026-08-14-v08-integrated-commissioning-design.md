# v0.8 Commissioning Evidence Gate Design

## Decision

v0.8 delivers an offline, fail-closed commissioning-evidence gate for a
future controlled low-energy hardware trial. It does not assemble, energize,
connect to, command, or move hardware. The shipped reference contains only an
empty commissioning intake and therefore remains `awaiting_authorization`.

This is deliberately a tooling release, not a claim that the reference robot
has completed integrated commissioning. A real trial still requires explicit
site and motion authority, a bounded area, a reachable E-stop, named roles,
qualified operators, controlled energy limits, and retained original records.

## Scope and alternatives

Three approaches were considered:

1. Add only narrative checklists. This is cheap but cannot detect omitted
   preconditions, stale upstream evidence, or altered results.
2. Build a device-control test runner. This would exceed the release's
   authority boundary and cannot prove that a local host is safe to command a
   real robot.
3. Build a closed, local evidence-intake and replay validator. This is the
   selected option: it gives reviewers a deterministic handoff package while
   keeping every device interface out of the distribution.

## Commissioning package

`commissioning-index.json` is canonical compact UTF-8 JSON and contains a
stable intake ID, a hash-bound design contract, engineering-freeze package,
bench-evidence intake, and an ordered non-empty-or-explicitly-empty list of
phase records. Every external path is a regular local file beneath the index
directory; absolute paths, traversal, symlinks, duplicate records, stale
SHA-256 bindings, noncanonical JSON, oversized files, and extra fields fail
closed.

An empty, exact reference index is valid and returns
`awaiting_authorization`. A populated index must bind the exact design,
freeze, and bench packages, so later commissioning evidence cannot silently
target a different robot or replace component characterization.

## Stage model

The fixed stage order is:

1. `unpowered_inspection` — assembly, wiring, identity, continuity and
   mechanical-limit inspection; no power or command evidence is permitted.
2. `protected_power` — protected power-up with all motion inhibited.
3. `isolated_joint` — one bounded joint mode at a time.
4. `separated_base_arm` — bounded base and arm modes remain separated.
5. `integrated_low_energy` — bounded integrated base/arm mode only after all
   previous stages have passed.

Every record names its phase, test-card ID, authority record ID, two or more
roles, bounded area ID, reachable E-stop ID, explicit energy/speed/torque
limits, watchdog/command-timeout limit, abort criteria, and required evidence
artifacts. Later phases require all earlier phases to have a passing retained
record. A phase may be planned or recorded; a recorded phase must include
hash-bound command/state/stop event traces and a post-test inspection record.
No phase can be retried or overwritten: a failure/abort remains visible and
blocks dependents.

## Evidence and authorization boundary

The validator checks integrity and consistency of records; it cannot establish
that a named human, site, E-stop, or machine was actually present. Therefore
its output distinguishes `validated_commissioning_record` from an externally
attested hardware fact. It never changes `procurement_authorized` or
`motion_authorized` from `false`, including when every submitted trace passes.

`integrated-hardware-tested` is never emitted by v0.8 solely from local JSON
or generated/simulated data. It is reserved for a later release that has a
reviewed external attestation mechanism and actual retained records. v0.8
instead reports the highest validated stage as an intake fact and lists the
missing external authority/attestation dependency explicitly.

Fixture-only inputs may test parsers but receive no commissioning evidence
label. A reference fixture must not include any fabricated command, state,
stop, inspection, or motion data.

## Trace and inspection validation

Recorded phase data is bounded and schema-closed:

- command trace: integer nanosecond timestamp, declared mode, requested
  speed/torque/energy bounded by the phase limits;
- state trace: timestamp, mode, motion-inhibit state, measured bounded values,
  watchdog health, and finite values with monotonic time;
- stop trace: timestamp, initiating event, asserted safe state, and latency;
- inspection record: pre/post identity, wiring/fastener/guard checks and a
  signed-off disposition field.

The validator correlates trace times, requires a tested E-stop and timeout
transition before any motion-capable stage can pass, rejects motion observations
in inhibited stages, rejects limit violations, and checks required post-test
inspection. It stores canonical report data plus source hashes only; it never
opens a serial port, network socket, ROS graph, driver, or actuator.

## Outputs and exit codes

The CLI `validate_commissioning_evidence.py --index …` prints canonical JSON.
It returns:

- `0` for a complete, internally consistent submission, while both
  authorization flags remain false;
- `1` for a structurally valid package with planned stages, missing external
  authorization/attestation, a retained abort/failure, or an incomplete stage;
- `2` for malformed, tampered, unsafe-path, stale, or internally
  contradictory input.

Reports are deterministic, include package/phase findings, phase lineage,
highest validated phase, source hashes, and explicit claim/authority boundary.

## Reference and release criteria

The reference adds an exact empty commissioning index and a raw-data README
that prohibits fabricated measurements. Its validator returns
`awaiting_authorization`, not a hardware, task, or commissioning pass.

Release tests cover canonicalization, paths/symlinks, hash drift, wrong design
or freeze binding, duplicate/skip/reordered stages, fixture-only evidence,
limit and timestamp violations, missing E-stop/timeout/post-inspection traces,
abort retention, malformed nested values, no-traceback behavior, immutable
result records, and both authorization flags. Full-suite, distribution,
installer, and Linux consumer gates remain required.

## Non-goals

v0.8 does not buy parts, create manufacturing files, select vendors, assemble
hardware, power a circuit, issue ROS or motor commands, certify safety,
authenticate human signatures, or claim task performance. Those require
separate external authority and evidence not available to this repository.
