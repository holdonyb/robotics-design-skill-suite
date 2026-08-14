# v1.0 Reproducible Public Delivery Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Ship a reproducible v1.0 public delivery whose software/evidence surface is hash-bound, semantically checked, and explicitly non-hardware-promoting.

Architecture: A standard-library-only assurance.release package loads a canonical release contract, recomputes an exact artifact allow-list, checks public boundaries, and emits a deterministic report. A CLI and generator expose it; the normal distribution validator and CI make it a release gate.

Tech Stack: Python 3.11/3.12 standard library, existing canonical JSON helpers, unittest, Bash CI, GitHub Actions.

---

### Task 1: Define the closed v1 release contract

Files:
- Create: skills/robotics-design/scripts/assurance/release/__init__.py
- Create: skills/robotics-design/scripts/assurance/release/model.py
- Create: skills/robotics-design/scripts/assurance/release/schema.py
- Create: tests/test_release_delivery_model.py

- [ ] Step 1: Write failing model and loader tests

~~~python
from assurance.release.model import ReleaseDeliveryFinding, ReleaseDeliveryReport
from assurance.release.schema import ReleaseSchemaError, load_release_contract

def test_report_derives_status_and_never_claims_hardware(self):
    finding = ReleaseDeliveryFinding("RELEASE.BOUNDARY", "indeterminate", "hardware_claims", "hardware evidence is unavailable")
    report = ReleaseDeliveryReport("v1.0.0", "awaiting_external_publication", (finding,))
    self.assertFalse(report.hardware_claims)
    with self.assertRaisesRegex(ValueError, "hardware_claims"):
        ReleaseDeliveryReport("v1.0.0", "passed", (), hardware_claims=True)

def test_loader_rejects_duplicate_noncanonical_and_unsafe_contracts(self):
    for name, payload in {
        "duplicate.json": b'{"release_id":"v1.0.0","release_id":"v1.0.1"}\n',
        "noncanonical.json": b'{ "release_id":"v1.0.0"}\n',
        "unsafe.json": b'{"artifact_bindings":[{"path":"../escape","sha256":"' + b"0" * 64 + b'"}],"hardware_claims":false,"release_id":"v1.0.0","schema_version":1}\n',
    }.items():
        path = self.directory / name
        path.write_bytes(payload)
        with self.assertRaises(ReleaseSchemaError):
            load_release_contract(path)
~~~

- [ ] Step 2: Run RED

Run: python -m unittest tests.test_release_delivery_model -v

Expected: FAIL with ModuleNotFoundError for assurance.release.

- [ ] Step 3: Implement only the closed records and loader

~~~python
@dataclass(frozen=True)
class ReleaseDeliveryReport:
    release_id: str
    status: str
    findings: tuple[ReleaseDeliveryFinding, ...]
    hardware_claims: bool = False

    def __post_init__(self) -> None:
        if self.hardware_claims is not False:
            raise ValueError("hardware_claims must always be false")
        derived = "failed" if any(item.severity == "error" for item in self.findings) else "awaiting_external_publication" if any(item.severity == "indeterminate" for item in self.findings) else "passed"
        if self.status != derived:
            raise ValueError("status must equal derived findings")

    @property
    def passed(self) -> bool:
        return self.status == "passed"
~~~

Use engineering_freeze.schema.load_canonical_json, then require exactly schema_version, release_id, artifact_bindings, and hardware_claims; require schema 1, release ID v1.0.0, false hardware claim, 1–128 unique path/sha256 entries, safe POSIX paths, and lowercase SHA-256. Freeze copies in tuples.

- [ ] Step 4: Run GREEN

Run: python -m unittest tests.test_release_delivery_model -v

Expected: PASS.

- [ ] Step 5: Commit

~~~bash
git add skills/robotics-design/scripts/assurance/release tests/test_release_delivery_model.py
git commit -m "feat: define v1 release delivery contract"
~~~

### Task 2: Verify the bound public delivery surface

Files:
- Create: skills/robotics-design/scripts/assurance/release/evaluator.py
- Create: tests/test_release_delivery_evaluator.py

- [ ] Step 1: Write failing evaluator tests

~~~python
from assurance.release.evaluator import evaluate_release_delivery

def test_rehashed_contract_cannot_hide_stale_public_boundary(self):
    root = self.copy_candidate_tree()
    self.write_canonical_contract(root, self.required_bindings(root))
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("awaiting_authorization", "task validated"), encoding="utf-8")
    self.rehash_contract_binding(root, "README.md")
    report = evaluate_release_delivery(root, root / "release/v1-release-contract.json")
    self.assertFalse(report.passed)
    self.assertIn("RELEASE.PUBLIC_BOUNDARY", {item.code for item in report.findings})

def test_tamper_symlink_extra_and_empty_intake_attacks_fail_closed(self):
    for attack in ("digest", "symlink", "extra", "nonempty_task_intake"):
        root = self.copy_candidate_tree()
        self.write_canonical_contract(root, self.required_bindings(root))
        self.apply_attack(root, attack)
        self.assertFalse(evaluate_release_delivery(root, root / "release/v1-release-contract.json").passed)
