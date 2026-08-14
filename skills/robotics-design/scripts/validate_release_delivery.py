#!/usr/bin/env python3
"""Validate the closed v1 public delivery without hardware interfaces."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assurance.hypothesis.canonical import canonical_bytes
from assurance.release.evaluator import evaluate_release_delivery


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate_release_delivery(args.root, args.contract)
        sys.stdout.buffer.write(canonical_bytes(report.to_dict()))
        return 0 if report.passed else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: release delivery validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
