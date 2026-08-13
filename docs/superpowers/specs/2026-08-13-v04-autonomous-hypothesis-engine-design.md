# Autonomous Hypothesis Engine v0.4 Design

## Purpose

Version 0.4 adds bounded, deterministic design-space exploration on top of the
v0.3 physical-plausibility kernel. It generates complete candidate contracts,
rejects invalid candidates at the earliest applicable gate, explores declared
uncertainty, searches for counterexamples, records repair lineage, and exposes
Pareto trade-offs without inventing requirements, vendor data, or evidence.

The user has authorized autonomous execution without routine approval. This
document therefore selects the recommended architecture directly while
preserving all safety and external-authority boundaries in the v1 design.

## Considered approaches

### Selected: immutable contract overlays

A design space contains finite axes. Each choice is a closed bundle of semantic
operations against an immutable base v0.3 contract. Resolution produces a full
contract which is passed to the existing v0.3 validator and evaluator.

This approach is auditable, standard-library only, deterministic across
platforms, and naturally content-addressed. It supports architecture,
component, evidence, and parameter hypotheses without creating a second robot
model owner.

### Rejected for v0.4: independent robot-graph DSL

A new graph language would provide more expressive topology generation, but it
would duplicate the v0.3 contract, require a migration layer, and create a
large new semantic attack surface before simulation integration exists.

### Deferred: external optimization framework

Bayesian, evolutionary, or mixed-integer optimizers may become backends after
the deterministic interfaces are stable. Making one authoritative in v0.4
would add dependencies, obscure candidate ordering, and weaken byte-for-byte
reproducibility.

## Design-space contract

`hypothesis-space` schema version 1 is closed JSON with these root fields:

- `schema_version`: integer `1`;
- `space_id`: stable identifier;
- `base_contract`: repository-relative `path` plus lowercase SHA-256;
- `max_candidates`: integer from 1 through 10,000;
- `axes`: ordered records with unique IDs and non-empty finite choices;
- `uncertainties`: ordered bounded perturbation records;
- `objectives`: visible Pareto objectives;
- `repair_rules`: ordered diagnostic-to-operation rules;
- `evaluation`: stage and budget declarations.

An axis choice has `id` and a non-empty `operations` list. Operations are
closed records with `target` and `value`. Supported semantic targets are:

- `quantity:ID.value` and `quantity:ID.tolerance`;
- `component:ID` for a complete replacement component record with the same ID;
- `evidence:ID` for a complete replacement evidence record with the same ID;
- `architecture.features`, `architecture.drive_units`,
  `architecture.actuators`, `architecture.moving_cables`, and
  `architecture.claimed_safety_functions`.

Requirements, assumptions, analyses, artifact hashes, schema version, and
candidate status are immutable in schema 1. Architecture/component choices
that need different analyses or artifacts must select a separately hash-bound
base contract. This prevents a choice from silently weakening a requirement or
removing a gate obligation.

Every target must exist before application. Duplicate targets within one
choice, unknown fields, empty choices, duplicate choice IDs, non-finite values,
oversized integers, path escape, and a Cartesian product larger than
`max_candidates` are schema errors. Operations apply in canonical axis-ID
order, not input order.

## Candidate identity, resolution, and lineage

A candidate decision record contains the base-contract hash, sorted
`axis_id=choice_id` assignments, seed, optional parent ID, and optional repair
rule ID. Its canonical UTF-8 JSON SHA-256 yields
`candidate_id = candidate-<first 24 hex characters>`.

The resolver deep-copies the base contract, applies operations, assigns the
derived candidate ID, and validates the complete v0.3 contract. Candidate
deduplication uses the SHA-256 of the resolved contract after removing only the
derived candidate ID. Distinct assignments that resolve to identical designs
are aliases of the first canonical candidate and remain visible in the index.

Lineage is append-only. A record contains candidate ID, parent ID, assignment
set, repair rule, resolved-contract hash, evaluation key, and status. No record
is edited after emission.

## Evaluation scheduler and cache

The scheduler is a small registry of deterministic stages. Version 0.4 ships:

1. `contract_v1`: resolve and validate the complete design contract;
2. `physical_v030`: invoke the v0.3 assurance engine;
3. `uncertainty_v1`: evaluate declared perturbation cases;
4. `counterexample_v1`: retain the smallest declared perturbation that blocks
   promotion;
5. `objectives_v1`: extract visible objective vectors and Pareto relations.

Each stage declares its name, version, dependencies, maximum evaluations, and
input hash. Its cache key is SHA-256 of candidate contract hash, stage name and
version, dependency report hashes, uncertainty case, and tool versions. Cache
entries are canonical JSON written transactionally to a caller-selected output
bundle. A malformed or stale entry is ignored and recomputed; cache data never
changes a promotion result.

Unknown stages are errors. A downstream stage does not run after a blocking
dependency except when explicitly collecting a rejected-candidate trace.

