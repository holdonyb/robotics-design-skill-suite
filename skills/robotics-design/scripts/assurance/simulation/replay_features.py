"""Strict trace-native features shared by portable simulation consumers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Mapping

from .model import MetricResult, SimulationResult


class ReplayFeatureError(ValueError):
    """A supplied replay cannot safely be used as an evaluation input."""


_MAX_REPLAY_SAMPLES = 10_000


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ReplayFeatureError(f"{name} must be finite")
    return float(value)


def _metric_value(metrics: tuple[MetricResult, ...], name: str, unit: str, *, require_passed: bool) -> float:
    values: dict[str, float] = {}
    metric_names: set[str] = set()
    for index, metric in enumerate(metrics):
        if not isinstance(metric, MetricResult):
            raise ReplayFeatureError(f"replay metrics[{index}] is invalid")
        metric_name = metric.name
        if metric_name in metric_names:
            raise ReplayFeatureError("replay metrics contains duplicate or invalid names")
        metric_names.add(metric_name)
        if require_passed and metric.status != "passed":
            raise ReplayFeatureError(f"replay metric {metric_name} is not passed")
        if not require_passed and metric.status not in {"passed", "failed"}:
            raise ReplayFeatureError(f"replay metric {metric_name} has invalid status")
        if metric_name == name:
            if metric.unit != unit:
                raise ReplayFeatureError(f"replay metric {name} unit is invalid")
            values[metric_name] = _finite(metric.value, f"replay metric {name}.value")
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
    if not isinstance(value, SimulationResult):
        raise ReplayFeatureError("replay must be a receipt-validated SimulationResult")
    if require_passed and value.status != "passed":
        raise ReplayFeatureError("replay status must be passed")
    if not require_passed and value.status not in {"passed", "failed"}:
        raise ReplayFeatureError("replay status must be passed or failed")
    if value.evidence_level not in {"simulated", "calibrated_simulation"}:
        raise ReplayFeatureError("replay evidence_level is invalid")
    joint_order = value.joint_order
    samples = value.samples
    if len(samples) < 3 or len(samples) > _MAX_REPLAY_SAMPLES:
        raise ReplayFeatureError("replay samples must contain at least three records")
    timestamps: list[int] = []
    positions: list[tuple[float, ...]] = []
    left: list[float] = []
    right: list[float] = []
    previous = -1
    period: int | None = None
    for index, sample in enumerate(samples):
        timestamp = sample.timestamp_ns
        if type(timestamp) is not int or timestamp < 0 or timestamp <= previous:
            raise ReplayFeatureError("replay sample timestamps must be strictly increasing non-negative integers")
        if index:
            current_period = timestamp - previous
            if period is None:
                period = current_period
            elif current_period != period:
                raise ReplayFeatureError("replay sample period must be constant")
        previous = timestamp
        row = sample.positions
        if len(row) != len(joint_order):
            raise ReplayFeatureError(f"replay samples[{index}] position width is invalid")
        positions.append(tuple(_finite(item, f"replay samples[{index}].positions[{column}]") for column, item in enumerate(row)))
        state = sample.state
        if not isinstance(state, Mapping):
            raise ReplayFeatureError(f"replay samples[{index}].state is invalid")
        left.append(_finite(state.get("left_wheel_rad_s"), f"replay samples[{index}].state.left_wheel_rad_s"))
        right.append(_finite(state.get("right_wheel_rad_s"), f"replay samples[{index}].state.right_wheel_rad_s"))
        timestamps.append(timestamp)

    elapsed = (timestamps[-1] - timestamps[0]) / 1_000_000_000
    metric_elapsed = _metric_value(value.metrics, "elapsed_time", "s", require_passed=require_passed)
    if not math.isclose(metric_elapsed, elapsed, rel_tol=0.0, abs_tol=1e-12):
        raise ReplayFeatureError("replay elapsed_time metric disagrees with samples")
    metric_final_error = _metric_value(value.metrics, "final_joint_error", "rad", require_passed=require_passed)
    final_error = max(abs(item) for item in positions[-1])
    if final_error < 0 or not math.isclose(metric_final_error, final_error, rel_tol=0.0, abs_tol=1e-12):
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
        value.scenario_id, value.model_sha256, value.trajectory_sha256, value.trace_sha256, joint_order,
        tuple(timestamps), tuple(positions), tuple(left), tuple(right), elapsed,
        _finite(left_travel, "left wheel travel"), _finite(right_travel, "right wheel travel"),
        _finite(progress, "wheel progress"), _finite(effort, "wheel effort"), final_error,
    )
