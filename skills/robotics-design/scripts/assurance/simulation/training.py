"""Bounded policy callback adapter with an absolute simulation promotion firewall.

This module deliberately does not train, deploy, or authorize a robot.  It turns a
single bounded policy observation into a reproducible *simulated* record after
checking the declared contract and a physical-blocker receipt.
"""

from __future__ import annotations

import copy
import hashlib
import math
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..hypothesis.canonical import (
    canonical_bytes,
    canonical_value,
    validate_identifier,
    validate_sha256,
)
from .replay_features import ReplayFeatureError, ReplayFeatures, extract_replay_features
from .scenario import CompiledScenario
from .trace import TraceError, replay_trace_bundle
from .policy_trace import (
    PolicyTraceError,
    TrustedPolicyTraceContext,
    replay_policy_trace_bundle,
    run_reference_policy_trace,
)
from .trusted_registry import TrustedRegistryError, load_reference_trusted_scenario_registry


class TrainingError(ValueError):
    """A training-boundary input or callback violated its closed contract."""


_FIELDS = {
    "schema_version",
    "contract_id",
    "artifact_sha256",
    "observation",
    "action",
    "reward_weights",
    "baseline_mean_reward",
    "hard_constraints",
    "budgets",
    "train_seeds",
    "evaluation_seeds",
    "randomization",
    "held_out_faults",
    "physical_blockers",
}
_IO_FIELDS = {"frame", "unit", "rate_hz", "fields"}
_BUDGET_FIELDS = {"episodes", "steps", "wall_time_s", "memory_mb"}
_CONSTRAINT_FIELDS = {
    "max_linear_m_s",
    "max_angular_rad_s",
    "max_joint_error_rad",
}
_REWARD_FIELDS = {"wheel_progress", "wheel_effort"}
_OBSERVATION_FIELDS = ["joint_rad", "left_wheel_rad_s", "right_wheel_rad_s"]
_ACTION_FIELDS = ["linear_m_s", "angular_rad_s"]
_MAX_COLLECTION_ITEMS = 64
_ASSIGNMENT_FIELDS = {"phase", "seed", "fault_id", "scenario", "bundle_root", "manifest_sha256"}


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise TrainingError(f"{name} must be finite")
    return float(value)


def _closed_identifier_list(value: object, name: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > _MAX_COLLECTION_ITEMS
        or len(set(value)) != len(value)
    ):
        raise TrainingError(f"{name} must be a non-empty unique bounded list")
    for index, item in enumerate(value):
        validate_identifier(item, f"{name}[{index}]")


def _validate_io(value: object, name: str, expected_fields: list[str]) -> None:
    if not isinstance(value, dict) or set(value) != _IO_FIELDS:
        raise TrainingError(f"{name} schema is invalid")
    if value["frame"] != "base_link" or value["unit"] != "si":
        raise TrainingError(f"{name} frame or unit is invalid")
    if type(value["rate_hz"]) is not int or not 1 <= value["rate_hz"] <= 1000:
        raise TrainingError(f"{name} rate_hz is invalid")
    if value["fields"] != expected_fields:
        raise TrainingError(f"{name} fields are invalid")


