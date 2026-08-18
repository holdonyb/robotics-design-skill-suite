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
from assurance.simulation.model import SimulationResult, TraceSample
from assurance.simulation.scenario import CompiledScenario, compile_scenarios, load_scenario_registry
from assurance.simulation.trace import publish_trace_bundle, replay_trace_bundle
from assurance.simulation.training import evaluate_policy, validate_training_contract
from assurance.simulation.replay_features import ReplayFeatureError, extract_replay_features


class BenchmarkError(ValueError):
    """The reference benchmark could not safely establish a portable result."""


_EXPECTED_BLOCKER = "BOM.PLACEHOLDER_BLOCKS_CLAIM"
_ROS_WORKSPACE_RECEIPT = "fe325213ea6081a8bb35a5c7651b7183678bb62d8a2baf26cf267a896aba4db1"
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


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _profile_source_snapshot(root: Path) -> dict[str, bytes]:
    manifest_path = root / "simulation" / "ros-workspace-manifest.json"
    errors = validate_ros_workspace_manifest(root, manifest_path, _ROS_WORKSPACE_RECEIPT)
    if errors:
        raise BenchmarkError("ROS workspace is not receipt-valid: " + "; ".join(errors))
    try:
        manifest_bytes = manifest_path.read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != _ROS_WORKSPACE_RECEIPT:
            raise BenchmarkError("ROS workspace manifest changed after validation")
        manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise BenchmarkError(f"cannot snapshot ROS workspace manifest: {exc}") from None
    outputs = manifest.get("outputs") if isinstance(manifest, dict) else None
    if not isinstance(outputs, list):
        raise BenchmarkError("ROS workspace manifest outputs are invalid")
    hashes: dict[str, str] = {}
    for item in outputs:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise BenchmarkError("ROS workspace manifest output entry is invalid")
        path, sha256 = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or path in hashes:
            raise BenchmarkError("ROS workspace manifest output path is invalid")
        try:
            validate_sha256(sha256, f"ROS workspace output {path}")
        except ValueError as exc:
            raise BenchmarkError(str(exc)) from None
        hashes[path] = sha256
    snapshot: dict[str, bytes] = {}
    for relative in _PROFILE_SOURCES:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise BenchmarkError("ROS workspace profile source is missing or a symlink")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise BenchmarkError(f"cannot read ROS workspace profile source: {exc}") from None
        if hashes.get(relative) != hashlib.sha256(payload).hexdigest():
            raise BenchmarkError(f"profile source SHA-256 mismatch: {relative}")
        snapshot[relative] = payload
    return snapshot


