"""Immutable authorization-negative task-evidence report records."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ..hypothesis.canonical import validate_identifier


_SEVERITIES = frozenset({"info", "warning", "error", "indeterminate"})
_STATUSES = frozenset({"evidence_complete", "rejected", "awaiting_authorization"})


@dataclass(frozen=True)
class TaskEvidenceFinding:
    code: str
    severity: str
    path: str
    message: str

    def __post_init__(self) -> None:
        validate_identifier(self.code, "finding code")
        if self.severity not in _SEVERITIES:
            raise ValueError("severity must be info, warning, error, or indeterminate")
        if not isinstance(self.path, str) or not self.path.strip():
            raise ValueError("path must be a non-empty string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class MetricSummary:
    metric_id: str
    count: int
    minimum: float
    maximum: float
    mean: float
    passed: bool

    def __post_init__(self) -> None:
        validate_identifier(self.metric_id, "metric_id")
        if type(self.count) is not int or self.count <= 0 or type(self.passed) is not bool or any(type(value) not in {int, float} or not math.isfinite(float(value)) for value in (self.minimum, self.maximum, self.mean)):
            raise ValueError("metric summary fields must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {"metric_id": self.metric_id, "count": self.count, "minimum": self.minimum, "maximum": self.maximum, "mean": self.mean, "passed": self.passed}


@dataclass(frozen=True)
class FaultDisposition:
    fault_id: str
    package_id: str
    safe_state: str
    recovery: str
    passed: bool

    def __post_init__(self) -> None:
        validate_identifier(self.fault_id, "fault_id")
        validate_identifier(self.package_id, "package_id")
        if not all(isinstance(value, str) and value for value in (self.safe_state, self.recovery)) or type(self.passed) is not bool:
            raise ValueError("fault disposition fields are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"fault_id": self.fault_id, "package_id": self.package_id, "safe_state": self.safe_state, "recovery": self.recovery, "passed": self.passed}


@dataclass(frozen=True)
class ComparisonResidual:
    quantity_id: str
    package_id: str
    count: int
    maximum_abs_residual: float
    maximum_rel_residual: float
    passed: bool

    def __post_init__(self) -> None:
        validate_identifier(self.quantity_id, "quantity_id")
        validate_identifier(self.package_id, "package_id")
        if type(self.count) is not int or self.count <= 0 or type(self.passed) is not bool or any(type(value) not in {int, float} or not math.isfinite(float(value)) or float(value) < 0 for value in (self.maximum_abs_residual, self.maximum_rel_residual)):
            raise ValueError("comparison residual fields are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"quantity_id": self.quantity_id, "package_id": self.package_id, "count": self.count, "maximum_abs_residual": self.maximum_abs_residual, "maximum_rel_residual": self.maximum_rel_residual, "passed": self.passed}


@dataclass(frozen=True)
class TaskEvidenceReport:
    task_evidence_id: str
    status: str
    findings: tuple[TaskEvidenceFinding, ...]
    metric_summaries: tuple[MetricSummary, ...]
    fault_dispositions: tuple[FaultDisposition, ...]
    comparison_residuals: tuple[ComparisonResidual, ...]
    procurement_authorized: bool = False
    motion_authorized: bool = False
    task_validated: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.task_evidence_id, "task_evidence_id")
        if self.status not in _STATUSES:
            raise ValueError("invalid task evidence status")
        if not all(isinstance(value, tuple) for value in (self.findings, self.metric_summaries, self.fault_dispositions, self.comparison_residuals)):
            raise ValueError("report collections must be immutable tuples")
        if any(not isinstance(item, TaskEvidenceFinding) for item in self.findings):
            raise ValueError("findings must contain TaskEvidenceFinding records")
        if any(not isinstance(item, MetricSummary) for item in self.metric_summaries):
            raise ValueError("metric_summaries must contain MetricSummary records")
        if any(not isinstance(item, FaultDisposition) for item in self.fault_dispositions):
            raise ValueError("fault_dispositions must contain FaultDisposition records")
        if any(not isinstance(item, ComparisonResidual) for item in self.comparison_residuals):
            raise ValueError("comparison_residuals must contain ComparisonResidual records")
        if any(type(value) is not bool for value in (self.procurement_authorized, self.motion_authorized, self.task_validated)):
            raise ValueError("authorization and task_validated flags must be booleans")
        if self.procurement_authorized or self.motion_authorized or self.task_validated:
            raise ValueError("authorization and task_validated flags must always be false")
        derived = "rejected" if any(item.severity == "error" for item in self.findings) else "awaiting_authorization" if any(item.severity == "indeterminate" for item in self.findings) else "evidence_complete"
        if self.status != derived:
            raise ValueError("status must equal the derived finding status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_evidence_id": self.task_evidence_id,
            "status": self.status,
            "procurement_authorized": False,
            "motion_authorized": False,
            "task_validated": False,
            "findings": [item.to_dict() for item in sorted(self.findings, key=lambda item: (item.code, item.path, item.message, item.severity))],
            "metric_summaries": [item.to_dict() for item in sorted(self.metric_summaries, key=lambda item: item.metric_id)],
            "fault_dispositions": [item.to_dict() for item in sorted(self.fault_dispositions, key=lambda item: (item.fault_id, item.package_id))],
            "comparison_residuals": [item.to_dict() for item in sorted(self.comparison_residuals, key=lambda item: (item.quantity_id, item.package_id))],
        }
