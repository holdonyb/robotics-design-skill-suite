"""Canonical, manifest-bound, transactional evidence bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import uuid
import ctypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .canonical import canonical_bytes, canonical_value


_MAX_FILES = 10_000
_MAX_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")


class BundleError(ValueError):
    """Raised when a bundle cannot be safely validated or published."""


@dataclass(frozen=True)
class BundleReceipt:
    """Out-of-band integrity receipt for a published bundle."""

    path: Path
    manifest_sha256: str


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {token}")


def _load(data: bytes) -> Any:
    if len(data) > _MAX_BYTES:
        raise BundleError("bundle file exceeds maximum size")
    try:
        parsed = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
        return canonical_value(parsed, "bundle JSON")
    except (
        UnicodeError,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        TypeError,
        ValueError,
    ) as exc:
        raise BundleError(f"invalid UTF-8 JSON: {exc}") from None


def _path(value: object) -> str:
    valid = isinstance(value, str) and bool(value) and "\\" not in value and ":" not in value
    if valid:
        path = PurePosixPath(value)
        valid = (
            not path.is_absolute()
            and value != "."
            and path.as_posix() == value
            and all(part not in ("", ".", "..") for part in value.split("/"))
        )
    if not valid:
        raise BundleError("bundle paths must be normalized relative POSIX paths")
    return value


def _manifest(index: object) -> dict[str, str]:
    if (
        not isinstance(index, dict)
        or set(index) != {"schema_version", "files"}
        or index.get("schema_version") != 1
        or type(index.get("schema_version")) is not int
        or not isinstance(index.get("files"), list)
    ):
        raise BundleError("manifest.json requires schema_version 1 and files")
    if len(index["files"]) + 1 > _MAX_FILES:
        raise BundleError("bundle file count exceeds maximum")
    result: dict[str, str] = {}
    for item in index["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise BundleError("manifest records require path and sha256")
        path = _path(item["path"])
        digest = item["sha256"]
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise BundleError("manifest sha256 is invalid")
        if path == "manifest.json":
            raise BundleError("manifest must not contain manifest.json")
        if path in result:
            raise BundleError("manifest has duplicate path")
        result[path] = digest
    return result


def validate_bundle(
    root: str | Path,
    *,
    manifest_sha256: str | None = None,
) -> list[str]:
    """Return structural errors and optionally verify an out-of-band receipt."""

    root = Path(root)
    errors: list[str] = []
    try:
        if not root.is_dir() or root.is_symlink():
            return ["bundle root is invalid"]
        manifest_data = (root / "manifest.json").read_bytes()
        if manifest_sha256 is not None:
            if not isinstance(manifest_sha256, str) or _SHA256.fullmatch(
                manifest_sha256
            ) is None:
                errors.append("expected manifest SHA-256 is invalid")
            elif _hash(manifest_data) != manifest_sha256:
                errors.append(
                    "manifest SHA-256 mismatch: "
                    f"expected {manifest_sha256}, observed {_hash(manifest_data)}"
                )
        manifest = _manifest(_load(manifest_data))
        actual: dict[str, str] = {}
        total_bytes = 0
        for item in root.rglob("*"):
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                errors.append(f"symlink is forbidden: {relative}")
            elif item.is_file():
                if len(actual) + 1 > _MAX_FILES:
                    errors.append("bundle file count exceeds maximum")
                    break
                data = item.read_bytes()
                total_bytes += len(data)
                if total_bytes > _MAX_BYTES:
                    errors.append("bundle total size exceeds maximum")
                    break
                parsed = _load(data)
                if canonical_bytes(parsed) != data:
                    errors.append(f"noncanonical file: {relative}")
                actual[relative] = _hash(data)
        expected = set(manifest) | {"manifest.json"}
        if set(actual) != expected:
            errors.append("bundle files do not match manifest")
        for path, digest in manifest.items():
            if actual.get(path) != digest:
                errors.append(f"stale hash: {path}")
    except (OSError, BundleError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return sorted(set(errors))


def _rename_absent(source: Path, target: Path) -> None:
    """Atomically rename a directory only when the destination is absent."""

    if os.name == "nt":
        source.rename(target)
        return
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise BundleError("atomic no-replace publication is unavailable")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        encoded_source = os.fsencode(source)
        encoded_target = os.fsencode(target)
        result = renameat2(-100, encoded_source, -100, encoded_target, 1)
        if result != 0:
            error = ctypes.get_errno()
            if error == 17:
                raise BundleError("output publication race: target already exists")
            raise OSError(error, os.strerror(error), str(target))
        return
    raise BundleError("atomic no-replace publication is unavailable on this platform")


def write_bundle_with_receipt(
    output: str | Path,
    files: Mapping[str, object],
    *,
    force: bool = False,
) -> BundleReceipt:
    """Validate and atomically publish a new bundle, restoring forced output on failure."""

    target = Path(output)
    if not isinstance(files, Mapping) or "index.json" not in files:
        raise BundleError("bundle requires index.json")
    if len(files) > _MAX_FILES:
        raise BundleError("bundle file count exceeds maximum")
    if target.exists() and not force:
        raise BundleError("output already exists")

    prepared: dict[str, bytes] = {}
    for raw_path, value in files.items():
        path = _path(raw_path)
        if path in prepared:
            raise BundleError("bundle contains duplicate path")
        prepared[path] = canonical_bytes(canonical_value(value, path))
    index = _load(prepared["index.json"])
    if not isinstance(index, dict):
        raise BundleError("index.json must be an object")
    index = dict(index)
    index["files"] = [
        {"path": path, "sha256": _hash(data)}
        for path, data in sorted(prepared.items())
        if path != "index.json"
    ]
    prepared["index.json"] = canonical_bytes(index)
    manifest = {
        "schema_version": 1,
        "files": [
            {"path": path, "sha256": _hash(data)}
            for path, data in sorted(prepared.items())
        ],
    }
    prepared["manifest.json"] = canonical_bytes(manifest)
    manifest_sha256 = _hash(prepared["manifest.json"])
    if len(prepared) > _MAX_FILES:
        raise BundleError("bundle file count exceeds maximum")
    if sum(len(data) for data in prepared.values()) > _MAX_BYTES:
        raise BundleError("bundle total size exceeds maximum")

    transaction = target.parent / f".hypothesis-txn-{uuid.uuid4().hex}"
    backup = target.parent / f".hypothesis-backup-{uuid.uuid4().hex}"
    moved_backup = False
    published = False
    try:
        transaction.mkdir(parents=True)
        for path, data in prepared.items():
            destination = transaction / Path(*PurePosixPath(path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        errors = validate_bundle(transaction)
        if errors:
            raise BundleError("bundle verification failed: " + "; ".join(errors))
        if force and target.exists():
            target.replace(backup)
            moved_backup = True
        if force:
            _rename_absent(transaction, target)
        else:
            try:
                _rename_absent(transaction, target)
            except (FileExistsError, PermissionError) as exc:
                raise BundleError(
                    "output publication race: target already exists"
                ) from exc
        published = True
        if backup.exists():
            shutil.rmtree(backup)
        return BundleReceipt(target, manifest_sha256)
    except BaseException as exc:
        recovery_error: str | None = None
        if moved_backup and backup.exists():
            if target.exists() and not published:
                recovery_error = (
                    "publication race preserved third-party output; original output "
                    f"is recoverable at backup {backup}"
                )
            elif not target.exists():
                backup.replace(target)
        if recovery_error is not None:
            raise BundleError(recovery_error) from exc
        if isinstance(exc, BundleError):
            raise
        raise BundleError(f"cannot publish bundle: {exc}") from exc
    finally:
        if transaction.exists():
            shutil.rmtree(transaction, ignore_errors=True)


def write_bundle(
    output: str | Path,
    files: Mapping[str, object],
    *,
    force: bool = False,
) -> Path:
    """Publish a bundle and retain the original Path-returning public API."""

    return write_bundle_with_receipt(output, files, force=force).path
