"""Strict trace-native features shared by portable simulation consumers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..hypothesis.canonical import validate_identifier, validate_sha256


class ReplayFeatureError(ValueError):
    """A supplied replay cannot safely be used as an evaluation input."""


_REPLAY_FIELDS = {
    "scenario_id",
    "status",
    "evidence_level",
    "model_sha256",
    "trajectory_sha256",
    "environment_sha256",
    "trace_sha256",
    "joint_order",
    "samples",
    "metrics",
    "diagnostics",
}
_METRIC_FIELDS = {"name", "unit", "status", "value", "limit", "details"}


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ReplayFeatureError(f"{name} must be finite")
    return float(value)


def _metric_value(metrics: object, name: str, unit: str, *, require_passed: bool) -> float:
    if not isinstance(metrics, list):
        raise ReplayFeatureError("replay metrics must be a list")
    values: dict[str, float] = {}
    metric_names: set[str] = set()
    for index, metric in enumerate(metrics):
        if not isinstance(metric, dict) or set(metric) != _METRIC_FIELDS:
            raise ReplayFeatureError(f"replay metrics[{index}] fields are invalid")
        metric_name = metric.get("name")
        if not isinstance(metric_name, str) or metric_name in metric_names:
            raise ReplayFeatureError("replay metrics contains duplicate or invalid names")
        metric_names.add(metric_name)
        if require_passed and metric.get("status") != "passed":
            raise ReplayFeatureError(f"replay metric {metric_name} is not passed")
        if not require_passed and metric.get("status") not in {"passed", "failed"}:
            raise ReplayFeatureError(f"replay metric {metric_name} has invalid status")
        if metric_name == name:
            if metric.get("unit") != unit:
                raise ReplayFeatureError(f"replay metric {name} unit is invalid")
            values[metric_name] = _finite(metric.get("value"), f"replay metric {name}.value")
    if name not in values:
        raise ReplayFeatureError(f"replay metrics lacks {name}")
    return values[name]


@dataclass(frozen=True)
class ReplayFeatures:
    """Finite, receipt-provenance-preserving values derived from one replay."""

    scenario_id: str
    model_sha256: str
    trajectory_sha256: str
    trace_sha256: str
    joint_order: tuple[str, ...]
    timestamps_ns: tuple[int, ...]
    positions: tuple[tuple[float, ...], ...]
    left_wheel_rad_s: tuple[float, ...]
    right_wheel_rad_s: tuple[float, ...]
    elapsed_time_s: float
    left_wheel_travel_rad: float
    right_wheel_travel_rad: float
    wheel_progress_rad: float
    wheel_effort_rad2_s: float
    final_joint_error_rad: float

    @property
    def observation(self) -> dict[str, object]:
        return {
            "joint_rad": list(self.positions[-1]),
            "left_wheel_rad_s": self.left_wheel_rad_s[-1],
            "right_wheel_rad_s": self.right_wheel_rad_s[-1],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "model_sha256": self.model_sha256,
            "trajectory_sha256": self.trajectory_sha256,
            "trace_sha256": self.trace_sha256,
            "joint_order": list(self.joint_order),
            "timestamps_ns": list(self.timestamps_ns),
            "positions": [list(row) for row in self.positions],
            "left_wheel_rad_s": list(self.left_wheel_rad_s),
            "right_wheel_rad_s": list(self.right_wheel_rad_s),
            "elapsed_time_s": self.elapsed_time_s,
            "left_wheel_travel_rad": self.left_wheel_travel_rad,
            "right_wheel_travel_rad": self.right_wheel_travel_rad,
            "wheel_progress_rad": self.wheel_progress_rad,
            "wheel_effort_rad2_s": self.wheel_effort_rad2_s,
            "final_joint_error_rad": self.final_joint_error_rad,
        }


def extract_replay_features(value: object, *, require_passed: bool = True) -> ReplayFeatures:
    """Decode a successful replay without accepting caller-reported outcomes."""

    if type(require_passed) is not bool:
        raise ReplayFeatureError("require_passed must be boolean")
    if not isinstance(value, dict) or set(value) != _REPLAY_FIELDS:
        raise ReplayFeatureError("replay fields are not closed")
    if require_passed and value.get("status") != "passed":
        raise ReplayFeatureError("replay status must be passed")
    if not require_passed and value.get("status") not in {"passed", "failed"}:
        raise ReplayFeatureError("replay status must be passed or failed")
    if value.get("evidence_level") not in {"simulated", "calibrated_simulation"}:
        raise ReplayFeatureError("replay evidence_level is invalid")
    if not isinstance(value.get("diagnostics"), list):
        raise ReplayFeatureError("replay diagnostics must be a list")
    try:
        scenario_id = validate_identifier(value["scenario_id"], "replay.scenario_id")
        model_sha256 = validate_sha256(value["model_sha256"], "replay.model_sha256")
        trajectory_sha256 = validate_sha256(value["trajectory_sha256"], "replay.trajectory_sha256")
        validate_sha256(value["environment_sha256"], "replay.environment_sha256")
        trace_sha256 = validate_sha256(value["trace_sha256"], "replay.trace_sha256")
    except (KeyError, ValueError) as exc:
        raise ReplayFeatureError(f"replay provenance is invalid: {exc}") from None
    joints = value.get("joint_order")
    if not isinstance(joints, list) or not joints:
        raise ReplayFeatureError("replay joint_order must be a non-empty list")
    try:
        joint_order = tuple(validate_identifier(item, f"replay.joint_order[{index}]") for index, item in enumerate(joints))
    except ValueError as exc:
        raise ReplayFeatureError(str(exc)) from None
    if len(set(joint_order)) != len(joint_order):
        raise ReplayFeatureError("replay joint_order contains duplicates")

    samples = value.get("samples")
    if not isinstance(samples, list) or len(samples) < 3:
        raise ReplayFeatureError("replay samples must contain at least three records")
    timestamps: list[int] = []
    positions: list[tuple[float, ...]] = []
    left: list[float] = []
    right: list[float] = []
    previous = -1
    period: int | None = None
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != {"timestamp_ns", "positions", "state"}:
            raise ReplayFeatureError(f"replay samples[{index}] fields are invalid")
        timestamp = sample.get("timestamp_ns")
        if type(timestamp) is not int or timestamp < 0 or timestamp <= previous:
            raise ReplayFeatureError("replay sample timestamps must be strictly increasing non-negative integers")
        if index:
            current_period = timestamp - previous
            if period is None:
                period = current_period
            elif current_period != period:
                raise ReplayFeatureError("replay sample period must be constant")
        previous = timestamp
        row = sample.get("positions")
        if not isinstance(row, list) or len(row) != len(joint_order):
            raise ReplayFeatureError(f"replay samples[{index}] position width is invalid")
        positions.append(tuple(_finite(item, f"replay samples[{index}].positions[{column}]") for column, item in enumerate(row)))
        state = sample.get("state")
        if not isinstance(state, dict):
            raise ReplayFeatureError(f"replay samples[{index}].state is invalid")
        left.append(_finite(state.get("left_wheel_rad_s"), f"replay samples[{index}].state.left_wheel_rad_s"))
        right.append(_finite(state.get("right_wheel_rad_s"), f"replay samples[{index}].state.right_wheel_rad_s"))
        timestamps.append(timestamp)

    elapsed = (timestamps[-1] - timestamps[0]) / 1_000_000_000
    metric_elapsed = _metric_value(value.get("metrics"), "elapsed_time", "s", require_passed=require_passed)
    if not math.isclose(metric_elapsed, elapsed, rel_tol=0.0, abs_tol=1e-12):
        raise ReplayFeatureError("replay elapsed_time metric disagrees with samples")
    final_error = _metric_value(value.get("metrics"), "final_joint_error", "rad", require_passed=require_passed)
    if final_error < 0:
        raise ReplayFeatureError("replay final_joint_error must be non-negative")
    left_travel = right_travel = progress = effort = 0.0
    for index in range(1, len(timestamps)):
        dt = (timestamps[index] - timestamps[index - 1]) / 1_000_000_000
        left_travel += (left[index - 1] + left[index]) * dt / 2
        right_travel += (right[index - 1] + right[index]) * dt / 2
        previous_progress = (left[index - 1] + right[index - 1]) / 2
        current_progress = (left[index] + right[index]) / 2
        progress += (previous_progress + current_progress) * dt / 2
        previous_effort = (left[index - 1] ** 2 + right[index - 1] ** 2) / 2
        current_effort = (left[index] ** 2 + right[index] ** 2) / 2
        effort += (previous_effort + current_effort) * dt / 2
    return ReplayFeatures(
        scenario_id, model_sha256, trajectory_sha256, trace_sha256, joint_order,
        tuple(timestamps), tuple(positions), tuple(left), tuple(right), elapsed,
        _finite(left_travel, "left wheel travel"), _finite(right_travel, "right wheel travel"),
        _finite(progress, "wheel progress"), _finite(effort, "wheel effort"), final_error,
    )
