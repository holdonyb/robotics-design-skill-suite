"""Closed and resource-bounded simulation-contract schema."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..hypothesis.canonical import (
    canonical_bytes,
    canonical_value,
    validate_candidate_id,
    validate_identifier,
    validate_integer,
    validate_sha256,
)
from .model import ArtifactRecord, EnvironmentLock, ScenarioSpec


_MAX_FILE_BYTES = 5 * 1024 * 1024
_ROOT_FIELDS = {
    "schema_version",
    "contract_id",
    "candidate_id",
    "resolved_contract_sha256",
    "environment",
    "max_scenarios",
    "max_trace_samples",
    "max_trace_bytes",
    "artifacts",
    "scenarios",
}
_ENVIRONMENT_FIELDS = {
    "environment_id",
    "image_digest",
    "ros_distro",
    "gazebo_version",
    "physics_engine",
    "parameters",
    "package_versions",
}
_ARTIFACT_FIELDS = {
    "artifact_id",
    "kind",
    "path",
    "sha256",
    "source_sha256",
    "consumer",
    "observations",
}
_SCENARIO_FIELDS = {
    "scenario_id",
    "version",
    "model_sha256",
    "trajectory_sha256",
    "environment_sha256",
    "seed",
    "duration_ns",
    "joint_order",
    "parameters",
    "faults",
}
_FAULT_FIELDS = {"fault_id", "at_ns"}


def _closed(record: dict[str, Any], fields: set[str], path: str, errors: list[str]) -> None:
    missing = sorted(fields - set(record))
    unknown = sorted(set(record) - fields)
    if missing:
        errors.append(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")


def _bounded_integer(
    value: object, low: int, high: int, path: str, errors: list[str]
) -> None:
    if type(value) is not int or not low <= value <= high:
        errors.append(f"{path} must be an integer from {low} through {high}")


def _construct(record_type: type, record: dict[str, Any], path: str, errors: list[str]) -> None:
    try:
        record_type(**record)
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        errors.append(f"{path}: {exc}")


def validate_simulation_contract(data: object) -> list[str]:
    """Return deterministic errors for a closed simulation contract without mutation."""

    if not isinstance(data, dict):
        return ["simulation-contract root must be a JSON object"]
    try:
        canonical_bytes(data)
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        return [f"simulation-contract is outside the canonical JSON domain: {exc}"]

    errors: list[str] = []
    _closed(data, _ROOT_FIELDS, "root", errors)
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("schema_version must be integer 1")
    for function, value, name in (
        (validate_identifier, data.get("contract_id"), "contract_id"),
        (validate_candidate_id, data.get("candidate_id"), "candidate_id"),
        (validate_sha256, data.get("resolved_contract_sha256"), "resolved_contract_sha256"),
    ):
        try:
            function(value, name)
        except ValueError as exc:
            errors.append(str(exc))

    _bounded_integer(data.get("max_scenarios"), 1, 32, "max_scenarios", errors)
    _bounded_integer(data.get("max_trace_samples"), 1, 10_000, "max_trace_samples", errors)
    _bounded_integer(data.get("max_trace_bytes"), 1, 10_000_000, "max_trace_bytes", errors)

    environment = data.get("environment")
    if not isinstance(environment, dict):
        errors.append("environment must be an object")
    else:
        _closed(environment, _ENVIRONMENT_FIELDS, "environment", errors)
        if set(environment) == _ENVIRONMENT_FIELDS:
            _construct(EnvironmentLock, environment, "environment", errors)

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
    else:
        artifact_ids: set[str] = set()
        for index, artifact in enumerate(artifacts):
            path = f"artifacts[{index}]"
            if not isinstance(artifact, dict):
                errors.append(f"{path} must be an object")
                continue
            _closed(artifact, _ARTIFACT_FIELDS, path, errors)
            artifact_id = artifact.get("artifact_id")
            if isinstance(artifact_id, str) and artifact_id in artifact_ids:
                errors.append(f"artifacts has duplicate artifact_id: {artifact_id}")
            elif isinstance(artifact_id, str):
                artifact_ids.add(artifact_id)
            if set(artifact) == _ARTIFACT_FIELDS:
                _construct(ArtifactRecord, artifact, path, errors)

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        errors.append("scenarios must be a non-empty list")
    else:
        if type(data.get("max_scenarios")) is int and len(scenarios) > data["max_scenarios"]:
            errors.append("scenarios exceeds max_scenarios")
        scenario_ids: set[str] = set()
        for index, scenario in enumerate(scenarios):
            path = f"scenarios[{index}]"
            if not isinstance(scenario, dict):
                errors.append(f"{path} must be an object")
                continue
            _closed(scenario, _SCENARIO_FIELDS, path, errors)
            scenario_id = scenario.get("scenario_id")
            if isinstance(scenario_id, str) and scenario_id in scenario_ids:
                errors.append(f"scenarios has duplicate scenario_id: {scenario_id}")
            elif isinstance(scenario_id, str):
                scenario_ids.add(scenario_id)
            faults = scenario.get("faults")
            if isinstance(faults, list):
                for fault_index, fault in enumerate(faults):
                    fault_path = f"{path}.faults[{fault_index}]"
                    if not isinstance(fault, dict):
                        errors.append(f"{fault_path} must be an object")
                        continue
                    _closed(fault, _FAULT_FIELDS, fault_path, errors)
                    try:
                        validate_identifier(fault.get("fault_id"), f"{fault_path}.fault_id")
                        timestamp = validate_integer(fault.get("at_ns"), f"{fault_path}.at_ns")
                        if timestamp < 0:
                            errors.append(f"{fault_path}.at_ns must be non-negative")
                    except ValueError as exc:
                        errors.append(str(exc))
            if set(scenario) == _SCENARIO_FIELDS:
                _construct(ScenarioSpec, scenario, path, errors)

    return sorted(set(errors))


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {token}")


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number is not allowed: {token}")
    return value


def _parse_int(token: str) -> int:
    if len(token.removeprefix("-")) > 308:
        raise ValueError("JSON integers may contain at most 308 digits")
    return int(token)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_simulation_contract(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load strict UTF-8 JSON within hard byte/depth bounds, then validate it."""

    source = Path(path)
    try:
        if not source.exists():
            return None, [f"simulation contract does not exist: {source}"]
        if source.stat().st_size > _MAX_FILE_BYTES:
            return None, ["simulation contract exceeds maximum size of 5 MiB"]
        try:
            text = source.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return None, ["simulation contract is not valid UTF-8"]
        data = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
        try:
            canonical_value(data, "simulation contract")
        except ValueError as exc:
            message = str(exc).replace("maximum canonical JSON depth", "maximum JSON depth")
            return None, [message]
        return data if isinstance(data, dict) else None, validate_simulation_contract(data)
    except (OSError, json.JSONDecodeError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        return None, [f"cannot load simulation contract: {exc}"]
