"""Canonical JSON and deterministic identity helpers for hypotheses."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID_RE = re.compile(r"^candidate-[0-9a-f]{24}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]*$")
_JSON_INTEGER_MIN = -(2**63)
_JSON_INTEGER_MAX = 2**63 - 1
_MAX_CANONICAL_JSON_DEPTH = 64


def validate_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{name} must be a non-empty identifier containing only letters, "
            "digits, '.', '_', ':', '/', '+', '@', or '-'"
        )
    return value


def validate_optional_identifier(value: object, name: str) -> str | None:
    if value is None:
        return None
    return validate_identifier(value, name)


def validate_candidate_id(value: object, name: str = "candidate_id") -> str:
    if not isinstance(value, str) or not _CANDIDATE_ID_RE.fullmatch(value):
        raise ValueError(f"{name} must match candidate-[0-9a-f]{{24}}")
    return value


def validate_optional_candidate_id(value: object, name: str) -> str | None:
    if value is None:
        return None
    return validate_candidate_id(value, name)


def validate_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 digest")
    return value


def validate_integer(value: object, name: str, *, positive: bool = False) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer (booleans are not allowed)")
    if value < _JSON_INTEGER_MIN or value > _JSON_INTEGER_MAX:
        raise ValueError(f"{name} is outside the supported 64-bit integer range")
    if positive and value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def canonical_value(
    value: object,
    path: str = "value",
    *,
    _active_ids: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    """Validate and copy a value into the closed canonical-JSON domain."""

    if _depth > _MAX_CANONICAL_JSON_DEPTH:
        raise ValueError(
            f"{path} exceeds maximum canonical JSON depth "
            f"of {_MAX_CANONICAL_JSON_DEPTH}"
        )
    if value is None or type(value) is bool or isinstance(value, str):
        return value
    if type(value) is int:
        return validate_integer(value, path)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        return value
    if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
        active_ids = _active_ids if _active_ids is not None else set()
        value_id = id(value)
        if value_id in active_ids:
            raise ValueError(f"{path} contains a cycle")
        active_ids.add(value_id)
        try:
            if isinstance(value, Mapping):
                copied: dict[str, Any] = {}
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError(
                            f"{path} keys must be strings for canonical JSON"
                        )
                    copied[key] = canonical_value(
                        item,
                        f"{path}[{key}]",
                        _active_ids=active_ids,
                        _depth=_depth + 1,
                    )
                return dict(sorted(copied.items()))
            return [
                canonical_value(
                    item,
                    f"{path}[{index}]",
                    _active_ids=active_ids,
                    _depth=_depth + 1,
                )
                for index, item in enumerate(value)
            ]
        finally:
            active_ids.remove(value_id)
    raise ValueError(f"{path} must contain only canonical JSON values")


def canonical_bytes(value: object) -> bytes:
    """Return sorted compact UTF-8 JSON with exactly one trailing LF."""

    try:
        checked = canonical_value(value)
        text = json.dumps(
            checked,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return (text + "\n").encode("utf-8")
    except (OverflowError, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"value cannot be encoded as canonical JSON: {exc}") from None


def validate_assignments(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("assignments must be a mapping of identifiers to identifiers")
    result: dict[str, str] = {}
    for key, item in value.items():
        try:
            axis = validate_identifier(key, "axis identifier")
            choice = validate_identifier(item, f"assignment for {key!r}")
        except ValueError as exc:
            raise ValueError(f"assignments: {exc}") from None
        result[axis] = choice
    return dict(sorted(result.items()))


def candidate_id(
    base_sha256: object,
    assignments: object,
    seed: object,
    parent_id: object = None,
    repair_rule_id: object = None,
) -> str:
    """Derive a stable candidate identity from its immutable decision record."""

    record = {
        "base_sha256": validate_sha256(base_sha256, "base_sha256"),
        "assignments": validate_assignments(assignments),
        "seed": validate_integer(seed, "seed"),
        "parent_id": validate_optional_candidate_id(parent_id, "parent_id"),
        "repair_rule_id": validate_optional_identifier(repair_rule_id, "repair_rule_id"),
    }
    digest = hashlib.sha256(canonical_bytes(record)).hexdigest()
    return "candidate-" + digest[:24]


def seeded_order(items: object, seed_material: object) -> tuple[str, ...]:
    """Return a stable SHA-256 order independent of input and interpreter state."""

    if isinstance(items, (str, bytes)) or not isinstance(items, Iterable):
        raise ValueError("items must be an iterable of non-empty identifiers")
    seed = validate_identifier(seed_material, "seed_material")
    validated: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        try:
            identifier = validate_identifier(item, f"items[{index}]")
        except ValueError as exc:
            raise ValueError(f"items: {exc}") from None
        if identifier in seen:
            raise ValueError(f"items contains duplicate identifier: {identifier}")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(
        sorted(
            validated,
            key=lambda item: (
                hashlib.sha256(canonical_bytes([seed, item])).digest(),
                item,
            ),
        )
    )
