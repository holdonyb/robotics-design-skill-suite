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
non-finite values, guessed units, dimension mismatches, missing keys, and
unknown keys are errors; every value/tolerance object contains exactly
`value` and `unit`.
Optional `observation` binds the owned value to a normalized artifact location
using `artifact:ID#normalized.path`; the drift gate compares it in SI units.

Supported evidence levels are `assumed`, `generated`, `parsed`, `calculated`,
`simulated`, `bench-tested`, `integrated-hardware-tested`, `task-validated`,
and `certified`. Ordering supports comparison only; it never promotes a claim.
The quantity level may equal or conservatively downgrade its source evidence
level, but it may not exceed it.

## Components and architecture

A component has `id`, `role`, lifecycle `state`, unique `interfaces`, and one
or more explicit `bindings`. A binding names the exact architecture
responsibility it realizes: `feature:ID`, `drive:ID`, `actuator:ID`, `moving_cable:ID`, or
`safety_function:ID`. Motor, reducer, and bearing records cannot be shared
across multiple actuators; each declared actuator therefore has an auditable
physical load path instead of inheriting a global role checkbox.
States are `verified_part`, `qualified_substitute`, `engineering_placeholder`,
or `missing`. Verified and substitute records additionally use manufacturer,
part number, absolute HTTP(S) source URL, ISO source date, `source_evidence`,
limits and supported claims. Verified and substitute components require a
non-empty `supports_claims` edge. Their evidence `kind` is exactly
`component_catalog_v1`, with evidence level exactly `parsed` or `certified`;
calculated, simulated, and test labels cannot substitute for catalog parsing.
The bounded JSON snapshot records schema version, locator, observation date,
and component ID/manufacturer/part number/typed limits. Runtime validation
compares every declared component limit to that hash-bound snapshot in SI
units. Catalog roots, component records, role limit names, and typed limit
objects are recursively closed; a typed limit contains exactly `value` and
`unit`. Every limit is a role-approved `quantity:ID` reference owned by that
component and sourced from that same evidence.

Architecture contains string lists: `features`, `drive_units`, `actuators`, `moving_cables`,
and `claimed_safety_functions`. The ledger maps these declarations to mandatory
component roles; absence from the schema never means absence from the robot.
Unknown features or claimed safety functions remain structurally valid for
forward transport but are physically indeterminate until a role contract is
implemented.

## Artifacts, analyses, and evidence

An artifact has `id`, `kind`, manifest-relative non-escaping `path`, and
lowercase SHA-256. Native URDF and bounded `declared_json` observation artifacts
have semantic adapters; other kinds remain hash-bound until an adapter is
supplied. An analysis has `id`, plug-in name, explicit `covers` edges, and an
`inputs` object.
Inputs may nest objects/lists and non-empty identifiers, but every physical
number is a typed reference such as `quantity:Q-MASS`; bare numeric literals
are forbidden. Known plug-ins close both input shape and expected dimensions.
Architecture-derived plug-in coverage and reciprocal plug-in-to-architecture
scope checks are required. Each drive and actuator requires its own thermal
analysis, and drivetrain/arm/battery rating inputs must be owned by the exact
covered component and equal the corresponding named `limits` reference. Known
plug-ins reject unrelated coverage types instead of skipping checks when an
extra scope is present. A physical contract with no applicable analysis is
indeterminate.

Evidence has `id`, optional semantic `kind`, `level`, a path/SHA-256 `source`, and unique `supports`
references. Optional `locator` and `observed_date` record the external URL and
capture date; they are mandatory through the component provenance edge for
verified parts and qualified substitutes. Every quantity's selected evidence source must explicitly include
that `quantity:ID` in `supports`; merely naming an evidence record is not a
closed evidence graph. `certified` evidence additionally requires a non-empty external
`authority` and `certificate_id`; the suite never creates those values.

Schema validation establishes shape and references. File existence, digest
freshness, component completeness, artifact semantics, physical analyses and
promotion are separate cumulative gates.
