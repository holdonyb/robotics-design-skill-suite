#!/usr/bin/env python3
"""Run the portable reference simulation benchmark without hardware promotion.

Exit codes: 0 for a valid all-passing benchmark, 1 for a valid benchmark with a
failed or indeterminate scenario, and 2 for invalid/tampered input or execution
errors.  This script is intentionally a portable synthetic-replay check; it does
not launch ROS, Gazebo, controllers, or physical hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from assurance.engine import evaluate_contract
from assurance.hypothesis.canonical import canonical_bytes, canonical_value, validate_sha256
from assurance.simulation.admission import evaluate_simulation_admission
from assurance.simulation.backend import (
    compare_backends,
    evaluate_independent_dynamics,
    evaluate_trace_kinematics,
)
from assurance.simulation.calibration import fit_calibration, load_calibration_dataset
from assurance.simulation.artifacts import validate_ros_workspace_manifest
from assurance.simulation.model import TraceSample
from assurance.simulation.scenario import compile_scenarios, load_scenario_registry
from assurance.simulation.trace import publish_trace_bundle, replay_trace_bundle
from assurance.simulation.training import evaluate_policy, validate_training_contract


class BenchmarkError(ValueError):
    """The reference benchmark could not safely establish a portable result."""


_EXPECTED_BLOCKER = "BOM.PLACEHOLDER_BLOCKS_CLAIM"
_ROS_WORKSPACE_RECEIPT = "09a754c3253be4f799a8a7ea0bdea526db04c6741f81abdf5b765803b3bb3fb7"
_XACRO_NAMESPACE = "http://www.ros.org/wiki/xacro"
_PROFILE_SOURCES = (
    "ros2_ws/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro",
    "ros2_ws/src/jx_mobile_manipulator_sim/config/controllers.yaml",
    "ros2_ws/src/jx_mobile_manipulator_nav/config/nav2_params.yaml",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = canonical_value(data, path.name)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise BenchmarkError(f"cannot load {path.name}: {exc}") from None
    if not isinstance(data, dict):
        raise BenchmarkError(f"{path.name} must contain an object")
    return data


def _admission_from_reference(root: Path) -> dict[str, Any]:
    physical, errors = evaluate_contract(root / "design-contract.json")
    if errors or physical is None:
        raise BenchmarkError("physical assurance contract cannot be evaluated: " + "; ".join(errors))
    report = physical.to_dict()
    # The physical report has richer, schema-versioned analysis records than the
    # deliberately minimal admission receipt.  Retain only the fields admission
    # consumes and give duplicate plugin runs unique identity-bearing versions.
    normalized_analyses = []
    for index, analysis in enumerate(report["analyses"]):
        normalized_analyses.append(
            {
                "name": analysis["name"],
                "version": f"{analysis['version']}-{analysis['analysis_id']}",
                "passed": analysis["passed"],
                "outputs": analysis["outputs"],
                "analysis_id": analysis["analysis_id"],
                "evidence_level": analysis["evidence_level"],
                "inputs": analysis["inputs"],
                "validity_assumptions": analysis["validity_assumptions"],
            }
        )
    report["analyses"] = normalized_analyses
    blocker_codes = sorted(
        {
            item["code"]
            for item in report["diagnostics"]
            if item["severity"] in {"error", "indeterminate"}
        }
    )
    if blocker_codes != [_EXPECTED_BLOCKER] or report["promotable"] is not False:
        raise BenchmarkError("reference physical report is not placeholder-only blocked")
    # The v0.3 reference contract predates the canonical hypothesis candidate
    # namespace.  Preserve its contents but derive a v0.4-shaped candidate for
    # this simulation-only admission receipt; this does not rewrite the source.
    resolved = _load_json(root / "design-contract.json")
    content = {key: value for key, value in resolved.items() if key != "candidate_id"}
    candidate_id = "candidate-" + hashlib.sha256(canonical_bytes(content)).hexdigest()[:24]
    resolved["candidate_id"] = candidate_id
    report["candidate_id"] = candidate_id
    report["metadata"]["contract_sha256"] = hashlib.sha256(
        canonical_bytes(resolved)
    ).hexdigest()
    hypothesis = {
        "candidate_id": candidate_id,
        "resolved_contract_sha256": hashlib.sha256(canonical_bytes(content)).hexdigest(),
        "contract_passed": True,
        "physical_passed": False,
        "hard_counterexample": False,
        "complete": True,
        "blocking_diagnostics": blocker_codes,
    }
    return evaluate_simulation_admission(report, hypothesis, resolved).to_dict()


def _samples_for(scenario, *, failed: bool) -> tuple[TraceSample, TraceSample]:
    terminal = 0.1 if failed else 0.001
    width = len(scenario.joint_order)
    return (
        TraceSample(0, (0.0,) * width, {"mode": "start", "left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
        TraceSample(scenario.stop["at_ns"] // 2, (terminal / 2,) * width, {"mode": "running", "left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
        TraceSample(scenario.stop["at_ns"], (terminal,) * width, {"mode": "duration_elapsed", "left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
    )


def _profile_number(value: object, name: str) -> float:
    if not isinstance(value, str):
        raise BenchmarkError(f"{name} must be a numeric string")
    try:
        result = float(value)
    except ValueError:
        raise BenchmarkError(f"{name} must be a numeric string") from None
    if not math.isfinite(result) or result <= 0:
        raise BenchmarkError(f"{name} must be a positive finite number")
    return result


def _yaml_scalar(source: str, field: str) -> float:
    values = re.findall(rf"(?m)^\s*{re.escape(field)}:\s*([^\s#]+)\s*$", source)
    if len(values) != 1:
        raise BenchmarkError(f"profile YAML requires exactly one {field}")
    return _profile_number(values[0], f"profile YAML {field}")


def _yaml_vector(source: str, field: str) -> tuple[float, float, float]:
    values = re.findall(rf"(?m)^\s*{re.escape(field)}:\s*\[([^\]]+)\]\s*$", source)
    if len(values) != 1:
        raise BenchmarkError(f"profile YAML requires exactly one {field}")
    parts = [item.strip() for item in values[0].split(",")]
    if len(parts) != 3:
        raise BenchmarkError(f"profile YAML {field} must contain exactly three values")
    converted = []
    for index, item in enumerate(parts):
        try:
            value = float(item)
        except ValueError:
            raise BenchmarkError(f"profile YAML {field}[{index}] must be numeric") from None
        if not math.isfinite(value):
            raise BenchmarkError(f"profile YAML {field}[{index}] must be finite")
        converted.append(value)
    return tuple(converted)  # type: ignore[return-value]


def _load_backend_profile(root: Path) -> dict[str, Any]:
    """Extract a closed portable dynamics profile from receipt-bound ROS inputs."""
    manifest = root / "simulation" / "ros-workspace-manifest.json"
    errors = validate_ros_workspace_manifest(root, manifest, _ROS_WORKSPACE_RECEIPT)
    if errors:
        raise BenchmarkError("ROS workspace is not receipt-valid: " + "; ".join(errors))
    paths = {relative: root / relative for relative in _PROFILE_SOURCES}
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise BenchmarkError("ROS workspace profile source is missing or a symlink")
    try:
        xacro_bytes = paths[_PROFILE_SOURCES[0]].read_bytes()
        if b"<!" in xacro_bytes:
            raise BenchmarkError("xacro profile source must not contain declarations")
        xacro = ET.fromstring(xacro_bytes)
        controllers = paths[_PROFILE_SOURCES[1]].read_text(encoding="utf-8")
        nav2 = paths[_PROFILE_SOURCES[2]].read_text(encoding="utf-8")
    except (OSError, UnicodeError, ET.ParseError) as exc:
        raise BenchmarkError(f"cannot load ROS workspace profile source: {exc}") from None

    wheel_radii: dict[str, float] = {}
    wheel_y: dict[str, float] = {}
    total_mass = 0.0
    for node in xacro.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "cylinder_link" and node.get("name") in {"left_wheel_link", "right_wheel_link"}:
            name = node.get("name")
            assert name is not None
            if name in wheel_radii:
                raise BenchmarkError(f"xacro profile has duplicate {name}")
            wheel_radii[name] = _profile_number(node.get("radius"), f"xacro {name} radius")
        if tag in {"inertial", "cylinder_link"} and node.tag.startswith("{" + _XACRO_NAMESPACE + "}"):
            raw_mass = node.get("mass")
            if raw_mass is not None and "${" not in raw_mass:
                total_mass += _profile_number(raw_mass, f"xacro {tag} mass")
        if (
            tag == "joint"
            and node.get("name") in {"left_wheel_joint", "right_wheel_joint"}
            and node.find("parent") is not None
            and node.find("child") is not None
        ):
            origin = node.find("origin")
            if origin is None or origin.get("xyz") is None:
                raise BenchmarkError(f"xacro {node.get('name')} must declare origin xyz")
            parts = origin.get("xyz").split()
            if len(parts) != 3:
                raise BenchmarkError(f"xacro {node.get('name')} origin must have three values")
            try:
                y = float(parts[1])
            except ValueError:
                raise BenchmarkError(f"xacro {node.get('name')} origin y must be numeric") from None
            if not math.isfinite(y):
                raise BenchmarkError(f"xacro {node.get('name')} origin y must be finite")
            name = node.get("name")
            assert name is not None
            if name in wheel_y:
                raise BenchmarkError(f"xacro profile has duplicate {name}")
            wheel_y[name] = y
    if set(wheel_radii) != {"left_wheel_link", "right_wheel_link"} or set(wheel_y) != {"left_wheel_joint", "right_wheel_joint"}:
        raise BenchmarkError("xacro profile must declare exactly two drive wheels and joints")
    if wheel_radii["left_wheel_link"] != wheel_radii["right_wheel_link"]:
        raise BenchmarkError("xacro wheel radii must agree")
    if not math.isfinite(total_mass) or total_mass <= 0:
        raise BenchmarkError("xacro total simulator mass must be positive and finite")
    wheel_separation = abs(wheel_y["left_wheel_joint"] - wheel_y["right_wheel_joint"])
    if wheel_separation <= 0:
        raise BenchmarkError("xacro wheel separation must be positive")

    controller_radius = _yaml_scalar(controllers, "wheel_radius")
    controller_separation = _yaml_scalar(controllers, "wheel_separation")
    max_linear, _, _ = _yaml_vector(nav2, "max_velocity")
    max_decel, _, _ = _yaml_vector(nav2, "max_decel")
    if max_linear <= 0 or max_decel >= 0:
        raise BenchmarkError("Nav2 profile requires positive max velocity and negative max deceleration")
    radius = wheel_radii["left_wheel_link"]
    if controller_radius != radius or controller_separation != wheel_separation:
        raise BenchmarkError("controller and xacro wheel geometry disagree")
    return {
        "evidence_level": "parsed",
        "workspace_manifest_sha256": _ROS_WORKSPACE_RECEIPT,
        "sources": [
            {"path": relative, "sha256": hashlib.sha256(paths[relative].read_bytes()).hexdigest()}
            for relative in _PROFILE_SOURCES
        ],
        "wheel_radius_m": radius,
        "wheel_separation_m": wheel_separation,
        "wheel_speed_limit_rad_s": max_linear / radius,
        "mass_kg": total_mass,
        "brake_deceleration_m_s2": abs(max_decel),
    }


def _backend_input(replay: dict[str, Any], profile: dict[str, Any]) -> dict[str, object]:
    """Use receipt-validated replay samples as the backend-consumer input."""
    try:
        identity = {
            "scenario_id": replay["scenario_id"],
            "trace_sha256": replay["trace_sha256"],
            "model_sha256": replay["model_sha256"],
            "trajectory_sha256": replay["trajectory_sha256"],
        }
    except (KeyError, TypeError) as exc:
        raise BenchmarkError(f"replayed trace lacks required provenance: {exc}") from None
    if not isinstance(identity["scenario_id"], str) or not identity["scenario_id"]:
        raise BenchmarkError("replayed trace scenario provenance is invalid")
    try:
        for field in ("trace_sha256", "model_sha256", "trajectory_sha256"):
            validate_sha256(identity[field], f"replay.{field}")
    except ValueError as exc:
        raise BenchmarkError(f"replayed trace provenance is invalid: {exc}") from None
    samples = replay["samples"]
    try:
        timestamps = [item["timestamp_ns"] for item in samples]
        left = [item["state"]["left_wheel_rad_s"] for item in samples]
        right = [item["state"]["right_wheel_rad_s"] for item in samples]
    except (KeyError, TypeError) as exc:
        raise BenchmarkError(f"replayed trace lacks required wheel state: {exc}") from None
    for name, values in (("left_wheel_rad_s", left), ("right_wheel_rad_s", right)):
        if any(type(value) not in (int, float) or not math.isfinite(float(value)) for value in values):
            raise BenchmarkError(f"replayed trace wheel state {name} must contain finite numbers")
    return {
        "model_sha256": identity["model_sha256"],
        "trajectory_sha256": identity["trajectory_sha256"],
        "units": "si",
        "timestamps_ns": timestamps,
        "left_wheel_rad_s": left,
        "right_wheel_rad_s": right,
        "wheel_radius_m": profile["wheel_radius_m"],
        "wheel_separation_m": profile["wheel_separation_m"],
        "wheel_speed_limit_rad_s": profile["wheel_speed_limit_rad_s"],
        "mass_kg": profile["mass_kg"],
        "slope_rad": 0.0,
        "brake_deceleration_m_s2": profile["brake_deceleration_m_s2"],
        "joint_final_rad": replay["samples"][-1]["positions"],
        "joint_target_rad": [0.0] * len(replay["joint_order"]),
        "joint_error_limit_rad": 0.01,
    }


def _backend_result(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "metrics": [
            {
                "name": metric.name,
                "unit": metric.unit,
                "value": metric.value,
                "lower": metric.lower,
                "upper": metric.upper,
                "status": metric.status,
            }
            for metric in result.metrics
        ],
    }


def _crosscheck_record(replay: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    backend_trace = _backend_input(replay, profile)
    primary = evaluate_trace_kinematics(backend_trace)
    independent = evaluate_independent_dynamics(backend_trace)
    tolerances = {metric.name: 1e-9 for metric in primary.metrics}
    comparison = compare_backends(primary, independent, tolerances)
    return {
        "scenario_id": replay["scenario_id"],
        "trace_sha256": replay["trace_sha256"],
        "model_sha256": replay["model_sha256"],
        "trajectory_sha256": replay["trajectory_sha256"],
        "profile": profile,
        "primary": _backend_result(primary),
        "independent": _backend_result(independent),
        "comparison": _backend_result(comparison),
        "status": comparison.status,
    }


def _training_result(root: Path) -> dict[str, Any]:
    contract = _load_json(root / "simulation" / "training-contract.json")
    errors = validate_training_contract(contract)
    if errors:
        raise BenchmarkError("training contract is invalid: " + "; ".join(errors))
    result = evaluate_policy(
        contract,
        lambda _: {"linear_m_s": 0.2, "angular_rad_s": 0.0, "final_joint_error_rad": 0.0},
        {
            "remaining_blockers": list(contract["physical_blockers"]),
            "hardware_promotable": False,
        },
    ).to_dict()
    if result["evidence_level"] != "simulated" or result["status"] != "not_justified":
        raise BenchmarkError("training firewall did not retain simulated/not_justified evidence")
    if "hardware_promotable" in result:
        raise BenchmarkError("training result exposes an illegal hardware promotion field")
    return result


def run_reference_benchmark(
    reference_root: str | Path, *, force_failed_scenario: bool = False
) -> dict[str, Any]:
    """Run admission, all ten trace replays, backend check, calibration, and training."""

    root = Path(reference_root)
    if root.is_symlink() or not root.is_dir():
        raise BenchmarkError("reference root is missing, not a directory, or a symlink")
    admission = _admission_from_reference(root)
    if admission["status"] != "simulation_admitted" or admission["hardware_promotable"] is not False:
        raise BenchmarkError("reference candidate is not simulation-admitted with hardware disabled")

    registry = load_scenario_registry(root / "simulation" / "scenarios.json")
    scenarios = compile_scenarios(registry)
    if len(scenarios) != 10:
        raise BenchmarkError("reference registry must compile exactly ten scenarios")
    replayed: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="robotics-design-reference-") as raw:
        temporary = Path(raw)
        for index, scenario in enumerate(scenarios):
            receipt = publish_trace_bundle(
                temporary / scenario.scenario_id,
                scenario,
                _samples_for(scenario, failed=force_failed_scenario and index == 0),
            )
            replayed.append(
                replay_trace_bundle(
                    temporary / scenario.scenario_id, receipt.manifest_sha256
                ).to_dict()
            )
    passed = sum(item["status"] == "passed" for item in replayed)
    failed = len(replayed) - passed

    profile = _load_backend_profile(root)
    crosschecks = [_crosscheck_record(replay, profile) for replay in replayed]
    crosschecks.sort(key=lambda item: item["scenario_id"])
    comparison = "passed" if all(item["status"] == "passed" for item in crosschecks) else "failed"
    calibration = fit_calibration(
        load_calibration_dataset(root / "simulation" / "calibration-synthetic.json")
    )
    training = _training_result(root)
    return {
        "schema_version": 1,
        "kind": "portable_reference_simulation",
        "admission": admission,
        "scenario_count": len(replayed),
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "replays": replayed,
        "backend_crosschecks": crosschecks,
        "independent_backend": {
            "status": comparison,
            "evidence_level": "calculated",
            "crosscheck_count": len(crosschecks),
        },
        "calibration": {
            "evidence_level": calibration.evidence_level,
            "pipeline_test_only": calibration.pipeline_test_only,
            "evaluation_rmse": calibration.evaluation_rmse,
        },
        "training": training,
        "hardware_promotable": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--force-failed-scenario", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_reference_benchmark(
            args.reference_root, force_failed_scenario=args.force_failed_scenario
        )
        print(canonical_bytes(report).decode("utf-8"), end="")
    except (BenchmarkError, OSError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        print(f"ERROR: simulation validation failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if report["failed_scenarios"] or report["independent_backend"]["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
