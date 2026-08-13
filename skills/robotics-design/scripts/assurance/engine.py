"""Deterministic orchestration for physical-plausibility contract evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .analyses import AnalysisResult, run_plugin
from .artifacts import compare_observations, observe_declared_json, observe_urdf
from .contract import load_contract
from .ledger import validate_ledger
from .model import Diagnostic, EvidenceLevel, Report
from .plugin_contracts import required_analysis_coverage
from .units import QuantityError, to_si


KERNEL_VERSION = "0.3.0"


def _analysis_coverage_diagnostics(data: dict[str, Any]) -> list[Diagnostic]:
    analyses = data.get("analyses", [])
    diagnostics: list[Diagnostic] = []
    if not analyses and (data.get("requirements") or data.get("quantities")):
        diagnostics.append(
            Diagnostic(
                "PHY.ANALYSIS.MISSING",
                "indeterminate",
                "analyses",
                "physical requirements or quantities exist but no analysis is declared",
            )
        )
        return diagnostics

    coverage_edges = {
        (str(item.get("plugin")), coverage)
        for item in analyses
        if isinstance(item, dict)
        for coverage in item.get("covers", [])
        if isinstance(coverage, str)
    }
    covered_responsibilities = {coverage for _, coverage in coverage_edges}
    for requirement in data.get("requirements", []):
        responsibility = f"requirement:{requirement.get('id')}"
        if responsibility not in covered_responsibilities:
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.MISSING_COVERAGE",
                    "indeterminate",
                    "analyses",
                    f"no analysis covers declared requirement {requirement.get('id')}",
                )
            )

    architecture = data.get("architecture", {})
    for plugin, responsibility in sorted(required_analysis_coverage(architecture)):
        if (plugin, responsibility) not in coverage_edges:
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.MISSING_COVERAGE",
                    "indeterminate",
                    "analyses",
                    f"{responsibility} requires analysis {plugin}",
                )
            )

    declared_actuators = set(architecture.get("actuators", []))
    for index, analysis in enumerate(analyses):
        if analysis.get("plugin") != "arm_gravity_v1":
            continue
        joint_ids = {
            joint.get("id")
            for joint in analysis.get("inputs", {}).get("joints", [])
            if isinstance(joint, dict) and isinstance(joint.get("id"), str)
        }
        covered_actuators = {
            value[9:]
            for value in analysis.get("covers", [])
            if isinstance(value, str) and value.startswith("actuator:")
        }
        for actuator in sorted(covered_actuators - joint_ids):
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.COVERAGE_MISMATCH",
                    "indeterminate",
                    f"analyses[{index}].covers",
                    f"arm analysis claims actuator coverage without a joint load: {actuator}",
                )
            )
        for joint_id in sorted(joint_ids - declared_actuators):
            if declared_actuators:
                diagnostics.append(
                    Diagnostic(
                        "PHY.ANALYSIS.COVERAGE_MISMATCH",
                        "indeterminate",
                        f"analyses[{index}].inputs.joints",
                        f"arm analysis contains undeclared actuator joint: {joint_id}",
                    )
                )
    drive_units = architecture.get("drive_units", [])
    if isinstance(drive_units, list) and drive_units:
        quantities = {
            item.get("id"): item
            for item in data.get("quantities", [])
            if isinstance(item, dict)
        }
        for index, analysis in enumerate(analyses):
            if analysis.get("plugin") != "drivetrain_v1":
                continue
            reference = analysis.get("inputs", {}).get("driven_wheels")
            quantity = (
                quantities.get(reference[9:])
                if isinstance(reference, str) and reference.startswith("quantity:")
                else None
            )
            if quantity is None:
                continue
            try:
                declared_count = to_si(
                    quantity.get("value"),
                    quantity.get("dimension"),
                    f"analyses[{index}].inputs.driven_wheels",
                )
            except QuantityError:
                continue
            if declared_count != float(len(drive_units)):
                diagnostics.append(
                    Diagnostic(
                        "PHY.DRIVE.CARDINALITY_MISMATCH",
                        "error",
                        f"analyses[{index}].inputs.driven_wheels",
                        f"declared driven wheel count {declared_count:g} does not match {len(drive_units)} drive responsibilities",
                    )
                )
    return diagnostics


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

    def resolve(reference: Any, path: str) -> Any:
        if isinstance(reference, str) and reference.startswith("quantity:"):
            quantity_id = reference[9:]
            quantity = quantities.get(quantity_id)
            if quantity is None:
                report.add(
                    Diagnostic(
                        "PHY.INPUT.REFERENCE",
                        "indeterminate",
                        path,
                        f"unknown quantity reference: {reference}",
                    )
                )
                return None
            try:
                return to_si(
                    quantity.get("value"),
                    quantity.get("dimension"),
                    f"quantity:{quantity_id}",
                )
            except QuantityError as exc:
                report.add(
                    Diagnostic(
                        "PHY.INPUT.REFERENCE",
                        "error",
                        path,
                        str(exc),
                    )
                )
                return None
        if isinstance(reference, str):
            return reference
        if isinstance(reference, list):
            return [resolve(item, f"{path}[{index}]") for index, item in enumerate(reference)]
        if isinstance(reference, dict):
            return {
                key: resolve(value, f"{path}.{key}")
                for key, value in sorted(reference.items())
            }
        report.add(
            Diagnostic(
                "PHY.INPUT.REFERENCE",
                "indeterminate",
                path,
                f"unsupported analysis input reference: {reference}",
            )
        )
        return None

    for name, reference in sorted(inputs.items()):
        value = resolve(reference, f"analyses.{analysis.get('id')}.inputs.{name}")
        if value is not None:
            resolved[name] = value
        else:
            report.add(
                Diagnostic(
                    "PHY.INPUT.REFERENCE",
                    "indeterminate",
                    f"analyses.{analysis.get('id')}.inputs.{name}",
                    "analysis input could not be resolved",
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
    for diagnostic in _analysis_coverage_diagnostics(data):
        report.add(diagnostic)

    contract_dir = path.parent
    observations: dict[str, Any] = {}
    for index, artifact in enumerate(data.get("artifacts", [])):
        artifact_path, valid_artifact = _resolve_file(
            contract_dir, artifact, f"artifacts[{index}]", report
        )
        if artifact_path is None or not valid_artifact:
            continue
        if artifact.get("kind") == "urdf":
            observation, diagnostics = observe_urdf(artifact_path)
            for diagnostic in diagnostics:
                report.add(diagnostic)
            if observation is not None:
                observations[str(artifact.get("id"))] = observation
        elif artifact.get("kind") == "declared_json":
            observation, diagnostics = observe_declared_json(artifact_path)
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
    level_counts: dict[str, int] = {}
    declared_levels: list[EvidenceLevel] = []
    for quantity in data.get("quantities", []):
        level = EvidenceLevel(quantity["evidence_level"])
        declared_levels.append(level)
        level_counts[level.value] = level_counts.get(level.value, 0) + 1
    report.metadata["evidence_level_counts"] = dict(sorted(level_counts.items()))
    report.metadata["minimum_evidence_level"] = (
        min(declared_levels).value if declared_levels else "none"
    )

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
