# v0.6 Engineering Freeze Design

## Decision

v0.6 is an evidence-management and engineering-freeze release. It does not
select, purchase, fabricate, energize, or move a robot. The reference robot
continues to contain `engineering_placeholder` components; therefore its v0.6
freeze result must be `not_ready`, with actionable missing-evidence findings.

The release creates a closed, hash-bound package for the information that must
be reviewed before any purchasing decision can be proposed: supplier-document
snapshots, controlled drawings, wiring/protection topology, hazard and safety
function records, verification matrix, inspection plan, and future hardware
test cards. A complete synthetic fixture proves the validator can accept a
well-formed package; it is never presented as a selected physical robot.

## Architecture

`assurance.engineering_freeze` will be a pure-Python, fail-closed layer. It
loads canonical JSON with duplicate-key, byte, depth, and path restrictions;
checks every referenced file hash; and returns a deterministic
`EngineeringFreezeReport`. The report has three derived booleans:

- `procurement_authorized = false` unconditionally;
- `motion_authorized = false` unconditionally;
- `freeze_ready` is true only for a complete review package with no critical
  gap, and is explicitly only a purchasing-decision input.

The package is an evidence graph, not a storage location for proprietary
datasheets or standards. Supplier records carry a public URL, capture date,
local snapshot path/hash, exact manufacturer/part number, reviewed limits, and
claim/component edges. Snapshot content is hash-bound but no network fetch is
trusted at validation time. A stale snapshot, unreviewed limit, unsupported
claim, path escape, or placeholder claim dependency prevents readiness.

Hazards name source, affected phase, severity/probability before and after
controls, controls, verification IDs, and residual disposition. Safety
functions name the initiating event, safe state, independent control path,
test-card reference, and unresolved review boundary. Test cards remain
`planned`; their required site authorization, E-stop, operators, energy and
abort conditions are recorded as future preconditions, not satisfied facts.

## Reference and standards boundary

The reference package includes a standards profile with official public URLs
and applicability questions, but no conformity assertion. ISO 12100:2010
remains published while being revised; ISO 13849-1:2023 is published; ISO
3691-4:2023 applies to driverless industrial trucks and systems; ISO
10218-1:2025 explicitly excludes mobility on mobile platforms, so it cannot
stand alone for this reference robot. Qualified safety and regulatory review
is required to select the final applicable profile.

## Validation and release gate

Tests cover canonical parsing, source/hash drift, directory traversal and
symlink rejection, duplicate IDs, graph integrity, risk monotonicity,
unresolved critical hazards, missing safety/control/test-card links,
placeholder supplier dependencies, and immutable denial of procurement/motion
authorization. The reference fixture is required to fail only with declared
open evidence gaps. v0.6 can ship only with a public audit that says the same;
no fixture may be labelled as an approved BOM, hardware-ready robot, or safety
conformity result.
