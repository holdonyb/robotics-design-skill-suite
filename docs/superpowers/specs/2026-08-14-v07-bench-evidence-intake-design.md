# v0.7 Bench Evidence Intake Design

## Decision

v0.7 accepts and validates real bench-evidence packages but cannot create,
modify, replay as measurement, or promote invented measurements. The reference
robot ships only a valid empty intake index and is therefore not bench-tested.

## Evidence contract

Each package binds a component, one approved test-card identity, instrument
records, a raw CSV file, its SHA-256, CSV columns/units, sample count and time
range, an operator identity, a site identity, and an observed date. Instruments
require an independent calibration record with certificate identifier, valid
date interval, source file/hash, and measured quantity compatibility. Raw data
must be regular local files under `raw/`, UTF-8, bounded, header-exact,
strictly increasing timestamps, finite numeric cells, and must match its
declared summary.

An intake report returns `accepted`, `rejected`, or `awaiting_authorization`.
Only an accepted, hash-bound non-fixture package earns the `bench-tested` evidence label;
that label supports only its explicit component and measurement claim. It is
not a purchasing approval, integrated hardware result, task result,
certification, energization, or motion authorization.

## Authorization boundary

Test cards in an intake package must be `approved_for_recording`, name an
authority, and state that physical execution still requires per-run site
authority, reachable E-stop, operators, energy bound and abort criterion. The
validator confirms a record exists; it does not satisfy these real-world
preconditions and has no device/control interface.

## Validation

Tests inject path traversal, symlink, hash/summary drift, duplicate IDs,
invalid calibration windows, wrong units/columns, non-monotonic timestamps,
incomplete test cards, and forged evidence-level fields. A complete synthetic
fixture proves the parser only; it is labelled `fixture_only` and cannot be
used to claim a reference measurement.
