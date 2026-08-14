"""Validate externally supplied commissioning authority records without granting authority."""

from __future__ import annotations

import hashlib
import math
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from ..engineering_freeze.schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import validate_identifier, validate_sha256
from .model import CommissioningFinding


_ROOT = frozenset(
    {
        "schema_version",
        "authority_record_id",
        "authorization_kind",
        "design_contract_sha256",
        "phase",
        "execution_window",
        "site_id",
        "area_id",
        "estop_id",
        "roles",
        "limits",
        "watchdog_timeout_ns",
        "attested_by_role",
        "approval_reference",
    }
)
_BINDING = frozenset({"path", "sha256"})
_WINDOW = frozenset({"start_date", "end_date"})
_LIMITS = frozenset({"energy_j", "speed_m_s", "torque_nm"})


def _finding(code: str, path: str, message: str) -> CommissioningFinding:
    return CommissioningFinding(code, "error", path, message)


def _safe_file(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        return None
    target = root
    for part in parsed.parts:
        target = target / part
        if target.is_symlink():
            return None
    return target if target.is_file() else None


def _bound_record(root: Path, binding: object, findings: list[CommissioningFinding]) -> dict[str, Any] | None:
    if not isinstance(binding, dict) or set(binding) != _BINDING:
        findings.append(_finding("COMM.AUTHORITY_BINDING_INVALID", "authority_record", "authority record requires exactly path and SHA-256"))
        return None
    target = _safe_file(root, binding.get("path"))
    if target is None:
        findings.append(_finding("COMM.AUTHORITY_PATH_INVALID", "authority_record.path", "authority record must be a local regular non-symlink file"))
        return None
    try:
        expected = validate_sha256(binding.get("sha256"), "authority_record.sha256")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        findings.append(_finding("COMM.AUTHORITY_BINDING_INVALID", "authority_record", str(exc)))
        return None
    if actual != expected:
        findings.append(_finding("COMM.AUTHORITY_HASH_MISMATCH", "authority_record.sha256", "authority record hash does not match"))
        return None
    try:
        return load_canonical_json(target)
    except FreezeSchemaError as exc:
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record", str(exc)))
        return None


def _finite_positive(value: object) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(float(value)) and float(value) > 0.0
    except OverflowError:
        return False


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _validate_record(data: object, findings: list[CommissioningFinding]) -> dict[str, Any] | None:
    if not isinstance(data, dict) or set(data) != _ROOT or data.get("schema_version") != 1:
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record", "authority record fields are closed and schema_version must be 1"))
        return None
    for field in ("authority_record_id", "phase", "site_id", "area_id", "estop_id"):
        try:
            validate_identifier(data.get(field), f"authority_record.{field}")
        except ValueError as exc:
            findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", f"authority_record.{field}", str(exc)))
    if data.get("authorization_kind") != "external_human_attestation":
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.authorization_kind", "authority record must declare external_human_attestation"))
    try:
        validate_sha256(data.get("design_contract_sha256"), "authority_record.design_contract_sha256")
    except ValueError as exc:
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.design_contract_sha256", str(exc)))
    window = data.get("execution_window")
    start = end = None
    if not isinstance(window, dict) or set(window) != _WINDOW:
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.execution_window", "execution window needs exactly start_date and end_date"))
    else:
        start, end = _iso_date(window.get("start_date")), _iso_date(window.get("end_date"))
        if start is None or end is None or start > end:
            findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.execution_window", "execution window must be an ordered canonical ISO date interval"))
    roles = data.get("roles")
    if not isinstance(roles, list) or len(roles) < 2 or any(not isinstance(item, str) or not item for item in roles) or len(set(roles)) != len(roles):
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.roles", "authority record requires at least two unique non-empty roles"))
    limits = data.get("limits")
    if not isinstance(limits, dict) or set(limits) != _LIMITS or any(not _finite_positive(limits.get(field)) for field in _LIMITS):
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.limits", "authority limits must be positive finite energy, speed, and torque"))
    if type(data.get("watchdog_timeout_ns")) is not int or data["watchdog_timeout_ns"] <= 0:
        findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", "authority_record.watchdog_timeout_ns", "authority watchdog timeout must be a positive integer"))
    for field in ("attested_by_role", "approval_reference"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            findings.append(_finding("COMM.AUTHORITY_RECORD_INVALID", f"authority_record.{field}", "authority attestation fields must be non-empty strings"))
    return data


def validate_authority_record(
    root: Path,
    binding: object,
    phase: object,
    expected_design_contract_sha256: object | None,
) -> tuple[CommissioningFinding, ...]:
    """Cross-bind one external attestation to one recorded phase.

    This function verifies retained evidence only. It never grants procurement
    or motion authority.
    """

    findings: list[CommissioningFinding] = []
    data = _bound_record(root, binding, findings)
    if data is None:
        return tuple(findings)
    record = _validate_record(data, findings)
    if record is None:
        return tuple(findings)
    if not isinstance(phase, dict):
        findings.append(_finding("COMM.AUTHORITY_SCOPE_MISMATCH", "phase", "recorded phase must be an object"))
        return tuple(findings)
    expected = None
    if expected_design_contract_sha256 is not None:
        try:
            expected = validate_sha256(expected_design_contract_sha256, "expected design contract SHA-256")
        except ValueError as exc:
            findings.append(_finding("COMM.AUTHORITY_EXPECTED_DESIGN_INVALID", "design_contract", str(exc)))
    if expected is not None and record["design_contract_sha256"] != expected:
        findings.append(_finding("COMM.AUTHORITY_DESIGN_MISMATCH", "authority_record.design_contract_sha256", "authority record is bound to a different design contract"))
    if record["phase"] != phase.get("phase"):
        findings.append(_finding("COMM.AUTHORITY_PHASE_MISMATCH", "authority_record.phase", "authority record does not cover this commissioning phase"))
    for field in ("site_id", "area_id", "estop_id"):
        if record[field] != phase.get(field):
            findings.append(_finding("COMM.AUTHORITY_SCOPE_MISMATCH", f"authority_record.{field}", f"authority {field} does not match the recorded phase"))
    phase_roles = phase.get("roles")
    record_roles = record.get("roles")
    if (
        not isinstance(phase_roles, list)
        or not isinstance(record_roles, list)
        or any(not isinstance(role, str) for role in phase_roles)
        or any(not isinstance(role, str) for role in record_roles)
        or set(record_roles) != set(phase_roles)
    ):
        findings.append(_finding("COMM.AUTHORITY_SCOPE_MISMATCH", "authority_record.roles", "authority roles must exactly match the recorded phase roles"))
    execution_date = _iso_date(phase.get("execution_date"))
    window = record.get("execution_window")
    start = _iso_date(window.get("start_date")) if isinstance(window, dict) else None
    end = _iso_date(window.get("end_date")) if isinstance(window, dict) else None
    if execution_date is None or start is None or end is None or not start <= execution_date <= end:
        findings.append(_finding("COMM.AUTHORITY_DATE_INVALID", "authority_record.execution_window", "phase execution_date must be inside the authority execution window"))
    phase_limits = phase.get("limits")
    record_limits = record.get("limits")
    if not isinstance(phase_limits, dict) or not isinstance(record_limits, dict) or any(not _finite_positive(phase_limits.get(field)) or float(phase_limits[field]) > float(record_limits[field]) for field in _LIMITS):
        findings.append(_finding("COMM.AUTHORITY_LIMIT_EXCEEDED", "authority_record.limits", "phase limits must be positive and not exceed authority limits"))
    timeout = phase.get("watchdog_timeout_ns")
    if type(timeout) is not int or type(record.get("watchdog_timeout_ns")) is not int or timeout <= 0 or timeout > record["watchdog_timeout_ns"]:
        findings.append(_finding("COMM.AUTHORITY_TIMEOUT_EXCEEDED", "authority_record.watchdog_timeout_ns", "phase watchdog timeout must not exceed authority timeout"))
    findings.sort(key=lambda item: (item.code, item.path, item.message, item.severity))
    return tuple(findings)
