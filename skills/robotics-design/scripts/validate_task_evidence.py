#!/usr/bin/env python3
"""Validate offline task and robustness evidence without hardware interfaces."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path, PurePosixPath

from assurance.engineering_freeze.schema import load_canonical_json
from assurance.hypothesis.canonical import canonical_bytes, validate_sha256
from assurance.task_evidence.model import TaskEvidenceFinding, TaskEvidenceReport


_EMPTY = frozenset({"schema_version", "task_evidence_id", "packages"})
_POPULATED = _EMPTY | {"design_contract", "freeze_package", "bench_index", "commissioning_index", "task_protocol"}


def _bound_file(root: Path, record: object, field: str) -> Path:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise ValueError(f"{field} must contain exactly path and sha256")
    value = record["path"]
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field}.path must be a nonempty forward-slash local path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field}.path must remain under the task evidence directory")
    target = root
    for part in parsed.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError(f"{field}.path must not traverse a symbolic link")
    if not target.is_file():
        raise ValueError(f"{field}.path must name a local regular file")
    if hashlib.sha256(target.read_bytes()).hexdigest() != validate_sha256(record["sha256"], f"{field}.sha256"):
        raise ValueError(f"{field} hash does not match intake index")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = load_canonical_json(args.index)
        if not isinstance(index, dict) or set(index) not in {_EMPTY, _POPULATED} or index.get("schema_version") != 1 or not isinstance(index.get("task_evidence_id"), str) or not isinstance(index.get("packages"), list):
            raise ValueError("task evidence index must be a closed schema-v1 object")
        if index["packages"]:
            if set(index) != _POPULATED:
                raise ValueError("populated task evidence intake requires all upstream bindings")
            for field in ("design_contract", "freeze_package", "bench_index", "commissioning_index", "task_protocol"):
                _bound_file(args.index.parent, index[field], field)
            raise ValueError("populated task evidence intake requires upstream evaluator integration")
        if set(index) != _EMPTY:
            raise ValueError("empty task evidence intake must not carry upstream bindings")
        report = TaskEvidenceReport(index["task_evidence_id"], "awaiting_authorization", (TaskEvidenceFinding("TASK.AUTHORIZATION_REQUIRED", "indeterminate", "packages", "no task evidence package is supplied"),), (), (), ())
        sys.stdout.buffer.write(canonical_bytes(report.to_dict()))
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: task evidence validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
