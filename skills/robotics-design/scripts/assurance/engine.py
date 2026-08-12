"""Deterministic orchestration for physical-plausibility contract evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .analyses import AnalysisResult, run_plugin
from .artifacts import compare_observations, observe_urdf
from .contract import load_contract
from .ledger import validate_ledger
from .model import Diagnostic, Report
from .units import QuantityError, to_si


KERNEL_VERSION = "0.3.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_file(
    contract_dir: Path,
    record: dict[str, Any],
    path: str,
    report: Report,
) -> tuple[Path | None, bool]:
    raw_path = record.get("path")
    expected = record.get("sha256")
    if not isinstance(raw_path, str):
        return None, False
    root = contract_dir.resolve()
    candidate = (contract_dir / raw_path).resolve()
    if not candidate.is_relative_to(root):
        report.add(
            Diagnostic(
                "EVIDENCE.PATH_ESCAPE",
                "error",
                path,
                f"file path escapes contract directory: {raw_path}",
            )
        )
        return None, False
    if not candidate.is_file():
        report.add(
            Diagnostic(
                "EVIDENCE.MISSING_ARTIFACT",
                "error",
                path,
                f"bound file does not exist: {raw_path}",
            )
        )
        return candidate, False
    try:
        actual = _sha256(candidate)
    except OSError as exc:
        report.add(
            Diagnostic(
                "EVIDENCE.READ",
                "error",
                path,
                f"cannot hash bound file: {exc}",
            )
        )
        return candidate, False
    if actual != expected:
        report.add(
            Diagnostic(
                "EVIDENCE.STALE_ARTIFACT",
                "error",
                path,
                f"SHA-256 mismatch for {raw_path}",
            )
        )
        return candidate, False
    return candidate, True


def _analysis_dict(result: AnalysisResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "version": result.version,
        "evidence_level": result.evidence_level.value,
        "inputs": result.inputs,
        "outputs": result.outputs,
        "validity_assumptions": list(result.validity_assumptions),
        "passed": result.passed,
    }


def _resolved_analysis_inputs(
    analysis: dict[str, Any], quantities: dict[str, dict[str, Any]], report: Report
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    inputs = analysis.get("inputs", {})
    if not isinstance(inputs, dict):
        return resolved
    for name, reference in sorted(inputs.items()):
        if isinstance(reference, str) and reference.startswith("quantity:"):
            quantity_id = reference[9:]
            quantity = quantities.get(quantity_id)
            if quantity is None:
                report.add(
                    Diagnostic(
                        "PHY.INPUT.REFERENCE",
                        "indeterminate",
                        f"analyses.{analysis.get('id')}.inputs.{name}",
                        f"unknown quantity reference: {reference}",
                    )
                )
                continue
            try:
                resolved[name] = to_si(
                    quantity.get("value"),
                    quantity.get("dimension"),
                    f"quantity:{quantity_id}",
                )
            except QuantityError as exc:
                report.add(
                    Diagnostic(
                        "PHY.INPUT.REFERENCE",
                        "error",
                        f"analyses.{analysis.get('id')}.inputs.{name}",
                        str(exc),
                    )
                )
        else:
            report.add(
                Diagnostic(
                    "PHY.INPUT.REFERENCE",
                    "indeterminate",
                    f"analyses.{analysis.get('id')}.inputs.{name}",
                    f"unsupported analysis input reference: {reference}",
                )
            )
    return resolved


def evaluate_contract(path: Path) -> tuple[Report | None, list[str]]:
    """Evaluate a contract; schema/load errors are separate from physical findings."""

    data, errors = load_contract(path)
    if errors:
        return None, errors
    assert isinstance(data, dict)
    try:
        contract_digest = _sha256(path)
    except OSError as exc:
        return None, [f"cannot hash contract: {exc}"]

    report = Report(str(data["candidate_id"]))
    report.metadata.update(
        {
            "schema_version": data["schema_version"],
            "contract_sha256": contract_digest,
            "tool_versions": {"assurance_kernel": KERNEL_VERSION},
        }
    )
    for diagnostic in validate_ledger(data):
        report.add(diagnostic)

    contract_dir = path.parent
    observations: dict[str, Any] = {}
    for index, artifact in enumerate(data.get("artifacts", [])):
        artifact_path, _ = _resolve_file(
            contract_dir, artifact, f"artifacts[{index}]", report
        )
        if artifact_path is None or not artifact_path.is_file():
            continue
        if artifact.get("kind") == "urdf":
            observation, diagnostics = observe_urdf(artifact_path)
            for diagnostic in diagnostics:
                report.add(diagnostic)
            if observation is not None:
                observations[str(artifact.get("id"))] = observation

    evidence_records = data.get("evidence", [])
    valid_evidence = 0
    for index, evidence in enumerate(evidence_records):
        _, valid = _resolve_file(
            contract_dir,
            evidence.get("source", {}),
            f"evidence[{index}].source",
            report,
        )
        if valid:
            valid_evidence += 1
    report.metadata["evidence_coverage"] = f"{valid_evidence}/{len(evidence_records)}"

    for diagnostic in compare_observations(data, observations):
        report.add(diagnostic)

    quantities = {
        item["id"]: item
        for item in data.get("quantities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for analysis in data.get("analyses", []):
        resolved = _resolved_analysis_inputs(analysis, quantities, report)
        result = run_plugin(str(analysis.get("plugin")), resolved)
        report.analyses.append(_analysis_dict(result))
        for diagnostic in result.diagnostics:
            report.add(diagnostic)

    return report, []


def serialize_report(report: Report) -> str:
    """Return canonical UTF-8-compatible JSON text with one trailing newline."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"
