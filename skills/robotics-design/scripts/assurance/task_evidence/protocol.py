"""Closed schema and normalized record for a task-evidence protocol."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..hypothesis.canonical import validate_identifier
from .model import TaskEvidenceFinding


_ROOT = frozenset({"schema_version", "task_id", "phases", "envelope", "repetitions", "metrics", "faults", "endurance", "comparison"})
_UNITS = frozenset({"kg", "m/s", "s", "rad", "N", "Nm", "J"})


@dataclass(frozen=True)
class EnvelopeAxis:
    id: str
    unit: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class MetricRule:
    id: str
    unit: str
    direction: str
    threshold: float


@dataclass(frozen=True)
class FaultProfile:
    id: str
    safe_state: str
    recovery: str


@dataclass(frozen=True)
class EnduranceProfile:
    sample_interval_ns: int
    max_duration_ns: int
    max_samples: int


@dataclass(frozen=True)
class ComparisonRule:
    id: str
    unit: str
    max_abs_residual: float
    max_rel_residual: float


@dataclass(frozen=True)
class TaskProtocol:
    task_id: str
    phases: tuple[str, ...]
    envelope: tuple[EnvelopeAxis, ...]
    repetitions: int
    metrics: tuple[MetricRule, ...]
    faults: tuple[FaultProfile, ...]
    endurance: EnduranceProfile
    comparison: tuple[ComparisonRule, ...]


def _finding(code: str, path: str, message: str) -> TaskEvidenceFinding:
    return TaskEvidenceFinding(code, "error", path, message)


def _finite(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _ids(records: object, fields: frozenset[str], path: str, findings: list[TaskEvidenceFinding]) -> tuple[dict[str, Any], ...]:
    if not isinstance(records, list) or not records:
        findings.append(_finding(f"TASK.PROTOCOL_{path.upper()}_INVALID", path, "must be a non-empty list"))
        return ()
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        if not isinstance(item, dict) or set(item) != fields or not isinstance(item.get("id"), str):
            findings.append(_finding(f"TASK.PROTOCOL_{path.upper()}_INVALID", f"{path}[{index}]", "fields are closed and id is required"))
            continue
        try:
            validate_identifier(item["id"], f"{path}[{index}].id")
        except ValueError:
            findings.append(_finding(f"TASK.PROTOCOL_{path.upper()}_INVALID", f"{path}[{index}].id", "id must be stable"))
            continue
        if item["id"] in seen:
            findings.append(_finding(f"TASK.PROTOCOL_{path.upper()}_INVALID", path, "ids must be unique"))
            continue
        seen.add(item["id"])
        result.append(item)
    return tuple(result)


def validate_task_protocol(data: object) -> tuple[TaskProtocol | None, tuple[TaskEvidenceFinding, ...]]:
    findings: list[TaskEvidenceFinding] = []
    if not isinstance(data, dict) or set(data) != _ROOT or data.get("schema_version") != 1:
        return None, (_finding("TASK.PROTOCOL_INVALID", "protocol", "fields are closed and schema_version must be 1"),)
    try:
        validate_identifier(data.get("task_id"), "task_id")
    except ValueError:
        findings.append(_finding("TASK.PROTOCOL_INVALID", "task_id", "task_id must be stable"))
    phases = data.get("phases")
    if not isinstance(phases, list) or not phases or any(not isinstance(item, str) or not item for item in phases) or len(set(phases)) != len(phases):
        findings.append(_finding("TASK.PROTOCOL_INVALID", "phases", "phases must be non-empty unique strings")); phases = []
    envelope = _ids(data.get("envelope"), frozenset({"id", "unit", "values"}), "envelope", findings)
    for item in envelope:
        if item["unit"] not in _UNITS or not isinstance(item["values"], list) or not item["values"] or any(not _finite(value) for value in item["values"]) or len(set(item["values"])) != len(item["values"]):
            findings.append(_finding("TASK.PROTOCOL_ENVELOPE_INVALID", f"envelope.{item['id']}", "unit and finite unique values are required"))
    metrics = _ids(data.get("metrics"), frozenset({"id", "unit", "direction", "threshold"}), "metrics", findings)
    for item in metrics:
        if item["unit"] not in _UNITS or item["direction"] not in {"maximum", "minimum"} or not _finite(item["threshold"]):
            findings.append(_finding("TASK.PROTOCOL_METRIC_INVALID", f"metrics.{item['id']}", "unit, direction, and finite threshold are required"))
    faults = _ids(data.get("faults"), frozenset({"id", "safe_state", "recovery"}), "faults", findings)
    for item in faults:
        if not all(isinstance(item[name], str) and item[name] for name in ("safe_state", "recovery")):
            findings.append(_finding("TASK.PROTOCOL_FAULTS_INVALID", f"faults.{item['id']}", "safe state and recovery are required"))
    endurance = data.get("endurance")
    if not isinstance(endurance, dict) or set(endurance) != {"sample_interval_ns", "max_duration_ns", "max_samples"} or any(type(endurance.get(name)) is not int or endurance[name] <= 0 for name in endurance):
        findings.append(_finding("TASK.PROTOCOL_ENDURANCE_INVALID", "endurance", "positive integer bounds are required")); endurance = {}
    comparison = _ids(data.get("comparison"), frozenset({"id", "unit", "max_abs_residual", "max_rel_residual"}), "comparison", findings)
    for item in comparison:
        if item["unit"] not in _UNITS or not _finite(item["max_abs_residual"]) or not _finite(item["max_rel_residual"]) or float(item["max_abs_residual"]) < 0 or float(item["max_rel_residual"]) < 0:
            findings.append(_finding("TASK.PROTOCOL_COMPARISON_INVALID", f"comparison.{item['id']}", "unit and non-negative finite residual limits are required"))
    if type(data.get("repetitions")) is not int or data["repetitions"] <= 0:
        findings.append(_finding("TASK.PROTOCOL_REPETITIONS_INVALID", "repetitions", "must be a positive integer"))
    findings.sort(key=lambda item: (item.code, item.path, item.message))
    if findings:
        return None, tuple(findings)
    return TaskProtocol(
        data["task_id"], tuple(phases),
        tuple(EnvelopeAxis(item["id"], item["unit"], tuple(float(value) for value in item["values"])) for item in envelope),
        data["repetitions"],
        tuple(MetricRule(item["id"], item["unit"], item["direction"], float(item["threshold"])) for item in metrics),
        tuple(FaultProfile(item["id"], item["safe_state"], item["recovery"]) for item in faults),
        EnduranceProfile(endurance["sample_interval_ns"], endurance["max_duration_ns"], endurance["max_samples"]),
        tuple(ComparisonRule(item["id"], item["unit"], float(item["max_abs_residual"]), float(item["max_rel_residual"])) for item in comparison),
    ), ()
