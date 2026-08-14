"""Bounded offline evaluator for hash-bound task trial traces."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path, PurePosixPath
from typing import Any

from ..engineering_freeze.schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import validate_identifier, validate_sha256
from .model import TaskEvidenceFinding, TaskEvidenceReport
from .protocol import TaskProtocol


_PACKAGE = frozenset({"schema_version", "package_id", "kind", "envelope", "repetition", "fault_id", "command_trace", "state_trace", "task_trace", "disposition"})


def _finding(code: str, path: str, message: str) -> TaskEvidenceFinding:
    return TaskEvidenceFinding(code, "error", path, message)


def _finite(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _bound_json(root: Path, record: object, path: str, findings: list[TaskEvidenceFinding]) -> dict[str, Any] | None:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"} or not isinstance(record.get("path"), str) or not record["path"] or "\\" in record["path"]:
        findings.append(_finding("TASK.TRACE_BINDING_INVALID", path, "trace needs exactly safe path and SHA-256")); return None
    parsed = PurePosixPath(record["path"])
    if parsed.is_absolute() or ".." in parsed.parts:
        findings.append(_finding("TASK.TRACE_PATH_INVALID", path, "trace path must remain under evidence root")); return None
    target = root
    for part in parsed.parts:
        target = target / part
        if target.is_symlink():
            findings.append(_finding("TASK.TRACE_PATH_INVALID", path, "trace path must not traverse symlink")); return None
    try:
        expected = validate_sha256(record["sha256"], f"{path}.sha256")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            findings.append(_finding("TASK.TRACE_HASH_MISMATCH", path, "trace hash does not match")); return None
        return load_canonical_json(target)
    except (OSError, ValueError, FreezeSchemaError) as exc:
        findings.append(_finding("TASK.TRACE_INVALID", path, f"cannot load canonical trace: {exc}")); return None


def _trace(data: object, fields: frozenset[str], path: str, findings: list[TaskEvidenceFinding]) -> list[dict[str, Any]] | None:
    if not isinstance(data, dict) or set(data) != {"schema_version", "events"} or data.get("schema_version") != 1 or not isinstance(data.get("events"), list) or not data["events"] or len(data["events"]) > 10_000:
        findings.append(_finding("TASK.TRACE_INVALID", path, "trace must be bounded schema-v1 events")); return None
    events: list[dict[str, Any]] = []
    stamps: list[int] = []
    for index, item in enumerate(data["events"]):
        if not isinstance(item, dict) or set(item) != fields or type(item.get("timestamp_ns")) is not int or item["timestamp_ns"] < 0:
            findings.append(_finding("TASK.TRACE_INVALID", f"{path}.events[{index}]", "event fields are closed with non-negative timestamp")); continue
        events.append(item); stamps.append(item["timestamp_ns"])
    if not events or stamps != sorted(stamps) or len(set(stamps)) != len(stamps):
        findings.append(_finding("TASK.TRACE_TIMESTAMPS", path, "timestamps must be strictly increasing"))
    return events


def evaluate_task_packages(root: Path, protocol: TaskProtocol, packages: object) -> TaskEvidenceReport:
    findings: list[TaskEvidenceFinding] = []
    if not isinstance(packages, list) or not packages:
        findings.append(TaskEvidenceFinding("TASK.AUTHORIZATION_REQUIRED", "indeterminate", "packages", "no task package is supplied")); packages = []
    package_ids: set[str] = set()
    expected_envelope = {axis.id: set(axis.values) for axis in protocol.envelope}
    for index, package in enumerate(packages):
        path = f"packages[{index}]"
        if not isinstance(package, dict) or set(package) != _PACKAGE or package.get("schema_version") != 1:
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "package fields are closed and schema_version must be 1")); continue
        try:
            validate_identifier(package.get("package_id"), f"{path}.package_id")
        except ValueError:
            findings.append(_finding("TASK.PACKAGE_INVALID", f"{path}.package_id", "package id must be stable")); continue
        if package["package_id"] in package_ids:
            findings.append(_finding("TASK.PACKAGE_INVALID", f"{path}.package_id", "package ids must be unique")); continue
        package_ids.add(package["package_id"])
        if package.get("kind") != "nominal" or package.get("fault_id") is not None or package.get("disposition") not in {"passed", "aborted", "failed"} or type(package.get("repetition")) is not int or not 1 <= package["repetition"] <= protocol.repetitions:
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "only bounded nominal trial records are accepted at this stage")); continue
        envelope = package.get("envelope")
        if not isinstance(envelope, dict) or set(envelope) != set(expected_envelope) or any(not _finite(value) or float(value) not in expected_envelope[name] for name, value in envelope.items()):
            findings.append(_finding("TASK.ENVELOPE_INVALID", f"{path}.envelope", "envelope must match declared protocol values"))
        command = _trace(_bound_json(root, package["command_trace"], f"{path}.command_trace", findings), frozenset({"timestamp_ns", "phase", "speed_m_s", "torque_nm", "watchdog_healthy"}), f"{path}.command_trace", findings)
        state = _trace(_bound_json(root, package["state_trace"], f"{path}.state_trace", findings), frozenset({"timestamp_ns", "phase", "speed_m_s", "torque_nm", "watchdog_healthy"}), f"{path}.state_trace", findings)
        task = _trace(_bound_json(root, package["task_trace"], f"{path}.task_trace", findings), frozenset({"timestamp_ns", "phase", "completed"}), f"{path}.task_trace", findings)
        for trace, trace_path in ((command, "command"), (state, "state")):
            if trace is not None:
                for event in trace:
                    if not isinstance(event.get("phase"), str) or event["phase"] not in protocol.phases or not _finite(event.get("speed_m_s")) or not _finite(event.get("torque_nm")) or type(event.get("watchdog_healthy")) is not bool or not event["watchdog_healthy"]:
                        findings.append(_finding("TASK.TRACE_INVALID", f"{path}.{trace_path}_trace", "phase, finite motion values, and healthy watchdog are required"))
        if task is not None and any(not isinstance(event.get("phase"), str) or event["phase"] not in protocol.phases or type(event.get("completed")) is not bool for event in task):
            findings.append(_finding("TASK.TRACE_INVALID", f"{path}.task_trace", "task phase and completion flag are required"))
    findings.sort(key=lambda item: (item.code, item.path, item.message, item.severity))
    status = "rejected" if any(item.severity == "error" for item in findings) else "awaiting_authorization" if any(item.severity == "indeterminate" for item in findings) else "evidence_complete"
    return TaskEvidenceReport(protocol.task_id, status, tuple(findings), (), (), ())