def _load_backend_profile(root: Path) -> dict[str, Any]:
    """Extract a closed portable dynamics profile from receipt-bound ROS inputs."""
    sources = _profile_source_snapshot(root)
    xacro_bytes = sources[_PROFILE_SOURCES[0]]
    if b"<!" in xacro_bytes:
        raise BenchmarkError("xacro profile source must not contain declarations")
    try:
        xacro = ET.fromstring(xacro_bytes)
        controllers = sources[_PROFILE_SOURCES[1]].decode("utf-8")
        nav2 = sources[_PROFILE_SOURCES[2]].decode("utf-8")
    except (UnicodeError, ET.ParseError) as exc:
        raise BenchmarkError(f"cannot load ROS workspace profile source: {exc}") from None
    if xacro.tag != "robot":
        raise BenchmarkError("xacro profile source must have robot root")

    xacro_inertial = "{" + "http://www.ros.org/wiki/xacro" + "}inertial"
    xacro_cylinder_link = "{" + "http://www.ros.org/wiki/xacro" + "}cylinder_link"
    links: set[str] = set()
    cylinders: set[str] = set()
    total_mass = 0.0
    wheel_radii: dict[str, float] = {}
    wheel_y: dict[str, float] = {}
    for node in xacro:
        if node.tag == "link":
            name = node.get("name")
            if not isinstance(name, str) or not name or name in links:
                raise BenchmarkError("xacro top-level link inventory is invalid")
            links.add(name)
            inertial = node.find(xacro_inertial)
            if inertial is not None:
                total_mass += _profile_number(inertial.get("mass"), f"xacro {name} mass")
        elif node.tag == xacro_cylinder_link:
            name = node.get("name")
            if not isinstance(name, str) or not name or name in cylinders:
                raise BenchmarkError("xacro top-level cylinder-link inventory is invalid")
            cylinders.add(name)
            total_mass += _profile_number(node.get("mass"), f"xacro {name} mass")
            if name in {"left_wheel_link", "right_wheel_link"}:
                wheel_radii[name] = _profile_number(node.get("radius"), f"xacro {name} radius")
        elif node.tag == "joint" and node.get("name") in {"left_wheel_joint", "right_wheel_joint"}:
            name = node.get("name")
            assert name is not None
            if name in wheel_y:
                raise BenchmarkError(f"xacro profile has duplicate {name}")
            if node.get("type") != "continuous":
                raise BenchmarkError(f"xacro {name} must be a continuous wheel joint")
            parent, child = node.find("parent"), node.find("child")
            if parent is None or parent.get("link") != "base_link":
                raise BenchmarkError(f"xacro {name} must have parent link base_link")
            expected_child = "left_wheel_link" if name == "left_wheel_joint" else "right_wheel_link"
            if child is None or child.get("link") != expected_child:
                raise BenchmarkError(f"xacro {name} must have child link {expected_child}")
            origin = node.find("origin")
            if origin is None or origin.get("xyz") is None:
                raise BenchmarkError(f"xacro {name} must declare origin xyz")
            parts = origin.get("xyz").split()
            if len(parts) != 3:
                raise BenchmarkError(f"xacro {name} origin must have three values")
            try:
                y = float(parts[1])
            except ValueError:
                raise BenchmarkError(f"xacro {name} origin y must be numeric") from None
            if not math.isfinite(y):
                raise BenchmarkError(f"xacro {name} origin y must be finite")
            wheel_y[name] = y
    if set(wheel_radii) != {"left_wheel_link", "right_wheel_link"}:
        raise BenchmarkError("xacro profile must declare exactly two top-level drive wheels")
    if wheel_radii["left_wheel_link"] != wheel_radii["right_wheel_link"]:
        raise BenchmarkError("xacro wheel radii must agree")
    if not math.isfinite(total_mass) or total_mass <= 0:
        raise BenchmarkError("xacro total simulator mass must be positive and finite")
    if set(wheel_y) != {"left_wheel_joint", "right_wheel_joint"}:
        raise BenchmarkError("xacro profile must declare exactly two top-level drive wheel joints")
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
            {"path": relative, "sha256": hashlib.sha256(sources[relative]).hexdigest()}
            for relative in _PROFILE_SOURCES
        ],
        "wheel_radius_m": radius,
        "wheel_separation_m": wheel_separation,
        "wheel_speed_limit_rad_s": max_linear / radius,
        "mass_kg": total_mass,
        "brake_deceleration_m_s2": abs(max_decel),
    }


