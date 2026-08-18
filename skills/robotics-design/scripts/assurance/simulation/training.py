"""Bounded policy callback adapter with an absolute simulation promotion firewall.

This module deliberately does not train, deploy, or authorize a robot.  It turns a
single bounded policy observation into a reproducible *simulated* record after
checking the declared contract and a physical-blocker receipt.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
import tracemalloc
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
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
from .reference_profile import ReferenceProfileError, load_reference_runner_profile
from .policy_artifact import PolicyArtifactError, load_policy_artifact
from .policy_backend import PolicyBackendError, execute_policy


class TrainingError(ValueError):
    """A training-boundary input or callback violated its closed contract."""


_FIELDS = {
    "schema_version",
    "contract_id",
    "artifact_path",
    "artifact_policy_id",
    "artifact_observation_order",
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
REFERENCE_TRAINING_CONTRACT_RECEIPT = "5d175993fd47b8ef8d830f834955299ec7cc0b8c1af60ebbe0f254849d039d18"


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
    _safe_artifact_path(data["artifact_path"])
    validate_identifier(data["artifact_policy_id"], "artifact_policy_id")
    artifact_observation_order = data["artifact_observation_order"]
    if (
        not isinstance(artifact_observation_order, list)
        or not artifact_observation_order
        or len(artifact_observation_order) > _MAX_COLLECTION_ITEMS
        or len(set(artifact_observation_order)) != len(artifact_observation_order)
    ):
        raise TrainingError("artifact_observation_order must be a non-empty unique bounded list")
    for index, field in enumerate(artifact_observation_order):
        validate_identifier(field, f"artifact_observation_order[{index}]")
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


def _safe_artifact_path(value: object) -> PurePosixPath:
    """Return a closed reference-root-relative policy location."""

    if not isinstance(value, str) or not value or "\\" in value:
        raise TrainingError("artifact_path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if str(path) != value or path.is_absolute() or PureWindowsPath(value).is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise TrainingError("artifact_path must stay safely relative to the reference root")
    return path


def validate_training_contract(value: object) -> list[str]:
    """Return deterministic, actionable validation errors without raising."""

    try:
        _validate_contract_or_raise(value)
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        return [str(exc)]
    return []


def load_reference_training_contract(reference_root: str | Path) -> dict[str, Any]:
    """Load only the benchmark-owner's exact training contract bytes."""

    root = Path(reference_root)
    path = root / "simulation" / "training-contract.json"
    try:
        if root.is_symlink() or not root.is_dir() or path.is_symlink() or not path.is_file():
            raise TrainingError("reference training contract is missing or symlinked")
        payload = path.read_bytes()
    except OSError as exc:
        raise TrainingError("cannot read reference training contract: " + str(exc)) from None
    if hashlib.sha256(payload).hexdigest() != REFERENCE_TRAINING_CONTRACT_RECEIPT:
        raise TrainingError("reference training contract does not match benchmark owner receipt")
    try:
        value = json.loads(payload.decode("utf-8"))
        checked = _validate_contract_or_raise(value)
        if canonical_bytes(checked) != payload:
            raise TrainingError("reference training contract is not canonical JSON")
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, TrainingError):
            raise
        raise TrainingError("reference training contract is invalid: " + str(exc)) from None
    return checked


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
    artifact_sha256: str | None = None
    training_contract_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "policy_id": self.policy_id,
            "status": self.status,
            "evidence_level": self.evidence_level,
            "physical_blockers": list(self.physical_blockers),
            "mean_reward": self.mean_reward,
            "evaluation_count": self.evaluation_count,
            "held_out_evaluation_count": self.held_out_evaluation_count,
            "trace_sha256s": list(self.trace_sha256s),
        }
        if self.artifact_sha256 is not None:
            value["artifact_sha256"] = self.artifact_sha256
            value["policy_artifact_sha256"] = self.artifact_sha256
        if self.training_contract_sha256 is not None:
            value["training_contract_sha256"] = self.training_contract_sha256
        return value


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
    *,
    artifact_sha256: str | None = None,
    training_contract_sha256: str | None = None,
) -> PolicyResult:
    """Run one bounded synthetic policy callback and retain physical blockers.

    The callback has no actuator interface.  Wall-time and traced-allocation limits
    are checked on return; an external process supervisor remains responsible for
    forcibly terminating an uncooperative callback.
    """

    checked_contract = _validate_contract_or_raise(contract)
    if artifact_sha256 is not None:
        try:
            artifact_sha256 = validate_sha256(artifact_sha256, "artifact_sha256")
        except ValueError as exc:
            raise TrainingError(str(exc)) from None
        if artifact_sha256 != checked_contract["artifact_sha256"]:
            raise TrainingError("artifact_sha256 does not match the training contract")
    if training_contract_sha256 is not None:
        try:
            training_contract_sha256 = validate_sha256(
                training_contract_sha256, "training_contract_sha256"
            )
        except ValueError as exc:
            raise TrainingError(str(exc)) from None
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
    # Capture receipt-bound ROS geometry before user callback code runs.  These
    # scalar locals are never read back from caller-visible configuration.
    try:
        profile = load_reference_runner_profile(trace_context.reference_root)
    except ReferenceProfileError as exc:
        raise TrainingError("trace context runner profile is invalid: " + str(exc)) from None
    wheel_radius_m, wheel_separation_m = profile.wheel_radius_m, profile.wheel_separation_m
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
                artifact_sha256=artifact_sha256,
                training_contract_sha256=training_contract_sha256,
            )
            replay = replay_policy_trace_bundle(
                assignment.bundle_root, assignment.manifest_sha256,
                registry, policy_sha256,
                expected_actions=actions,
                expected_artifact_sha256=artifact_sha256,
                expected_training_contract_sha256=training_contract_sha256,
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
        training_contract_sha256=training_contract_sha256,
    )


