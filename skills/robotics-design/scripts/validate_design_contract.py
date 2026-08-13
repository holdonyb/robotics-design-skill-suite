#!/usr/bin/env python3
"""Validate a robot design contract and emit physical-assurance evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assurance.engine import evaluate_contract, serialize_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="Path to design-contract JSON")
    parser.add_argument("--report", type=Path, help="Write canonical evidence JSON")
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing report path"
    )
    args = parser.parse_args(argv)

    if args.report is not None and args.report.exists() and not args.force:
        print(f"ERROR: report already exists: {args.report}", file=sys.stderr)
        return 2

    try:
        report, errors = evaluate_contract(args.contract)
    except Exception as exc:  # Last-resort fail-closed CLI boundary.
        print(f"ERROR: assurance evaluation failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    assert report is not None
    try:
        serialized = serialize_report(report)
    except (TypeError, ValueError, OverflowError) as exc:
        print(f"ERROR: assurance report is not serializable: {exc}", file=sys.stderr)
        return 2
    if args.report is not None:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(serialized, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
            return 2

    if not report.promotable:
        for diagnostic in report.to_dict()["diagnostics"]:
            if diagnostic["severity"] in {"error", "indeterminate"}:
                print(
                    f"ERROR: {diagnostic['code']} {diagnostic['path']}: {diagnostic['message']}",
                    file=sys.stderr,
                )
        return 1

    print(f"Design contract promotable: {report.candidate_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
