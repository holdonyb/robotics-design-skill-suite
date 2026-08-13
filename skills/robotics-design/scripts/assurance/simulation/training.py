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
from typing import Any, Callable

from ..hypothesis.canonical import (
    canonical_bytes,
    canonical_value,
    validate_identifier,
    validate_sha256,
)


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
_REWARD_FIELDS = {"progress", "energy"}
_OBSERVATION_FIELDS = ["scan_m", "joint_rad"]
_ACTION_FIELDS = ["linear_m_s", "angular_rad_s"]
_MAX_COLLECTION_ITEMS = 64


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

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "status": self.status,
            "evidence_level": self.evidence_level,
            "physical_blockers": list(self.physical_blockers),
            "mean_reward": self.mean_reward,
            "evaluation_count": self.evaluation_count,
            "held_out_evaluation_count": self.held_out_evaluation_count,
        }


def evaluate_policy(
    contract: object,
    callback: Callable[[dict[str, Any]], dict[str, Any]],
    physical_report: object,
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

    cases = [
        ("train", seed, None) for seed in checked_contract["train_seeds"]
    ] + [
        ("evaluation", seed, None) for seed in checked_contract["evaluation_seeds"]
    ] + [
        ("held_out", seed, fault)
        for fault in checked_contract["held_out_faults"]
        for seed in checked_contract["evaluation_seeds"]
    ]
    if len(cases) > checked_contract["budgets"]["episodes"]:
        raise TrainingError("episodes budget is smaller than required train/evaluation cases")
    if len(cases) > checked_contract["budgets"]["steps"]:
        raise TrainingError("steps budget is smaller than required callback steps")
    started = time.monotonic()
    tracemalloc.start()
    try:
        results = []
        for phase, seed, fault_id in cases:
            observation = {
                "scan_m": [1.0],
                "joint_rad": [0.0],
                "phase": phase,
                "seed": seed,
                "fault_id": fault_id,
                "randomization": copy.deepcopy(checked_contract["randomization"]),
            }
            results.append(callback(copy.deepcopy(observation)))
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

    accepted_results = []
    for index, result in enumerate(results):
        if not isinstance(result, dict) or set(result) != {*_ACTION_FIELDS, "mean_reward"}:
            raise TrainingError("callback action fields are invalid")
        linear = _finite(result["linear_m_s"], "callback linear")
        angular = _finite(result["angular_rad_s"], "callback angular")
        reported_reward = _finite(result["mean_reward"], "callback mean_reward")
        accepted_results.append((linear, angular, reported_reward))
    constraints = checked_contract["hard_constraints"]
    for linear, angular, _ in accepted_results:
        if (
            abs(linear) > constraints["max_linear_m_s"]
            or abs(angular) > constraints["max_angular_rad_s"]
        ):
            raise TrainingError("callback violates hard constraint")
    reward = sum(item[2] for item in accepted_results) / len(accepted_results)
    reward = _finite(reward, "mean_reward")
    if reward < checked_contract["baseline_mean_reward"]:
        raise TrainingError("callback regresses baseline_mean_reward")
    identity = hashlib.sha256(
        canonical_bytes({"contract": checked_contract, "results": results})
    ).hexdigest()[:24]
    return PolicyResult(
        policy_id="policy-" + identity,
        status="not_justified",
        evidence_level="simulated",
        physical_blockers=blockers,
        mean_reward=reward,
        evaluation_count=len(cases),
        held_out_evaluation_count=sum(phase == "held_out" for phase, _, _ in cases),
    )
