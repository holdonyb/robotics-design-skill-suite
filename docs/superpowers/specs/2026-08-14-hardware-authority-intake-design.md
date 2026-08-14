# Hardware Authority Intake Design

## Problem

Commissioning records currently retain only a free-form `authority_record_id`.
It cannot prove that the submitted external authorization covers the recorded
phase, exact design, date, area, emergency stop, people, or limits. This is a
documentation gap, not permission to control hardware.

## Decision

Use a canonical, hash-bound local authority record for every recorded
commissioning phase. The record is externally supplied evidence that the
validator verifies structurally and cross-binds to its retained test record.
It does not issue authority: every report still derives
`procurement_authorized: false` and `motion_authorized: false`.

The authority record has exactly these fields:

```text
schema_version, authority_record_id, authorization_kind,
design_contract_sha256, phase, execution_window, site_id, area_id, estop_id,
roles, limits, watchdog_timeout_ns, attested_by_role, approval_reference
```

`authorization_kind` is the literal `external_human_attestation`. The date
window is inclusive ISO `YYYY-MM-DD`; the commissioning phase supplies its
`execution_date`. Limits are maximum energy, speed, and torque. The phase must
not exceed them, its watchdog timeout must not exceed the authorized maximum,
and its site/area/E-stop/roles must exactly match.

## Integration and safety

`authority_record_id` becomes `authority_record`, a `{path, sha256}` binding.
The commissioning evaluator loads canonical bytes, rejects missing, stale,
symlinked, malformed, expired, wrong-phase, wrong-design, or scope-mismatched
records, and returns deterministic `COMM.AUTHORITY_*` errors. The populated
commissioning CLI supplies the exact hash of its already bound design contract.
The empty reference intake remains unchanged and continues to return
`awaiting_authorization`.

No local JSON, hash, approval reference, or test result can authorize a person
to purchase, energize, or move a robot. Actual action still requires the
separate explicit operator/site/E-stop decision at execution time.

## Verification

Focused tests will cover happy-path cross-binding, forged IDs, path/hash,
noncanonical input, wrong design/phase/date/site/area/E-stop/roles/limits, and
the permanent authorization-negative report fields. Existing commissioning CLI
tests will prove the design hash reaches the authority checker. Full-suite,
distribution, dry-run, compile, and diff checks remain required.
