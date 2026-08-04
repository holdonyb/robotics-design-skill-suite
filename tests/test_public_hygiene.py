import re
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
    "scripts/install.py",
    "scripts/validate.py",
    "skills/robotics-design/SKILL.md",
    ".github/workflows/ci.yml",
}
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".txt"}
FORBIDDEN = {
    "windows_drive": re.compile(r"\b[A-Za-z]:[\\/]"),
    "private_user_path": re.compile(r"(?:Users|home)[\\/]" + "hol" + "do", re.IGNORECASE),
    "private_workspace": re.compile("京" + "新数智"),
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
        }
        self.assertEqual({name for name in expected if name in text}, expected)


if __name__ == "__main__":
    unittest.main()
