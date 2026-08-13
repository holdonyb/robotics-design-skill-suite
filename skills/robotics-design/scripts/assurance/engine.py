"""Deterministic orchestration for physical-plausibility contract evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .analyses import AnalysisResult, run_plugin
from .artifacts import compare_observations, observe_declared_json, observe_urdf
from .contract import ROLE_LIMIT_DIMENSIONS, load_contract
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
            "differential_drive" not in declared_features
            or len(scoped_drives) != 1
            or bool(scoped_actuators)
        ):
            undeclared_message = (
                "drivetrain_v1 requires differential_drive architecture, exactly one drive responsibility, and no actuator scope"
            )
        elif plugin == "stability_v1" and (
            "differential_drive" not in declared_features
            or not scoped_drives
            or bool(scoped_actuators)
        ):
            undeclared_message = (
                f"{plugin} requires differential_drive architecture, explicit drive coverage, and no actuator scope"
            )
        elif plugin == "battery_v1" and (
            "battery_powered" not in declared_features
            or bool(scoped_drives)
            or bool(scoped_actuators)
        ):
            undeclared_message = (
                "battery_v1 requires battery_powered architecture and no drive or actuator scope"
            )
        elif plugin == "arm_gravity_v1" and (
            not declared_actuators or not scoped_actuators or bool(scoped_drives)
        ):
            undeclared_message = (
                "arm_gravity_v1 requires declared actuators, explicit actuator coverage, and no drive scope"
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

    def component_for(responsibility: str, role: str) -> dict[str, Any] | None:
        matches = [
            item
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
        limit_name: str,
        nested_path: str = "",
    ) -> None:
        reference = inputs.get(field)
        if not isinstance(reference, str) or not reference.startswith("quantity:"):
            return
        quantity = quantities.get(reference[9:])
        component = component_for(responsibility, role)
        component_id = component.get("id") if component is not None else None
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
            return
        if component is not None and component.get("state") in {
            "verified_part",
            "qualified_substitute",
        }:
            limits = component.get("limits", {})
            if not isinstance(limits, dict) or limits.get(limit_name) != reference:
                field_path = f"analyses[{analysis_index}].inputs{nested_path}.{field}"
                diagnostics.append(
                    Diagnostic(
                        "PHY.ANALYSIS.RATING_LIMIT",
                        "indeterminate",
                        field_path,
                        f"{field} must equal the {limit_name} limit of component:{component_id}",
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
        scoped_drives = {
            value[6:]
            for value in covers
            if isinstance(value, str) and value.startswith("drive:")
        }
        scoped_actuators = {
            value[9:]
            for value in covers
            if isinstance(value, str) and value.startswith("actuator:")
        }
        scoped = [
            *(f"drive:{value}" for value in sorted(scoped_drives)),
            *(f"actuator:{value}" for value in sorted(scoped_actuators)),
        ]
        if plugin == "drivetrain_v1" and len(scoped_drives) == 1:
            responsibility = f"drive:{next(iter(scoped_drives))}"
            for field, limit_name in (
                ("motor_continuous_torque_nm", "continuous_torque"),
                ("motor_peak_torque_nm", "peak_torque"),
                ("motor_max_speed_rad_s", "max_speed"),
            ):
                check_owner(index, inputs, field, responsibility, "traction_motor", limit_name)
            for field in ("gear_ratio", "efficiency"):
                check_owner(index, inputs, field, responsibility, "reducer", field)
            check_owner(index, inputs, "wheel_radius_m", responsibility, "wheel", "radius")
        elif plugin == "battery_v1":
            responsibility = "feature:battery_powered"
            for field, limit_name in (
                ("voltage_v", "nominal_voltage"),
                ("max_continuous_current_a", "continuous_current"),
                ("max_peak_current_a", "peak_current"),
                ("usable_energy_j", "usable_energy"),
            ):
                check_owner(index, inputs, field, responsibility, "battery", limit_name)
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
                    "continuous_torque",
                    nested,
                )
                check_owner(
                    index,
                    joint,
                    "brake_holding_torque_nm",
                    responsibility,
                    "brake",
                    "holding_torque",
                    nested,
                )
        elif plugin == "thermal_duty_v1" and len(scoped) == 1:
            responsibility = scoped[0]
            role = "traction_motor" if responsibility.startswith("drive:") else "motor"
            for field, limit_name in (
                ("winding_resistance_ohm", "winding_resistance"),
                ("on_current_a", "continuous_current"),
                ("thermal_resistance_k_per_w", "thermal_resistance"),
                ("max_winding_temperature_k", "max_winding_temperature"),
            ):
                check_owner(index, inputs, field, responsibility, role, limit_name)
    return diagnostics


def _component_catalog_diagnostics(
    snapshot: dict[str, Any],
    evidence: dict[str, Any],
    components: list[dict[str, Any]],
    quantities: dict[str, dict[str, Any]],
    evidence_index: int,
) -> list[Diagnostic]:
    """Validate a bounded, hash-bound component catalog snapshot."""

    diagnostics: list[Diagnostic] = []
    base = f"evidence[{evidence_index}].source"

    def reject(path: str, message: str) -> None:
        diagnostics.append(
            Diagnostic("EVIDENCE.COMPONENT_CATALOG", "indeterminate", path, message)
        )

    allowed_root = {"schema_version", "locator", "observed_date", "components"}
    unknown_root = sorted(set(snapshot) - allowed_root)
    if unknown_root:
        reject(base, "component catalog has unknown fields: " + ", ".join(unknown_root))
    if snapshot.get("schema_version") != 1 or isinstance(
        snapshot.get("schema_version"), bool
    ):
        reject(f"{base}.schema_version", "component catalog schema_version must be 1")
    if snapshot.get("locator") != evidence.get("locator"):
        reject(f"{base}.locator", "component catalog locator must match evidence locator")
    if snapshot.get("observed_date") != evidence.get("observed_date"):
        reject(
            f"{base}.observed_date",
            "component catalog observed_date must match evidence observed_date",
        )

    records = snapshot.get("components")
    if not isinstance(records, list):
        reject(f"{base}.components", "component catalog components must be a list")
        return diagnostics
    by_id: dict[str, dict[str, Any]] = {}
    components_by_id = {
        str(component.get("id")): component
        for component in components
        if component.get("source_evidence") == f"evidence:{evidence.get('id')}"
    }
    for record_index, record in enumerate(records):
        record_path = f"{base}.components[{record_index}]"
        if not isinstance(record, dict):
            reject(record_path, "component catalog record must be an object")
            continue
        unknown = sorted(
            set(record) - {"id", "manufacturer", "part_number", "limits"}
        )
        if unknown:
            reject(record_path, "component catalog record has unknown fields: " + ", ".join(unknown))
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            reject(f"{record_path}.id", "component catalog record id must be non-empty")
            continue
        if record_id in by_id:
            reject(f"{record_path}.id", f"duplicate component catalog id: {record_id}")
            continue
        by_id[record_id] = record
        component = components_by_id.get(record_id)
        if component is None:
            reject(record_path, "catalog record does not map to a supported verified component")
            continue
        snapshot_limits = record.get("limits")
        if not isinstance(snapshot_limits, dict):
            reject(f"{record_path}.limits", "catalog limits must be an object")
            continue
        role = component.get("role")
        allowed_limits = ROLE_LIMIT_DIMENSIONS.get(str(role), {})
        unknown_limits = sorted(set(snapshot_limits) - set(allowed_limits))
        if unknown_limits:
            reject(
                f"{record_path}.limits",
                f"catalog limits has unsupported fields for role {role}: "
                + ", ".join(unknown_limits),
            )
        for limit_name, typed_value in sorted(snapshot_limits.items()):
            value_path = f"{record_path}.limits.{limit_name}"
            if not isinstance(typed_value, dict):
                reject(value_path, "catalog limit must be a typed value/unit object")
                continue
            unknown_typed = sorted(set(typed_value) - {"value", "unit"})
            missing_typed = sorted({"value", "unit"} - set(typed_value))
            if unknown_typed:
                reject(
                    value_path,
                    "catalog typed limit has unknown fields: " + ", ".join(unknown_typed),
                )
            if missing_typed:
                reject(
                    value_path,
                    "catalog typed limit is missing fields: " + ", ".join(missing_typed),
                )
            expected_dimension = allowed_limits.get(limit_name)
            if expected_dimension is not None:
                try:
                    to_si(typed_value, expected_dimension, value_path)
                except QuantityError as exc:
                    reject(value_path, str(exc))

    evidence_ref = f"evidence:{evidence.get('id')}"
    for component in components:
        if component.get("source_evidence") != evidence_ref:
            continue
        component_id = str(component.get("id"))
        record = by_id.get(component_id)
        component_path = f"{base}.components.{component_id}"
        if record is None:
            reject(component_path, "verified component is missing from catalog snapshot")
            continue
        for field in ("manufacturer", "part_number"):
            if record.get(field) != component.get(field):
                reject(
                    f"{component_path}.{field}",
                    f"catalog {field} must match component:{component_id}",
                )
        snapshot_limits = record.get("limits")
        if not isinstance(snapshot_limits, dict):
            reject(f"{component_path}.limits", "catalog limits must be an object")
            continue
        declared_limits = component.get("limits", {})
        if not isinstance(declared_limits, dict):
            continue
        for limit_name, reference in sorted(declared_limits.items()):
            limit_path = f"{component_path}.limits.{limit_name}"
            if limit_name not in snapshot_limits:
                reject(limit_path, "declared component limit is missing from catalog snapshot")
                continue
            if not isinstance(reference, str) or not reference.startswith("quantity:"):
                continue
            quantity = quantities.get(reference[9:])
            if quantity is None:
                continue
            try:
                declared_value = to_si(
                    quantity.get("value"),
                    str(quantity.get("dimension")),
                    f"{reference}.value",
                )
                snapshot_value = to_si(
                    snapshot_limits[limit_name],
                    str(quantity.get("dimension")),
                    limit_path,
                )
            except QuantityError as exc:
                reject(limit_path, str(exc))
                continue
            tolerance = max(1e-12, abs(declared_value) * 1e-12)
            if abs(snapshot_value - declared_value) > tolerance:
                reject(
                    limit_path,
                    f"catalog limit differs from {reference} by {abs(snapshot_value - declared_value):.12g} SI",
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

    quantities = {
        item["id"]: item
        for item in data.get("quantities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    components = [
        item for item in data.get("components", []) if isinstance(item, dict)
    ]
    evidence_records = data.get("evidence", [])
    valid_evidence = 0
    for index, evidence in enumerate(evidence_records):
        evidence_path, valid = _resolve_file(
            contract_dir,
            evidence.get("source", {}),
            f"evidence[{index}].source",
            report,
        )
        semantic_valid = valid
        if valid and evidence_path is not None and evidence.get("kind") == "component_catalog_v1":
            snapshot, catalog_parse_diagnostics = observe_declared_json(evidence_path)
            for diagnostic in catalog_parse_diagnostics:
                report.add(diagnostic)
            if snapshot is None:
                semantic_valid = False
            else:
                catalog_diagnostics = _component_catalog_diagnostics(
                    snapshot, evidence, components, quantities, index
                )
                for diagnostic in catalog_diagnostics:
                    report.add(diagnostic)
                if catalog_diagnostics:
                    semantic_valid = False
        if semantic_valid:
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
