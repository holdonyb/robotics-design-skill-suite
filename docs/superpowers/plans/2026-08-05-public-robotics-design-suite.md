# Public Robotics Design Skill Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a public, independently installable robotics design skill-suite repository with pinned upstream sources and deterministic validation.

**Architecture:** Keep the original router and public references in-repo. Drive third-party installation from one JSON manifest and a standard-library Python installer that downloads pinned archives, copies declared skill paths, preserves licenses, and performs the one documented Codex frontmatter normalization.

**Tech Stack:** Agent Skills Markdown/YAML, Python 3.11+ standard library, `unittest`, GitHub Actions, Git/GitHub CLI.

---

### Task 1: Repository contract

**Files:**
- Create: `README.md`
- Create: `README.zh-CN.md`
- Create: `LICENSE`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Create: `.gitignore`

- [ ] **Step 1: Write the public contract**

Document the thin-distribution architecture, public/non-public boundaries, supported installation target, current source commits, usage examples, safety limits, and optional CAD runtime.

- [ ] **Step 2: Scan for private data**

Run:

```powershell
rg -n "E:/|E:\\\\|holdo|京新数智|gho_|github_pat_|sk-" . --glob '!.git/**'
```

Expected: no match outside the historical design document's declared local path; tests must exclude design history or explicitly allow that one path.

- [ ] **Step 3: Commit**

```powershell
git add README.md README.zh-CN.md LICENSE THIRD_PARTY_NOTICES.md SECURITY.md CONTRIBUTING.md .gitignore
git commit -m "docs: define public robotics skill suite"
```

### Task 2: Local routing skill

**Files:**
- Create: `skills/robotics-design/SKILL.md`
- Create: `skills/robotics-design/agents/openai.yaml`
- Create: `skills/robotics-design/references/design-contract.md`
- Create: `skills/robotics-design/references/validation-gates.md`
- Create: `skills/robotics-design/references/authority-map.md`
- Create: `skills/robotics-design/references/runtime.md`
- Create: `skills/robotics-design/references/source-lock.md`

- [ ] **Step 1: Copy only original public material**

Remove host-specific runtime paths and installation dates. Preserve capability routing, artifact ownership, evidence ladder, hard safety gates, and upstream provenance.

- [ ] **Step 2: Validate frontmatter**

Run:

```powershell
python -X utf8 E:/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/robotics-design
```

Expected: `Skill is valid!`

- [ ] **Step 3: Commit**

```powershell
git add skills/robotics-design
git commit -m "feat: add robotics design router"
```

### Task 3: Manifest and installer

**Files:**
- Create: `manifest.json`
- Create: `scripts/install.py`
- Create: `scripts/validate.py`
- Test: `tests/test_manifest.py`
- Test: `tests/test_install.py`

- [ ] **Step 1: Write failing manifest and installer tests**

Tests must assert full 40-character commits, unique destination names, declared license data, deterministic dry-run output, local fixture installation, license copying, ROS frontmatter normalization, and collision refusal.

- [ ] **Step 2: Run tests and observe RED**

Run:

```powershell
python -m unittest tests.test_manifest tests.test_install -v
```

Expected: failure because `manifest.json` and installer modules do not exist.

- [ ] **Step 3: Implement minimal installer**

Use only `argparse`, `json`, `pathlib`, `shutil`, `tempfile`, `urllib.request`, and `zipfile`. Reject archive traversal, verify declared `SKILL.md` files, refuse existing destinations, copy upstream license text, and install the local router after external skills.

- [ ] **Step 4: Run tests and observe GREEN**

Run the same unittest command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add manifest.json scripts tests/test_manifest.py tests/test_install.py
git commit -m "feat: add pinned skill installer"
```

### Task 4: Public hygiene and CI

**Files:**
- Create: `tests/test_public_hygiene.py`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write hygiene tests**

Scan public distribution files for absolute Windows/home paths, credential prefixes, private workspace names, unresolved placeholders, and invalid skill references. Exclude `.git` and design-history files from deployable-content checks.

- [ ] **Step 2: Run test and fix violations**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 3: Add CI**

GitHub Actions must run on Windows and Ubuntu with Python 3.11 and execute compile, unit tests, validator, and installer dry-run.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_public_hygiene.py .github/workflows/ci.yml
git commit -m "ci: validate public skill distribution"
```

### Task 5: End-to-end verification and publication

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Run fresh verification**

```powershell
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run --dest .tmp-install
python -X utf8 E:/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/robotics-design
git status --short
```

Expected: all commands exit 0; only intended committed or ready-to-commit files exist.

- [ ] **Step 2: Create public repository and push**

```powershell
gh repo create holdonyb/robotics-design-skill-suite --public --source . --remote origin --push --description "Evidence-gated robotics design skills for Codex: CAD, URDF, SDF, SRDF, ROS 2, and Gazebo."
```

- [ ] **Step 3: Verify remote**

```powershell
gh repo view holdonyb/robotics-design-skill-suite --json nameWithOwner,visibility,url,defaultBranchRef
gh api repos/holdonyb/robotics-design-skill-suite/contents --jq '.[].name'
```

Expected: public repository, `main` default branch, and all release files visible.

## Self-review

- Spec coverage: repository identity, thin packaging, manifest, installer, licensing, hygiene, CI, validation, and publication each map to a task.
- Placeholder scan: no `TBD`, `TODO`, “implement later,” or underspecified test steps.
- Type consistency: manifest destinations are skill names; installer and tests use the same source/skill mapping contract.
