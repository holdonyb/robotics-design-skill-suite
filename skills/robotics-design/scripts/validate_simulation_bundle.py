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
import sys
import tempfile
from pathlib import Path
from typing import Any

from assurance.engine import evaluate_contract
from assurance.hypothesis.canonical import canonical_bytes, canonical_value
from assurance.simulation.admission import evaluate_simulation_admission
from assurance.simulation.backend import (
    compare_backends,
    evaluate_independent_dynamics,
    evaluate_trace_kinematics,
)
from assurance.simulation.calibration import fit_calibration, load_calibration_dataset
from assurance.simulation.model import TraceSample
from assurance.simulation.scenario import compile_scenarios, load_scenario_registry
from assurance.simulation.trace import publish_trace_bundle, replay_trace_bundle
from assurance.simulation.training import evaluate_policy, validate_training_contract


class BenchmarkError(ValueError):
    """The reference benchmark could not safely establish a portable result."""


_EXPECTED_BLOCKER = "BOM.PLACEHOLDER_BLOCKS_CLAIM"


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
        TraceSample(0, (0.0,) * width, {"mode": "start"}),
        TraceSample(scenario.stop["at_ns"], (terminal,) * width, {"mode": "duration_elapsed"}),
    )


def _backend_input(scenario) -> dict[str, object]:
    return {
        "model_sha256": scenario.model_sha256,
        "trajectory_sha256": scenario.trajectory_sha256,
        "units": "si",
        "timestamps_ns": [0, 1_000_000_000, 2_000_000_000],
        "left_wheel_rad_s": [1.0, 1.0, 1.0],
        "right_wheel_rad_s": [1.0, 1.0, 1.0],
        "wheel_radius_m": 0.1,
        "wheel_separation_m": 0.5,
        "wheel_speed_limit_rad_s": 2.0,
        "mass_kg": 100.0,
        "slope_rad": 0.0,
        "brake_deceleration_m_s2": 1.0,
        "joint_final_rad": [0.0] * len(scenario.joint_order),
        "joint_target_rad": [0.0] * len(scenario.joint_order),
        "joint_error_limit_rad": 0.01,
    }


def _training_result(root: Path) -> dict[str, Any]:
    contract = _load_json(root / "simulation" / "training-contract.json")
    errors = validate_training_contract(contract)
    if errors:
        raise BenchmarkError("training contract is invalid: " + "; ".join(errors))
    result = evaluate_policy(
        contract,
        lambda _: {"linear_m_s": 0.2, "angular_rad_s": 0.0, "mean_reward": 1.0},
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

    primary = evaluate_trace_kinematics(_backend_input(scenarios[0]))
    independent = evaluate_independent_dynamics(_backend_input(scenarios[0]))
    tolerances = {metric.name: 1e-9 for metric in primary.metrics}
    comparison = compare_backends(primary, independent, tolerances).status
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
        "independent_backend": {"status": comparison, "evidence_level": "calculated"},
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
