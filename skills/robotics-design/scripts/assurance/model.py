"""Shared diagnostics, evidence levels, and deterministic assurance reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import total_ordering
from typing import Any


@total_ordering
class EvidenceLevel(str, Enum):
    """Evidence labels are ordered for comparison, never automatic promotion."""

    ASSUMED = "assumed"
    GENERATED = "generated"
    PARSED = "parsed"
    CALCULATED = "calculated"
    SIMULATED = "simulated"
    BENCH_TESTED = "bench-tested"
    INTEGRATED_HARDWARE_TESTED = "integrated-hardware-tested"
    TASK_VALIDATED = "task-validated"
    CERTIFIED = "certified"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, EvidenceLevel):
            return NotImplemented
        levels = tuple(EvidenceLevel)
        return levels.index(self) < levels.index(other)


SEVERITIES = frozenset({"info", "warning", "error", "indeterminate"})


@dataclass(frozen=True)
class Diagnostic:
    """A stable, field-addressed assurance finding."""

    code: str
    severity: str
    path: str
    message: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(
                "severity must be one of: " + ", ".join(sorted(SEVERITIES))
            )
        for name, value in (
            ("code", self.code),
            ("path", self.path),
            ("message", self.message),
        ):
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


@dataclass
class Report:
    """Mutable collector with deterministic serialization and fail-closed status."""

    candidate_id: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    analyses: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    @property
    def promotable(self) -> bool:
        blocking = {"error", "indeterminate"}
        return not any(item.severity in blocking for item in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(
            self.diagnostics,
            key=lambda item: (item.code, item.path, item.message, item.severity),
        )
        return {
            "candidate_id": self.candidate_id,
            "promotable": self.promotable,
            "diagnostics": [item.to_dict() for item in ordered],
            "analyses": sorted(
                self.analyses,
                key=lambda item: (
                    str(item.get("name", "")),
                    str(item.get("version", "")),
                ),
            ),
            "metadata": dict(sorted(self.metadata.items())),
        }
