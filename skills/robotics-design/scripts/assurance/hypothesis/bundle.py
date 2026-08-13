"""Canonical, manifest-bound, transactional evidence bundles."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Mapping

from .canonical import canonical_bytes, canonical_value

_MAX_FILES = 10_000
_MAX_BYTES = 16 * 1024 * 1024

class BundleError(ValueError): pass
def _hash(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out
def _load(data: bytes):
    if len(data) > _MAX_BYTES: raise BundleError("bundle file exceeds maximum size")
    try: return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc: raise BundleError(f"invalid UTF-8 JSON: {exc}") from None
def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value: raise BundleError("bundle paths must be normalized relative POSIX paths")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value: raise BundleError("bundle paths must be normalized relative POSIX paths")
    return value
def _manifest(index: object):
    if not isinstance(index, dict) or not isinstance(index.get("files"), list): raise BundleError("index.json requires files manifest")
    result = {}
    for item in index["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}: raise BundleError("manifest records require path and sha256")
        path = _path(item["path"]); digest = item["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest): raise BundleError("manifest sha256 is invalid")
        if path in result: raise BundleError("manifest has duplicate path")
        result[path] = digest
    return result
def validate_bundle(root: str | Path) -> list[str]:
    root = Path(root); errors=[]
    moved_backup = False
    published = False
    try:
        if not root.is_dir() or root.is_symlink(): return ["bundle root is invalid"]
        index_data=(root/"index.json").read_bytes(); index=_load(index_data); manifest=_manifest(index)
        actual={}
        for item in root.rglob("*"):
            if item.is_symlink(): errors.append(f"symlink is forbidden: {item.relative_to(root).as_posix()}")
            elif item.is_file():
                rel=item.relative_to(root).as_posix(); data=item.read_bytes(); parsed=_load(data)
                if canonical_bytes(canonical_value(parsed)) != data: errors.append(f"noncanonical file: {rel}")
                actual[rel]=_hash(data)
        expected=set(manifest)|{"index.json"}
        if set(actual)!=expected: errors.append("bundle files do not match manifest")
        for path,digest in manifest.items():
            if actual.get(path)!=digest: errors.append(f"stale hash: {path}")
    except (OSError, BundleError, ValueError) as exc: errors.append(str(exc))
    return sorted(set(errors))
def write_bundle(output: str | Path, files: Mapping[str,object], *, force=False) -> Path:
    target=Path(output); prepared={}
    if not isinstance(files, Mapping) or "index.json" not in files: raise BundleError("bundle requires index.json")
    if target.exists() and (not target.is_dir() or any(target.iterdir())) and not force: raise BundleError("output already exists and is non-empty")
    for path,value in files.items(): prepared[_path(path)] = canonical_bytes(canonical_value(value, path))
    index=_load(prepared["index.json"])
    if not isinstance(index,dict): raise BundleError("index.json must be an object")
    index=dict(index); index["files"]=[{"path":p,"sha256":_hash(data)} for p,data in sorted(prepared.items()) if p!="index.json"]; prepared["index.json"]=canonical_bytes(index)
    txn=target.parent/f".hypothesis-txn-{uuid.uuid4().hex}"; backup=target.parent/f".hypothesis-backup-{uuid.uuid4().hex}"
    try:
        txn.mkdir(parents=True)
        for path,data in prepared.items():
            dest=txn/path; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
        errors=validate_bundle(txn)
        if errors: raise BundleError("bundle verification failed: "+"; ".join(errors))
        if target.exists():
            target.replace(backup)
            moved_backup = True
        txn.replace(target)
        published = True
        if backup.exists(): shutil.rmtree(backup)
        return target
    except BaseException as exc:
        if moved_backup and backup.exists():
            if target.exists() and not published:
                shutil.rmtree(target, ignore_errors=True)
            if not target.exists():
                backup.replace(target)
        if isinstance(exc, BundleError):
            raise
        raise BundleError(f"cannot publish bundle: {exc}") from exc
    finally:
        if txn.exists(): shutil.rmtree(txn,ignore_errors=True)
