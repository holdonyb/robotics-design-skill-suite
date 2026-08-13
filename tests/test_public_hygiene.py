import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "manifest.json",
    "PROJECT_STATUS.md",
    "docs/releases/v0.4-completion-audit.md",
    "docs/research/2026-08-14-v05-dependency-audit.md",
    "reference/mobile-manipulator/simulation-benchmark.md",
    "scripts/install.py",
    "scripts/validate.py",
    "skills/robotics-design/SKILL.md",
    "skills/robotics-design/references/visualization-contract.md",
    "skills/robotics-design/references/mission-animation-contract.md",
    "skills/robotics-design/references/patent-design-around.md",
    "skills/robotics-design/references/physical-plausibility-contract.md",
    "skills/robotics-design/references/hypothesis-engine-contract.md",
    "skills/robotics-design/scripts/validate_design_contract.py",
    "skills/robotics-design/scripts/generate_design_hypotheses.py",
    "reference/mobile-manipulator/design-contract.json",
    "reference/mobile-manipulator/hypothesis-space.json",
    "reference/mobile-manipulator/hypothesis-expected.json",
    "reference/mobile-manipulator/robot.urdf",
    "skills/robotics-design/scripts/validate_visual_manifest.py",
    "skills/robotics-design/scripts/validate_mission_animation_manifest.py",
    ".github/workflows/ci.yml",
    ".github/workflows/simulation.yml",
    ".gitattributes",
}
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".txt"}
FORBIDDEN = {
    "windows_drive": re.compile(r"\b[A-Za-z]:[\\/]"),
    "private_user_path": re.compile(r"(?:Users|home)[\\/]" + "hol" + "do", re.IGNORECASE),
    "private_workspace": re.compile("京" + "新数智"),
    "private_installation": re.compile("Local" + "/private", re.IGNORECASE),
    "github_token": re.compile(r"(?:gho|ghp|github_pat)_[A-Za-z0-9_]+"),
    "api_key": re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    "placeholder": re.compile(r"\b(?:" + "T" + r"BD|T" + r"ODO|FIX" + r"ME)\b"),
}


def deployable_text_files():
    excluded = {".git", ".worktrees", ".tmp-install", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in excluded for part in path.relative_to(ROOT).parts):
            continue
        yield path


