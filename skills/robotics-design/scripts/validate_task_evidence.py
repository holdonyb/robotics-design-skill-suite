#!/usr/bin/env python3
"""Validate offline task and robustness evidence without hardware interfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

from assurance.engineering_freeze.schema import load_canonical_json
from assurance.contract import load_contract
from assurance.engineering_freeze.evaluator import evaluate_engineering_freeze
from assurance.hypothesis.canonical import canonical_bytes, validate_sha256
from assurance.task_evidence.model import TaskEvidenceFinding, TaskEvidenceReport
from assurance.task_evidence.protocol import validate_task_protocol
from assurance.task_evidence.evaluator import evaluate_task_packages


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


def _run_bound_gate(root: Path, script_name: str, index_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name(script_name)), "--index", str(index_path)],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"{script_name} rejected its bound intake: {detail or 'no diagnostic'}")
    try:
        data = json.loads(result.stdout)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"{script_name} did not produce a canonical JSON report: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{script_name} report must be an object")
    return data


def _upstream_findings(root: Path, index: dict[str, object], *, design_path: Path, freeze_path: Path, bench_path: Path, commissioning_path: Path) -> tuple[TaskEvidenceFinding, ...]:
    """Evaluate every prerequisite under its own existing fail-closed gate."""
    contract, contract_errors = load_contract(design_path)
    if contract_errors or not isinstance(contract, dict):
        raise ValueError("design contract is invalid: " + "; ".join(contract_errors))
    components = contract.get("components")
    if not isinstance(components, list):
        raise ValueError("design contract components must be a list")
    placeholders = {
        item.get("id") for item in components
        if isinstance(item, dict) and item.get("state") == "engineering_placeholder" and isinstance(item.get("id"), str)
    }

    design_binding = index["design_contract"]
    if not isinstance(design_binding, dict):
        raise ValueError("task-evidence design contract binding is invalid")
    freeze_data = load_canonical_json(freeze_path)
    freeze_design = freeze_data.get("design_contract") if isinstance(freeze_data, dict) else None
    if not isinstance(freeze_design, dict) or freeze_design.get("sha256") != design_binding["sha256"]:
        raise ValueError("freeze package does not bind the task-evidence design contract")
    freeze_report = evaluate_engineering_freeze(root, freeze_path, placeholder_components=placeholders)
    if freeze_report.freeze_id == "freeze-invalid":
        raise ValueError("freeze package is invalid")

    bench_data = load_canonical_json(bench_path)
    if not isinstance(bench_data, dict) or type(bench_data.get("schema_version")) is not int or bench_data["schema_version"] != 1 or not isinstance(bench_data.get("packages"), list):
        raise ValueError("bench_index must be a closed schema-v1 intake")
    if bench_data["packages"]:
        bench_design = bench_data.get("design_contract")
        if not isinstance(bench_design, dict) or bench_design.get("sha256") != design_binding["sha256"]:
            raise ValueError("bench_index does not bind the task-evidence design contract")
    bench_report = _run_bound_gate(root, "validate_bench_evidence.py", bench_path)
    bench_ready = bench_report.get("status") == "accepted" and bench_report.get("evidence_level") == "bench-tested"

    commissioning_data = load_canonical_json(commissioning_path)
    empty = frozenset({"schema_version", "commissioning_id", "phases"})
    populated = empty | {"design_contract", "freeze_package", "bench_index"}
    if not isinstance(commissioning_data, dict) or set(commissioning_data) not in {empty, populated}:
        raise ValueError("commissioning_index must be a closed schema-v1 intake")
    if type(commissioning_data.get("schema_version")) is not int or commissioning_data["schema_version"] != 1:
        raise ValueError("commissioning_index must be schema_version 1")
    if commissioning_data.get("phases") and set(commissioning_data) != populated:
        raise ValueError("populated commissioning_index requires all upstream bindings")
    commissioning_design = commissioning_data.get("design_contract") if isinstance(commissioning_data, dict) else None
    if set(commissioning_data) == populated and (not isinstance(commissioning_design, dict) or commissioning_design.get("sha256") != design_binding["sha256"]):
        raise ValueError("commissioning_index does not bind the task-evidence design contract")
    commissioning_report = _run_bound_gate(root, "validate_commissioning_evidence.py", commissioning_path)

    findings: list[TaskEvidenceFinding] = []
    if not freeze_report.freeze_ready:
        findings.append(TaskEvidenceFinding("TASK.FREEZE_NOT_READY", "indeterminate", "freeze_package", "engineering freeze remains incomplete"))
    if not bench_ready:
        findings.append(TaskEvidenceFinding("TASK.BENCH_EVIDENCE_REQUIRED", "indeterminate", "bench_index", "accepted retained bench evidence is required"))
    if commissioning_report.get("status") != "ready":
        severity = "error" if commissioning_report.get("status") == "rejected" else "indeterminate"
        findings.append(TaskEvidenceFinding("TASK.COMMISSIONING_REQUIRED", severity, "commissioning_index", "commissioning evidence is not ready"))
    return tuple(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = load_canonical_json(args.index)
        if not isinstance(index, dict) or set(index) not in {_EMPTY, _POPULATED} or type(index.get("schema_version")) is not int or index["schema_version"] != 1 or not isinstance(index.get("task_evidence_id"), str) or not isinstance(index.get("packages"), list):
            raise ValueError("task evidence index must be a closed schema-v1 object")
        if index["packages"]:
            if set(index) != _POPULATED:
                raise ValueError("populated task evidence intake requires all upstream bindings")
            bound = {field: _bound_file(args.index.parent, index[field], field) for field in ("design_contract", "freeze_package", "bench_index", "commissioning_index", "task_protocol")}
            protocol_data = load_canonical_json(bound["task_protocol"])
            protocol, protocol_findings = validate_task_protocol(protocol_data)
            if protocol is None:
                raise ValueError("task protocol is invalid: " + "; ".join(item.message for item in protocol_findings))
            package_paths: list[Path] = []
            package_hashes: set[str] = set()
            for position, record in enumerate(index["packages"]):
                package_path = _bound_file(args.index.parent, record, f"packages[{position}]")
                if not isinstance(record, dict):
                    raise ValueError(f"packages[{position}] must contain a hash binding")
                package_hash = validate_sha256(record.get("sha256"), f"packages[{position}].sha256")
                if package_hash in package_hashes:
                    raise ValueError(f"packages[{position}] duplicates an earlier package hash")
                package_hashes.add(package_hash)
                package_paths.append(package_path)
            packages = [load_canonical_json(package_path) for package_path in package_paths]
            report = evaluate_task_packages(args.index.parent, protocol, packages)
            upstream = _upstream_findings(args.index.parent, index, design_path=bound["design_contract"], freeze_path=bound["freeze_package"], bench_path=bound["bench_index"], commissioning_path=bound["commissioning_index"])
            findings = report.findings + upstream
            status = "rejected" if any(item.severity == "error" for item in findings) else "awaiting_authorization" if any(item.severity == "indeterminate" for item in findings) else "evidence_complete"
            report = TaskEvidenceReport(index["task_evidence_id"], status, findings, report.metric_summaries, report.fault_dispositions, report.comparison_residuals)
            sys.stdout.buffer.write(canonical_bytes(report.to_dict()))
            return 0 if report.status == "evidence_complete" else 1
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
