# v1.0 Reproducible Public Delivery Design

## Decision

Version 1.0 is the public, reproducible closure of the existing evidence-gated
suite. It does not turn the empty reference hardware intakes into measurements,
and it does not authorize procurement, fabrication, energization, device access,
or motion. The release instead makes the complete software and evidence surface
machine-checkable, while preserving every unfulfilled hardware dependency as an
explicit non-claim.

This is the selected middle path among three alternatives:

1. Tag the current tree with documentation only. This is rejected because a
   future documentation or manifest drift could make a claimed v1 delivery
   unreproducible.
2. Create a closed release-integrity contract and validate it in the normal
   public distribution gate. This is selected because it gives users a concrete,
   replayable release boundary without fabricating unavailable physical evidence.
3. Complete hardware build and field validation before v1. This is not
   authorized and cannot be substituted with simulation or generated records.

## Scope

The v1 contract will bind the public artifacts required to reproduce the suite:

- exact suite version and supported interpreter baseline;
- the public manifest and the ten installed skill destinations;
- all local validator entry points for physical, hypothesis, simulation, bench,
  commissioning, and task evidence;
- the bilingual README quick starts and their current, non-stale evidence
  boundaries;
- the v0.4 through v0.9 public release-audit chain that led to this delivery;
- the reference robot's intentionally empty bench, commissioning, and task
  intakes; and
- an explicit `hardware_claims: false` boundary.

The contract is a canonical JSON document with a schema version, a release
identifier, a closed list of relative artifact paths and SHA-256 digests, and a
closed non-claim record. The contract itself is intentionally not self-hashed;
its canonical bytes and closed schema are verified separately. It must not
contain URLs, local paths, external state, or a mutable “latest” reference. The
validator resolves every path below the
repository root, rejects missing, duplicate, symlinked, extra, stale, or
noncanonical records, recomputes hashes, and returns stable actionable errors.

## Architecture

`assurance/release/` is a small standard-library-only package, separate from
the existing physical and simulation evaluators:

```text
v1-release-contract.json
  -> release loader (duplicate-key / canonical / path safety)
  -> digest and closed-record verifier
  -> public-surface semantic verifier
  -> deterministic ReleaseDeliveryReport
  -> validate_release_delivery.py CLI
  -> scripts/validate.py + CI + fresh install regression
```

The semantic verifier has no promotion authority. It asserts only that required
public text and empty reference intakes state the same boundary. It explicitly
rejects a source tree that claims a reference measurement, hardware motion,
or hardware/task validation without an approved evidence intake. Existing
evidence validators retain their ownership of analytical, simulation, bench,
commissioning, and task semantics; the new validator calls their published
reference-intake interfaces only to confirm that the shipped fixtures remain
non-promoted.

The report derives `status` from findings (`passed`, `failed`, or `invalid`),
sorts findings deterministically, emits canonical UTF-8 JSON with one trailing
LF, and always derives `hardware_claims: false`. Cache, network access, and
hardware interfaces are out of scope.

## Public documentation

The English and Chinese READMEs will replace the stale “upcoming v0.9” wording
with the published v0.9 capability and introduce a v1 delivery verification
command. They will say plainly that the command verifies software provenance
and empty-intake boundaries, not real-world performance.

`PROJECT_STATUS.md` will record the v1 candidate scope and its residual external
dependency. `docs/releases/v1.0-completion-audit.md` begins as a candidate audit
and is rewritten after merge, tag CI, and GitHub Release. It will list actual
run IDs only after they have passed.

## Error handling and security boundary

- JSON is decoded as UTF-8 with duplicate-key rejection, finite-number checks,
  closed mappings, bounded recursion depth, and bounded input sizes.
- Relative paths are POSIX-normalized; absolute paths, `..`, drive prefixes,
  empty segments, symlinks, and files outside the release allow-list fail.
- All schema/type mistakes, file errors, and integer/float overflows become
  field-specific diagnostics or CLI exit code `2`, never a traceback.
- A changed artifact or a self-consistently rehashed contract cannot bypass the
  semantic invariant checks. The public release tag remains an external GitHub
  publication gate, not a locally asserted fact.
- No release record can elevate evidence to bench-tested,
  integrated-hardware-tested, task-validated, or certified.

## Verification

Tests will cover canonical identity, duplicate keys, nested malformed values,
path traversal, symlink and extra-file attacks, digest tampering, stale
documentation, non-empty reference intakes, and attempts to set hardware claims
true. They will also cover deterministic reports and CLI exit codes.

The release candidate must pass the full unit suite on Python 3.11 and 3.12,
distribution validation, fresh installer validation, compilation, diff check,
and the Linux Jazzy/Harmonic consumer gate. The public v1 tag and release happen
only after the reviewed-head and merged-main gates pass. The final report will
separate those verified software results from the still-unavailable externally
authorized hardware evidence.

## Acceptance criteria

1. A pristine candidate validates a closed, deterministic v1 delivery report
   with `hardware_claims: false`.
2. Every listed source artifact, digest, validator entry point, audit document,
   README boundary, and reference empty intake is checked by the contract.
3. Any path, bytes, JSON, semantic wording, intake, or claim-boundary attack
   fails closed with actionable diagnostics.
4. Existing physical, simulation, bench, commissioning, and task validators
   continue to retain their own gates and no new code connects to hardware.
5. The public release documents exact verified CI/tag/release evidence only
   after those external events occur.
