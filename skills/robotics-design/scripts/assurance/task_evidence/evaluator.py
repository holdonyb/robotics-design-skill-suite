"""Bounded offline evaluator for hash-bound task trial traces."""

from __future__ import annotations

import hashlib
import math
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any

from ..engineering_freeze.schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import validate_identifier, validate_sha256
from .model import TaskEvidenceFinding, TaskEvidenceReport
from .protocol import TaskProtocol


_PACKAGE = frozenset({"schema_version", "package_id", "kind", "envelope", "repetition", "fault_id", "fault_record", "endurance_record", "comparison_record", "command_trace", "state_trace", "task_trace", "disposition"})


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
    if not isinstance(data, dict) or set(data) != {"schema_version", "events"} or type(data.get("schema_version")) is not int or data["schema_version"] != 1 or not isinstance(data.get("events"), list) or not data["events"] or len(data["events"]) > 10_000:
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
    nominal_coverage: set[tuple[tuple[tuple[str, float], ...], int]] = set()
    expected_envelope = {axis.id: set(axis.values) for axis in protocol.envelope}
    for index, package in enumerate(packages):
        path = f"packages[{index}]"
        if not isinstance(package, dict) or set(package) != _PACKAGE or type(package.get("schema_version")) is not int or package["schema_version"] != 1:
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "package fields are closed and schema_version must be 1")); continue
        try:
            validate_identifier(package.get("package_id"), f"{path}.package_id")
        except ValueError:
            findings.append(_finding("TASK.PACKAGE_INVALID", f"{path}.package_id", "package id must be stable")); continue
        if package["package_id"] in package_ids:
            findings.append(_finding("TASK.PACKAGE_INVALID", f"{path}.package_id", "package ids must be unique")); continue
        package_ids.add(package["package_id"])
        if package.get("kind") not in {"nominal", "fault", "endurance", "comparison"} or package.get("disposition") not in {"passed", "aborted", "failed"} or type(package.get("repetition")) is not int or not 1 <= package["repetition"] <= protocol.repetitions:
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "kind, disposition, and repetition are invalid")); continue
        if package["disposition"] != "passed":
            findings.append(_finding("TASK.TRIAL_NOT_PASSED", f"{path}.disposition", "only a passed trial can satisfy task evidence coverage"))
        fault_profiles = {item.id: item for item in protocol.faults}
        if package["kind"] == "nominal" and (package.get("fault_id") is not None or package.get("fault_record") is not None):
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "nominal trials must not carry fault evidence"))
        if package["kind"] != "endurance" and package.get("endurance_record") is not None:
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "only endurance trials may carry endurance record"))
        if package["kind"] != "comparison" and package.get("comparison_record") is not None:
            findings.append(_finding("TASK.PACKAGE_INVALID", path, "only comparison trials may carry comparison record"))
        if package["kind"] == "fault":
            fault_id = package.get("fault_id")
            profile = fault_profiles.get(fault_id) if isinstance(fault_id, str) else None
            fault = _trace(_bound_json(root, package.get("fault_record"), f"{path}.fault_record", findings), frozenset({"timestamp_ns", "fault_id", "detected", "safe_state", "recovery"}), f"{path}.fault_record", findings)
            if profile is None:
                findings.append(_finding("TASK.FAULT_UNKNOWN", f"{path}.fault_id", "fault must be declared by protocol"))
            elif fault is not None:
                for event in fault:
                    if event.get("fault_id") != profile.id or type(event.get("detected")) is not bool or not event["detected"] or event.get("safe_state") != profile.safe_state:
                        findings.append(_finding("TASK.FAULT_SAFE_STATE", f"{path}.fault_record", "fault must be detected and reach declared safe state"))
                    if event.get("recovery") != profile.recovery:
                        findings.append(_finding("TASK.FAULT_RECOVERY", f"{path}.fault_record", "fault recovery must match protocol"))
        if package["kind"] == "endurance":
            record = _trace(_bound_json(root, package.get("endurance_record"), f"{path}.endurance_record", findings), frozenset({"timestamp_ns", "health", "terminal"}), f"{path}.endurance_record", findings)
            if record is not None:
                stamps = [event["timestamp_ns"] for event in record]
                if len(record) > protocol.endurance.max_samples or stamps[-1] > protocol.endurance.max_duration_ns or any(stamps[position] - stamps[position - 1] != protocol.endurance.sample_interval_ns for position in range(1, len(stamps))):
                    findings.append(_finding("TASK.ENDURANCE_TIMESTAMPS", f"{path}.endurance_record", "samples must be bounded and evenly spaced"))
                if any(not _finite(event.get("health")) or type(event.get("terminal")) is not bool for event in record) or [event["terminal"] for event in record].count(True) != 1 or not record[-1]["terminal"]:
                    findings.append(_finding("TASK.ENDURANCE_INVALID", f"{path}.endurance_record", "finite health and one terminal final sample are required"))
        if package["kind"] == "comparison":
            record = _trace(_bound_json(root, package.get("comparison_record"), f"{path}.comparison_record", findings), frozenset({"timestamp_ns", "quantity_id", "simulated", "observed"}), f"{path}.comparison_record", findings)
            rules = {item.id: item for item in protocol.comparison}
            if record is not None:
                for event in record:
                    quantity_id = event.get("quantity_id")
                    rule = rules.get(quantity_id) if isinstance(quantity_id, str) else None
                    if rule is None or not _finite(event.get("simulated")) or not _finite(event.get("observed")):
                        findings.append(_finding("TASK.COMPARISON_INVALID", f"{path}.comparison_record", "comparison quantity and finite values are required")); continue
                    absolute = abs(float(event["observed"]) - float(event["simulated"]))
                    relative = absolute / max(abs(float(event["simulated"])), 1e-12)
                    if absolute > rule.max_abs_residual or relative > rule.max_rel_residual:
                        findings.append(_finding("TASK.COMPARISON_RESIDUAL", f"{path}.comparison_record", "comparison residual exceeds declared limit"))
        envelope = package.get("envelope")
        envelope_valid = isinstance(envelope, dict) and set(envelope) == set(expected_envelope) and not any(not _finite(value) or float(value) not in expected_envelope[name] for name, value in envelope.items())
        if not envelope_valid:
            findings.append(_finding("TASK.ENVELOPE_INVALID", f"{path}.envelope", "envelope must match declared protocol values"))
        elif package["kind"] == "nominal" and package["disposition"] == "passed":
            nominal_coverage.add((tuple(sorted((name, float(value)) for name, value in envelope.items())), package["repetition"]))
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
    axis_values = [(axis.id, axis.values) for axis in protocol.envelope]
    for values in product(*(values for _, values in axis_values)):
        point = tuple(sorted((axis_values[position][0], float(value)) for position, value in enumerate(values)))
        for repetition in range(1, protocol.repetitions + 1):
            if (point, repetition) not in nominal_coverage:
                findings.append(_finding("TASK.REPETITION_MISSING", "packages", "every declared envelope point requires every nominal repetition"))
                break
    findings.sort(key=lambda item: (item.code, item.path, item.message, item.severity))
    status = "rejected" if any(item.severity == "error" for item in findings) else "awaiting_authorization" if any(item.severity == "indeterminate" for item in findings) else "evidence_complete"
    return TaskEvidenceReport(protocol.task_id, status, tuple(findings), (), (), ())
