"""Immutable records for an engineering freeze without hardware authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..hypothesis.canonical import validate_identifier


_SEVERITIES = frozenset({"info", "warning", "error", "indeterminate"})
_BLOCKING_SEVERITIES = frozenset({"error", "indeterminate"})


@dataclass(frozen=True)
class FreezeFinding:
    """A stable, evidence-addressed engineering-freeze finding."""

    code: str
    severity: str
    path: str
    message: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.code, "finding code")
        if self.severity not in _SEVERITIES:
            raise ValueError("severity must be info, warning, error, or indeterminate")
        for name, value in (("path", self.path), ("message", self.message)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence_ids must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
            "evidence_ids": sorted(set(self.evidence_ids)),
        }


@dataclass(frozen=True)
class EngineeringFreezeReport:
    """Freeze readiness is an engineering-review result, never hardware authority."""

    freeze_id: str
    findings: tuple[FreezeFinding, ...]
    freeze_ready: bool
    procurement_authorized: bool = False
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.freeze_id, "freeze_id")
        if type(self.procurement_authorized) is not bool or type(self.motion_authorized) is not bool:
            raise ValueError("authorization flags must be booleans")
        if self.procurement_authorized or self.motion_authorized:
            raise ValueError("authorization flags must always be false for an engineering freeze")
        if type(self.freeze_ready) is not bool:
            raise ValueError("freeze_ready must be a boolean")
        if any(not isinstance(item, FreezeFinding) for item in self.findings):
            raise ValueError("findings must contain FreezeFinding records")
        derived_ready = not any(item.severity in _BLOCKING_SEVERITIES for item in self.findings)
        if self.freeze_ready != derived_ready:
            raise ValueError("freeze_ready must equal the derived non-blocking finding state")

    def to_dict(self) -> dict[str, Any]:
        return {
            "freeze_id": self.freeze_id,
            "freeze_ready": self.freeze_ready,
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
