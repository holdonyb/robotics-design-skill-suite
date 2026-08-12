# Portable Workflow Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover the installed-only mission-animation and patent-aware workflows into a portable, tested v0.2.0 distribution with an optional generated host-runtime overlay.

**Architecture:** Reusable contracts and validators live in the tracked `robotics-design` skill. Host-specific Python and destination paths are generated only in a staged `host-runtime.md` during installation, before the existing destination transaction. Third-party source locks remain unchanged for this release.

**Tech Stack:** Python 3.11+ standard library, `unittest`, Markdown Agent Skills, JSON manifests, GitHub Actions.

---

### Task 1: Recover mission-animation evidence gates

**Files:**
- Create: `skills/robotics-design/references/mission-animation-contract.md`
- Create: `skills/robotics-design/scripts/validate_mission_animation_manifest.py`
- Create: `tests/test_mission_animation_manifest.py`
- Modify: `tests/test_robotics_design_behavior.py`
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `skills/robotics-design/references/design-contract.md`
- Modify: `skills/robotics-design/references/validation-gates.md`

- [ ] **Step 1: Write failing routing and manifest tests**

Add behavior assertions that `SKILL.md` routes mission animation to
`references/mission-animation-contract.md`, forbids hand-keyframed robot joint
motion, and requires the mission validator. Add manifest fixtures with hashed
model, trajectory, physics trace, and animation files. Assert that a promoted
manifest passes only when required/observed moving joints match and neither end
is simultaneously free.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_robotics_design_behavior tests.test_mission_animation_manifest -v
```

Expected: failures because the contract and validator do not exist and routing
text is absent.

- [ ] **Step 3: Add the portable contract and validator**

Recover the installed contract and validator without host paths or bytecode.
The validator must expose:

```python
def validate_manifest(data: Any, manifest_dir: Path) -> list[str]:
    ...
```

It validates source hashes, canonical joint order, required and observed moving
joints, phase contact states, load-case IDs, zero-count promotion checks,
physics-trace disposition, and review metadata.

- [ ] **Step 4: Route and cross-link the new gate**

Update the router, design contract, and validation gates so one accepted
trajectory/contact trace owns mission motion and hand-authored joint keyframes
cannot be promoted as engineering evidence.

- [ ] **Step 5: Run targeted and regression tests**

Run:

```powershell
python -m unittest tests.test_robotics_design_behavior tests.test_mission_animation_manifest -v
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_robotics_design_behavior.py tests/test_mission_animation_manifest.py skills/robotics-design
git commit -m "feat: gate mission animation evidence"
```

### Task 2: Recover patent-aware architecture controls

**Files:**
- Create: `skills/robotics-design/references/patent-design-around.md`
- Modify: `tests/test_robotics_design_behavior.py`
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `skills/robotics-design/references/design-contract.md`
- Modify: `skills/robotics-design/references/validation-gates.md`
- Modify: `skills/robotics-design/references/authority-map.md`
- Modify: `skills/robotics-design/agents/openai.yaml`

- [ ] **Step 1: Write failing patent-routing tests**

Assert that patent/FTO requests route through `$deep-research` and
`references/patent-design-around.md`, and that the reference requires a claim
chart, equivalents analysis, official legal-status evidence, positive design
constraints, drift tests, and a qualified-counsel boundary.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_robotics_design_behavior -v
```

Expected: failures because the patent contract and routing are absent.

- [ ] **Step 3: Add the portable patent contract and routing**

Recover the installed claim-element workflow as engineering guidance, retain
the explicit non-legal-opinion boundary, and connect selected design-around
principles to owned CAD/URDF/SDF/software artifacts and regression tests.

- [ ] **Step 4: Run tests and commit**

```powershell
python -m unittest tests.test_robotics_design_behavior -v
python -m unittest discover -s tests -v
git add tests/test_robotics_design_behavior.py skills/robotics-design
git commit -m "feat: add patent-aware robot architecture gates"
```

### Task 3: Generate an optional host-runtime overlay transactionally

**Files:**
- Modify: `tests/test_install.py`
- Modify: `scripts/install.py`
- Modify: `skills/robotics-design/SKILL.md`
- Modify: `skills/robotics-design/references/runtime.md`

- [ ] **Step 1: Write failing installer tests**

Add tests for this API:

```python
install_from_manifest(
    manifest_path=manifest_path,
    destination=dest,
    repository_root=repo_root,
    archive_provider=lambda _source: archive,
    host_runtime_python=runtime,
)
```

