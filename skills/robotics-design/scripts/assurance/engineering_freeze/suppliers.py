"""Offline validation of hash-bound supplier document snapshots."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .model import FreezeFinding
from .schema import FreezeSchemaError, load_canonical_json
from ..hypothesis.canonical import canonical_bytes, validate_sha256


_FIELDS = frozenset({
    "id", "component_id", "manufacturer", "part_number", "source_url", "source_date",
    "review_date", "reviewer", "snapshot_path", "sha256", "limits", "supports_requirements",
})
_ROOT_FIELDS = frozenset({"schema_version", "supplier_manifest_id", "snapshots"})


def _finding(code: str, path: str, message: str) -> FreezeFinding:
    return FreezeFinding(code, "error", path, message)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _safe_snapshot_path(value: object) -> Path | None:
    if not isinstance(value, str) or "\\" in value:
        return None
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or not parsed.parts or parsed.parts[0] != "supplier-snapshots":
        return None
    return Path(*parsed.parts)


def _valid_limits(value: object) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    for name, item in value.items():
        if not _nonempty(name) or not isinstance(item, dict) or set(item) != {"value", "unit"}:
            return False
        if type(item["value"]) not in {int, float} or isinstance(item["value"], bool) or not _nonempty(item["unit"]):
            return False
    try:
        canonical_bytes(value)
        return True
    except ValueError:
        return False


def validate_supplier_manifest(
    root: Path, manifest_path: Path, component_ids: set[str], requirement_ids: set[str]
) -> list[FreezeFinding]:
    """Validate source snapshots without network access or promotion authority."""

    try:
        manifest = load_canonical_json(manifest_path)
    except FreezeSchemaError as exc:
        return [_finding("FREEZE.SUPPLIER_MANIFEST_INVALID", "supplier-manifest", str(exc))]
    findings: list[FreezeFinding] = []
    if set(manifest) != _ROOT_FIELDS or manifest.get("schema_version") != 1 or not _nonempty(manifest.get("supplier_manifest_id")):
        findings.append(_finding("FREEZE.SUPPLIER_MANIFEST_INVALID", "supplier-manifest", "supplier manifest fields are closed and schema_version must be 1"))
    snapshots = manifest.get("snapshots")
    if not isinstance(snapshots, list):
        return sorted(findings + [_finding("FREEZE.SUPPLIER_MANIFEST_INVALID", "snapshots", "snapshots must be a list")], key=lambda item: (item.code, item.path, item.message))
    seen: set[str] = set()
    for index, entry in enumerate(snapshots):
        path = f"snapshots[{index}]"
        if not isinstance(entry, dict) or set(entry) != _FIELDS:
            findings.append(_finding("FREEZE.SUPPLIER_RECORD_INVALID", path, "supplier snapshot record fields are closed"))
            continue
        identity = entry.get("id")
        if not _nonempty(identity):
            findings.append(_finding("FREEZE.SUPPLIER_RECORD_INVALID", f"{path}.id", "id must be non-empty"))
        elif identity in seen:
            findings.append(_finding("FREEZE.SUPPLIER_DUPLICATE_ID", f"{path}.id", f"duplicate supplier snapshot id: {identity}"))
        else:
            seen.add(identity)
        if entry.get("component_id") not in component_ids:
            findings.append(_finding("FREEZE.SUPPLIER_COMPONENT_UNKNOWN", f"{path}.component_id", "supplier snapshot references an unknown component"))
        supports = entry.get("supports_requirements")
        if not isinstance(supports, list) or not supports or any(item not in requirement_ids for item in supports):
            findings.append(_finding("FREEZE.SUPPLIER_REQUIREMENT_UNKNOWN", f"{path}.supports_requirements", "supplier snapshot must support only known requirements"))
        if not all(_nonempty(entry.get(name)) for name in ("manufacturer", "part_number", "reviewer")) or not _safe_url(entry.get("source_url")) or not _date(entry.get("source_date")) or not _date(entry.get("review_date")):
            findings.append(_finding("FREEZE.SUPPLIER_IDENTITY_INVALID", path, "supplier identity, HTTPS URL, review, and ISO dates are required"))
        if not _valid_limits(entry.get("limits")):
            findings.append(_finding("FREEZE.SUPPLIER_LIMITS_INVALID", f"{path}.limits", "limits must be closed typed value/unit records"))
        relative = _safe_snapshot_path(entry.get("snapshot_path"))
        if relative is None:
            findings.append(_finding("FREEZE.SUPPLIER_SNAPSHOT_PATH", f"{path}.snapshot_path", "snapshot path must remain under supplier-snapshots"))
            continue
        target = root / relative
        if target.is_symlink() or not target.is_file():
            findings.append(_finding("FREEZE.SUPPLIER_SNAPSHOT_MISSING", f"{path}.snapshot_path", "supplier snapshot must be a regular local file"))
            continue
        try:
            expected = validate_sha256(entry.get("sha256"), f"{path}.sha256")
        except ValueError as exc:
            findings.append(_finding("FREEZE.SUPPLIER_HASH_INVALID", f"{path}.sha256", str(exc)))
            continue
        observed = hashlib.sha256(target.read_bytes()).hexdigest()
        if observed != expected:
            findings.append(_finding("FREEZE.SUPPLIER_HASH_MISMATCH", f"{path}.sha256", "supplier snapshot SHA-256 does not match"))
            continue
        try:
            snapshot = load_canonical_json(target)
        except FreezeSchemaError as exc:
            findings.append(_finding("FREEZE.SUPPLIER_SNAPSHOT_INVALID", f"{path}.snapshot_path", str(exc)))
            continue
        for field in ("manufacturer", "part_number", "limits"):
            if snapshot.get(field) != entry.get(field):
                findings.append(_finding("FREEZE.SUPPLIER_IDENTITY_MISMATCH", f"{path}.{field}", f"snapshot {field} must equal manifest value"))
    return sorted(findings, key=lambda item: (item.code, item.path, item.message))