def _backend_input(replay: SimulationResult, profile: dict[str, Any]) -> dict[str, object]:
    """Use receipt-validated replay samples as the backend-consumer input."""
    try:
        features = extract_replay_features(replay, require_passed=False)
    except ReplayFeatureError as exc:
        raise BenchmarkError("receipt-validated replay cannot produce backend input: " + str(exc)) from None
    return {
        "model_sha256": features.model_sha256,
        "trajectory_sha256": features.trajectory_sha256,
        "units": "si",
        "timestamps_ns": list(features.timestamps_ns),
        "left_wheel_rad_s": list(features.left_wheel_rad_s),
        "right_wheel_rad_s": list(features.right_wheel_rad_s),
        "wheel_radius_m": profile["wheel_radius_m"],
        "wheel_separation_m": profile["wheel_separation_m"],
        "wheel_speed_limit_rad_s": profile["wheel_speed_limit_rad_s"],
        "mass_kg": profile["mass_kg"],
        "slope_rad": 0.0,
        "brake_deceleration_m_s2": profile["brake_deceleration_m_s2"],
        "joint_final_rad": list(features.positions[-1]),
        "joint_target_rad": [0.0] * len(features.joint_order),
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


def _crosscheck_record(replay: SimulationResult, profile: dict[str, Any]) -> dict[str, Any]:
    backend_trace = _backend_input(replay, profile)
    primary = evaluate_trace_kinematics(backend_trace)
    independent = evaluate_independent_dynamics(backend_trace)
    tolerances = {metric.name: 1e-9 for metric in primary.metrics}
    comparison = compare_backends(primary, independent, tolerances)
    return {
        "scenario_id": replay.scenario_id,
        "trace_sha256": replay.trace_sha256,
        "model_sha256": replay.model_sha256,
        "trajectory_sha256": replay.trajectory_sha256,
        "profile": profile,
        "primary": _backend_result(primary),
        "independent": _backend_result(independent),
        "comparison": _backend_result(comparison),
        "status": comparison.status,
    }


def _training_result(root: Path, replayed: list[tuple[CompiledScenario, SimulationResult]]) -> dict[str, Any]:
    contract = _load_json(root / "simulation" / "training-contract.json")
    errors = validate_training_contract(contract)
    if errors:
        raise BenchmarkError("training contract is invalid: " + "; ".join(errors))
    expected_cases = [
        ("train", seed, None) for seed in contract["train_seeds"]
    ] + [
        ("evaluation", seed, None) for seed in contract["evaluation_seeds"]
    ] + [
        ("held_out", seed, fault)
        for fault in contract["held_out_faults"]
        for seed in contract["evaluation_seeds"]
    ]
    assignments = []
    for phase, seed, fault_id in expected_cases:
        expected_faults = () if fault_id is None else (fault_id,)
        matches = [
            (scenario, replay)
            for scenario, replay in replayed
            if scenario.seed == seed
            and tuple(item["fault_id"] for item in scenario.faults) == expected_faults
        ]
        if len(matches) != 1:
            raise BenchmarkError("training trace assignment requires exactly one matching scenario case")
        scenario, replay = matches[0]
        if replay.status != "passed":
            return {
                "status": "not_justified",
                "evidence_level": "simulated",
                "physical_blockers": list(contract["physical_blockers"]),
                "mean_reward": None,
                "evaluation_count": 0,
                "held_out_evaluation_count": 0,
                "trace_sha256s": [],
                "reason": "not_evaluated",
            }
        assignments.append(
            {"phase": phase, "seed": seed, "fault_id": fault_id, "scenario": scenario, "replay": replay}
        )
    result = evaluate_policy(
        contract,
        lambda _: {"linear_m_s": 0.2, "angular_rad_s": 0.0},
        {
            "remaining_blockers": list(contract["physical_blockers"]),
            "hardware_promotable": False,
        },
        assignments,
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
    replayed: list[tuple[CompiledScenario, SimulationResult]] = []
    with tempfile.TemporaryDirectory(prefix="robotics-design-reference-") as raw:
        temporary = Path(raw)
        for index, scenario in enumerate(scenarios):
            receipt = publish_trace_bundle(
                temporary / scenario.scenario_id,
                scenario,
                _samples_for(scenario, failed=force_failed_scenario and index == 0),
            )
            replayed.append((
                scenario,
                replay_trace_bundle(temporary / scenario.scenario_id, receipt.manifest_sha256),
            ))
    replayed.sort(key=lambda item: item[0].scenario_id)
    replay_dicts = [item.to_dict() for _, item in replayed]
    passed = sum(item.status == "passed" for _, item in replayed)
    failed = len(replayed) - passed

    profile = _load_backend_profile(root)
    crosschecks = [_crosscheck_record(replay, profile) for _, replay in replayed]
    crosschecks.sort(key=lambda item: item["scenario_id"])
    comparison = "passed" if all(item["status"] == "passed" for item in crosschecks) else "failed"
    calibration = fit_calibration(
        load_calibration_dataset(root / "simulation" / "calibration-synthetic.json")
    )
    training = _training_result(root, replayed)
    return {
        "schema_version": 1,
        "kind": "portable_reference_simulation",
        "admission": admission,
        "scenario_count": len(replayed),
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "replays": replay_dicts,
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
