"""Closed compilation of deterministic simulation scenarios."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..hypothesis.canonical import canonical_bytes, canonical_value, validate_identifier, validate_integer, validate_sha256
from .model import ScenarioSpec

_MAX_BYTES = 5 * 1024 * 1024
_ROOT = {"schema_version", "registry_id", "model_sha256", "trajectory_sha256", "environment_sha256", "joint_order", "scenarios"}
_SCENARIO = {"scenario_id", "version", "seed", "duration_ns", "parameters", "faults", "metrics", "stop"}
_FAULT = {"fault_id", "at_ns"}
_METRIC = {"name", "unit", "direction", "limit"}
_STOP = {"reason", "at_ns"}
_UNITS = {"final_joint_error": "rad", "elapsed_time": "s", "base_distance_error": "m", "peak_wheel_speed": "rad_s", "peak_joint_speed": "rad_s", "stop_latency": "s"}


class ScenarioError(ValueError):
    """Scenario registry is not safe to compile."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite(value: object, path: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ScenarioError(f"{path} must be a finite number")
    return float(value)


def _closed(value: object, fields: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{path} must be an object")
    missing, unknown = sorted(fields - set(value)), sorted(set(value) - fields)
    if missing:
        raise ScenarioError(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        raise ScenarioError(f"{path} has unknown fields: {', '.join(unknown)}")
    return value


def _load_registry_bytes(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes) or len(payload) > _MAX_BYTES:
        raise ScenarioError("scenario registry exceeds maximum size of 5 MiB")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda item: (_ for _ in ()).throw(ScenarioError(f"non-finite JSON number is not allowed: {item}")))
        value = canonical_value(value, "scenario registry")
    except ScenarioError:
        raise
    except (UnicodeError, json.JSONDecodeError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise ScenarioError(f"cannot load scenario registry: {exc}") from None
    if not isinstance(value, dict):
        raise ScenarioError("scenario registry root must be a JSON object")
    return value


def load_scenario_registry(path: str | Path) -> dict[str, Any]:
    try:
        return _load_registry_bytes(Path(path).read_bytes())
    except OSError as exc:
        raise ScenarioError(f"cannot load scenario registry: {exc}") from None


@dataclass(frozen=True)
class CompiledScenario:
    spec: ScenarioSpec
    metrics: tuple[MappingProxyType, ...]
    stop: MappingProxyType
    scenario_sha256: str

    def __getattr__(self, name: str) -> Any:
        return getattr(self.spec, name)

    def to_dict(self) -> dict[str, Any]:
        return {**self.spec.to_dict(), "metrics": [dict(item) for item in self.metrics], "stop": dict(self.stop)}


def compile_scenarios(registry: object) -> tuple[CompiledScenario, ...]:
    try:
        root = canonical_value(registry, "scenario registry")
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        raise ScenarioError(f"scenario registry is outside canonical JSON: {exc}") from None
    root = _closed(root, _ROOT, "root")
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise ScenarioError("schema_version must be integer 1")
    validate_identifier(root["registry_id"], "registry_id")
    for field in ("model_sha256", "trajectory_sha256", "environment_sha256"):
        validate_sha256(root[field], field)
    if not isinstance(root["joint_order"], list) or not root["joint_order"]:
        raise ScenarioError("joint_order must be a non-empty list")
    joints = tuple(validate_identifier(value, f"joint_order[{index}]") for index, value in enumerate(root["joint_order"]))
    if len(set(joints)) != len(joints):
        raise ScenarioError("joint_order contains duplicate identifiers")
    if not isinstance(root["scenarios"], list) or len(root["scenarios"]) != 10:
        raise ScenarioError("scenarios must contain exactly 10 records")
    compiled, ids, seed_fault_cases = [], set(), set()
    for index, raw in enumerate(root["scenarios"]):
        path, item = f"scenarios[{index}]", _closed(raw, _SCENARIO, f"scenarios[{index}]")
        scenario_id = validate_identifier(item["scenario_id"], f"{path}.scenario_id")
        seed, duration = validate_integer(item["seed"], f"{path}.seed"), validate_integer(item["duration_ns"], f"{path}.duration_ns", positive=True)
        if scenario_id in ids:
            raise ScenarioError(f"scenarios contains duplicate scenario_id: {scenario_id}")
        ids.add(scenario_id)
        if not isinstance(item["parameters"], dict) or not isinstance(item["faults"], list):
            raise ScenarioError(f"{path}.parameters must be an object and faults must be a list")
        fault_ids, faults = set(), []
        for fault_index, fault in enumerate(item["faults"]):
            fault = _closed(fault, _FAULT, f"{path}.faults[{fault_index}]")
            fault_id, at_ns = validate_identifier(fault["fault_id"], f"{path}.faults[{fault_index}].fault_id"), validate_integer(fault["at_ns"], f"{path}.faults[{fault_index}].at_ns")
            if fault_id in fault_ids:
                raise ScenarioError(f"{path}.faults contains duplicate fault_id: {fault_id}")
            if not 0 <= at_ns <= duration:
                raise ScenarioError(f"{path}.faults[{fault_index}].at_ns must be within duration_ns")
            fault_ids.add(fault_id); faults.append({"fault_id": fault_id, "at_ns": at_ns})
        seed_fault_case = (seed, tuple(sorted(fault_ids)))
        if seed_fault_case in seed_fault_cases:
            raise ScenarioError(f"scenarios contains duplicate seed/fault case: {seed}")
        seed_fault_cases.add(seed_fault_case)
        if not isinstance(item["metrics"], list) or not item["metrics"]:
            raise ScenarioError(f"{path}.metrics must be a non-empty list")
        names, metrics = set(), []
        for metric_index, metric in enumerate(item["metrics"]):
            metric = _closed(metric, _METRIC, f"{path}.metrics[{metric_index}]")
            name = validate_identifier(metric["name"], f"{path}.metrics[{metric_index}].name")
            if name in names:
                raise ScenarioError(f"{path}.metrics contains duplicate name: {name}")
            if _UNITS.get(name) != metric["unit"]:
                raise ScenarioError(f"{path}.metrics[{metric_index}].unit is invalid for {name}")
            if metric["direction"] not in {"max", "min"}:
                raise ScenarioError(f"{path}.metrics[{metric_index}].direction must be max or min")
            names.add(name); metrics.append({"name": name, "unit": metric["unit"], "direction": metric["direction"], "limit": _finite(metric["limit"], f"{path}.metrics[{metric_index}].limit")})
        stop = _closed(item["stop"], _STOP, f"{path}.stop")
        if validate_integer(stop["at_ns"], f"{path}.stop.at_ns") != duration:
            raise ScenarioError(f"{path}.stop.at_ns must equal duration_ns")
        normalized_stop = {"reason": validate_identifier(stop["reason"], f"{path}.stop.reason"), "at_ns": duration}
        spec = ScenarioSpec(scenario_id, item["version"], root["model_sha256"], root["trajectory_sha256"], root["environment_sha256"], seed, duration, joints, item["parameters"], tuple(faults))
        normal = {**spec.to_dict(), "metrics": sorted(metrics, key=lambda value: value["name"]), "stop": normalized_stop}
        compiled.append(CompiledScenario(spec, tuple(MappingProxyType(metric) for metric in normal["metrics"]), MappingProxyType(normalized_stop), hashlib.sha256(canonical_bytes(normal)).hexdigest()))
    return tuple(sorted(compiled, key=lambda value: (value.seed, value.scenario_id)))
