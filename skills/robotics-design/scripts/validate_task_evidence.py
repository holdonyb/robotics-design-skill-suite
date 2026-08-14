#!/usr/bin/env python3
"""Validate offline task and robustness evidence without hardware interfaces."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assurance.engineering_freeze.schema import load_canonical_json
from assurance.hypothesis.canonical import canonical_bytes
from assurance.task_evidence.model import TaskEvidenceFinding, TaskEvidenceReport


_EMPTY = frozenset({"schema_version", "task_evidence_id", "packages"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = load_canonical_json(args.index)
        if not isinstance(index, dict) or set(index) != _EMPTY or index.get("schema_version") != 1 or not isinstance(index.get("task_evidence_id"), str) or not isinstance(index.get("packages"), list):
            raise ValueError("task evidence index must be a closed schema-v1 object")
        if index["packages"]:
            raise ValueError("populated task evidence intake is not yet bound to upstream evidence")
        report = TaskEvidenceReport(index["task_evidence_id"], "awaiting_authorization", (TaskEvidenceFinding("TASK.AUTHORIZATION_REQUIRED", "indeterminate", "packages", "no task evidence package is supplied"),), (), (), ())
        sys.stdout.buffer.write(canonical_bytes(report.to_dict()))
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: task evidence validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
