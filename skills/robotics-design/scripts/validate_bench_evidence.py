#!/usr/bin/env python3
"""Validate local raw bench-evidence intake without hardware control authority."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assurance.engineering_freeze.schema import load_canonical_json
from assurance.hypothesis.canonical import canonical_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = load_canonical_json(args.index)
        if set(index) != {"schema_version", "intake_id", "packages"} or index.get("schema_version") != 1 or not isinstance(index.get("packages"), list):
            raise ValueError("intake index must be a closed schema-v1 object")
        if index["packages"]:
            raise ValueError("multi-package aggregation is not implemented; validate each package independently")
        output = {
            "status": "awaiting_authorization",
            "intake_id": index.get("intake_id"),
            "accepted_packages": 0,
            "procurement_authorized": False,
            "motion_authorized": False,
            "findings": [{"code": "BENCH.NO_RAW_EVIDENCE", "path": "packages", "message": "no raw bench package has been provided under authorized test conditions"}],
        }
        sys.stdout.buffer.write(canonical_bytes(output))
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: bench evidence validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