def _bound_artifact_path(
    artifact_path: object, contract_path: PurePosixPath, reference_root: Path
) -> Path:
    """Require the caller-selected path to be exactly the contract-bound file."""

    raw_path = artifact_path.as_posix() if isinstance(artifact_path, Path) else artifact_path
    supplied_path = _safe_artifact_path(raw_path)
    if supplied_path != contract_path:
        raise TrainingError("artifact_path does not exactly match the training contract")
    if reference_root.is_symlink() or not reference_root.is_dir():
        raise TrainingError("reference root is missing, not a directory, or a symlink")
    root = reference_root.resolve(strict=True)
    expected = root.joinpath(*contract_path.parts)
    current = root
    for part in contract_path.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise TrainingError("artifact_path cannot be inspected") from exc
        if current.is_symlink():
            raise TrainingError("artifact_path must not traverse a symlink")
        if part != contract_path.parts[-1] and not current.is_dir():
            raise TrainingError("artifact_path parent must be a directory")
    return expected


def evaluate_policy_artifact(
    contract: object,
    artifact_path: str | Path,
    physical_report: object,
    trace_context: object,
) -> PolicyResult:
    """Evaluate only the exact declarative artifact named by a trusted contract.

    This public path intentionally accepts no caller callback.  It verifies all
    contract, root, artifact, registry, and profile bindings before the first
    worker request, then delegates each strictly constructed observation to the
    isolated affine-tanh worker.
    """

    checked_contract = _validate_contract_or_raise(contract)
    blockers = _validated_physical_receipt(physical_report, checked_contract)
    if not isinstance(trace_context, TrustedPolicyTraceContext):
        raise TrainingError("trace context must be a TrustedPolicyTraceContext")
    owner_contract = load_reference_training_contract(trace_context.reference_root)
    if canonical_bytes(checked_contract) != canonical_bytes(owner_contract):
        raise TrainingError("training contract does not match benchmark owner receipt")
    try:
        registry = load_reference_trusted_scenario_registry(trace_context.reference_root)
    except TrustedRegistryError as exc:
        raise TrainingError("trace context registry is not the benchmark owner receipt: " + str(exc)) from None
    try:
        profile = load_reference_runner_profile(trace_context.reference_root)
    except ReferenceProfileError as exc:
        raise TrainingError("trace context runner profile is invalid: " + str(exc)) from None
    contract_path = _safe_artifact_path(checked_contract["artifact_path"])
    target = _bound_artifact_path(artifact_path, contract_path, trace_context.reference_root)
    try:
        artifact = load_policy_artifact(target)
    except PolicyArtifactError as exc:
        raise TrainingError("policy artifact is invalid: " + str(exc)) from None
    if artifact.sha256 != checked_contract["artifact_sha256"]:
        raise TrainingError("training contract artifact_sha256 does not match policy artifact")
    if artifact.policy_id != checked_contract["artifact_policy_id"]:
        raise TrainingError("training contract artifact_policy_id does not match policy artifact")
    contract_order = tuple(checked_contract["artifact_observation_order"])
    if artifact.observation_order != contract_order:
        raise TrainingError("training contract artifact_observation_order does not match policy artifact")
    if not registry.scenarios:
        raise TrainingError("trusted registry must contain scenarios")
    expected_order = tuple(registry.scenarios[0].joint_order) + (
        "left_wheel_rad_s", "right_wheel_rad_s",
    )
    if (
        any(tuple(scenario.joint_order) != tuple(registry.scenarios[0].joint_order) for scenario in registry.scenarios)
        or artifact.observation_order != expected_order
    ):
        raise TrainingError("artifact_observation_order does not match trusted runner state")

    started = time.monotonic()

    def artifact_action(observation: dict[str, Any]) -> dict[str, float]:
        joints = observation.get("joint_rad")
        if not isinstance(joints, list) or len(joints) != len(registry.scenarios[0].joint_order):
            raise TrainingError("trusted runner observation is invalid")
        worker_observation = {
            **{
                joint_name: joints[index]
                for index, joint_name in enumerate(registry.scenarios[0].joint_order)
            },
            "left_wheel_rad_s": observation["left_wheel_rad_s"],
            "right_wheel_rad_s": observation["right_wheel_rad_s"],
        }
        remaining = checked_contract["budgets"]["wall_time_s"] - (time.monotonic() - started)
        if remaining <= 0:
            raise TrainingError("policy worker exceeds wall-time budget")
        try:
            return execute_policy(artifact, worker_observation, timeout_s=min(1.0, remaining))
        except PolicyBackendError as exc:
            raise TrainingError("policy worker failed: " + str(exc)) from None

    # `evaluate_policy` owns the trusted runner, receipt replay, reward and
    # hardware firewall.  The only callback supplied here is this closed
    # adapter around the already verified artifact worker, never caller code.
    result = evaluate_policy(
        checked_contract,
        artifact_action,
        physical_report,
        trace_context,
        artifact_sha256=artifact.sha256,
        training_contract_sha256=REFERENCE_TRAINING_CONTRACT_RECEIPT,
    )
    if result.physical_blockers != blockers:
        raise TrainingError("physical report blockers changed during evaluation")
    return replace(
        result,
        policy_id=artifact.policy_id,
        artifact_sha256=artifact.sha256,
        training_contract_sha256=REFERENCE_TRAINING_CONTRACT_RECEIPT,
    )
