"""Immutable hypothesis decisions, lineage, stages, and result records."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .canonical import (
    candidate_id,
    canonical_bytes,
    canonical_value,
    validate_assignments,
    validate_candidate_id,
    validate_identifier,
    validate_integer,
    validate_optional_candidate_id,
    validate_optional_identifier,
    validate_sha256,
)


_CANDIDATE_STATUSES = frozenset(
    {"pending", "evaluated", "accepted", "rejected", "alias", "failed", "indeterminate"}
)
_STAGE_STATUSES = frozenset(
    {"pending", "running", "passed", "failed", "blocked", "skipped", "cached", "indeterminate"}
)


def _status(value: object, name: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} must be one of: " + ", ".join(sorted(allowed)))
    return value


def _sequence(value: object, name: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple")
    return tuple(value)


def _freeze_json(value: object, path: str) -> Any:
    checked = canonical_value(value, path)
    if isinstance(checked, dict):
        return MappingProxyType({key: _freeze_json(item, f"{path}[{key}]") for key, item in checked.items()})
    if isinstance(checked, list):
        return tuple(_freeze_json(item, f"{path}[{index}]") for index, item in enumerate(checked))
    return checked


def _thaw_json(value: Any) -> Any:
    if isinstance(value, dict) or isinstance(value, MappingProxyType):
        return {key: _thaw_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class CandidateDecision:
    base_sha256: str
    assignments: dict[str, str]
    seed: int
    parent_id: str | None = None
    repair_rule_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_sha256", validate_sha256(self.base_sha256, "base_sha256"))
        object.__setattr__(self, "assignments", MappingProxyType(validate_assignments(self.assignments)))
        object.__setattr__(self, "seed", validate_integer(self.seed, "seed"))
        object.__setattr__(self, "parent_id", validate_optional_candidate_id(self.parent_id, "parent_id"))
        object.__setattr__(self, "repair_rule_id", validate_optional_identifier(self.repair_rule_id, "repair_rule_id"))

    @property
    def candidate_id(self) -> str:
        return candidate_id(
            self.base_sha256,
            self.assignments,
            self.seed,
            self.parent_id,
            self.repair_rule_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_sha256": self.base_sha256,
            "assignments": dict(self.assignments),
            "seed": self.seed,
            "parent_id": self.parent_id,
            "repair_rule_id": self.repair_rule_id,
        }


@dataclass(frozen=True)
class CandidateLineage:
    candidate_id: str
    parent_id: str | None
    assignments: dict[str, str]
    repair_rule_id: str | None
    resolved_contract_sha256: str
    evaluation_key: str
    status: str
    alias_of: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", validate_candidate_id(self.candidate_id))
        object.__setattr__(self, "parent_id", validate_optional_candidate_id(self.parent_id, "parent_id"))
        object.__setattr__(self, "assignments", MappingProxyType(validate_assignments(self.assignments)))
        object.__setattr__(self, "repair_rule_id", validate_optional_identifier(self.repair_rule_id, "repair_rule_id"))
        object.__setattr__(self, "resolved_contract_sha256", validate_sha256(self.resolved_contract_sha256, "resolved_contract_sha256"))
        object.__setattr__(self, "evaluation_key", validate_identifier(self.evaluation_key, "evaluation_key"))
        object.__setattr__(self, "status", _status(self.status, "status", _CANDIDATE_STATUSES))
        object.__setattr__(self, "alias_of", validate_optional_candidate_id(self.alias_of, "alias_of"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_id": self.parent_id,
            "assignments": dict(self.assignments),
            "repair_rule_id": self.repair_rule_id,
            "resolved_contract_sha256": self.resolved_contract_sha256,
            "evaluation_key": self.evaluation_key,
            "status": self.status,
            "alias_of": self.alias_of,
        }


@dataclass(frozen=True)
class StageSpec:
    name: str
    version: str
    dependencies: tuple[str, ...]
    max_evaluations: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "name"))
        object.__setattr__(self, "version", validate_identifier(self.version, "version"))
        dependencies = _sequence(self.dependencies, "dependencies")
        validated = tuple(validate_identifier(item, f"dependencies[{index}]") for index, item in enumerate(dependencies))
        if len(set(validated)) != len(validated):
            raise ValueError("dependencies contains duplicate identifiers")
        object.__setattr__(self, "dependencies", tuple(sorted(validated)))
        object.__setattr__(self, "max_evaluations", validate_integer(self.max_evaluations, "max_evaluations", positive=True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "max_evaluations": self.max_evaluations,
        }


@dataclass(frozen=True)
class StageResult:
    name: str
    version: str
    status: str
    cache_key: str
    input_hash: str
    output: dict[str, Any]
    diagnostics: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "name"))
        object.__setattr__(self, "version", validate_identifier(self.version, "version"))
        object.__setattr__(self, "status", _status(self.status, "status", _STAGE_STATUSES))
        object.__setattr__(self, "cache_key", validate_sha256(self.cache_key, "cache_key"))
        object.__setattr__(self, "input_hash", validate_sha256(self.input_hash, "input_hash"))
        if not isinstance(self.output, dict):
            raise ValueError("output must be a JSON object")
        object.__setattr__(self, "output", _freeze_json(self.output, "output"))
        diagnostics = _sequence(self.diagnostics, "diagnostics")
        frozen = []
        for index, diagnostic in enumerate(diagnostics):
            if not isinstance(diagnostic, dict):
                raise ValueError(f"diagnostics[{index}] must be a JSON object")
            frozen.append(_freeze_json(diagnostic, f"diagnostics[{index}]"))
        frozen.sort(key=lambda item: canonical_bytes(_thaw_json(item)))
        object.__setattr__(self, "diagnostics", tuple(frozen))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "cache_key": self.cache_key,
            "input_hash": self.input_hash,
            "output": _thaw_json(self.output),
            "diagnostics": [_thaw_json(item) for item in self.diagnostics],
        }


@dataclass(frozen=True)
class HypothesisResult:
    space_id: str
    space_sha256: str
    seed: int
    candidates: tuple[CandidateLineage, ...]
    stages: tuple[StageResult, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "space_id", validate_identifier(self.space_id, "space_id"))
        object.__setattr__(self, "space_sha256", validate_sha256(self.space_sha256, "space_sha256"))
        object.__setattr__(self, "seed", validate_integer(self.seed, "seed"))
        candidates = _sequence(self.candidates, "candidates")
        for index, item in enumerate(candidates):
            if not isinstance(item, CandidateLineage):
                raise ValueError(f"candidates[{index}] must be a CandidateLineage")
        candidates_by_id: dict[str, CandidateLineage] = {}
        for item in candidates:
            if item.candidate_id in candidates_by_id:
                raise ValueError(
                    f"candidates contains duplicate candidate_id: {item.candidate_id}"
                )
            candidates_by_id[item.candidate_id] = item

        for candidate_id_value in sorted(candidates_by_id):
            item = candidates_by_id[candidate_id_value]
            if (item.status == "alias") != (item.alias_of is not None):
                raise ValueError(
                    f"candidate {candidate_id_value} status must be 'alias' "
                    "iff alias_of is present"
                )
            for field_name in ("parent_id", "alias_of"):
                target = getattr(item, field_name)
                if target is None:
                    continue
                if target == candidate_id_value:
                    raise ValueError(
                        f"candidate {candidate_id_value} {field_name} must differ from self"
                    )
                if target not in candidates_by_id:
                    raise ValueError(
                        f"candidate {candidate_id_value} {field_name} "
                        f"target must exist in candidates: {target}"
                    )
                if field_name == "alias_of":
                    alias_target = candidates_by_id[target]
                    if alias_target.status == "alias" or alias_target.alias_of is not None:
                        raise ValueError(
                            f"candidate {candidate_id_value} alias_of target "
                            f"must be canonical non-alias: {target}"
                        )
                    if (
                        item.resolved_contract_sha256
                        != alias_target.resolved_contract_sha256
                    ):
                        raise ValueError(
                            f"candidate {candidate_id_value} alias_of "
                            "resolved_contract_sha256 must match target"
                        )
                    if item.evaluation_key != alias_target.evaluation_key:
                        raise ValueError(
                            f"candidate {candidate_id_value} alias_of "
                            "evaluation_key must match target"
                        )

        visit_state: dict[str, int] = {}
        for start_id in sorted(candidates_by_id):
            if visit_state.get(start_id, 0) != 0:
                continue
            start = candidates_by_id[start_id]
            start_targets = tuple(
                target
                for target in (start.parent_id, start.alias_of)
                if target is not None
            )
            visit_state[start_id] = 1
            visit_stack: list[tuple[str, tuple[str, ...], int]] = [
                (start_id, start_targets, 0)
            ]
            active_positions = {start_id: 0}

            while visit_stack:
                candidate_id_value, targets, next_index = visit_stack[-1]
                if next_index == len(targets):
                    visit_stack.pop()
                    del active_positions[candidate_id_value]
                    visit_state[candidate_id_value] = 2
                    continue

                target = targets[next_index]
                visit_stack[-1] = (
                    candidate_id_value,
                    targets,
                    next_index + 1,
                )
                state = visit_state.get(target, 0)
                if state == 1:
                    cycle_length = len(visit_stack) - active_positions[target]
                    raise ValueError(
                        "candidates contains lineage cycle at "
                        f"{target} (cycle length {cycle_length})"
                    )
                if state == 0:
                    target_item = candidates_by_id[target]
                    target_references = tuple(
                        reference
                        for reference in (target_item.parent_id, target_item.alias_of)
                        if reference is not None
                    )
                    visit_state[target] = 1
                    active_positions[target] = len(visit_stack)
                    visit_stack.append((target, target_references, 0))

        stages = _sequence(self.stages, "stages")
        for index, item in enumerate(stages):
            if not isinstance(item, StageResult):
                raise ValueError(f"stages[{index}] must be a StageResult")
        stage_identities: set[tuple[str, str]] = set()
        for item in stages:
            identity = (item.name, item.version)
            if identity in stage_identities:
                raise ValueError(
                    f"stages contains duplicate stage identity: {item.name}@{item.version}"
                )
            stage_identities.add(identity)
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a JSON object")
        object.__setattr__(self, "candidates", tuple(sorted(candidates, key=lambda item: item.candidate_id)))
        object.__setattr__(self, "stages", tuple(sorted(stages, key=lambda item: (item.name, item.version))))
        object.__setattr__(self, "metadata", _freeze_json(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "space_sha256": self.space_sha256,
            "seed": self.seed,
            "candidates": [item.to_dict() for item in self.candidates],
            "stages": [item.to_dict() for item in self.stages],
            "metadata": _thaw_json(self.metadata),
        }
