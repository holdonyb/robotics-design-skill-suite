# Hardware Authority Intake Contract

Use this contract before submitting retained commissioning records for a real
robot. It is an evidence-binding mechanism, not a controller, permission
service, purchasing workflow, or motion enable.

## Required external record

Each recorded commissioning phase must bind canonical JSON with a SHA-256 path
record. The object must contain exactly:

```text
schema_version, authority_record_id, authorization_kind,
design_contract_sha256, phase, execution_window, site_id, area_id, estop_id,
roles, limits, watchdog_timeout_ns, attested_by_role, approval_reference
```

`authorization_kind` is exactly `external_human_attestation`. The record binds
one exact design contract, one commissioning phase, inclusive canonical ISO
dates, a site, bounded area, reachable emergency stop, named operator and
observer roles, maximum energy/speed/torque, and a maximum command timeout.
The recorded phase must be no broader than every authorized value.

## Boundary

A valid record only establishes that supplied external evidence is structurally
bound to retained local data. It never grants procurement or motion authority.
Before physical activity, the responsible humans must separately confirm that
the selected hardware, site, bounded area, reachable emergency stop, operator,
observer, energy/torque/speed limits, abort criteria, and timeout are actually
available and appropriate at the time of execution.

Simulation, calibration, a hash, an approval reference, or a passing
commissioning validator cannot replace that decision. The validator reports
`procurement_authorized: false` and `motion_authorized: false` in every case.

## Validation

Run `scripts/validate_commissioning_evidence.py` on a populated commissioning
index. The validator rejects missing, noncanonical, stale, symlinked, wrong
design, wrong phase, expired, scope-mismatched, or limit-exceeding records.
Retain failures; do not edit them into passing evidence.
