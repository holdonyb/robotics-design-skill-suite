# Bounded Hypothesis Engine Contract

Use this contract after requirements and the machine-readable physical contract
exist, and before simulation, training, procurement, or hardware work. It owns
finite multi-concept exploration, parameter sweeps, robustness cases, Pareto
comparison, counterexample search, and owner-correct repair lineage.

## Run

Create a closed schema-v1 hypothesis space and run:

```bash
python skills/robotics-design/scripts/generate_design_hypotheses.py hypothesis-space.json --out ../hypothesis-evidence --seed 42
```

The output must be outside the source directory. Use `--force` only to replace
an existing bundle transactionally. Exit `0` means at least one candidate is
accepted by every declared gate. Exit `1` means evaluation completed but no
candidate was accepted. Exit `2` means invalid input, unsafe output, exhausted
budget, publication failure, or another fail-closed invocation error.

## Closed hypothesis space

The root fields are `schema_version`, `space_id`, `base_contract`,
`max_candidates`, `axes`, `uncertainties`, `objectives`, `repair_rules`, and
`evaluation`. Unknown or duplicate fields, invalid UTF-8, non-finite numbers,
oversized integers, excessive nesting, unsupported targets, and stale base
contract hashes are rejected.

- `base_contract` binds a relative `path` and SHA-256.
- `axes` contain finite choices and semantic operations. Quantity operations
  replace only `.value` or `.tolerance`; component and evidence operations
  replace the complete same-ID record; only declared architecture lists may be
  replaced. Requirements, analyses, and artifact hashes are immutable.
- `uncertainties` contain a quantity `.value` target, explicit-unit discrete
  values, and a Boolean `hard` disposition.
- `objectives` use quantity, analysis-output, minimum-evidence, or blocking-count
  sources and declare `min` or `max`. There is no hidden scalar score.
- `repair_rules` bind `diagnostic_code`, `owner_prefix`, semantic operations,
  and bounded `max_applications`. A repair outside the earliest diagnostic's
  owner is rejected.
- `evaluation` declares ordered stages and `max_stage_evaluations`.

`max_candidates` and `max_stage_evaluations` are hard global bounds, not hints.
Cartesian candidate count, nominal evaluations, uncertainty cases, sensitivity
probes, and repair children all consume the declared budgets.

## Identity, stages, and cache

Canonical UTF-8 JSON, the base hash, assignments, and seed derive stable
`candidate-<24 lowercase hex>` identities. Equal resolved contracts retain one
canonical candidate and explicit alias lineage. Candidate ordering and files
are deterministic for the same inputs, seed, and tool versions.

The only stage order is:

1. `contract_v1`
2. `physical_v030`
3. `uncertainty_v1`
4. `counterexample_v1`
5. `objectives_v1`

Dependencies cannot be bypassed. The physical stage always uses the v0.3
contract evaluator. Content-addressed cache entries are authenticated only for
the scheduler instance that wrote them; malformed, stale, foreign, or tampered
entries are recomputed. Cache data never changes a promotion result.

## Uncertainty and counterexamples

Evaluation is nominal-first, followed by a seed-stable permutation of the same
finite case set. Explicit units are normalized before distance or sensitivity
calculation. The nearest failing hard case is the blocking counterexample;
soft cases remain visible risk records. A failing nominal case is fail-closed.
Hard uncertainty can only reduce eligibility, never upgrade it.

## Objectives, screening, and repairs

`pareto.json` contains the promotion Pareto result. Blocked candidates and
incomplete or non-finite vectors are ineligible. Pairwise dominance uses only
the visible declared directions.

`screening-pareto.json` is a separate analytical comparison for the public
reference robot: a candidate may enter only when every analysis passes, its
only blocker is `BOM.PLACEHOLDER_BLOCKS_CLAIM`, every objective is complete,
and no hard counterexample exists. Root and owner-correct repair candidates use
the same rule. Screening never accepts or promotes a candidate.

Repairs start from the deterministic earliest repairable blocking diagnostic
and must match its `owner_prefix`. The public reference policy ignores
`BOM.PLACEHOLDER_BLOCKS_CLAIM` only while correcting another declared physical
fault; that placeholder remains visible and keeps the child unpromoted. Any
unrepairable non-placeholder blocker prevents repair, so the engine never skips
a safety or unsupported-physics failure merely to apply a later rule. A repair
creates a child with parent/rule lineage, rejects repeated content and cycles,
and reruns the failed stage plus downstream dependencies. An unrelated
controller edit cannot repair a motor-rating failure.

## Evidence bundle and verification

Publication creates canonical JSON files in a sibling transaction directory,
validates them, and atomically renames the verified tree. `manifest.json` binds
every bundle file. The CLI prints an out-of-band `manifest_sha256` receipt;
retain it separately from the bundle, then verify with:

```python
from assurance.hypothesis.bundle import validate_bundle

errors = validate_bundle("hypothesis-evidence", manifest_sha256=receipt)
```

`validate_bundle` rejects a stale receipt, changed or extra file, symlink,
unsafe path, duplicate key, invalid UTF-8, noncanonical JSON, and resource-limit
violation. A manifest stored only beside the files it authenticates is not an
external integrity anchor.

The reference space is
`reference/mobile-manipulator/hypothesis-space.json`; its pinned evidence is in
`hypothesis-expected.json` and its interpretation is in
`hypothesis-benchmark.md`.

## Claim boundary

Hypothesis output is generated, parsed, and calculated evidence. It does not
prove simulation or hardware performance. Screening and Pareto position do not
prove dynamics, collision safety, controllability, training convergence,
manufacturability, reliability, or a purchasable BOM. Simulation and training
belong to later gates; bench and hardware claims require retained measurements,
approved parts, a bounded site, qualified operators, reachable emergency stop,
and explicit motion authorization.
