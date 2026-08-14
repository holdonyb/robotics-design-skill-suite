"""Immutable, hardware-negative release-delivery report records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..hypothesis.canonical import validate_identifier


_SEVERITIES = frozenset({"info", "warning", "error", "indeterminate"})
_STATUSES = frozenset({"passed", "failed", "awaiting_external_publication"})


@dataclass(frozen=True)
class ReleaseDeliveryFinding:
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
class ReleaseDeliveryReport:
    release_id: str
    status: str
    findings: tuple[ReleaseDeliveryFinding, ...]
    hardware_claims: bool = False

    def __post_init__(self) -> None:
        if self.release_id != "v1.0.0":
            raise ValueError("release_id must be v1.0.0")
        if self.status not in _STATUSES:
            raise ValueError("status must be passed, failed, or awaiting_external_publication")
        if not isinstance(self.findings, tuple) or any(
            not isinstance(item, ReleaseDeliveryFinding) for item in self.findings
        ):
            raise ValueError("findings must be an immutable tuple of ReleaseDeliveryFinding records")
        if type(self.hardware_claims) is not bool or self.hardware_claims:
            raise ValueError("hardware_claims must always be false")
        derived = (
            "failed"
            if any(item.severity == "error" for item in self.findings)
            else "awaiting_external_publication"
            if any(item.severity == "indeterminate" for item in self.findings)
            else "passed"
        )
        if self.status != derived:
            raise ValueError("status must equal the derived finding status")

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "status": self.status,
            "hardware_claims": False,
            "findings": [
                item.to_dict()
                for item in sorted(
                    self.findings,
                    key=lambda item: (item.code, item.path, item.message, item.severity),
                )
            ],
        }
