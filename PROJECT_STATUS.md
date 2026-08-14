# Project Status

## Purpose

This public repository distributes an evidence-gated robotics-design skill
suite. It owns the integration contract, v0.3 physical-assurance kernel, v0.4
bounded hypothesis engine, reference mobile manipulator, tests, and
transactional installer while locking third-party CAD, robot-description,
ROS 2, and simulation skills to audited commits.

## Live State

- v0.9.0 candidate is local-only on `feature/v090-task-evidence`; it adds a
  hash-bound offline task/fault/endurance/comparison dossier, keeps the shipped
  reference intake empty, and never authorizes procurement, motion, or task
  validation. Candidate evidence: 445 tests, distribution validation,
  installer dry-run, compile check, and diff check passed locally.
- Public release: `v0.8.0`; pull request `#10` merged as `e6521fd`, annotated
  tag and GitHub Release are published. Main CI `31763218034`, main
  Jazzy/Harmonic consumer gate `31763218001`, and tag CI `31763519145` passed.
- v0.8 accepts future offline commissioning-evidence submissions only through
  hash-bound staged records and accepted non-fixture bench evidence. The
  shipped reference index is intentionally empty and remains
  `awaiting_authorization`, not integrated-hardware-tested.
- Hardware boundaries remain unchanged: every v0.8 result derives
  `procurement_authorized: false` and `motion_authorized: false`.
- Release evidence: 419 local tests, distribution validation, installer dry-run,
  compilation, PR/main/tag CI, and Jazzy/Harmonic consumer gates passed.
- Third-party source locks are unchanged from v0.3.0.

## v0.5 Development Checkpoint

The v0.5 release candidate adds closed simulation admission, source-bound ROS 2
workspace artifacts, ten deterministic scenarios, trace receipts and replay,
two distinct portable dynamics calculations, bounded calibration, and a
train/evaluation/held-out synthetic policy firewall. The portable reference
benchmark compiles and replays 10/10 scenarios, retains a placeholder-only
simulation admission (`hardware_promotable: false`), a passed calculated
backend comparison, simulated synthetic calibration, and a simulated/
not-justified training result.

Retained Linux Jazzy/Harmonic consumer evidence is now present: GitHub Actions
`31756050051` passed at the main merge commit; the candidate evidence was
also retained at artifact digest
`8c7acb48090911107a341238ba94d333e9497858b3fe1d64baa79e25560f7d02`.
It records active controllers, MoveIt planning readiness, and Nav2 lifecycle
servers. This is live simulator-consumer evidence, not task validation, bench
calibration, hardware safety, or real robot motion evidence. The Windows host
still has no local Docker execution evidence because its Docker Desktop Linux
containerd metadata store failed before image pull.

## v0.4 Candidate Capability

The candidate adds a closed, deterministic, bounded hypothesis layer on top of
the v0.3 physical gate:

- canonical candidate identity, immutable semantic overlays, content aliases,
  parent/repair lineage, and cycle-safe records up to the declared bounds;
- a closed finite design-space schema with explicit-unit operations, immutable
  requirements/analyses/artifact hashes, hard candidate and stage budgets, and
  safe UTF-8/JSON/resource boundaries;
- dependency-ordered `contract_v1`, `physical_v030`, `uncertainty_v1`,
  `counterexample_v1`, and `objectives_v1` stages, with tool-version keys and
  scheduler-local authenticated cache entries;
- nominal-first discrete uncertainty, SI-normalized sensitivity, nearest hard
  counterexample selection, and fail-closed promotion effects;
- visible multi-objective Pareto fronts without hidden scalarization;
- deterministic earliest-repairable diagnosis, exact owner-prefix enforcement,
  bounded child generation, downstream reruns, and retained repair traces;
- canonical manifest-bound evidence bundles, an out-of-band manifest receipt,
  transactional publication/rollback, and tamper/path/symlink/extra-file checks;
- CLI exit codes `0` accepted, `1` evaluated with none accepted, and `2` invalid
  or fail-closed execution/publication error, without user-facing tracebacks;
- bilingual routing and an operational hypothesis-engine contract.

## Reference Benchmark

`reference/mobile-manipulator/hypothesis-space.json` resolves four roots and two
owner-correct repair children: 6 candidates under 76 stage evaluations with
seed `20260813`. Calculated battery runtime improves from 22,500 to 27,000
seconds without a hard uncertainty counterexample in the declared 5/6 kg and
5/6 degree set. The deliberately undersized right-motor rating is traced to
`component:CMP-TRACTION-MOTOR-R` and repaired only through its owned rating.

The result remains 0 accepted. All 49 claim-driving components are still
`engineering_placeholder`, so `BOM.PLACEHOLDER_BLOCKS_CLAIM` remains explicit.
`screening-pareto.json` compares only complete, analytically passing,
placeholder-only, hard-uncertainty-clean roots and repair children; it never
changes promotion. The pinned pre-release bundle receipt is
`311b50ca5150b1fcf8aa3215282a658d73995fb82bc15b2ae87dfb04540e7bba`.

