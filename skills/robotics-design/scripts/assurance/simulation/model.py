"""Closed immutable records for simulation evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

from ..hypothesis.canonical import (
    canonical_bytes,
    canonical_value,
    validate_candidate_id,
    validate_identifier,
    validate_integer,
    validate_sha256,
)


EVIDENCE_LEVELS = (
    "generated",
    "parsed",
    "calculated",
    "simulation_admitted",
    "simulated",
    "calibrated_simulation",
    "bench_tested",
    "integrated_hardware_tested",
    "task_validated",
    "certified",
)
_ADMISSION_STATUSES = frozenset({"simulation_admitted", "rejected", "indeterminate"})
_RESULT_STATUSES = frozenset({"passed", "failed", "indeterminate"})
_METRIC_STATUSES = frozenset({"passed", "failed", "indeterminate"})
_SIMULATION_RESULT_LEVELS = frozenset({"simulated", "calibrated_simulation"})
_MAX_TRACE_SAMPLES = 10_000


def _closed(value: object, name: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} must be one of: " + ", ".join(sorted(allowed)))
    return value


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number (booleans are not allowed)")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


def _sequence(value: object, name: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple")
    return tuple(value)


def _identifiers(value: object, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    items = _sequence(value, name)
    if nonempty and not items:
        raise ValueError(f"{name} must not be empty")
    validated = tuple(validate_identifier(item, f"{name}[{index}]") for index, item in enumerate(items))
    if len(set(validated)) != len(validated):
        raise ValueError(f"{name} contains duplicate identifiers")
    return validated


def _freeze_json(value: object, path: str) -> Any:
    try:
        checked = canonical_value(value, path)
        canonical_bytes(checked)
    except (UnicodeError, ValueError) as exc:
        message = str(exc)
        if "surrogates not allowed" in message:
            raise ValueError(f"{path} contains a Unicode surrogate") from None
        raise
    if isinstance(checked, dict):
        return MappingProxyType(
            {key: _freeze_json(item, f"{path}[{key}]") for key, item in checked.items()}
        )
    if isinstance(checked, list):
        return tuple(
            _freeze_json(item, f"{path}[{index}]") for index, item in enumerate(checked)
        )
    return checked


def _thaw_json(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType)):
        return {key: _thaw_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _json_object(value: object, path: str) -> MappingProxyType:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return _freeze_json(value, path)


def _relative_path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{name} must be a non-empty portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"{name} must be a safe portable relative path")
    if path.parts and ":" in path.parts[0]:
        raise ValueError(f"{name} must not contain a drive prefix")
    return path.as_posix()


def _positions(value: object, name: str, width: int | None = None) -> tuple[tuple[float, ...], ...]:
    rows = _sequence(value, name)
    result = []
    for row_index, row in enumerate(rows):
        values = _sequence(row, f"{name}[{row_index}]")
        if width is not None and len(values) != width:
            raise ValueError(f"{name}[{row_index}] width must equal joint_order width {width}")
        result.append(
            tuple(_finite(item, f"{name}[{row_index}][{index}]") for index, item in enumerate(values))
        )
    return tuple(result)


@dataclass(frozen=True)
class EnvironmentLock:
    environment_id: str
    image_digest: str
    ros_distro: str
    gazebo_version: str
    physics_engine: str
    parameters: dict[str, Any]
    package_versions: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment_id", validate_identifier(self.environment_id, "environment_id"))
        object.__setattr__(self, "image_digest", validate_sha256(self.image_digest, "image_digest"))
        for name in ("ros_distro", "gazebo_version", "physics_engine"):
            object.__setattr__(self, name, validate_identifier(getattr(self, name), name))
        object.__setattr__(self, "parameters", _json_object(self.parameters, "parameters"))
        object.__setattr__(self, "package_versions", _json_object(self.package_versions, "package_versions"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "image_digest": self.image_digest,
            "ros_distro": self.ros_distro,
            "gazebo_version": self.gazebo_version,
            "physics_engine": self.physics_engine,
            "parameters": _thaw_json(self.parameters),
            "package_versions": _thaw_json(self.package_versions),
        }


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    kind: str
    path: str
    sha256: str
    source_sha256: str
    consumer: str
    observations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", validate_identifier(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "kind", validate_identifier(self.kind, "kind"))
        object.__setattr__(self, "path", _relative_path(self.path, "path"))
        object.__setattr__(self, "sha256", validate_sha256(self.sha256, "sha256"))
        object.__setattr__(self, "source_sha256", validate_sha256(self.source_sha256, "source_sha256"))
        object.__setattr__(self, "consumer", validate_identifier(self.consumer, "consumer"))
        object.__setattr__(self, "observations", _json_object(self.observations, "observations"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "source_sha256": self.source_sha256,
            "consumer": self.consumer,
            "observations": _thaw_json(self.observations),
        }


@dataclass(frozen=True)
class SimulationAdmission:
    candidate_id: str
    resolved_contract_sha256: str
    status: str
    evidence_level: str
    hardware_promotable: bool
    remaining_blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", validate_candidate_id(self.candidate_id))
        object.__setattr__(self, "resolved_contract_sha256", validate_sha256(self.resolved_contract_sha256, "resolved_contract_sha256"))
        object.__setattr__(self, "status", _closed(self.status, "status", _ADMISSION_STATUSES))
        if type(self.hardware_promotable) is not bool or self.hardware_promotable:
            raise ValueError("hardware_promotable must be false for simulation admission")
        if self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError("evidence_level must be a declared evidence level")
        expected_level = "simulation_admitted" if self.status == "simulation_admitted" else "calculated"
        if self.evidence_level != expected_level:
            raise ValueError(f"evidence_level must be {expected_level!r} when status is {self.status!r}")
        blockers = _identifiers(self.remaining_blockers, "remaining_blockers")
        if len(set(blockers)) != len(blockers):
            raise ValueError("remaining_blockers contains duplicate identifiers")
        object.__setattr__(self, "remaining_blockers", tuple(sorted(blockers)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "resolved_contract_sha256": self.resolved_contract_sha256,
            "status": self.status,
            "evidence_level": self.evidence_level,
            "hardware_promotable": self.hardware_promotable,
            "remaining_blockers": list(self.remaining_blockers),
        }


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    version: str
    model_sha256: str
    trajectory_sha256: str
    environment_sha256: str
    seed: int
    duration_ns: int
    joint_order: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    faults: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for name in ("scenario_id", "version"):
            object.__setattr__(self, name, validate_identifier(getattr(self, name), name))
        for name in ("model_sha256", "trajectory_sha256", "environment_sha256"):
            object.__setattr__(self, name, validate_sha256(getattr(self, name), name))
        object.__setattr__(self, "seed", validate_integer(self.seed, "seed"))
        duration = validate_integer(self.duration_ns, "duration_ns", positive=True)
        object.__setattr__(self, "duration_ns", duration)
        object.__setattr__(self, "joint_order", _identifiers(self.joint_order, "joint_order", nonempty=True))
        object.__setattr__(self, "parameters", _json_object(self.parameters, "parameters"))
        faults = _sequence(self.faults, "faults")
        frozen_faults = []
        fault_ids = set()
        for index, fault in enumerate(faults):
            frozen = _json_object(fault, f"faults[{index}]")
            fault_id = validate_identifier(frozen.get("fault_id"), f"faults[{index}].fault_id")
            if fault_id in fault_ids:
                raise ValueError(f"faults contains duplicate fault_id: {fault_id}")
            fault_ids.add(fault_id)
            frozen_faults.append(frozen)
        frozen_faults.sort(key=lambda item: canonical_bytes(_thaw_json(item)))
        object.__setattr__(self, "faults", tuple(frozen_faults))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "version": self.version,
            "model_sha256": self.model_sha256,
            "trajectory_sha256": self.trajectory_sha256,
            "environment_sha256": self.environment_sha256,
            "seed": self.seed,
            "duration_ns": self.duration_ns,
            "joint_order": list(self.joint_order),
            "parameters": _thaw_json(self.parameters),
            "faults": [_thaw_json(item) for item in self.faults],
        }


@dataclass(frozen=True)
class TrajectoryRecord:
    trajectory_id: str
    model_sha256: str
    joint_order: tuple[str, ...]
    sample_period_ns: int
    positions: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "trajectory_id", validate_identifier(self.trajectory_id, "trajectory_id"))
        object.__setattr__(self, "model_sha256", validate_sha256(self.model_sha256, "model_sha256"))
        joints = _identifiers(self.joint_order, "joint_order", nonempty=True)
        object.__setattr__(self, "joint_order", joints)
        object.__setattr__(self, "sample_period_ns", validate_integer(self.sample_period_ns, "sample_period_ns", positive=True))
        positions = _positions(self.positions, "positions", len(joints))
        if not positions:
            raise ValueError("positions must not be empty")
        object.__setattr__(self, "positions", positions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "model_sha256": self.model_sha256,
            "joint_order": list(self.joint_order),
            "sample_period_ns": self.sample_period_ns,
            "positions": [list(row) for row in self.positions],
        }


@dataclass(frozen=True)
class TraceSample:
    timestamp_ns: int
    positions: tuple[float, ...]
    state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timestamp = validate_integer(self.timestamp_ns, "timestamp_ns")
        if timestamp < 0:
            raise ValueError("timestamp_ns must be non-negative")
        object.__setattr__(self, "timestamp_ns", timestamp)
        rows = _positions((self.positions,), "positions")
        object.__setattr__(self, "positions", rows[0])
        object.__setattr__(self, "state", _json_object(self.state, "state"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "positions": list(self.positions),
            "state": _thaw_json(self.state),
        }


@dataclass(frozen=True)
class MetricResult:
    name: str
    unit: str
    status: str
    value: float
    limit: float
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "name"))
        object.__setattr__(self, "unit", validate_identifier(self.unit, "unit"))
        object.__setattr__(self, "status", _closed(self.status, "status", _METRIC_STATUSES))
        object.__setattr__(self, "value", _finite(self.value, "value"))
        object.__setattr__(self, "limit", _finite(self.limit, "limit"))
        object.__setattr__(self, "details", _json_object(self.details, "details"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "status": self.status,
            "value": self.value,
            "limit": self.limit,
            "details": _thaw_json(self.details),
        }


@dataclass(frozen=True)
class SimulationResult:
    scenario_id: str
    status: str
    evidence_level: str
    model_sha256: str
    trajectory_sha256: str
    environment_sha256: str
    trace_sha256: str
    joint_order: tuple[str, ...]
    samples: tuple[TraceSample, ...]
    metrics: tuple[MetricResult, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", validate_identifier(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "status", _closed(self.status, "status", _RESULT_STATUSES))
        if self.evidence_level not in _SIMULATION_RESULT_LEVELS:
            raise ValueError("evidence_level must be simulated or calibrated_simulation")
        for name in ("model_sha256", "trajectory_sha256", "environment_sha256", "trace_sha256"):
            object.__setattr__(self, name, validate_sha256(getattr(self, name), name))
        joints = _identifiers(self.joint_order, "joint_order", nonempty=True)
        object.__setattr__(self, "joint_order", joints)
        samples = _sequence(self.samples, "samples")
        if not samples:
            raise ValueError("samples must not be empty")
        if len(samples) > _MAX_TRACE_SAMPLES:
            raise ValueError(f"samples must contain at most {_MAX_TRACE_SAMPLES} records")
        previous = -1
        checked_samples = []
        for index, sample in enumerate(samples):
            if not isinstance(sample, TraceSample):
                raise ValueError(f"samples[{index}] must be a TraceSample")
            if len(sample.positions) != len(joints):
                raise ValueError(f"sample {index} width must equal joint_order width")
            if sample.timestamp_ns <= previous:
                raise ValueError("sample timestamps must be strictly increasing")
            previous = sample.timestamp_ns
            checked_samples.append(sample)
        object.__setattr__(self, "samples", tuple(checked_samples))
        metrics = _sequence(self.metrics, "metrics")
        checked_metrics = []
        metric_names = set()
        for index, metric in enumerate(metrics):
            if not isinstance(metric, MetricResult):
                raise ValueError(f"metrics[{index}] must be a MetricResult")
            if metric.name in metric_names:
                raise ValueError(f"metrics contains duplicate name: {metric.name}")
            metric_names.add(metric.name)
            checked_metrics.append(metric)
        checked_metrics.sort(key=lambda item: item.name)
        object.__setattr__(self, "metrics", tuple(checked_metrics))
        diagnostics = _sequence(self.diagnostics, "diagnostics")
        checked_diagnostics = []
        for index, diagnostic in enumerate(diagnostics):
            checked_diagnostics.append(_json_object(diagnostic, f"diagnostics[{index}]"))
        checked_diagnostics.sort(key=lambda item: canonical_bytes(_thaw_json(item)))
        object.__setattr__(self, "diagnostics", tuple(checked_diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "status": self.status,
            "evidence_level": self.evidence_level,
            "model_sha256": self.model_sha256,
            "trajectory_sha256": self.trajectory_sha256,
            "environment_sha256": self.environment_sha256,
            "trace_sha256": self.trace_sha256,
            "joint_order": list(self.joint_order),
            "samples": [item.to_dict() for item in self.samples],
            "metrics": [item.to_dict() for item in self.metrics],
            "diagnostics": [_thaw_json(item) for item in self.diagnostics],
        }