class PublicHygieneTests(unittest.TestCase):
    def test_hash_bound_text_has_checkout_stable_lf_attributes(self):
        completed = subprocess.run(
            [
                "git", "check-attr", "eol", "--",
                "reference/mobile-manipulator/robot.urdf",
                "reference/mobile-manipulator/assumptions.json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        lines = [line for line in completed.stdout.splitlines() if line]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.endswith("eol: lf") for line in lines), lines)

    def test_local_delta_record_has_no_unresolved_disposition(self):
        record = (ROOT / "docs/research/2026-08-13-active-local-delta.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("unclassified", record.lower())
        for disposition in (
            "promote_with_tests",
            "superseded_by_v020_review_fix",
            "host_only",
            "generated_drop",
        ):
            self.assertIn(disposition, record)

    def test_required_release_files_exist(self):
        missing = sorted(item for item in REQUIRED if not (ROOT / item).is_file())
        self.assertEqual(missing, [])

    def test_deployable_files_do_not_leak_private_data(self):
        findings = []
        for path in deployable_text_files():
            text = path.read_text(encoding="utf-8")
            for label, pattern in FORBIDDEN.items():
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual(findings, [])

    def test_router_references_declared_skill_names(self):
        text = (ROOT / "skills" / "robotics-design" / "SKILL.md").read_text(encoding="utf-8")
        expected = {
            "$cad",
            "$cad-viewer",
            "$step-parts",
            "$dxf",
            "$urdf",
            "$sdf",
            "$srdf",
            "$ros2-engineering-skills",
            "$ros2-sim",
            "$deep-research",
            "$imagegen",
        }
        self.assertEqual({name for name in expected if name in text}, expected)

    def test_router_static_local_references_exist(self):
        skill_root = ROOT / "skills" / "robotics-design"
        text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        references = set(re.findall(r"`((?:references|scripts)/[^`]+\.(?:md|py))`", text))
        optional = {"references/host-runtime.md"}
        missing = sorted(item for item in references - optional if not (skill_root / item).is_file())
        self.assertEqual(missing, [])

    def test_tracked_distribution_excludes_generated_bytecode(self):
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        tracked = [Path(item.decode("utf-8")) for item in completed.stdout.split(b"\0") if item]
        generated = sorted(
            str(path) for path in tracked if "__pycache__" in path.parts or path.suffix == ".pyc"
        )
        self.assertEqual(generated, [])

    def test_bilingual_docs_describe_v020_workflows(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        source_lock = (
            ROOT / "skills" / "robotics-design" / "references" / "source-lock.md"
        ).read_text(encoding="utf-8").lower()
        for phrase in ("mission animation", "patent-aware", "--host-runtime-python"):
            self.assertIn(phrase, english)
        for phrase in ("任务动画", "专利", "--host-runtime-python"):
            self.assertIn(phrase, chinese)
        self.assertIn("mission-animation", source_lock)
        self.assertIn("patent-aware", source_lock)

    def test_bilingual_docs_expose_hypothesis_quick_start_and_nonclaims(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        command = "generate_design_hypotheses.py"
        for phrase in (command, "screening-pareto.json", "0.4"):
            self.assertIn(phrase, english)
            self.assertIn(phrase, chinese)
        self.assertIn("does not prove simulation or hardware performance", english)
        self.assertIn("不能证明仿真或实机性能", chinese)

    def test_bilingual_docs_expose_simulation_quick_start_and_hardware_boundary(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        for phrase in (
            "validate_simulation_bundle.py",
            "portable synthetic replay",
            "hardware promotion",
        ):
            self.assertIn(phrase, english)
        for phrase in (
            "validate_simulation_bundle.py",
            "便携式合成回放",
            "硬件",
        ):
            self.assertIn(phrase, chinese)

    def test_live_simulation_workflow_is_an_additional_gate_not_a_silent_success(self):
        workflow = (ROOT / ".github/workflows/simulation.yml").read_text(encoding="utf-8")
        for phrase in (
            "ubuntu-24.04",
            "Dockerfile.jazzy-harmonic",
            "run_live_simulation_gate.sh",
            "if: always()",
            "upload-artifact",
        ):
            self.assertIn(phrase, workflow)
        self.assertNotIn("continue-on-error: true", workflow)

    def test_ci_compiles_local_skill_runtime_before_tests(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "python -m compileall -q scripts tests skills/robotics-design/scripts",
            ci,
        )

    def test_ci_runs_fresh_install_and_pinned_official_skill_validation(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for required in (
            "release-install:",
            "python scripts/install.py --dest .release-install",
            "openai/skills/49f948faa9258a0c61caceaf225e179651397431",
            "PyYAML==6.0.3",
            "quick_validate.py",
            "UPSTREAM_LICENSE",
            "license_path",
            "raw.githubusercontent.com",
            "license content mismatch",
            "__pycache__",
            "host-runtime.md",
            "assurance/hypothesis/engine.py",
            "include-hidden-files: true",
        ):
            self.assertIn(required, ci)

    def test_v040_status_and_completion_audit_are_evidence_bounded(self):
        status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
        audit = (ROOT / "docs/releases/v0.4-completion-audit.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "6 candidates",
            "76 stage evaluations",
            "0 accepted",
            "v0.5",
            "simulation",
            "hardware",
        ):
            self.assertIn(phrase, status)
        for gate in (
            "Candidates never bypass v0.3 physical gates",
            "Identical inputs and seeds reproduce",
            "Injected design flaws are traced",
            "reference design trade-off is improved",
            "Uncertainty and counterexample results affect promotion",
            "Public release",
        ):
            self.assertIn(gate, audit)
        self.assertNotIn("| OPEN |", audit)
        for evidence in (
            "6881a2c",
            "31715656399",
            "31715652132",
            "10/10 skills",
            "9/9 per-skill pinned-source license byte matches",
            "whole-release adversarial review",
        ):
            self.assertIn(evidence, status + audit)
        for release_evidence in (
            "f37cd3b",
            "31716689574",
            "31716834403",
            "v0.4.0",
            "robotics-design-pre-v040-20260813-2350",
        ):
            self.assertIn(release_evidence, status + audit)
        self.assertNotIn("v0.4 remains open", audit)


if __name__ == "__main__":
    unittest.main()