## Uncertainty, sensitivity, and counterexamples

An uncertainty record targets an existing quantity value and contains an
ordered, non-empty list of explicit typed values plus an optional hard flag.
Version 0.4 deliberately uses declared discrete cases instead of implicit
probability distributions. This makes coverage and evaluation count exact.

The nominal case is always evaluated first. Remaining cases use a deterministic
SHA-256 permutation derived from the user seed, candidate ID, and uncertainty
ID. The engine refuses a requested product larger than the declared evaluation
budget.

One-at-a-time sensitivity reports the change in every objective and the set of
new blocking diagnostic codes for each non-nominal value. Counterexample search
orders cases by normalized distance from nominal and returns the first blocking
case at the smallest distance, breaking ties by canonical case ID. A hard
uncertainty counterexample blocks candidate acceptance. Soft cases remain
visible risk evidence but do not become presentation-only warnings.

## Objectives and Pareto ranking

Objectives are closed records with unique ID, `source`, and `direction`
(`minimize` or `maximize`). Schema 1 supports:

- `quantity:ID` after SI normalization;
- `analysis:ANALYSIS-ID.outputs.<dotted-path>`;
- `evidence:minimum-level` mapped to its declared ordinal only for display and
  dominance, never for evidence substitution;
- `diagnostics:blocking-count`.

A missing, Boolean, non-finite, or non-scalar objective is indeterminate and
excludes the candidate from the Pareto set. Hard-gate failures are never Pareto
accepted. Among promotable candidates, A dominates B only when A is no worse
on every objective and strictly better on at least one. The report includes
raw objective vectors, pairwise dominance edges, fronts, and trade-off deltas;
it never emits a hidden weighted score.

The placeholder reference mobile manipulator may be screened and compared but
cannot be labeled accepted or promoted. A small synthetic promotable fixture is
used only to test accepted/Pareto behavior. The public reference benchmark must
show at least one objective improvement with no new hard diagnostic while
retaining its existing placeholder block.

## Repair loop

A repair rule contains an ID, an exact diagnostic-code selector, a target-owner
prefix, a finite operation bundle, and a maximum application count. The engine
selects the earliest blocking diagnostic by scheduler stage, diagnostic code,
path, and message. A rule may apply only when every operation target belongs to
the diagnostic owner or to a component/evidence record directly referenced by
that owner.

Applying a repair creates a child candidate; it never mutates the parent. The
child reruns the failed stage and all downstream dependencies. Cycles are
prevented by resolved-contract hash, and the global candidate/evaluation
budgets still apply. A repair trace records the triggering diagnostic, owner,
rule, before/after target hashes, rerun stages, outcome, and remaining blockers.

No repair may change requirements, delete evidence obligations, downgrade a
hard uncertainty, or reinterpret an error as a warning.

## Evidence bundle and CLI

`generate_design_hypotheses.py` accepts a design-space path, output directory,
and integer seed. It refuses an existing non-empty output unless `--force` is
given. Output is transactional and contains:

- `index.json`: space hash, seed, tool versions, counts, candidate aliases,
  Pareto fronts, and bundle file hashes;
- `candidates/<id>/contract.json`;
- `candidates/<id>/physical-report.json`;
- `candidates/<id>/trace.json`;
- `cache/<stage-key>.json`;
- `benchmark.json` when a benchmark is requested.

Canonical serialization uses sorted keys, UTF-8, finite numbers, and one LF.
The bundle validator rehashes every listed file and rejects missing, extra,
stale, escaping, or non-canonical paths.

CLI exit codes are `0` when at least one candidate is promotable and all hard
uncertainty cases pass, `1` when generation succeeds but no candidate is
acceptable, and `2` for invalid input, budget, output, or serialization.

## Testing and release gates

Unit tests cover closed schemas, target resolution, canonical identities,
deduplication, cache keys, budget rejection, uncertainty ordering, objective
extraction, Pareto dominance, repair ownership, cycle prevention, transactional
output, and CLI codes.

Metamorphic and adversarial tests prove:

- reordering input axes, choices, or JSON keys does not change identities;
- changing seed changes only uncertainty order, not the candidate set;
- every resolved candidate is evaluated through the v0.3 gate;
- weakening a requirement or hiding an evidence/analysis obligation is
  impossible through schema-1 operations;
- hard uncertainty and counterexample failures block acceptance;
- an injected wrong motor rating traces to its owning component and a repair
  changes that owner rather than a downstream controller;
- identical inputs produce byte-identical bundles on Python 3.11 and 3.12;
- all prior v0.3 fault mutations remain fail-closed.

Release requires independent adversarial review, Ubuntu/Windows CI on Python
3.11/3.12, a fresh 10-skill install, reproducible public tag evidence, and
explicit nonclaims. Version 0.4 does not claim optimization optimality,
continuous-distribution coverage, simulation, training, bench, hardware, or
certification evidence.