~~~

- [ ] Step 2: Run RED

Run: python -m unittest tests.test_release_delivery_evaluator -v

Expected: FAIL because evaluate_release_delivery is absent.

- [ ] Step 3: Implement the evaluator

~~~python
REQUIRED_PATHS = frozenset({
    "README.md", "README.zh-CN.md", "manifest.json", "PROJECT_STATUS.md",
    "docs/releases/v0.4-completion-audit.md", "docs/releases/v0.5-completion-audit.md",
    "docs/releases/v0.6-completion-audit.md", "docs/releases/v0.7-completion-audit.md",
    "docs/releases/v0.8-completion-audit.md", "docs/releases/v0.9-completion-audit.md",
    "scripts/validate.py", "scripts/install.py", "skills/robotics-design/SKILL.md",
    "skills/robotics-design/scripts/validate_design_contract.py",
    "skills/robotics-design/scripts/generate_design_hypotheses.py",
    "skills/robotics-design/scripts/validate_simulation_bundle.py",
    "skills/robotics-design/scripts/validate_bench_evidence.py",
    "skills/robotics-design/scripts/validate_commissioning_evidence.py",
    "skills/robotics-design/scripts/validate_task_evidence.py",
    "reference/mobile-manipulator/bench-evidence/intake-index.json",
    "reference/mobile-manipulator/commissioning/commissioning-index.json",
    "reference/mobile-manipulator/task-evidence/task-evidence-index.json",
})

def evaluate_release_delivery(root: Path, contract_path: Path) -> ReleaseDeliveryReport:
    contract = load_release_contract(contract_path)
    findings = _verify_exact_bindings(root, contract.artifact_bindings)
    findings.extend(_verify_public_semantics(root))
    return ReleaseDeliveryReport(contract.release_id, _derived_status(findings), tuple(sorted(findings, key=_finding_key)))
~~~

The evaluator tests build their canonical contract in each temporary copied root; they do not depend on the tracked contract, which is generated only in Task 3. Require bound paths to equal REQUIRED_PATHS, reject symlinks and digest changes, and check manifest version is 1.0.0. Both READMEs must have no upcoming v0.9, list all six evidence validators plus the release validator, and state software-only/non-hardware verification. Bench must equal schema_version/intake_id/packages-empty; commissioning must equal schema_version/commissioning_id/phases-empty; task evidence must equal schema_version/task_evidence_id/packages-empty. Normalize errors as RELEASE.INVALID_INPUT findings.

- [ ] Step 4: Run GREEN and commit

Run: python -m unittest tests.test_release_delivery_evaluator -v

Expected: PASS.

~~~bash
git add skills/robotics-design/scripts/assurance/release/evaluator.py tests/test_release_delivery_evaluator.py
git commit -m "feat: validate v1 public delivery surface"
~~~

### Task 3: Expose a safe CLI and generate the tracked contract

Files:
- Create: skills/robotics-design/scripts/validate_release_delivery.py
- Create: skills/robotics-design/scripts/generate_release_delivery_contract.py
- Create: release/v1-release-contract.json
- Create: tests/test_release_delivery_cli.py

- [ ] Step 1: Write failing CLI tests

~~~python
def test_generator_and_cli_emit_canonical_passing_report(self):
    root = self.copy_candidate_tree()
    contract = root / "release/v1-release-contract.json"
    self.assertEqual(0, run("generate_release_delivery_contract.py", "--root", root, "--out", contract).returncode)
    result = run("validate_release_delivery.py", "--root", root, "--contract", contract)
    self.assertEqual(0, result.returncode, result.stderr)
    self.assertFalse(json.loads(result.stdout)["hardware_claims"])

def test_cli_returns_two_for_malformed_contract_without_traceback(self):
    result = run("validate_release_delivery.py", "--root", ROOT, "--contract", self.bad_contract)
    self.assertEqual(2, result.returncode)
    self.assertIn("failed safely", result.stderr)
    self.assertNotIn("Traceback", result.stderr)
~~~

- [ ] Step 2: Run RED

Run: python -m unittest tests.test_release_delivery_cli -v

Expected: FAIL because command files do not exist.

- [ ] Step 3: Implement generator and validator

~~~python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate_release_delivery(args.root.resolve(), args.contract.resolve())
        payload = canonical_bytes(report.to_dict())
        if args.report is not None:
            _write_new_regular_file(args.root.resolve(), args.report.resolve(), payload)
        sys.stdout.buffer.write(payload)
        return 0 if report.status == "passed" else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: release delivery validation failed safely: {exc}", file=sys.stderr)
        return 2
~~~

The generator derives every binding from REQUIRED_PATHS, writes canonical bytes only to a new regular output beneath root, and refuses overwrite, path escape, or symlinks. Generate the tracked contract only after Task 4 finalizes bound files.

