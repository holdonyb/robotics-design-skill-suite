"""Structural and semantic validation for robot design contract schema v1."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .model import EvidenceLevel
from .units import QuantityError, to_si


SCHEMA_VERSION = 1
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STATUSES = frozenset({"draft", "rejected", "promoted"})
CONFIDENCE = frozenset({"low", "medium", "high"})
COMPONENT_STATES = frozenset(
    {"verified_part", "qualified_substitute", "engineering_placeholder", "missing"}
)
ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "status",
        "requirements",
        "assumptions",
        "quantities",
        "components",
        "architecture",
        "artifacts",
        "analyses",
        "evidence",
    }
)
RECORD_FIELDS = {
    "requirements": frozenset({"id", "statement", "verification", "owner"}),
    "assumptions": frozenset(
        {
            "id",
            "statement",
            "confidence",
            "owner",
            "validation",
            "decision_deadline",
        }
    ),
    "quantities": frozenset(
        {
            "id",
            "dimension",
            "value",
            "owner",
            "source",
            "evidence_level",
            "tolerance",
        }
    ),
    "components": frozenset(
        {
            "id",
            "role",
            "state",
            "interfaces",
            "manufacturer",
            "part_number",
            "source_url",
            "source_date",
            "limits",
            "supports_claims",
        }
    ),
    "artifacts": frozenset({"id", "kind", "path", "sha256"}),
    "analyses": frozenset({"id", "plugin", "inputs"}),
    "evidence": frozenset(
        {
            "id",
            "level",
            "source",
            "supports",
            "authority",
            "certificate_id",
        }
    ),
}
ARCHITECTURE_FIELDS = frozenset(
    {"features", "actuators", "moving_cables", "claimed_safety_functions"}
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unknown_fields(
    value: dict[str, Any], allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")


def _records(data: dict[str, Any], name: str, errors: list[str]) -> list[dict[str, Any]]:
    value = data.get(name)
    if not isinstance(value, list):
        errors.append(f"{name} must be a list")
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        path = f"{name}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        _unknown_fields(item, RECORD_FIELDS[name], path, errors)
        record_id = item.get("id")
        if not _nonempty(record_id) or not ID.fullmatch(record_id):
            errors.append(f"{path}.id must match {ID.pattern}")
        elif record_id in seen:
            errors.append(f"{name} has duplicate id {record_id}")
        else:
            seen.add(record_id)
        records.append(item)
    return records


def _string_list(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty(item) for item in value):
        errors.append(f"{path} must be a list of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{path} must not contain duplicates")
    return value


def _file_record(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must contain path and sha256")
        return
    unknown = sorted(set(value) - {"path", "sha256"})
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")
    raw_path = value.get("path")
    digest = value.get("sha256")
    if not _nonempty(raw_path):
        errors.append(f"{path}.path must be a non-empty relative path")
    else:
        candidate = PurePosixPath(raw_path.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"{path}.path must be a non-escaping relative path")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append(f"{path}.sha256 must be a lowercase SHA-256 digest")


def validate_contract(data: Any) -> list[str]:
    """Return sorted actionable errors for schema v1; empty means valid."""

    if not isinstance(data, dict):
        return ["contract root must be a JSON object"]

    errors: list[str] = []
    _unknown_fields(data, ROOT_FIELDS, "root", errors)
    schema_version = data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != SCHEMA_VERSION
    ):
        errors.append("schema_version must be integer 1")
    if not _nonempty(data.get("candidate_id")) or not ID.fullmatch(
        str(data.get("candidate_id", ""))
    ):
        errors.append(f"candidate_id must match {ID.pattern}")
    if data.get("status") not in STATUSES:
        errors.append("status must be one of: draft, promoted, rejected")

    collections = {
        name: _records(data, name, errors)
        for name in RECORD_FIELDS
    }

    architecture = data.get("architecture")
    if not isinstance(architecture, dict):
        errors.append("architecture must be an object")
    else:
        _unknown_fields(architecture, ARCHITECTURE_FIELDS, "architecture", errors)
        for field in ARCHITECTURE_FIELDS:
            _string_list(architecture.get(field), f"architecture.{field}", errors)

    artifact_ids = {
        item.get("id") for item in collections["artifacts"] if _nonempty(item.get("id"))
    }
    component_ids = {
        item.get("id") for item in collections["components"] if _nonempty(item.get("id"))
    }
    evidence_ids = {
        item.get("id") for item in collections["evidence"] if _nonempty(item.get("id"))
    }
    quantity_ids = {
        item.get("id") for item in collections["quantities"] if _nonempty(item.get("id"))
    }
    known_owners = {"project:system"}
    known_owners.update(f"artifact:{item}" for item in artifact_ids)
    known_owners.update(f"component:{item}" for item in component_ids)

    for name in ("requirements", "assumptions", "quantities"):
        for index, item in enumerate(collections[name]):
            owner = item.get("owner")
            if owner not in known_owners:
                errors.append(
                    f"{name}[{index}].owner references unknown owner: {owner}"
                )

    for index, item in enumerate(collections["requirements"]):
        for field in ("statement", "verification", "owner"):
            if not _nonempty(item.get(field)):
                errors.append(f"requirements[{index}].{field} must be a non-empty string")

    for index, item in enumerate(collections["assumptions"]):
        for field in ("statement", "owner", "validation", "decision_deadline"):
            if not _nonempty(item.get(field)):
                errors.append(f"assumptions[{index}].{field} must be a non-empty string")
        if item.get("confidence") not in CONFIDENCE:
            errors.append(
                f"assumptions[{index}].confidence must be one of: high, low, medium"
            )

    for index, item in enumerate(collections["quantities"]):
        dimension = item.get("dimension")
        if not _nonempty(dimension):
            errors.append(f"quantities[{index}].dimension must be a non-empty string")
        else:
            try:
                to_si(item.get("value"), dimension, f"quantities[{index}].value")
            except QuantityError as exc:
                errors.append(str(exc))
            if "tolerance" in item:
                try:
                    to_si(
                        item.get("tolerance"),
                        dimension,
                        f"quantities[{index}].tolerance",
                    )
                except QuantityError as exc:
                    errors.append(str(exc))
        source = item.get("source")
        if source not in {f"evidence:{item_id}" for item_id in evidence_ids}:
            errors.append(f"quantities[{index}].source references unknown evidence: {source}")
        try:
            EvidenceLevel(item.get("evidence_level"))
        except (TypeError, ValueError):
            errors.append(f"quantities[{index}].evidence_level is invalid")

    for index, item in enumerate(collections["components"]):
        for field in ("role", "state"):
            if not _nonempty(item.get(field)):
                errors.append(f"components[{index}].{field} must be a non-empty string")
        if item.get("state") not in COMPONENT_STATES:
            errors.append(
                f"components[{index}].state must be a supported component state"
            )
        _string_list(item.get("interfaces"), f"components[{index}].interfaces", errors)
        if "supports_claims" in item:
            _string_list(
                item.get("supports_claims"),
                f"components[{index}].supports_claims",
                errors,
            )

    for index, item in enumerate(collections["artifacts"]):
        if not _nonempty(item.get("kind")):
            errors.append(f"artifacts[{index}].kind must be a non-empty string")
        _file_record(
            {"path": item.get("path"), "sha256": item.get("sha256")},
            f"artifacts[{index}]",
            errors,
        )

    for index, item in enumerate(collections["analyses"]):
        if not _nonempty(item.get("plugin")):
            errors.append(f"analyses[{index}].plugin must be a non-empty string")
        inputs = item.get("inputs")
        if not isinstance(inputs, dict):
            errors.append(f"analyses[{index}].inputs must be an object")
            continue
        for name, reference in sorted(inputs.items()):
            if not _nonempty(name) or not _nonempty(reference):
                errors.append(
                    f"analyses[{index}].inputs must map non-empty names to references"
                )
            elif reference.startswith("quantity:") and reference[9:] not in quantity_ids:
                errors.append(
                    f"analyses[{index}].inputs.{name} references unknown quantity: {reference}"
                )

    known_supports = {f"quantity:{item_id}" for item_id in quantity_ids}
    known_supports.update(f"artifact:{item_id}" for item_id in artifact_ids)
    for index, item in enumerate(collections["evidence"]):
        try:
            level = EvidenceLevel(item.get("level"))
        except (TypeError, ValueError):
            level = None
            errors.append(f"evidence[{index}].level is invalid")
        _file_record(item.get("source"), f"evidence[{index}].source", errors)
        supports = _string_list(item.get("supports"), f"evidence[{index}].supports", errors)
        for reference in supports:
            if reference not in known_supports:
                errors.append(
                    f"evidence[{index}].supports references unknown target: {reference}"
                )
        if level == EvidenceLevel.CERTIFIED:
            for field in ("authority", "certificate_id"):
                if not _nonempty(item.get(field)):
                    errors.append(
                        f"evidence[{index}].{field} must be a non-empty string for certified evidence"
                    )

    return sorted(set(errors))


def load_contract(path: Path) -> tuple[Any | None, list[str]]:
    """Load UTF-8 JSON and return data plus actionable validation errors."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"contract does not exist: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"contract is not valid JSON: {exc}"]
    except OSError as exc:
        return None, [f"cannot read contract: {exc}"]
    return data, validate_contract(data)
