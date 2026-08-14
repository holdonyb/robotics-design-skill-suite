"""Closed offline validation for staged commissioning evidence."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path, PurePosixPath
from typing import Any

from ..engineering_freeze.schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import validate_identifier, validate_sha256
from .authority import validate_authority_record
from .model import CommissioningFinding, CommissioningReport


_ROOT = frozenset({"schema_version", "commissioning_id", "phases"})
_PHASE = frozenset({"phase", "status", "test_card_id", "execution_date", "authority_record", "roles", "site_id", "area_id", "estop_id", "limits", "watchdog_timeout_ns", "abort_criteria", "command_trace", "state_trace", "stop_trace", "inspection_record"})
_BOUND_FILE = frozenset({"path", "sha256"})
_LIMITS = frozenset({"energy_j", "speed_m_s", "torque_nm"})
_PHASES = ("unpowered_inspection", "protected_power", "isolated_joint", "separated_base_arm", "integrated_low_energy")
_RECORDED = frozenset({"recorded", "aborted"})
_MAX_EVENTS = 10_000


def _finding(code: str, severity: str, path: str, message: str) -> CommissioningFinding:
    return CommissioningFinding(code, severity, path, message)


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


def _bound_json(root: Path, value: object, path: str, findings: list[CommissioningFinding]) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _BOUND_FILE:
        findings.append(_finding("COMM.EVIDENCE_BINDING_INVALID", "error", path, "evidence needs exactly path and SHA-256"))
        return None
    target = _safe_file(root, value.get("path"))
    if target is None:
        findings.append(_finding("COMM.EVIDENCE_PATH_INVALID", "error", f"{path}.path", "evidence must be a local regular non-symlink file"))
        return None
    try:
        expected = validate_sha256(value.get("sha256"), f"{path}.sha256")
    except ValueError as exc:
        findings.append(_finding("COMM.EVIDENCE_BINDING_INVALID", "error", f"{path}.sha256", str(exc)))
        return None
    try:
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError as exc:
        findings.append(_finding("COMM.EVIDENCE_READ_INVALID", "error", path, f"cannot read evidence safely: {exc}"))
        return None
    if actual != expected:
        findings.append(_finding("COMM.EVIDENCE_HASH_MISMATCH", "error", f"{path}.sha256", "evidence hash does not match"))
        return None
    try:
        return load_canonical_json(target)
    except FreezeSchemaError as exc:
        findings.append(_finding("COMM.EVIDENCE_JSON_INVALID", "error", path, str(exc)))
        return None


def _finite(value: object) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(float(value))
    except OverflowError:
        return False


def _events(data: object, path: str, fields: frozenset[str], findings: list[CommissioningFinding]) -> list[dict[str, Any]] | None:
    if not isinstance(data, dict) or set(data) != {"schema_version", "events"} or data.get("schema_version") != 1 or not isinstance(data.get("events"), list) or not data["events"] or len(data["events"]) > _MAX_EVENTS:
        findings.append(_finding("COMM.TRACE_INVALID", "error", path, "trace must be a bounded schema-v1 event object"))
        return None
    records = data["events"]
    timestamps: list[int] = []
    for index, item in enumerate(records):
        item_path = f"{path}.events[{index}]"
        if not isinstance(item, dict) or set(item) != fields or type(item.get("timestamp_ns")) is not int or item["timestamp_ns"] < 0:
            findings.append(_finding("COMM.TRACE_INVALID", "error", item_path, "trace event fields are closed and timestamp_ns must be non-negative integer"))
            continue
        timestamps.append(item["timestamp_ns"])
    if timestamps and (timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps)):
        findings.append(_finding("COMM.TRACE_TIMESTAMPS", "error", path, "trace timestamps must be strictly increasing"))
    return records


def _validate_limits(value: object, path: str, findings: list[CommissioningFinding]) -> dict[str, float] | None:
    if not isinstance(value, dict) or set(value) != _LIMITS or any(not _finite(value.get(name)) or float(value[name]) <= 0 for name in _LIMITS):
        findings.append(_finding("COMM.LIMIT_INVALID", "error", path, "energy, speed, and torque limits must be positive finite numbers"))
        return None
    return {name: float(value[name]) for name in _LIMITS}


def _validate_phase(
    root: Path,
    item: object,
    index: int,
    findings: list[CommissioningFinding],
    expected_design_contract_sha256: str | None,
) -> bool:
    path = f"phases[{index}]"
    before = len(findings)
    if not isinstance(item, dict) or set(item) != _PHASE:
        findings.append(_finding("COMM.PHASE_INVALID", "error", path, "phase fields are closed"))
        return False
    phase = item.get("phase")
    if phase not in _PHASES or phase != _PHASES[index]:
        findings.append(_finding("COMM.PHASE_ORDER", "error", f"{path}.phase", "phases must be the ordered non-repeating prefix of the commissioning sequence"))
    status = item.get("status")
    if status not in {"planned", "recorded", "aborted"}:
        findings.append(_finding("COMM.PHASE_STATUS_INVALID", "error", f"{path}.status", "status must be planned, recorded, or aborted"))
    for name in ("test_card_id", "site_id", "area_id", "estop_id"):
        try:
            validate_identifier(item.get(name), f"{path}.{name}")
        except ValueError as exc:
            findings.append(_finding("COMM.PHASE_ID_INVALID", "error", f"{path}.{name}", str(exc)))
    roles = item.get("roles")
    if not isinstance(roles, list) or len(roles) < 2 or any(not isinstance(role, str) or not role for role in roles) or len(set(roles)) != len(roles):
        findings.append(_finding("COMM.ROLES_INVALID", "error", f"{path}.roles", "phase requires at least two unique non-empty roles"))
    if not isinstance(item.get("abort_criteria"), list) or not item["abort_criteria"] or any(not isinstance(value, str) or not value for value in item["abort_criteria"]):
        findings.append(_finding("COMM.ABORT_CRITERIA_INVALID", "error", f"{path}.abort_criteria", "phase requires non-empty abort criteria"))
    limits = _validate_limits(item.get("limits"), f"{path}.limits", findings)
    timeout = item.get("watchdog_timeout_ns")
    if type(timeout) is not int or timeout <= 0:
        findings.append(_finding("COMM.WATCHDOG_INVALID", "error", f"{path}.watchdog_timeout_ns", "watchdog timeout must be a positive integer nanosecond value"))
    evidence_names = ("command_trace", "state_trace", "stop_trace", "inspection_record")
    if status == "planned":
        if item.get("execution_date") is not None or item.get("authority_record") is not None:
            findings.append(_finding("COMM.PLANNED_AUTHORITY_FORBIDDEN", "error", path, "planned phase must not carry execution date or authority evidence"))
        if any(item.get(name) is not None for name in evidence_names):
            findings.append(_finding("COMM.PLANNED_EVIDENCE_FORBIDDEN", "error", path, "planned phase must not include evidence records"))
        return len(findings) == before
    if not isinstance(item.get("execution_date"), str) or not item["execution_date"]:
        findings.append(_finding("COMM.EXECUTION_DATE_INVALID", "error", f"{path}.execution_date", "recorded phase requires a non-empty canonical execution date"))
    if item.get("authority_record") is None:
        findings.append(_finding("COMM.AUTHORITY_RECORD_REQUIRED", "error", f"{path}.authority_record", "recorded or aborted phase requires hash-bound external authority evidence"))
    else:
        findings.extend(validate_authority_record(root, item["authority_record"], item, expected_design_contract_sha256))
    if status == "aborted":
        findings.append(_finding("COMM.PHASE_ABORTED", "error", f"{path}.status", "aborted phase remains a blocking retained record"))
    data: dict[str, dict[str, Any]] = {}
    labels = {"command_trace": "COMMAND_TRACE", "state_trace": "STATE_TRACE", "stop_trace": "STOP_TRACE", "inspection_record": "INSPECTION_RECORD"}
    for name in evidence_names:
        if item.get(name) is None:
            findings.append(_finding(f"COMM.{labels[name]}_REQUIRED", "error", f"{path}.{name}", "recorded or aborted phase requires hash-bound evidence"))
        else:
            loaded = _bound_json(root, item[name], f"{path}.{name}", findings)
            if loaded is not None:
                data[name] = loaded
    command_events = _events(data.get("command_trace"), f"{path}.command_trace", frozenset({"timestamp_ns", "mode", "energy_j", "speed_m_s", "torque_nm"}), findings)
    state_events = _events(data.get("state_trace"), f"{path}.state_trace", frozenset({"timestamp_ns", "mode", "motion_inhibited", "speed_m_s", "torque_nm", "watchdog_healthy"}), findings)
    stop_events = _events(data.get("stop_trace"), f"{path}.stop_trace", frozenset({"timestamp_ns", "initiating_event", "safe_state", "latency_ns"}), findings)
    if limits is not None and command_events is not None:
        for event_index, event in enumerate(command_events):
            if not isinstance(event, dict):
                continue
            if not isinstance(event.get("mode"), str) or not event["mode"] or any(not _finite(event.get(name)) for name in _LIMITS):
                findings.append(_finding("COMM.COMMAND_TRACE_INVALID", "error", f"{path}.command_trace.events[{event_index}]", "command event requires finite mode, energy, speed, and torque"))
                continue
            if any(abs(float(event[name])) > limits[name] for name in _LIMITS):
                findings.append(_finding("COMM.COMMAND_LIMIT_EXCEEDED", "error", f"{path}.command_trace.events[{event_index}]", "command exceeds declared commissioning limit"))
    if limits is not None and state_events is not None:
        for event_index, event in enumerate(state_events):
            if not isinstance(event, dict):
                continue
            if not isinstance(event.get("mode"), str) or not event["mode"] or type(event.get("motion_inhibited")) is not bool or type(event.get("watchdog_healthy")) is not bool or not _finite(event.get("speed_m_s")) or not _finite(event.get("torque_nm")):
                findings.append(_finding("COMM.STATE_TRACE_INVALID", "error", f"{path}.state_trace.events[{event_index}]", "state event fields are invalid"))
                continue
            if not event["watchdog_healthy"] or abs(float(event["speed_m_s"])) > limits["speed_m_s"] or abs(float(event["torque_nm"])) > limits["torque_nm"]:
                findings.append(_finding("COMM.STATE_LIMIT_EXCEEDED", "error", f"{path}.state_trace.events[{event_index}]", "state violates watchdog or declared commissioning limit"))
            if phase in {"unpowered_inspection", "protected_power"} and (not event["motion_inhibited"] or float(event["speed_m_s"]) != 0.0 or float(event["torque_nm"]) != 0.0):
                findings.append(_finding("COMM.INHIBITED_MOTION", "error", f"{path}.state_trace.events[{event_index}]", "inhibited stage must retain zero observed motion and torque"))
    if phase in {"unpowered_inspection", "protected_power"} and command_events is not None:
        for event_index, event in enumerate(command_events):
            if not isinstance(event, dict):
                continue
            if all(_finite(event.get(name)) for name in _LIMITS) and any(float(event[name]) != 0.0 for name in _LIMITS):
                findings.append(_finding("COMM.INHIBITED_COMMAND", "error", f"{path}.command_trace.events[{event_index}]", "inhibited stage must retain zero command energy, speed, and torque"))
    if phase not in {"unpowered_inspection", "protected_power"} and stop_events is not None:
        events = {(event.get("initiating_event"), event.get("safe_state")) for event in stop_events if isinstance(event, dict)}
        if not {("emergency_stop", "motion_inhibited"), ("command_timeout", "motion_inhibited")} <= events:
            findings.append(_finding("COMM.STOP_TRANSITION_REQUIRED", "error", f"{path}.stop_trace", "motion phase requires emergency-stop and command-timeout transitions to motion_inhibited"))
    if stop_events is not None:
        for event_index, event in enumerate(stop_events):
            if not isinstance(event, dict):
                continue
            if not isinstance(event.get("initiating_event"), str) or not event["initiating_event"] or not isinstance(event.get("safe_state"), str) or not event["safe_state"] or type(event.get("latency_ns")) is not int or event["latency_ns"] < 0:
                findings.append(_finding("COMM.STOP_TRACE_INVALID", "error", f"{path}.stop_trace.events[{event_index}]", "stop event fields are invalid"))
    inspection = data.get("inspection_record")
    if not isinstance(inspection, dict) or set(inspection) != {"schema_version", "checks", "disposition"} or inspection.get("schema_version") != 1 or not isinstance(inspection.get("checks"), list) or not inspection["checks"] or any(not isinstance(check, str) or not check for check in inspection["checks"]) or inspection.get("disposition") != "accepted":
        findings.append(_finding("COMM.POST_INSPECTION_INVALID", "error", f"{path}.inspection_record", "recorded phase requires accepted non-empty post-test inspection"))
    return len(findings) == before


def evaluate_commissioning_package(
    root: Path,
    package: object,
    expected_design_contract_sha256: str | None = None,
) -> CommissioningReport:
    """Validate commissioning records without ever authorizing hardware action."""

    findings: list[CommissioningFinding] = []
    commissioning_id = package.get("commissioning_id") if isinstance(package, dict) else None
    try:
        validate_identifier(commissioning_id, "commissioning_id")
    except ValueError as exc:
        findings.append(_finding("COMM.PACKAGE_INVALID", "error", "commissioning_id", str(exc)))
        commissioning_id = "commissioning-invalid"
    if not isinstance(package, dict) or set(package) != _ROOT or package.get("schema_version") != 1 or not isinstance(package.get("phases"), list):
        findings.append(_finding("COMM.PACKAGE_INVALID", "error", "package", "package fields are closed and schema_version must be 1"))
        phases: list[Any] = []
    else:
        phases = package["phases"]
    if len(phases) > len(_PHASES):
        findings.append(_finding("COMM.PHASE_ORDER", "error", "phases", "commissioning package cannot exceed the fixed stage sequence"))
    highest: str | None = None
    predecessor_ready = True
    for index, item in enumerate(phases[: len(_PHASES)]):
        phase_ready = _validate_phase(root, item, index, findings, expected_design_contract_sha256)
        status = item.get("status") if isinstance(item, dict) else None
        if index and not predecessor_ready:
            findings.append(_finding("COMM.PHASE_DEPENDENCY", "error", f"phases[{index}]", "phase cannot proceed before every prior phase has a passing retained record"))
        if status == "recorded" and phase_ready and predecessor_ready and isinstance(item, dict):
            highest = item["phase"]
        predecessor_ready = predecessor_ready and status == "recorded" and phase_ready
    if not phases:
        findings.append(_finding("COMM.AUTHORIZATION_REQUIRED", "indeterminate", "phases", "no commissioning record is supplied; external authority and retained records are required"))
    elif any(isinstance(item, dict) and item.get("status") == "planned" for item in phases):
        findings.append(_finding("COMM.AUTHORIZATION_REQUIRED", "indeterminate", "phases", "planned commissioning phases await external authority and retained records"))
    findings = sorted(findings, key=lambda item: (item.code, item.path, item.message, item.severity))
    status = "rejected" if any(item.severity == "error" for item in findings) else "awaiting_authorization" if any(item.severity == "indeterminate" for item in findings) else "ready"
    return CommissioningReport(commissioning_id, status, tuple(findings), highest)
