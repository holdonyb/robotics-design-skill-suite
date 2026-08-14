"""Cross-record engineering-freeze evaluator with a permanent hardware firewall."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .model import EngineeringFreezeReport, FreezeFinding
from .schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import validate_sha256


_ROOT = frozenset({"schema_version", "freeze_id", "supplier_manifest", "artifacts", "hazards", "safety_functions", "verifications", "inspection_items", "test_cards"})
_ARTIFACT = frozenset({"id", "kind", "path", "sha256"})
_HAZARD = frozenset({"id", "phase", "pre_risk", "post_risk", "controls", "verification_ids", "safety_function_id", "residual_disposition"})
_SAFETY = frozenset({"id", "initiating_event", "safe_state", "independent_path", "test_card_id"})
_VERIFICATION = frozenset({"id", "artifact_id", "method"})
_INSPECTION = frozenset({"id", "artifact_id", "acceptance"})
_CARD = frozenset({"id", "status", "site_authorization", "reachable_estop", "operators", "energy_limit", "abort_criteria"})


def _finding(code: str, severity: str, path: str, message: str) -> FreezeFinding:
    return FreezeFinding(code, severity, path, message)


def _safe_file(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or "\\" in value:
        return None
    parsed = PurePosixPath(value)
    if not value or parsed.is_absolute() or ".." in parsed.parts:
        return None
    target = root / Path(*parsed.parts)
    if target.is_symlink() or not target.is_file():
        return None
    return target


def _ids(records: object, name: str, findings: list[FreezeFinding]) -> set[str]:
    result: set[str] = set()
    if not isinstance(records, list):
        findings.append(_finding("FREEZE.PACKAGE_INVALID", "error", name, f"{name} must be a list"))
        return result
    for index, item in enumerate(records):
        value = item.get("id") if isinstance(item, dict) else None
        if not isinstance(value, str) or not value:
            findings.append(_finding("FREEZE.RECORD_INVALID", "error", f"{name}[{index}].id", "id must be non-empty"))
        elif value in result:
            findings.append(_finding("FREEZE.DUPLICATE_ID", "error", f"{name}[{index}].id", f"duplicate id: {value}"))
        else:
            result.add(value)
    return result


def evaluate_engineering_freeze(root: Path, package_path: Path, *, placeholder_components: set[str]) -> EngineeringFreezeReport:
    """Evaluate a local engineering package; it never permits procurement or motion."""

    try:
        package = load_canonical_json(package_path)
    except FreezeSchemaError as exc:
        return EngineeringFreezeReport("freeze-invalid", (_finding("FREEZE.PACKAGE_INVALID", "error", "package", str(exc)),), False, False, False)
    findings: list[FreezeFinding] = []
    freeze_id = package.get("freeze_id") if isinstance(package.get("freeze_id"), str) else "freeze-invalid"
    if set(package) != _ROOT or package.get("schema_version") != 1 or freeze_id == "freeze-invalid":
        findings.append(_finding("FREEZE.PACKAGE_INVALID", "error", "package", "package fields are closed and schema_version must be 1"))
    supplier = package.get("supplier_manifest")
    if not isinstance(supplier, dict) or set(supplier) != {"path", "sha256"}:
        findings.append(_finding("FREEZE.SUPPLIER_MANIFEST_INVALID", "error", "supplier_manifest", "supplier manifest needs path and SHA-256"))
    else:
        target = _safe_file(root, supplier.get("path"))
        if target is None:
            findings.append(_finding("FREEZE.SUPPLIER_MANIFEST_INVALID", "error", "supplier_manifest.path", "supplier manifest must be a local regular file"))
        else:
            try:
                expected = validate_sha256(supplier.get("sha256"), "supplier_manifest.sha256")
                if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                    findings.append(_finding("FREEZE.SUPPLIER_MANIFEST_HASH_MISMATCH", "error", "supplier_manifest.sha256", "supplier manifest hash does not match"))
            except ValueError as exc:
                findings.append(_finding("FREEZE.SUPPLIER_MANIFEST_INVALID", "error", "supplier_manifest.sha256", str(exc)))
    artifact_ids = _ids(package.get("artifacts"), "artifacts", findings)
    verification_ids = _ids(package.get("verifications"), "verifications", findings)
    safety_ids = _ids(package.get("safety_functions"), "safety_functions", findings)
    card_ids = _ids(package.get("test_cards"), "test_cards", findings)
    _ids(package.get("hazards"), "hazards", findings)
    _ids(package.get("inspection_items"), "inspection_items", findings)
    for index, item in enumerate(package.get("artifacts", []) if isinstance(package.get("artifacts"), list) else []):
        path = f"artifacts[{index}]"
        if not isinstance(item, dict) or set(item) != _ARTIFACT:
            findings.append(_finding("FREEZE.ARTIFACT_INVALID", "error", path, "artifact fields are closed"))
            continue
        target = _safe_file(root, item.get("path"))
        if target is None:
            findings.append(_finding("FREEZE.ARTIFACT_MISSING", "error", f"{path}.path", "artifact must be a local regular file"))
            continue
        try:
            expected = validate_sha256(item.get("sha256"), f"{path}.sha256")
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                findings.append(_finding("FREEZE.ARTIFACT_HASH_MISMATCH", "error", f"{path}.sha256", "artifact hash does not match"))
        except ValueError as exc:
            findings.append(_finding("FREEZE.ARTIFACT_INVALID", "error", f"{path}.sha256", str(exc)))
    for index, item in enumerate(package.get("hazards", []) if isinstance(package.get("hazards"), list) else []):
        path = f"hazards[{index}]"
        if not isinstance(item, dict) or set(item) != _HAZARD:
            findings.append(_finding("FREEZE.HAZARD_INVALID", "error", path, "hazard fields are closed"))
            continue
        pre, post = item.get("pre_risk"), item.get("post_risk")
        if type(pre) is not int or type(post) is not int or not 1 <= pre <= 5 or not 1 <= post <= 5 or post > pre:
            findings.append(_finding("FREEZE.HAZARD_RISK_INVALID", "error", path, "risks must be integers 1..5 and post_risk cannot exceed pre_risk"))
        if not isinstance(item.get("verification_ids"), list) or any(value not in verification_ids for value in item.get("verification_ids", [])):
            findings.append(_finding("FREEZE.HAZARD_VERIFICATION_UNKNOWN", "error", f"{path}.verification_ids", "hazard must reference known verifications"))
        if item.get("safety_function_id") not in safety_ids:
            findings.append(_finding("FREEZE.HAZARD_SAFETY_UNKNOWN", "error", f"{path}.safety_function_id", "hazard must reference a known safety function"))
        if pre == 5 and item.get("residual_disposition") != "review_required":
            findings.append(_finding("FREEZE.CRITICAL_HAZARD_OPEN", "error", path, "critical hazard must retain review_required residual disposition"))
    for index, item in enumerate(package.get("safety_functions", []) if isinstance(package.get("safety_functions"), list) else []):
        path = f"safety_functions[{index}]"
        if not isinstance(item, dict) or set(item) != _SAFETY or any(not isinstance(item.get(key), str) or not item[key] for key in _SAFETY):
            findings.append(_finding("FREEZE.SAFETY_FUNCTION_INVALID", "error", path, "safety function requires all closed non-empty fields"))
        elif item["test_card_id"] not in card_ids:
            findings.append(_finding("FREEZE.SAFETY_TEST_CARD_UNKNOWN", "error", f"{path}.test_card_id", "safety function must reference a known test card"))
    for name, fields in (("verifications", _VERIFICATION), ("inspection_items", _INSPECTION)):
        for index, item in enumerate(package.get(name, []) if isinstance(package.get(name), list) else []):
            path = f"{name}[{index}]"
            if not isinstance(item, dict) or set(item) != fields or item.get("artifact_id") not in artifact_ids:
                findings.append(_finding("FREEZE.ARTIFACT_REFERENCE_UNKNOWN", "error", path, f"{name} must use closed fields and a known artifact"))
    for index, item in enumerate(package.get("test_cards", []) if isinstance(package.get("test_cards"), list) else []):
        path = f"test_cards[{index}]"
        if not isinstance(item, dict):
            findings.append(_finding("FREEZE.TEST_CARD_INVALID", "error", path, "test card fields are closed and status must be planned"))
            continue
        if set(item) != _CARD or item.get("status") != "planned":
            findings.append(_finding("FREEZE.TEST_CARD_INVALID", "error", path, "test card fields are closed and status must be planned"))
        if item.get("site_authorization") != "required" or item.get("reachable_estop") != "required" or not isinstance(item.get("operators"), list) or len(item["operators"]) < 2 or not isinstance(item.get("abort_criteria"), list) or not item["abort_criteria"] or not isinstance(item.get("energy_limit"), str) or not item["energy_limit"]:
            findings.append(_finding("FREEZE.TEST_CARD_PRECONDITION", "error", path, "planned card requires site authorization, reachable E-stop, two roles, energy limit, and abort criteria"))
    for component_id in sorted(placeholder_components):
        findings.append(_finding("FREEZE.PLACEHOLDER_COMPONENT", "indeterminate", "components", f"placeholder component blocks freeze: {component_id}"))
    findings = sorted(findings, key=lambda item: (item.code, item.path, item.message, item.severity))
    return EngineeringFreezeReport(freeze_id, tuple(findings), not any(item.severity in {"error", "indeterminate"} for item in findings), False, False)
