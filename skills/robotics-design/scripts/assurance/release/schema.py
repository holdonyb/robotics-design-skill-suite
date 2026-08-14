"""Closed canonical schema for one v1 public-delivery contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ..engineering_freeze.schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import validate_sha256


_ROOT = frozenset({"schema_version", "release_id", "artifact_bindings", "hardware_claims"})
_MAX_BINDINGS = 128


class ReleaseSchemaError(ValueError):
    """A user-actionable invalid release-delivery contract."""


@dataclass(frozen=True)
class ReleaseContract:
    release_id: str
    artifact_bindings: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.release_id != "v1.0.0":
            raise ValueError("release_id must be v1.0.0")
        if not isinstance(self.artifact_bindings, tuple) or not self.artifact_bindings:
            raise ValueError("artifact_bindings must be a non-empty immutable tuple")


def _safe_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReleaseSchemaError(f"{field} must be a non-empty forward-slash relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or any(not part for part in parsed.parts):
        raise ReleaseSchemaError(f"{field} must remain under the release root")
    if parsed.parts and ":" in parsed.parts[0]:
        raise ReleaseSchemaError(f"{field} must not contain a drive prefix")
    return parsed.as_posix()


def _validated_contract(data: object) -> ReleaseContract:
    if not isinstance(data, dict) or set(data) != _ROOT:
        raise ReleaseSchemaError("release contract fields are closed")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ReleaseSchemaError("schema_version must be integer 1")
    if data.get("release_id") != "v1.0.0":
        raise ReleaseSchemaError("release_id must be v1.0.0")
    if data.get("hardware_claims") is not False:
        raise ReleaseSchemaError("hardware_claims must be false")
    bindings = data.get("artifact_bindings")
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= _MAX_BINDINGS:
        raise ReleaseSchemaError(f"artifact_bindings must contain 1 to {_MAX_BINDINGS} entries")
    seen: set[str] = set()
    validated: list[tuple[str, str]] = []
    for index, binding in enumerate(bindings):
        field = f"artifact_bindings[{index}]"
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
            raise ReleaseSchemaError(f"{field} must contain exactly path and sha256")
        path = _safe_path(binding["path"], f"{field}.path")
        try:
            digest = validate_sha256(binding["sha256"], f"{field}.sha256")
        except ValueError as exc:
            raise ReleaseSchemaError(str(exc)) from None
        if path in seen:
            raise ReleaseSchemaError(f"{field}.path duplicates an earlier binding")
        seen.add(path)
        validated.append((path, digest))
    return ReleaseContract("v1.0.0", tuple(sorted(validated)))


def load_release_contract(path: Path) -> ReleaseContract:
    """Load one bounded canonical release contract with closed records."""

    try:
        return _validated_contract(load_canonical_json(path))
    except (FreezeSchemaError, OSError, ValueError, OverflowError) as exc:
        if isinstance(exc, ReleaseSchemaError):
            raise
        raise ReleaseSchemaError(f"invalid release contract: {exc}") from None
