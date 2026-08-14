"""Immutable, authorization-negative commissioning report records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..hypothesis.canonical import validate_identifier


_SEVERITIES = frozenset({"info", "warning", "error", "indeterminate"})
_STATUSES = frozenset({"ready", "rejected", "awaiting_authorization"})


@dataclass(frozen=True)
class CommissioningFinding:
    """One deterministic, user-actionable commissioning finding."""

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
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True)
class CommissioningReport:
    """Local-record readiness, never a procurement or motion authorization."""

    commissioning_id: str
    status: str
    findings: tuple[CommissioningFinding, ...]
    highest_validated_phase: str | None
    procurement_authorized: bool = False
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.commissioning_id, "commissioning_id")
        if self.status not in _STATUSES:
            raise ValueError("invalid commissioning status")
        if self.highest_validated_phase is not None:
            validate_identifier(self.highest_validated_phase, "highest_validated_phase")
        if type(self.procurement_authorized) is not bool or type(self.motion_authorized) is not bool:
            raise ValueError("authorization flags must be booleans")
        if self.procurement_authorized or self.motion_authorized:
            raise ValueError("authorization flags must always be false")
        if not isinstance(self.findings, tuple):
            raise ValueError("findings must be an immutable tuple")
        if any(not isinstance(item, CommissioningFinding) for item in self.findings):
            raise ValueError("findings must contain CommissioningFinding records")
        derived_status = (
            "rejected" if any(item.severity == "error" for item in self.findings)
            else "awaiting_authorization" if any(item.severity == "indeterminate" for item in self.findings)
            else "ready"
        )
        if self.status != derived_status:
            raise ValueError("status must equal the derived finding status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "commissioning_id": self.commissioning_id,
            "status": self.status,
            "highest_validated_phase": self.highest_validated_phase,
            "procurement_authorized": False,
            "motion_authorized": False,
            "findings": [
                finding.to_dict()
                for finding in sorted(
                    self.findings,
                    key=lambda item: (item.code, item.path, item.message, item.severity),
                )
            ],
        }
