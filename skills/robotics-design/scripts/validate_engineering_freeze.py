#!/usr/bin/env python3
"""Validate a bounded engineering-freeze package without granting hardware authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from assurance.engineering_freeze.evaluator import evaluate_engineering_freeze
from assurance.engineering_freeze.schema import load_canonical_json
from assurance.contract import load_contract
from assurance.hypothesis.canonical import canonical_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.report and args.report.exists() and not args.force:
        print(f"ERROR: report already exists: {args.report}", file=sys.stderr)
        return 2
    root = args.package.parent.parent
    try:
        load_canonical_json(args.package)
        package = load_canonical_json(args.package)
        contract_record = package.get("design_contract", {})
        contract_path = root / contract_record.get("path", "")
        if not contract_path.is_file() or contract_path.is_symlink():
            raise ValueError("design contract must be a local regular file")
        if hashlib.sha256(contract_path.read_bytes()).hexdigest() != contract_record.get("sha256"):
            raise ValueError("design contract hash does not match engineering-freeze package")
        contract, errors = load_contract(contract_path)
        if errors or not isinstance(contract, dict):
            raise ValueError("design contract is invalid: " + "; ".join(errors))
        components = contract.get("components")
        if not isinstance(components, list):
            raise ValueError("design contract components must be a list")
        placeholders = {
            item.get("id") for item in components
            if isinstance(item, dict) and item.get("state") == "engineering_placeholder" and isinstance(item.get("id"), str)
        }
        report = evaluate_engineering_freeze(root, args.package, placeholder_components=placeholders)
        data = canonical_bytes(report.to_dict())
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_bytes(data)
        sys.stdout.buffer.write(data)
        return 0 if report.freeze_ready else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: engineering freeze validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
