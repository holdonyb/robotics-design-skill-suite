"""Fail-closed objective extraction and deterministic Pareto fronts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ..model import EvidenceLevel
from ..units import QuantityError, to_si
from .canonical import validate_candidate_id, validate_identifier


_SEMANTIC_ID = r"[A-Za-z0-9][A-Za-z0-9_:/+@-]*"
_QUANTITY = re.compile(rf"^quantity:({_SEMANTIC_ID})$")
_ANALYSIS = re.compile(rf"^analysis:({_SEMANTIC_ID})\.outputs\.({_SEMANTIC_ID}(?:\.{_SEMANTIC_ID})*)$")
_EVIDENCE_ORDINAL = {level.value: float(index) for index, level in enumerate(EvidenceLevel)}


@dataclass(frozen=True)
class ObjectiveVector:
    candidate_id: str
    values: Mapping[str, float]
    reasons: Mapping[str, str]
    eligible: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", validate_candidate_id(self.candidate_id))
        checked_values = {validate_identifier(key, "objective identifier"): _scalar(value) for key, value in self.values.items()}
        if type(self.eligible) is not bool:
            raise ValueError("eligible must be a boolean")
        checked_reasons = {}
        for key, value in self.reasons.items():
            if key == "candidate":
                checked_reasons[key] = value
                continue
            checked_reasons[validate_identifier(key, "objective identifier")] = value
            if not isinstance(value, str) or not value.strip():
                raise ValueError("objective reason must be a non-empty string")
        if set(checked_values) & set(checked_reasons):
            raise ValueError("objective values and reasons must not overlap")
        object.__setattr__(self, "values", MappingProxyType(dict(sorted(checked_values.items()))))
        object.__setattr__(self, "reasons", MappingProxyType(dict(sorted(checked_reasons.items()))))
        object.__setattr__(self, "eligible", self.eligible and not checked_reasons)

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "eligible": self.eligible, "values": dict(self.values), "reasons": dict(self.reasons)}


@dataclass(frozen=True)
class ParetoResult:
    fronts: tuple[tuple[str, ...], ...]
    dominance_edges: tuple[tuple[str, str], ...]
    ineligible: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fronts", tuple(tuple(sorted(front)) for front in self.fronts))
        object.__setattr__(self, "dominance_edges", tuple(sorted(self.dominance_edges)))
        object.__setattr__(self, "ineligible", tuple(sorted(self.ineligible)))

    def to_dict(self) -> dict[str, Any]:
        return {"fronts": [list(front) for front in self.fronts], "dominance_edges": [{"dominant": left, "dominated": right} for left, right in self.dominance_edges], "ineligible": list(self.ineligible)}


def _scalar(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("objective value must be a finite scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("objective value must be a finite scalar")
    return result


def _declarations(value: object) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("objectives must be a list")
    seen: set[str] = set()
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"id", "source", "direction"}:
            raise ValueError(f"objectives[{index}] must contain exactly id, source, and direction")
        identifier = validate_identifier(item["id"], f"objectives[{index}].id")
        if identifier in seen:
            raise ValueError(f"objectives has duplicate id: {identifier}")
        seen.add(identifier)
        if not isinstance(item["source"], str):
            raise ValueError(f"objectives[{index}].source is unsupported")
        if item["direction"] not in {"min", "max"}:
            raise ValueError(f"objectives[{index}].direction must be min or max")
        result.append({"id": identifier, "source": item["source"], "direction": item["direction"]})
    return tuple(sorted(result, key=lambda item: item["id"]))


def _extract(source: str, contract: object, report: object) -> float:
    if not isinstance(contract, dict) or not isinstance(report, dict):
        raise ValueError("contract and report must be objects")
    quantity = _QUANTITY.fullmatch(source)
    if quantity:
        matches = [item for item in contract.get("quantities", []) if isinstance(item, dict) and item.get("id") == quantity.group(1)]
        if len(matches) != 1:
            raise ValueError(f"quantity {quantity.group(1)} is missing or not unique")
        return to_si(matches[0].get("value"), matches[0].get("dimension"), source)
    analysis = _ANALYSIS.fullmatch(source)
    if analysis:
        matches = [item for item in report.get("analyses", []) if isinstance(item, dict) and item.get("analysis_id") == analysis.group(1)]
        if len(matches) != 1:
            raise ValueError(f"analysis {analysis.group(1)} is missing or not unique")
        value: object = matches[0].get("outputs")
        for part in analysis.group(2).split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError(f"analysis output {analysis.group(2)} is missing")
            value = value[part]
        return _scalar(value)
    if source == "evidence:minimum-level":
        level = report.get("metadata", {}).get("minimum_evidence_level")
        if level not in _EVIDENCE_ORDINAL:
            raise ValueError("minimum evidence level is missing or invalid")
        return _EVIDENCE_ORDINAL[level]
    if source == "diagnostics:blocking-count":
        diagnostics = report.get("diagnostics")
        if not isinstance(diagnostics, list) or any(not isinstance(item, dict) or item.get("severity") not in {"info", "warning", "error", "indeterminate"} for item in diagnostics):
            raise ValueError("report diagnostics are invalid")
        return float(sum(item["severity"] in {"error", "indeterminate"} for item in diagnostics))
    raise ValueError("objective source is unsupported")


def extract_vector(candidate_id: object, contract: object, report: object, objectives: object) -> ObjectiveVector:
    """Extract every declared scalar or return deterministic ineligibility reasons."""
    candidate = validate_candidate_id(candidate_id)
    try:
        declarations = _declarations(objectives)
    except ValueError as exc:
        return ObjectiveVector(candidate, {}, {"objectives": str(exc)}, False)
    values: dict[str, float] = {}
    reasons: dict[str, str] = {}
    if not isinstance(report, dict) or type(report.get("promotable")) is not bool or not report["promotable"]:
        reasons["candidate"] = "report.promotable must be true"
    elif report.get("candidate_id") is not None and report.get("candidate_id") != candidate:
        reasons["candidate"] = "report.candidate_id must match candidate_id"
    elif any(isinstance(item, dict) and item.get("severity") in {"error", "indeterminate"} for item in report.get("diagnostics", [])):
        reasons["candidate"] = "report.promotable conflicts with blocking diagnostics"
    for item in declarations:
        try:
            values[item["id"]] = _extract(item["source"], contract, report)
        except (QuantityError, TypeError, ValueError, OverflowError) as exc:
            reasons[item["id"]] = str(exc)
    for identifier in reasons:
        values.pop(identifier, None)
    return ObjectiveVector(candidate, values, reasons, not reasons)


def pareto_fronts(vectors: Mapping[str, object], directions: Mapping[str, str]) -> ParetoResult:
    """Return deterministic non-dominated fronts without scalarization."""
    if not isinstance(vectors, Mapping) or not isinstance(directions, Mapping) or not directions:
        raise ValueError("vectors and directions must be non-empty mappings")
    ordered_directions = {validate_identifier(key, "objective identifier"): value for key, value in directions.items()}
    if any(value not in {"min", "max"} for value in ordered_directions.values()):
        raise ValueError("directions must be min or max")
    eligible: dict[str, dict[str, float]] = {}
    ineligible: list[str] = []
    for candidate in sorted(vectors):
        if not isinstance(candidate, str) or not candidate:
            raise ValueError("vector candidate identifiers must be non-empty strings")
        value = vectors[candidate]
        if isinstance(value, ObjectiveVector):
            if value.candidate_id != candidate:
                raise ValueError("ObjectiveVector candidate_id must match mapping key")
            if not value.eligible:
                ineligible.append(candidate)
                continue
            raw = dict(value.values)
        elif isinstance(value, Mapping):
            raw = dict(value)
        else:
            ineligible.append(candidate); continue
        try:
            if set(raw) != set(ordered_directions): raise ValueError()
            eligible[candidate] = {key: _scalar(raw[key]) for key in ordered_directions}
        except ValueError:
            ineligible.append(candidate)
    def dominates(left: str, right: str) -> bool:
        pairs = ((eligible[left][key], eligible[right][key], ordered_directions[key]) for key in ordered_directions)
        compared = list(pairs)
        return all(a <= b if direction == "min" else a >= b for a, b, direction in compared) and any(a < b if direction == "min" else a > b for a, b, direction in compared)
    edges = tuple((left, right) for left in sorted(eligible) for right in sorted(eligible) if left != right and dominates(left, right))
    remaining = set(eligible); fronts = []
    while remaining:
        front = tuple(item for item in sorted(remaining) if not any(dominates(other, item) for other in remaining if other != item))
        fronts.append(front); remaining.difference_update(front)
    return ParetoResult(tuple(fronts), edges, tuple(ineligible))