Assert that a valid runtime generates
`robotics-design/references/host-runtime.md` containing the resolved runtime and
destination, omission generates no overlay, a missing runtime fails before the
archive provider is called, and `--dry-run --host-runtime-python` reports the
overlay without creating files.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_install -v
```

Expected: `TypeError`/CLI failures because host overlay support is absent.

- [ ] **Step 3: Implement the minimal overlay functions**

Add:

```python
def resolve_host_runtime(path: Path | None) -> Path | None:
    ...

def write_host_runtime_overlay(skill_root: Path, runtime: Path, destination: Path) -> Path:
    ...
```

Resolve and validate the runtime before downloads. Generate the Markdown file
inside the staged local skill before `prepare_destination_transaction`. Pass
the optional runtime through `install_from_manifest` and CLI parsing.

- [ ] **Step 4: Document optional overlay discovery**

Tell the router to read `references/host-runtime.md` only when present, while
keeping tracked runtime guidance portable.

- [ ] **Step 5: Run installer and regression tests**

```powershell
python -m unittest tests.test_install -v
python -m unittest discover -s tests -v
```

Expected: all tests pass and transaction tests remain green.

- [ ] **Step 6: Commit**

```powershell
git add scripts/install.py tests/test_install.py skills/robotics-design/SKILL.md skills/robotics-design/references/runtime.md
git commit -m "feat: generate portable host runtime overlays"
```

### Task 4: Close public distribution and documentation gaps

**Files:**
- Modify: `tests/test_public_hygiene.py`
- Modify: `scripts/validate.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `skills/robotics-design/references/source-lock.md`
- Modify: `PROJECT_STATUS.md`

- [ ] **Step 1: Strengthen failing public-hygiene requirements**

Require the mission contract, patent contract, and mission validator. Reject
tracked `.pyc` files, `__pycache__`, drive-letter paths, private installation
markers, and references to missing local skill files.

- [ ] **Step 2: Run hygiene and distribution tests and verify RED**

```powershell
python -m unittest tests.test_public_hygiene -v
python scripts/validate.py
```

Expected: failure until required public files and cross-links are complete.

- [ ] **Step 3: Update bilingual docs, provenance, and status**

Document the three v0.2 evidence gates, optional host overlay, unchanged source
locks, exact validation commands, claim boundaries, and the separate follow-on
tracks for ROS 2 1.3.0 and `cadgen` 0.4.5.

- [ ] **Step 4: Run full local validation and commit**

```powershell
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run --dest .tmp-install/status-check
git diff --check
```

Expected: zero failures and a clean diff check.

```powershell
git add README.md README.zh-CN.md PROJECT_STATUS.md scripts/validate.py tests/test_public_hygiene.py skills/robotics-design/references/source-lock.md
git commit -m "docs: prepare robotics design suite v0.2.0"
```

### Task 5: Validate, review, and publish v0.2.0

**Files:**
- Review: all changes from `dc26cc8` to feature head
- Remote: `holdonyb/robotics-design-skill-suite`

- [ ] **Step 1: Perform a fresh real-install verification**

Install to a new ignored temporary destination using the host runtime option.
Validate all ten installed skills with the official skill validator in UTF-8
mode. Assert nine upstream-license copies and zero transaction residue.

- [ ] **Step 2: Request independent code review**

Review requirements, portability, supply-chain behavior, validator security,
transaction rollback, tests, and public hygiene. Fix every Critical or
Important finding and rerun affected plus full tests.

- [ ] **Step 3: Verify GitHub authentication and push the feature branch**

```powershell
gh auth status
git push -u origin feature/v020-visual-fidelity
```

Expected: authenticated account `holdonyb` and successful push.

- [ ] **Step 4: Open and land the pull request**

Create a draft PR to `main`, verify GitHub Actions on Windows/Linux and Python
3.11/3.12, mark ready, and merge only after checks pass.

- [ ] **Step 5: Tag, release, and verify**

Create annotated tag `v0.2.0`, publish release notes, wait for tag CI, and verify
the public manifest, release metadata, default branch commit, and private
vulnerability reporting.

- [ ] **Step 6: Refresh the local installation from the released commit**

Preserve the current installed skill until the release install has passed in a
temporary destination. Then replace only the suite-owned skill directories
through the reviewed installer workflow and start a new Codex task for skill
discovery.
