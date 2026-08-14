#!/usr/bin/env python3
"""Validate offline commissioning evidence without hardware interfaces."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path, PurePosixPath

from assurance.commissioning.evaluator import evaluate_commissioning_package
from assurance.contract import load_contract
from assurance.engineering_freeze.evaluator import evaluate_engineering_freeze
from assurance.engineering_freeze.schema import load_canonical_json
from assurance.hypothesis.canonical import canonical_bytes, validate_sha256
from assurance.commissioning.model import CommissioningFinding, CommissioningReport


_EMPTY = frozenset({"schema_version", "commissioning_id", "phases"})
_POPULATED = _EMPTY | {"design_contract", "freeze_package", "bench_index"}


def _safe_bound_file(root: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} must be a nonempty forward-slash local path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field} must remain under the intake directory")
    target = root
    for part in parsed.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError(f"{field} must not traverse a symbolic link")
    if not target.is_file():
        raise ValueError(f"{field} must name a local regular file")
    return target


def _bound_file(root: Path, record: object, field: str) -> Path:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise ValueError(f"{field} must contain exactly path and sha256")
    target = _safe_bound_file(root, record["path"], f"{field}.path")
    expected = validate_sha256(record["sha256"], f"{field}.sha256")
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError(f"{field} hash does not match intake index")
    return target


def _bound_json(root: Path, record: object, field: str) -> tuple[Path, dict[str, object]]:
    target = _bound_file(root, record, field)
    return target, load_canonical_json(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = load_canonical_json(args.index)
        if set(index) not in {_EMPTY, _POPULATED} or index.get("schema_version") != 1 or not isinstance(index.get("commissioning_id"), str) or not isinstance(index.get("phases"), list):
            raise ValueError("commissioning index must be a closed schema-v1 object")
        if not index["phases"]:
            if set(index) != _EMPTY:
                raise ValueError("empty commissioning intake must not carry upstream evidence bindings")
            report = evaluate_commissioning_package(args.index.parent, index)
        else:
            if set(index) != _POPULATED:
                raise ValueError("populated commissioning intake requires design_contract, freeze_package, and bench_index")
            contract_path = _bound_file(args.index.parent, index["design_contract"], "design_contract")
            contract, contract_errors = load_contract(contract_path)
            if contract_errors or not isinstance(contract, dict):
                raise ValueError("design contract is invalid: " + "; ".join(contract_errors))
            components = contract.get("components")
            if not isinstance(components, list):
                raise ValueError("design contract components must be a list")
            placeholders = {
                item.get("id") for item in components
                if isinstance(item, dict) and item.get("state") == "engineering_placeholder" and isinstance(item.get("id"), str)
            }
            freeze_path, freeze_data = _bound_json(args.index.parent, index["freeze_package"], "freeze_package")
            if freeze_data.get("design_contract", {}).get("sha256") != index["design_contract"]["sha256"]:
                raise ValueError("freeze package does not bind the commissioning design contract")
            freeze_report = evaluate_engineering_freeze(args.index.parent, freeze_path, placeholder_components=placeholders)
            if freeze_report.freeze_id == "freeze-invalid":
                raise ValueError("freeze package is invalid")
            _, bench_index = _bound_json(args.index.parent, index["bench_index"], "bench_index")
            if set(bench_index) not in ({"schema_version", "intake_id", "packages"}, {"schema_version", "intake_id", "packages", "design_contract"}) or bench_index.get("schema_version") != 1 or not isinstance(bench_index.get("packages"), list):
                raise ValueError("bench_index must be a closed schema-v1 intake")
            report = evaluate_commissioning_package(args.index.parent, {key: index[key] for key in _EMPTY})
            upstream_findings = []
            if not freeze_report.freeze_ready:
                upstream_findings.append(CommissioningFinding("COMM.FREEZE_NOT_READY", "indeterminate", "freeze_package", "engineering freeze remains incomplete and blocks commissioning readiness"))
            if not bench_index["packages"]:
                upstream_findings.append(CommissioningFinding("COMM.BENCH_EVIDENCE_REQUIRED", "indeterminate", "bench_index.packages", "commissioning readiness requires retained component bench evidence"))
            if upstream_findings and report.status != "rejected":
                report = CommissioningReport(report.commissioning_id, "awaiting_authorization", report.findings + tuple(upstream_findings), report.highest_validated_phase)
        sys.stdout.buffer.write(canonical_bytes(report.to_dict()))
        return 0 if report.status == "ready" else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: commissioning evidence validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
