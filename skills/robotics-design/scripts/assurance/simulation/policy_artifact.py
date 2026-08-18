"""Closed, SHA-bound declarative simulation policy artifacts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..hypothesis.canonical import canonical_bytes, canonical_value, validate_identifier


_MAX_ARTIFACT_BYTES = 64 * 1024
_MAX_OBSERVATIONS = 64
_MAX_ABSOLUTE_PARAMETER = 1_000.0
_ROOT_FIELDS = {
    "schema_version",
    "kind",
    "policy_id",
    "observation_order",
    "linear",
    "angular",
}
_CHANNEL_FIELDS = {"bias", "weights"}


class PolicyArtifactError(ValueError):
    """A policy artifact cannot be safely loaded."""


@dataclass(frozen=True)
class PolicyArtifact:
    """An immutable affine-tanh policy declaration bound to its source bytes."""

    policy_id: str
    sha256: str
    observation_order: tuple[str, ...]
    linear_bias: float
    linear_weights: tuple[float, ...]
    angular_bias: float
    angular_weights: tuple[float, ...]
    payload: Mapping[str, object]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyArtifactError("policy artifact has a duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite_json_number(value: str) -> None:
    raise PolicyArtifactError(
        f"policy artifact must not contain non-finite JSON numbers ({value})"
    )


def _read_artifact_bytes(path: str | Path) -> bytes:
    try:
        target = Path(path)
    except (TypeError, ValueError):
        raise PolicyArtifactError("policy artifact path is invalid") from None
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        raise PolicyArtifactError("policy artifact does not exist") from None
    except OSError:
        raise PolicyArtifactError("policy artifact cannot be inspected") from None
    if stat.S_ISLNK(metadata.st_mode):
        raise PolicyArtifactError("policy artifact must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise PolicyArtifactError("policy artifact must be a regular file")
    if metadata.st_size > _MAX_ARTIFACT_BYTES:
        raise PolicyArtifactError("policy artifact exceeds maximum size of 64 KiB")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(os.fspath(target), flags)
    except OSError:
        raise PolicyArtifactError("policy artifact cannot be read") from None
    try:
        descriptor_metadata = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_metadata.st_mode):
            raise PolicyArtifactError("policy artifact must be a regular file")
        if descriptor_metadata.st_size > _MAX_ARTIFACT_BYTES:
            raise PolicyArtifactError("policy artifact exceeds maximum size of 64 KiB")
        chunks: list[bytes] = []
        remaining = _MAX_ARTIFACT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
    except OSError:
        raise PolicyArtifactError("policy artifact cannot be read") from None
    finally:
        os.close(descriptor)
    if len(payload) > _MAX_ARTIFACT_BYTES:
        raise PolicyArtifactError("policy artifact exceeds maximum size of 64 KiB")
    return payload


def _load_canonical_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_json_number,
        )
    except PolicyArtifactError:
        raise
    except (UnicodeError, json.JSONDecodeError, OverflowError, RecursionError, TypeError, ValueError):
        raise PolicyArtifactError("policy artifact must be valid UTF-8 JSON") from None
    try:
        checked = canonical_value(value, "policy artifact")
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        raise PolicyArtifactError(f"policy artifact is outside canonical JSON: {exc}") from None
    if not isinstance(checked, dict):
        raise PolicyArtifactError("policy artifact root must be a JSON object")
    try:
        canonical_payload = canonical_bytes(checked)
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        raise PolicyArtifactError(
            f"policy artifact cannot be encoded as canonical JSON: {exc}"
        ) from None
    if payload != canonical_payload:
        raise PolicyArtifactError("policy artifact bytes are not canonical JSON")
    return checked


def _closed_object(value: object, expected_fields: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyArtifactError(f"{path} must be an object")
    actual_fields = set(value)
    missing = sorted(expected_fields - actual_fields)
    unknown = sorted(actual_fields - expected_fields)
    if missing:
        raise PolicyArtifactError(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        raise PolicyArtifactError(f"{path} has unknown fields: {', '.join(unknown)}")
    return value


def _identifier(value: object, path: str) -> str:
    try:
        return validate_identifier(value, path)
    except ValueError as exc:
        raise PolicyArtifactError(str(exc)) from None


def _finite_parameter(value: object, path: str) -> float:
    if type(value) not in (int, float):
        raise PolicyArtifactError(f"{path} must be a finite number (booleans are not allowed)")
    result = float(value)
    if not math.isfinite(result):
        raise PolicyArtifactError(f"{path} must be a finite number")
    if abs(result) > _MAX_ABSOLUTE_PARAMETER:
        raise PolicyArtifactError(
            f"{path} must be bounded by {_MAX_ABSOLUTE_PARAMETER:g} in absolute value"
        )
    return result


def _channel(value: object, path: str, observation_count: int) -> tuple[float, tuple[float, ...]]:
    channel = _closed_object(value, _CHANNEL_FIELDS, path)
    bias = _finite_parameter(channel["bias"], f"{path}.bias")
    weights = channel["weights"]
    if not isinstance(weights, list):
        raise PolicyArtifactError(f"{path}.weights must be a list")
    if len(weights) != observation_count:
        raise PolicyArtifactError(
            f"{path}.weights must contain exactly {observation_count} values"
        )
    return bias, tuple(
        _finite_parameter(weight, f"{path}.weights[{index}]")
        for index, weight in enumerate(weights)
    )


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def load_policy_artifact(path: str | Path) -> PolicyArtifact:
    """Load one canonical ``affine_tanh_v1`` policy artifact from a regular file."""

    payload = _read_artifact_bytes(path)
    data = _load_canonical_json(payload)
    root = _closed_object(data, _ROOT_FIELDS, "root")
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise PolicyArtifactError("schema_version must be integer 1")
    if root["kind"] != "affine_tanh_v1":
        raise PolicyArtifactError("kind must be affine_tanh_v1")
    policy_id = _identifier(root["policy_id"], "policy_id")

    observation_order = root["observation_order"]
    if not isinstance(observation_order, list) or not observation_order:
        raise PolicyArtifactError("observation_order must be a non-empty list")
    if len(observation_order) > _MAX_OBSERVATIONS:
        raise PolicyArtifactError(
            f"observation_order must contain at most {_MAX_OBSERVATIONS} identifiers"
        )
    observations = tuple(
        _identifier(value, f"observation_order[{index}]")
        for index, value in enumerate(observation_order)
    )
    if len(set(observations)) != len(observations):
        raise PolicyArtifactError("observation_order contains duplicate identifiers")

    linear_bias, linear_weights = _channel(root["linear"], "linear", len(observations))
    angular_bias, angular_weights = _channel(root["angular"], "angular", len(observations))
    return PolicyArtifact(
        policy_id=policy_id,
        sha256=hashlib.sha256(payload).hexdigest(),
        observation_order=observations,
        linear_bias=linear_bias,
        linear_weights=linear_weights,
        angular_bias=angular_bias,
        angular_weights=angular_weights,
        payload=_freeze(data),
    )