## Latest Verified Evidence

On 2026-08-13, before Task 12 release publication:

- Python 3.11.2 full suite: 293/293 passed at the Task 12 candidate head;
- bundled Python 3.12.13 full suite: 293/293 passed at the Task 12 candidate
  head;
- distribution validation: 10 skills and 3 pinned sources valid;
- installer dry run: complete 10-skill plan;
- reference plus legacy physical-fault regression: 11/11 passed, including the
  exact 32 curated critical fault IDs;
- Task 10 independent review: APPROVED with no Critical, Important, or Minor;
- Task 11 focused behavior/public-hygiene suite: 24/24 passed after the bounded
  placeholder-repair policy correction;
- compileall and `git diff --check`: passed.
- Python 3.11 and 3.12 generated byte-identical 42-file reference bundles:
  tree SHA-256 `12bca93f3bce89d2f8fc3d2000b39c84b76ace2a3b2982f9824439b7b121be5c`
  and manifest receipt `311b50ca5150b1fcf8aa3215282a658d73995fb82bc15b2ae87dfb04540e7bba`.
- release hardening reproduced interrupted and malformed codeload responses;
  the installer now retries three times, validates ZIP/CRC before accepting a
  source, removes partial files, and reports exhaustion without a traceback.
- the whole-release adversarial review at `d431688` found no Critical,
  Important, or Minor issues; its engineering release-candidate verdict was
  APPROVED, with only the then-unexecuted external release gates left open;
- GitHub Actions PR run `31715656399` passed the Ubuntu/Windows × Python
  3.11/3.12 matrix plus the strengthened `release-install` job at `6881a2c`;
  push run `31715652132` passed the same gates independently;
- the GitHub runner fresh-install evidence contains 10/10 skills, 9/9 upstream
  licenses, OpenAI's official validator pinned to `openai/skills@49f948f`, no
  bytecode/partial/transaction residue, a generated `host-runtime.md`, and an
  exact full-file/hash match for the installed `robotics-design` skill.

Release closure evidence:

- PR `#4` merged as `f37cd3b`; main workflow run `31716689574` passed all five
  jobs, and the merge tree exactly matched reviewed head `c2af7ef`;
- annotated tag `v0.4.0` resolves to `f37cd3b`; tag workflow run `31716834403`
  passed all five jobs, including the strengthened `release-install` gate;
- the public GitHub Release is published, not draft or prerelease, and the
  public tag's manifest reports suite version `0.4.0`;
- the public tag was staged through the Codex `skill-installer`, passed the
  official local validator and compileall, received a host-specific runtime
  overlay, and replaced only the installed `robotics-design` skill;
- the previous local integration skill remains recoverable at
  backup directory `robotics-design-pre-v040-20260813-2350`.

The current host repeatedly lost the 8.67 MiB pinned text-to-cad response over
codeload and Git smart protocol; no incomplete checkout or archive was accepted.
The complete-suite install evidence therefore comes from clean GitHub runners,
while the controlled local refresh intentionally changed only the locally owned
`robotics-design` integration skill and preserved all third-party installations.

## Claim Boundary and Open Engineering Risks

- v0.4 outputs generated, parsed, and calculated evidence. They do not establish
  simulation, training, bench, or hardware performance.
- The reference trade-off is analytical screening, not proof of dynamics,
  collision safety, controllability, training convergence, manufacturability,
  reliability, endurance, braking, payload, or human safety.
- The component ledger still contains engineering placeholders rather than an
  approved purchasable BOM with supplier-authenticated curves and certificates.
- The Windows host has no live ROS 2 Jazzy/Gazebo Harmonic evidence environment;
  repeatable Linux simulation and training integration belongs to v0.5.
- No real robot motion is authorized. Hardware work requires approved parts,
  exact site and operators, bounded energy, reachable emergency stop, explicit
  motion authority, and retained raw measurements.

## Run and Validate

```powershell
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
python skills/robotics-design/scripts/generate_design_hypotheses.py reference/mobile-manipulator/hypothesis-space.json --out ../v040-reference --seed 20260813
```

The last command is expected to exit `1`, publish a valid evidence bundle, and
report 0 accepted because placeholders remain.

## Roadmap and Next Action

1. Continue v0.9 with supplier/BOM, curves, traction/braking, structure,
   transient thermal/electrical, safety faults, bench evidence, controlled
   integration, field trials, and reliability evidence.
2. Complete v1.0 only after the end-to-end evidence chain and every required
   real-hardware dependency/authorization are genuinely satisfied.

## Durable Sources

- `docs/superpowers/specs/2026-08-13-trustworthy-autonomous-robot-design-v1-design.md`
- `docs/superpowers/specs/2026-08-13-v04-autonomous-hypothesis-engine-design.md`
- `docs/superpowers/plans/2026-08-13-v04-autonomous-hypothesis-engine.md`
- `docs/releases/v0.4-completion-audit.md`
- `skills/robotics-design/references/hypothesis-engine-contract.md`
- `reference/mobile-manipulator/hypothesis-benchmark.md`
