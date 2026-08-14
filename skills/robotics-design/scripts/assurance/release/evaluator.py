"""Verify the closed v1 public-delivery surface without hardware access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from .model import ReleaseDeliveryFinding, ReleaseDeliveryReport
from .schema import ReleaseContract, load_release_contract


V100_REQUIRED_PATHS = frozenset(
    {
        "README.md",
        "README.zh-CN.md",
        "manifest.json",
        "PROJECT_STATUS.md",
        "docs/releases/v0.4-completion-audit.md",
        "docs/releases/v0.5-completion-audit.md",
        "docs/releases/v0.6-completion-audit.md",
        "docs/releases/v0.7-completion-audit.md",
        "docs/releases/v0.8-completion-audit.md",
        "docs/releases/v0.9-completion-audit.md",
        "scripts/install.py",
        "scripts/validate.py",
        "skills/robotics-design/SKILL.md",
        "skills/robotics-design/scripts/generate_design_hypotheses.py",
        "skills/robotics-design/scripts/validate_bench_evidence.py",
        "skills/robotics-design/scripts/validate_commissioning_evidence.py",
        "skills/robotics-design/scripts/validate_design_contract.py",
        "skills/robotics-design/scripts/validate_simulation_bundle.py",
        "skills/robotics-design/scripts/validate_task_evidence.py",
        "reference/mobile-manipulator/bench-evidence/intake-index.json",
        "reference/mobile-manipulator/commissioning/commissioning-index.json",
        "reference/mobile-manipulator/task-evidence/task-evidence-index.json",
    }
)

V110_RUNTIME_PATHS = frozenset(
    {
        "reference/mobile-manipulator/component-mass-closure.json",
        "reference/mobile-manipulator/design-contract.json",
        "skills/robotics-design/references/hardware-authority-contract.md",
        "skills/robotics-design/scripts/generate_release_delivery_contract.py",
        "skills/robotics-design/scripts/validate_release_delivery.py",
        "skills/robotics-design/scripts/assurance/commissioning/__init__.py",
        "skills/robotics-design/scripts/assurance/commissioning/authority.py",
        "skills/robotics-design/scripts/assurance/commissioning/evaluator.py",
        "skills/robotics-design/scripts/assurance/commissioning/model.py",
        "skills/robotics-design/scripts/assurance/engineering_freeze/__init__.py",
        "skills/robotics-design/scripts/assurance/engineering_freeze/evaluator.py",
        "skills/robotics-design/scripts/assurance/engineering_freeze/model.py",
        "skills/robotics-design/scripts/assurance/engineering_freeze/schema.py",
        "skills/robotics-design/scripts/assurance/engineering_freeze/suppliers.py",
        "skills/robotics-design/scripts/assurance/hypothesis/canonical.py",
        "skills/robotics-design/scripts/assurance/release/__init__.py",
        "skills/robotics-design/scripts/assurance/release/evaluator.py",
        "skills/robotics-design/scripts/assurance/release/model.py",
        "skills/robotics-design/scripts/assurance/release/schema.py",
    }
)
V110_REQUIRED_PATHS = V100_REQUIRED_PATHS | V110_RUNTIME_PATHS

# Compatibility alias used by v1.0 regression fixtures and external callers.
REQUIRED_PATHS = V100_REQUIRED_PATHS
REQUIRED_PATHS_BY_RELEASE = {
    "v1.0.0": V100_REQUIRED_PATHS,
    "v1.1.0": V110_REQUIRED_PATHS,
}
MANIFEST_VERSION_BY_RELEASE = {"v1.0.0": "1.0.0", "v1.1.0": "1.1.0"}


def required_paths_for(release_id: str) -> frozenset[str]:
    """Return the immutable binding allow-list for a supported release."""

    if not isinstance(release_id, str):
        raise ValueError(f"unsupported release_id: {release_id}") from None
    try:
        return REQUIRED_PATHS_BY_RELEASE[release_id]
    except KeyError:
        raise ValueError(f"unsupported release_id: {release_id}") from None

_README_VALIDATORS = (
    "validate_design_contract.py",
    "validate_simulation_bundle.py",
    "validate_bench_evidence.py",
    "validate_commissioning_evidence.py",
    "validate_task_evidence.py",
    "validate_release_delivery.py",
)

_EMPTY_INTAKES = {
    "reference/mobile-manipulator/bench-evidence/intake-index.json": {
        "schema_version": 1,
        "intake_id": "bench-reference",
        "packages": [],
    },
    "reference/mobile-manipulator/commissioning/commissioning-index.json": {
        "schema_version": 1,
        "commissioning_id": "commissioning-reference",
        "phases": [],
    },
    "reference/mobile-manipulator/task-evidence/task-evidence-index.json": {
        "schema_version": 1,
        "task_evidence_id": "task-evidence-reference",
        "packages": [],
    },
}


def _finding(code: str, path: str, message: str) -> ReleaseDeliveryFinding:
    return ReleaseDeliveryFinding(code, "error", path, message)


def _safe_target(root: Path, relative: str) -> Path:
    parsed = PurePosixPath(relative)
    target = root
    for part in parsed.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError(f"{relative} traverses a symbolic link")
    if not target.is_file():
        raise ValueError(f"{relative} must name a local regular file")
    return target


def _verify_bindings(root: Path, contract: ReleaseContract) -> list[ReleaseDeliveryFinding]:
    findings: list[ReleaseDeliveryFinding] = []
    bindings = dict(contract.artifact_bindings)
    actual_paths = frozenset(bindings)
    required_paths = required_paths_for(contract.release_id)
    if actual_paths != required_paths:
        missing = sorted(required_paths - actual_paths)
        extra = sorted(actual_paths - required_paths)
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if extra:
            detail.append("extra: " + ", ".join(extra))
        findings.append(_finding("RELEASE.BINDING_SET", "artifact_bindings", "; ".join(detail)))
    for relative, expected in contract.artifact_bindings:
        try:
            target = _safe_target(root, relative)
            observed = hashlib.sha256(target.read_bytes()).hexdigest()
            if observed != expected:
                findings.append(_finding("RELEASE.STALE_ARTIFACT", relative, "SHA-256 does not match release contract"))
        except (OSError, ValueError) as exc:
            findings.append(_finding("RELEASE.BOUND_PATH", relative, str(exc)))
    return findings


def _read_text(root: Path, relative: str, findings: list[ReleaseDeliveryFinding]) -> str | None:
    try:
        return _safe_target(root, relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        findings.append(_finding("RELEASE.INVALID_INPUT", relative, f"cannot read text: {exc}"))
        return None


def _verify_semantics(root: Path, release_id: str) -> list[ReleaseDeliveryFinding]:
    findings: list[ReleaseDeliveryFinding] = []
    english = _read_text(root, "README.md", findings)
    chinese = _read_text(root, "README.zh-CN.md", findings)
    if english is not None:
        normalized_english = " ".join(english.split())
        for phrase in _README_VALIDATORS:
            if phrase not in english:
                findings.append(_finding("RELEASE.PUBLIC_BOUNDARY", "README.md", f"missing public validator reference: {phrase}"))
        for phrase in ("This command verifies public software and evidence delivery", "does not validate physical robot performance", "authorize hardware"):
            if phrase not in normalized_english:
                findings.append(_finding("RELEASE.PUBLIC_BOUNDARY", "README.md", f"missing v1 evidence boundary: {phrase}"))
        if "upcoming v0.9" in english.lower():
            findings.append(_finding("RELEASE.PUBLIC_BOUNDARY", "README.md", "published v0.9 must not be described as upcoming"))
    if chinese is not None:
        for phrase in _README_VALIDATORS:
            if phrase not in chinese:
                findings.append(_finding("RELEASE.PUBLIC_BOUNDARY", "README.zh-CN.md", f"missing public validator reference: {phrase}"))
        for phrase in ("此命令验证公开的软件与证据交付", "不验证实体机器人性能", "不授权硬件操作"):
            if phrase not in chinese:
                findings.append(_finding("RELEASE.PUBLIC_BOUNDARY", "README.zh-CN.md", f"missing v1 evidence boundary: {phrase}"))
        if "即将到来的 v0.9" in chinese:
            findings.append(_finding("RELEASE.PUBLIC_BOUNDARY", "README.zh-CN.md", "published v0.9 must not be described as upcoming"))
    try:
        manifest = json.loads(_safe_target(root, "manifest.json").read_text(encoding="utf-8"))
        expected_version = MANIFEST_VERSION_BY_RELEASE[release_id]
        if not isinstance(manifest, dict) or manifest.get("suite", {}).get("version") != expected_version:
            findings.append(_finding("RELEASE.MANIFEST_VERSION", "manifest.json", f"suite version must be {expected_version}"))
    except (OSError, UnicodeError, ValueError, AttributeError) as exc:
        findings.append(_finding("RELEASE.INVALID_INPUT", "manifest.json", f"cannot validate suite version: {exc}"))
    for relative, expected in _EMPTY_INTAKES.items():
        try:
            observed = json.loads(_safe_target(root, relative).read_text(encoding="utf-8"))
            if observed != expected:
                findings.append(_finding("RELEASE.EMPTY_INTAKE", relative, "shipped reference intake must remain exactly empty"))
        except (OSError, UnicodeError, ValueError) as exc:
            findings.append(_finding("RELEASE.INVALID_INPUT", relative, f"cannot validate empty intake: {exc}"))
    return findings


def evaluate_release_delivery(root: Path, contract_path: Path) -> ReleaseDeliveryReport:
    """Return a deterministic v1 report; any content issue fails the delivery."""

    resolved_root = Path(root).resolve()
    if not resolved_root.is_dir() or resolved_root.is_symlink():
        raise ValueError("root must be a local non-symlink directory")
    contract = load_release_contract(Path(contract_path))
    findings = _verify_bindings(resolved_root, contract) + _verify_semantics(resolved_root, contract.release_id)
    findings.sort(key=lambda item: (item.code, item.path, item.message, item.severity))
    return ReleaseDeliveryReport(contract.release_id, "failed" if findings else "passed", tuple(findings))
