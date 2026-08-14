"""Immutable authorization-negative task-evidence report records."""

from __future__ import annotations

from dataclasses import dataclass
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
class TaskEvidenceReport:
    task_evidence_id: str
    status: str
    findings: tuple[TaskEvidenceFinding, ...]
    metric_summaries: tuple[Any, ...]
    fault_dispositions: tuple[Any, ...]
    comparison_residuals: tuple[Any, ...]
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
            "metric_summaries": list(self.metric_summaries),
            "fault_dispositions": list(self.fault_dispositions),
            "comparison_residuals": list(self.comparison_residuals),
        }
