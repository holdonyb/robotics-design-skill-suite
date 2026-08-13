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
    declared_drives = set(architecture.get("drive_units", []))
    declared_features = set(architecture.get("features", []))
    for index, analysis in enumerate(analyses):
        plugin = analysis.get("plugin")
        covers = {
            value for value in analysis.get("covers", []) if isinstance(value, str)
        }
        scoped_drives = {value[6:] for value in covers if value.startswith("drive:")}
        scoped_actuators = {
            value[9:] for value in covers if value.startswith("actuator:")
        }
        undeclared_message: str | None = None
        if plugin == "drivetrain_v1" and (
            "differential_drive" not in declared_features or len(scoped_drives) != 1
        ):
            undeclared_message = (
                "drivetrain_v1 requires differential_drive architecture and exactly one drive responsibility"
            )
        elif plugin == "stability_v1" and (
            "differential_drive" not in declared_features or not scoped_drives
        ):
            undeclared_message = (
                f"{plugin} requires differential_drive architecture and explicit drive coverage"
            )
        elif plugin == "battery_v1" and "battery_powered" not in declared_features:
            undeclared_message = "battery_v1 requires battery_powered architecture"
        elif plugin == "arm_gravity_v1" and (
            not declared_actuators or not scoped_actuators
        ):
            undeclared_message = (
                "arm_gravity_v1 requires declared actuators and explicit actuator coverage"
            )
        elif plugin == "thermal_duty_v1" and (
            len(scoped_drives) + len(scoped_actuators) != 1
        ):
            undeclared_message = (
                "thermal_duty_v1 must cover exactly one declared drive or actuator"
            )
        if undeclared_message is not None:
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.UNDECLARED_SCOPE",
                    "indeterminate",
                    f"analyses[{index}].covers",
                    undeclared_message,
                )
            )

        for drive in sorted(scoped_drives - declared_drives):
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.UNDECLARED_SCOPE",
                    "indeterminate",
                    f"analyses[{index}].covers",
                    f"analysis covers undeclared drive: {drive}",
                )
            )
        for actuator in sorted(scoped_actuators - declared_actuators):
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.UNDECLARED_SCOPE",
                    "indeterminate",
                    f"analyses[{index}].covers",
                    f"analysis covers undeclared actuator: {actuator}",
                )
            )

        if plugin != "arm_gravity_v1":
            continue
        joint_ids = {
            joint.get("id")
            for joint in analysis.get("inputs", {}).get("joints", [])
            if isinstance(joint, dict) and isinstance(joint.get("id"), str)
        }
        covered_actuators = scoped_actuators
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


def _analysis_rating_owner_diagnostics(data: dict[str, Any]) -> list[Diagnostic]:
    """Bind analysis ratings to the exact component serving each responsibility."""

    diagnostics: list[Diagnostic] = []
    quantities = {
        item.get("id"): item
        for item in data.get("quantities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    components = [
        item
        for item in data.get("components", [])
        if isinstance(item, dict) and item.get("state") != "missing"
    ]

    def component_for(responsibility: str, role: str) -> str | None:
        matches = [
            str(item.get("id"))
            for item in components
            if item.get("role") == role
            and responsibility in item.get("bindings", [])
        ]
        return matches[0] if len(matches) == 1 else None

    def check_owner(
        analysis_index: int,
        inputs: dict[str, Any],
        field: str,
        responsibility: str,
        role: str,
        nested_path: str = "",
    ) -> None:
        reference = inputs.get(field)
        if not isinstance(reference, str) or not reference.startswith("quantity:"):
            return
        quantity = quantities.get(reference[9:])
        component_id = component_for(responsibility, role)
        expected_owner = f"component:{component_id}" if component_id is not None else None
        if quantity is None or expected_owner is None or quantity.get("owner") != expected_owner:
            field_path = f"analyses[{analysis_index}].inputs{nested_path}.{field}"
            diagnostics.append(
                Diagnostic(
                    "PHY.ANALYSIS.RATING_OWNER",
                    "indeterminate",
                    field_path,
                    f"{field} must be owned by the unique {role} bound to {responsibility}",
                )
            )

    for index, analysis in enumerate(data.get("analyses", [])):
        if not isinstance(analysis, dict):
            continue
        plugin = analysis.get("plugin")
        inputs = analysis.get("inputs", {})
        covers = analysis.get("covers", [])
        if not isinstance(inputs, dict) or not isinstance(covers, list):
            continue
        scoped = [
            value
            for value in covers
            if isinstance(value, str)
            and (value.startswith("drive:") or value.startswith("actuator:"))
        ]
        if plugin == "drivetrain_v1" and len(scoped) == 1:
            responsibility = scoped[0]
            for field in (
                "motor_continuous_torque_nm",
                "motor_peak_torque_nm",
                "motor_max_speed_rad_s",
            ):
                check_owner(index, inputs, field, responsibility, "traction_motor")
            for field in ("gear_ratio", "efficiency"):
                check_owner(index, inputs, field, responsibility, "reducer")
            check_owner(index, inputs, "wheel_radius_m", responsibility, "wheel")
        elif plugin == "battery_v1":
            responsibility = "feature:battery_powered"
            for field in (
                "voltage_v",
                "max_continuous_current_a",
                "max_peak_current_a",
                "usable_energy_j",
            ):
                check_owner(index, inputs, field, responsibility, "battery")
        elif plugin == "arm_gravity_v1":
            joints = inputs.get("joints", [])
            if not isinstance(joints, list):
                continue
            for joint_index, joint in enumerate(joints):
                if not isinstance(joint, dict) or not isinstance(joint.get("id"), str):
                    continue
                responsibility = f"actuator:{joint['id']}"
                nested = f".joints[{joint_index}]"
                check_owner(
                    index,
                    joint,
                    "rated_continuous_torque_nm",
                    responsibility,
                    "motor",
                    nested,
                )
                check_owner(
                    index,
                    joint,
                    "brake_holding_torque_nm",
                    responsibility,
                    "brake",
                    nested,
                )
        elif plugin == "thermal_duty_v1" and len(scoped) == 1:
            responsibility = scoped[0]
            role = "traction_motor" if responsibility.startswith("drive:") else "motor"
            for field in (
                "winding_resistance_ohm",
                "on_current_a",
                "thermal_resistance_k_per_w",
                "max_winding_temperature_k",
            ):
                check_owner(index, inputs, field, responsibility, role)
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
    for diagnostic in _analysis_rating_owner_diagnostics(data):
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
        analysis_record = _analysis_dict(result)
        analysis_record["analysis_id"] = str(analysis.get("id"))
        report.analyses.append(analysis_record)
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
