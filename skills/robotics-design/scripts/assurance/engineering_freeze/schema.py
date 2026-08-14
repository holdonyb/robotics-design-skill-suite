"""Bounded canonical JSON loading for engineering-freeze inputs."""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from ..hypothesis.canonical import canonical_bytes, canonical_value


_MAX_BYTES = 1024 * 1024


class FreezeSchemaError(ValueError):
    """A user-actionable invalid engineering-freeze input."""


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FreezeSchemaError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise FreezeSchemaError(f"non-finite JSON numeric literal: {value}")


def _validate_paths(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "path" and isinstance(child, str):
                parsed = PurePosixPath(child)
                if not child or parsed.is_absolute() or ".." in parsed.parts or "\\" in child:
                    raise FreezeSchemaError(f"{child_path} must be a safe relative POSIX path")
            _validate_paths(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_paths(child, f"{path}[{index}]")


def load_canonical_json(path: Path) -> dict[str, Any]:
    """Load one bounded canonical JSON object and reject unsafe local paths."""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FreezeSchemaError(f"cannot read {path}: {exc}") from None
    if not payload or len(payload) > _MAX_BYTES:
        raise FreezeSchemaError(f"{path} must contain 1 to {_MAX_BYTES} bytes")
    try:
        text = payload.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_nonfinite)
        checked = canonical_value(value)
        if not isinstance(checked, dict):
            raise FreezeSchemaError("root JSON value must be an object")
        if canonical_bytes(checked) != payload:
            raise FreezeSchemaError("JSON must use canonical compact UTF-8 bytes with one LF")
        _validate_paths(checked)
        return checked
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OverflowError) as exc:
        if isinstance(exc, FreezeSchemaError):
            raise
        raise FreezeSchemaError(f"invalid canonical JSON: {exc}") from None