def _validate_contract_or_raise(value: object) -> dict[str, Any]:
    data = canonical_value(value, "training contract")
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise TrainingError("training contract has unknown or missing fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise TrainingError("schema_version must be integer 1")
    validate_identifier(data["contract_id"], "contract_id")
    validate_sha256(data["artifact_sha256"], "artifact_sha256")

    _validate_io(data["observation"], "observation", _OBSERVATION_FIELDS)
    _validate_io(data["action"], "action", _ACTION_FIELDS)

    reward_weights = data["reward_weights"]
    if not isinstance(reward_weights, dict) or set(reward_weights) != _REWARD_FIELDS:
        raise TrainingError("reward_weights schema is invalid")
    for name, raw in reward_weights.items():
        if not -10_000 <= _finite(raw, f"reward_weights.{name}") <= 10_000:
            raise TrainingError(f"reward_weights.{name} is outside the safe range")
    _finite(data["baseline_mean_reward"], "baseline_mean_reward")

    constraints = data["hard_constraints"]
    if not isinstance(constraints, dict) or set(constraints) != _CONSTRAINT_FIELDS:
        raise TrainingError("hard_constraints schema is invalid")
    for name, raw in constraints.items():
        if not 0 < _finite(raw, f"hard_constraints.{name}") <= 1_000:
            raise TrainingError(f"hard_constraints.{name} is outside the safe range")

    budgets = data["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != _BUDGET_FIELDS:
        raise TrainingError("budgets schema is invalid")
    limits = {
        "episodes": 10_000,
        "steps": 1_000_000,
        "wall_time_s": 86_400,
        "memory_mb": 16_384,
    }
    for name, maximum in limits.items():
        raw = budgets[name]
        if type(raw) is not int or not 0 < raw <= maximum:
            raise TrainingError(f"budgets.{name} is invalid")

    for name in ("train_seeds", "evaluation_seeds"):
        seeds = data[name]
        if (
            not isinstance(seeds, list)
            or not seeds
            or len(seeds) > _MAX_COLLECTION_ITEMS
            or any(type(seed) is not int for seed in seeds)
            or len(set(seeds)) != len(seeds)
        ):
            raise TrainingError(f"{name} are invalid")
    if set(data["train_seeds"]) & set(data["evaluation_seeds"]):
        raise TrainingError("train and evaluation seeds must be distinct")

    randomization = data["randomization"]
    if (
        not isinstance(randomization, dict)
        or set(randomization) != {"owner", "friction"}
        or randomization["owner"] != "uncertainty_v1"
        or not isinstance(randomization["friction"], dict)
        or set(randomization["friction"]) != {"lower", "upper"}
    ):
        raise TrainingError("randomization owner or schema is invalid")
    lower = _finite(randomization["friction"]["lower"], "randomization lower")
    upper = _finite(randomization["friction"]["upper"], "randomization upper")
    if not 0 < lower <= upper <= 1:
        raise TrainingError("randomization range is invalid")

    _closed_identifier_list(data["held_out_faults"], "held_out_faults")
    _closed_identifier_list(data["physical_blockers"], "physical_blockers")
    return data


def validate_training_contract(value: object) -> list[str]:
    """Return deterministic, actionable validation errors without raising."""

    try:
        _validate_contract_or_raise(value)
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        return [str(exc)]
    return []


def _validated_physical_receipt(
    value: object, contract: dict[str, Any]
) -> tuple[str, ...]:
    receipt = canonical_value(value, "physical report")
    if not isinstance(receipt, dict) or set(receipt) != {
        "remaining_blockers",
        "hardware_promotable",
    }:
        raise TrainingError("physical report fields are invalid")
    if receipt["hardware_promotable"] is not False:
        raise TrainingError("physical report hardware promotion is forbidden")
    blockers = receipt["remaining_blockers"]
    _closed_identifier_list(blockers, "physical report blockers")
    if blockers != contract["physical_blockers"]:
        raise TrainingError("physical report blockers do not match contract")
    return tuple(blockers)


@dataclass(frozen=True)
class PolicyResult:
    """A portable policy observation.  It intentionally has no hardware field."""

    policy_id: str
    status: str
    evidence_level: str
    physical_blockers: tuple[str, ...]
    mean_reward: float
    evaluation_count: int
    held_out_evaluation_count: int
    trace_sha256s: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "status": self.status,
            "evidence_level": self.evidence_level,
            "physical_blockers": list(self.physical_blockers),
            "mean_reward": self.mean_reward,
            "evaluation_count": self.evaluation_count,
            "held_out_evaluation_count": self.held_out_evaluation_count,
            "trace_sha256s": list(self.trace_sha256s),
        }


def _expected_cases(contract: dict[str, Any]) -> list[tuple[str, int, str | None]]:
    return [
        ("train", seed, None) for seed in contract["train_seeds"]
    ] + [
        ("evaluation", seed, None) for seed in contract["evaluation_seeds"]
    ] + [
        ("held_out", seed, fault)
        for fault in contract["held_out_faults"]
        for seed in contract["evaluation_seeds"]
    ]


def _scenario_for_case(
    registry: object, case: tuple[str, int, str | None]
) -> CompiledScenario:
    phase, seed, fault_id = case
    matches = [
        scenario for scenario in registry.scenarios
        if scenario.seed == seed
        and tuple(item["fault_id"] for item in scenario.faults)
        == (() if fault_id is None else (fault_id,))
    ]
    if len(matches) != 1:
        raise TrainingError(f"trusted registry has no unique scenario for {phase}/{seed}/{fault_id}")
    return matches[0]


def _validated_assignments(
    value: object, expected: list[tuple[str, int, str | None]]
) -> list[tuple[tuple[str, int, str | None], ReplayFeatures]]:
    if not isinstance(value, list) or len(value) != len(expected):
        raise TrainingError("trace assignments must match the required evaluation cases")
    expected_set = set(expected)
    assignments: dict[tuple[str, int, str | None], ReplayFeatures] = {}
    trace_sha256s: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != _ASSIGNMENT_FIELDS:
            raise TrainingError(f"trace assignments[{index}] fields are invalid")
        phase, seed, fault_id = raw["phase"], raw["seed"], raw["fault_id"]
        if not isinstance(phase, str) or type(seed) is not int:
            raise TrainingError(f"trace assignments[{index}] case identity is invalid")
        if fault_id is not None:
            try:
                fault_id = validate_identifier(fault_id, f"trace assignments[{index}].fault_id")
            except ValueError as exc:
                raise TrainingError(str(exc)) from None
        key = (phase, seed, fault_id)
        if key not in expected_set or key in assignments:
            raise TrainingError("trace assignments do not match required cases")
        scenario = raw["scenario"]
        if not isinstance(scenario, CompiledScenario):
            raise TrainingError(f"trace assignments[{index}] scenario must be a compiled scenario")
        bundle_root, manifest_sha256 = raw["bundle_root"], raw["manifest_sha256"]
        if not isinstance(bundle_root, str) or not bundle_root:
            raise TrainingError(f"trace assignments[{index}] bundle_root is invalid")
        if not isinstance(manifest_sha256, str):
            raise TrainingError(f"trace assignments[{index}] manifest_sha256 is invalid")
        try:
            replay = replay_trace_bundle(Path(bundle_root), manifest_sha256)
        except (TraceError, TypeError, ValueError, OSError) as exc:
            raise TrainingError(f"trace assignments[{index}] receipt revalidation failed: {exc}") from None
        if scenario.seed != seed:
            raise TrainingError(f"trace assignments[{index}] scenario seed does not match case")
        scenario_faults = tuple(item["fault_id"] for item in scenario.faults)
        if phase == "held_out":
            if scenario_faults != (fault_id,):
                raise TrainingError(f"trace assignments[{index}] scenario fault does not match held-out case")
        elif fault_id is not None or scenario_faults:
            raise TrainingError(f"trace assignments[{index}] scenario fault is invalid for ordinary case")
        if (
            replay.scenario_id != scenario.scenario_id
            or replay.model_sha256 != scenario.model_sha256
            or replay.trajectory_sha256 != scenario.trajectory_sha256
            or replay.environment_sha256 != scenario.environment_sha256
            or replay.joint_order != scenario.joint_order
        ):
            raise TrainingError(f"trace assignments[{index}] replay does not match scenario provenance")
        expected_metrics = {
            item["name"]: (item["unit"], float(item["limit"]))
            for item in scenario.metrics
        }
        replay_metrics = {item.name: (item.unit, item.limit) for item in replay.metrics}
        if replay_metrics != expected_metrics:
            raise TrainingError(f"trace assignments[{index}] replay metrics do not match scenario provenance")
        try:
            features = extract_replay_features(replay)
        except ReplayFeatureError as exc:
            raise TrainingError(f"trace assignments[{index}] replay is invalid: {exc}") from None
        if features.trace_sha256 in trace_sha256s:
            raise TrainingError("trace assignments must use unique receipt-bound trace_sha256 values")
        trace_sha256s.add(features.trace_sha256)
        assignments[key] = features
    if set(assignments) != expected_set:
        raise TrainingError("trace assignments do not cover required cases")
    return [(case, assignments[case]) for case in expected]


def evaluate_policy(
    contract: object,
    callback: Callable[[dict[str, Any]], dict[str, Any]],
    physical_report: object,
    trace_context: object,
) -> PolicyResult:
    """Run one bounded synthetic policy callback and retain physical blockers.

    The callback has no actuator interface.  Wall-time and traced-allocation limits
    are checked on return; an external process supervisor remains responsible for
    forcibly terminating an uncooperative callback.
    """

    checked_contract = _validate_contract_or_raise(contract)
    if not callable(callback):
        raise TrainingError("callback must be callable")
    blockers = _validated_physical_receipt(physical_report, checked_contract)

    cases = _expected_cases(checked_contract)
    if len(cases) > checked_contract["budgets"]["episodes"]:
        raise TrainingError("episodes budget is smaller than required train/evaluation cases")
    if len(cases) > checked_contract["budgets"]["steps"]:
        raise TrainingError("steps budget is smaller than required callback steps")
    if not isinstance(trace_context, TrustedPolicyTraceContext):
        raise TrainingError("trace context must be a TrustedPolicyTraceContext")
    try:
        registry = load_reference_trusted_scenario_registry(trace_context.reference_root)
    except TrustedRegistryError as exc:
        raise TrainingError("trace context registry is not the benchmark owner receipt: " + str(exc)) from None
    scenarios = [_scenario_for_case(registry, case) for case in cases]
    # Capture release-bound geometry before user callback code runs.  These
    # scalar locals are never read back from a mutable caller-visible profile.
    wheel_radius_m, wheel_separation_m = 0.15, 0.68
    started = time.monotonic()
    tracemalloc.start()
    try:
        results, accepted_results = [], []
        for (phase, seed, fault_id), scenario in zip(cases, scenarios):
            action_rows, accepted_rows = [], []
            previous = (0.0, 0.0)
            grid = (0, scenario.stop["at_ns"] // 2, scenario.stop["at_ns"])
            for timestamp in grid:
                stopped = any(
                    item["fault_id"] == "fault-stop" and item["at_ns"] <= timestamp
                    for item in scenario.faults
                )
                effective = (0.0, 0.0) if stopped else previous
                observation = {
                    "joint_rad": [0.0] * len(scenario.joint_order),
                    "left_wheel_rad_s": effective[0] / wheel_radius_m,
                    "right_wheel_rad_s": effective[1] / wheel_radius_m,
                    "phase": phase,
                    "seed": seed,
                    "fault_id": fault_id,
                    "timestamp_ns": timestamp,
                    "randomization": copy.deepcopy(checked_contract["randomization"]),
                }
                result = callback(copy.deepcopy(observation))
                if not isinstance(result, dict) or set(result) != set(_ACTION_FIELDS):
                    raise TrainingError("callback action fields are invalid")
                linear = _finite(result["linear_m_s"], "callback linear")
                angular = _finite(result["angular_rad_s"], "callback angular")
                action_rows.append({"timestamp_ns": timestamp, "linear_m_s": linear, "angular_rad_s": angular})
                accepted_rows.append((linear, angular))
                previous = (linear, angular)
            results.append(action_rows)
            accepted_results.append(accepted_rows)
        _, peak_bytes = tracemalloc.get_traced_memory()
    except Exception as exc:
        raise TrainingError(f"callback failed: {exc}") from None
    finally:
        tracemalloc.stop()
    elapsed = time.monotonic() - started
    if elapsed > checked_contract["budgets"]["wall_time_s"]:
        raise TrainingError("callback exceeds wall-time budget")
    if peak_bytes > checked_contract["budgets"]["memory_mb"] * 1024 * 1024:
        raise TrainingError("callback exceeds memory budget")

    constraints = checked_contract["hard_constraints"]
    for action_rows in accepted_results:
        for linear, angular in action_rows:
            if abs(linear) > constraints["max_linear_m_s"] or abs(angular) > constraints["max_angular_rad_s"]:
                raise TrainingError("callback action violates hard constraint")
    assigned = []
    for case, scenario, actions in zip(cases, scenarios, results):
        policy_sha256 = hashlib.sha256(canonical_bytes({
            "policy_artifact_sha256": checked_contract["artifact_sha256"],
            "case": {"phase": case[0], "seed": case[1], "fault_id": case[2]},
            "actions": actions,
        })).hexdigest()
        safe_fault = case[2] or "nominal"
        try:
            assignment = run_reference_policy_trace(
                registry, scenario.scenario_id, policy_sha256,
                actions,
                trace_context.output_root / f"{case[0]}-{case[1]}-{safe_fault}",
                wheel_radius_m=wheel_radius_m,
                wheel_separation_m=wheel_separation_m,
            )
            replay = replay_policy_trace_bundle(
                assignment.bundle_root, assignment.manifest_sha256,
                registry, policy_sha256,
                expected_actions=actions,
            )
        except PolicyTraceError as exc:
            raise TrainingError("trusted policy trace failed: " + str(exc)) from None
        if replay.features.final_joint_error_rad > constraints["max_joint_error_rad"]:
            raise TrainingError("replayed joint error violates hard constraint")
        assigned.append((case, replay.features))
    reward = sum(
        checked_contract["reward_weights"]["wheel_progress"] * features.wheel_progress_rad
        + checked_contract["reward_weights"]["wheel_effort"] * features.wheel_effort_rad2_s
        for _, features in assigned
    ) / len(assigned)
    reward = _finite(reward, "mean_reward")
    if reward < checked_contract["baseline_mean_reward"]:
        raise TrainingError("callback regresses baseline_mean_reward")
    identity = hashlib.sha256(
        canonical_bytes(
            {
                "contract": checked_contract,
                "results": results,
                "trace_sha256s": [features.trace_sha256 for _, features in assigned],
            }
        )
    ).hexdigest()[:24]
    return PolicyResult(
        policy_id="policy-" + identity,
        status="not_justified",
        evidence_level="simulated",
        physical_blockers=blockers,
        mean_reward=reward,
        evaluation_count=len(cases),
        held_out_evaluation_count=sum(phase == "held_out" for phase, _, _ in cases),
        trace_sha256s=tuple(sorted(features.trace_sha256 for _, features in assigned)),
    )
