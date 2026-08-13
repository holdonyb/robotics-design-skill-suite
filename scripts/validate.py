#!/usr/bin/env python3
"""Validate the public distribution using only the Python standard library."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SKILL_NAME = re.compile(r"^[a-z0-9-]+$")


def validate() -> list[str]:
    errors: list[str] = []
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")

    names: list[str] = []
    for source in data.get("sources", []):
        if not COMMIT.fullmatch(source.get("commit", "")):
            errors.append(f"{source.get('id')}: commit is not a full SHA-1")
        if source.get("license") not in {"MIT", "Apache-2.0"}:
            errors.append(f"{source.get('id')}: unsupported or missing license")
        for skill in source.get("skills", []):
            names.append(skill.get("name", ""))

    for skill in data.get("local_skills", []):
        name = skill.get("name", "")
        names.append(name)
        path = ROOT / skill.get("path", "")
        if not (path / "SKILL.md").is_file():
            errors.append(f"local skill missing SKILL.md: {path}")

    if len(names) != len(set(names)):
        errors.append("skill destination names are not unique")
    for name in names:
        if not SKILL_NAME.fullmatch(name):
            errors.append(f"invalid skill name: {name}")

    router = ROOT / "skills" / "robotics-design"
    required_refs = {
        "design-contract.md",
        "validation-gates.md",
        "authority-map.md",
        "runtime.md",
        "source-lock.md",
        "visualization-contract.md",
        "mission-animation-contract.md",
        "patent-design-around.md",
        "physical-plausibility-contract.md",
        "hypothesis-engine-contract.md",
        "simulation-evidence-contract.md",
    }
    actual_refs = {path.name for path in (router / "references").glob("*.md")}
    missing_refs = required_refs - actual_refs
    if missing_refs:
        errors.append("router references missing: " + ", ".join(sorted(missing_refs)))

    skill_text = (router / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\nname: robotics-design\n"):
        errors.append("robotics-design frontmatter is invalid")
    if "description: Use when" not in skill_text.split("---", 2)[1]:
        errors.append("robotics-design description must start with Use when")
    required_visual_clauses = {
        "references/visualization-contract.md",
        "Never ask a generative model to articulate, repose, unfold, or reconfigure a robot",
        "A disclaimer does not make a structurally wrong robot image acceptable",
    }
    missing_clauses = sorted(clause for clause in required_visual_clauses if clause not in skill_text)
    if missing_clauses:
        errors.append("robotics-design visual gates missing: " + ", ".join(missing_clauses))

    visual_validator = router / "scripts" / "validate_visual_manifest.py"
    if not visual_validator.is_file():
        errors.append("robotics-design visual manifest validator is missing")
    mission_validator = router / "scripts" / "validate_mission_animation_manifest.py"
    if not mission_validator.is_file():
        errors.append("robotics-design mission animation validator is missing")
    physical_validator = router / "scripts" / "validate_design_contract.py"
    if not physical_validator.is_file():
        errors.append("robotics-design physical contract validator is missing")
    simulation_validator = router / "scripts" / "validate_simulation_bundle.py"
    if not simulation_validator.is_file():
        errors.append("robotics-design simulation evidence validator is missing")
    required_workflow_clauses = {
        "references/mission-animation-contract.md",
        "references/patent-design-around.md",
        "Never keyframe robot joint poses by hand",
        "qualified counsel",
        "references/physical-plausibility-contract.md",
        "validate_design_contract.py",
        "Simulation cannot supply a missing component",
        "references/simulation-evidence-contract.md",
        "validate_simulation_bundle.py",
        "Training callbacks have no actuator interface",
    }
    missing_workflows = sorted(
        clause for clause in required_workflow_clauses if clause not in skill_text
    )
    if missing_workflows:
        errors.append("robotics-design workflow gates missing: " + ", ".join(missing_workflows))
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    count = sum(len(source["skills"]) for source in manifest["sources"]) + len(manifest["local_skills"])
    print(f"Distribution valid: {count} skills, {len(manifest['sources'])} pinned sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
