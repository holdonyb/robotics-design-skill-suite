# Robot Design Contract Schema v1

Schema v1 is a closed, UTF-8 JSON contract. Unknown fields are errors. IDs
match `^[A-Za-z][A-Za-z0-9_.-]*$`; references use a typed `kind:ID` string.
Incompatible changes require an explicit migration and a new schema version.

## Root

All fields are required: `schema_version` (`1`), `candidate_id`, `status`
(`draft`, `rejected`, or `promoted`), and the collections `requirements`,
`assumptions`, `quantities`, `components`, `architecture`, `artifacts`,
`analyses`, and `evidence`. Collection IDs are unique within their collection.

## Requirements and assumptions

A requirement has `id`, `statement`, `verification`, and `owner`. An assumption
has `id`, `statement`, `confidence` (`low`, `medium`, or `high`), `owner`,
`validation`, and `decision_deadline`. Owners are `project:system`, an existing
`artifact:ID`, or an existing `component:ID`.

## Quantities

A quantity has `id`, `dimension`, explicit `value` (`{"value": number,
"unit": string}`), `owner`, `source` (`evidence:ID`), and `evidence_level`.
Optional `tolerance` uses the same dimension. Bare numbers, booleans,
non-finite values, guessed units, and dimension mismatches are errors.

Supported evidence levels are `assumed`, `generated`, `parsed`, `calculated`,
`simulated`, `bench-tested`, `integrated-hardware-tested`, `task-validated`,
and `certified`. Ordering supports comparison only; it never promotes a claim.

## Components and architecture

A component has `id`, `role`, lifecycle `state`, and unique `interfaces`.
States are `verified_part`, `qualified_substitute`, `engineering_placeholder`,
or `missing`. Verified and substitute records additionally use manufacturer,
part number, source URL/date, limits and supported claims as enforced by the
ledger gate.

Architecture contains string lists: `features`, `actuators`, `moving_cables`,
and `claimed_safety_functions`. The ledger maps these declarations to mandatory
component roles; absence from the schema never means absence from the robot.

## Artifacts, analyses, and evidence

An artifact has `id`, `kind`, manifest-relative non-escaping `path`, and
lowercase SHA-256. An analysis has `id`, plug-in name and an `inputs` object
whose values are typed references such as `quantity:Q-MASS`.

Evidence has `id`, `level`, a path/SHA-256 `source`, and unique `supports`
references. `certified` evidence additionally requires a non-empty external
`authority` and `certificate_id`; the suite never creates those values.

Schema validation establishes shape and references. File existence, digest
freshness, component completeness, artifact semantics, physical analyses and
promotion are separate cumulative gates.