- [ ] Step 4: Run GREEN and commit

Run: python -m unittest tests.test_release_delivery_cli -v

Expected: PASS.

~~~bash
git add skills/robotics-design/scripts/validate_release_delivery.py skills/robotics-design/scripts/generate_release_delivery_contract.py release/v1-release-contract.json tests/test_release_delivery_cli.py
git commit -m "feat: expose v1 release delivery gate"
~~~

### Task 4: Integrate v1 with distribution validation and bilingual docs

Files:
- Modify: manifest.json
- Modify: scripts/validate.py
- Modify: README.md
- Modify: README.zh-CN.md
- Modify: PROJECT_STATUS.md
- Modify: tests/test_manifest.py
- Modify: tests/test_public_hygiene.py
- Modify: release/v1-release-contract.json

- [ ] Step 1: Write failing integration tests

~~~python
def test_distribution_validator_requires_v1_release_delivery_gate(self):
    validator = (ROOT / "scripts/validate.py").read_text(encoding="utf-8")
    self.assertIn("validate_release_delivery.py", validator)
    self.assertIn("v1-release-contract.json", validator)

def test_bilingual_docs_describe_published_v09_and_v1_nonhardware_verification(self):
    for readme in (ROOT / "README.md", ROOT / "README.zh-CN.md"):
        text = readme.read_text(encoding="utf-8")
        self.assertNotIn("upcoming v0.9", text.lower())
        self.assertIn("validate_release_delivery.py", text)
        self.assertIn("v1.0", text)
~~~

- [ ] Step 2: Run RED

Run: python -m unittest tests.test_public_hygiene tests.test_manifest -v

Expected: FAIL because v1 integration is absent and both READMEs still call v0.9 upcoming.

- [ ] Step 3: Implement integration

Set manifest version to 1.0.0; make scripts/validate.py run the release validator after base manifest validation; replace the two stale v0.9 paragraphs; add this command to both README files:

~~~text
python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1-release-contract.json
~~~

Both language versions must state that this checks public software/evidence provenance and intentionally empty reference intakes, not real-world performance, authority, or evidence level. Update status to the v1 candidate and regenerate the contract after all bytes are final.

- [ ] Step 4: Run GREEN and commit

Run:

~~~bash
python -m unittest tests.test_public_hygiene tests.test_manifest tests.test_release_delivery_model tests.test_release_delivery_evaluator tests.test_release_delivery_cli -v
python scripts/validate.py
python skills/robotics-design/scripts/validate_release_delivery.py --root . --contract release/v1-release-contract.json
~~~

Expected: all pass and report hardware_claims false.

~~~bash
git add manifest.json scripts/validate.py README.md README.zh-CN.md PROJECT_STATUS.md tests/test_manifest.py tests/test_public_hygiene.py release/v1-release-contract.json
git commit -m "feat: integrate v1 reproducible delivery gate"
~~~

### Task 5: Freeze, verify, and publish only observed v1 facts

Files:
- Create: docs/releases/v1.0-completion-audit.md
- Modify: tests/test_public_hygiene.py
- Modify after external release only: docs/releases/v1.0-completion-audit.md and PROJECT_STATUS.md

- [ ] Step 1: Write failing candidate-audit test

~~~python
def test_v100_candidate_audit_preserves_reproducibility_and_hardware_boundary(self):
    audit = (ROOT / "docs/releases/v1.0-completion-audit.md").read_text(encoding="utf-8")
    self.assertIn("v1.0 candidate", audit)
    self.assertIn("hardware_claims: false", audit)
    self.assertIn("not a hardware-validation claim", audit)
    self.assertNotIn("tag CI passed", audit)
~~~

- [ ] Step 2: Run RED

Run: python -m unittest tests.test_public_hygiene.PublicHygieneTests.test_v100_candidate_audit_preserves_reproducibility_and_hardware_boundary -v

Expected: FAIL because the audit does not exist.

- [ ] Step 3: Add candidate audit and execute the full local gate

The audit must enumerate contract result, suite version, test count, distribution validation, installer dry-run, compilation, diff check, reviewed-head/main/tag CI requirements, and GitHub Release requirement. It must leave external run IDs unclaimed, say all reference hardware intakes are empty, and state no hardware authorization is granted.

Run:

~~~bash
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
python -m compileall -q scripts tests skills/robotics-design/scripts
git diff --check origin/main...HEAD
~~~

Expected: all pass.

- [ ] Step 4: Commit and publish

~~~bash
git add docs/releases/v1.0-completion-audit.md tests/test_public_hygiene.py release/v1-release-contract.json
git commit -m "release: prepare v1 reproducible delivery candidate"
~~~

Push a public PR, require reviewed-head cross-platform/fresh-install/Jazzy-Harmonic CI, merge after exact head checks, require merged-main and annotated v1.0.0 tag CI, then publish the GitHub Release. A separate post-release documentation PR replaces candidate wording only with observed IDs. No physical activity or hardware claim is permitted.
