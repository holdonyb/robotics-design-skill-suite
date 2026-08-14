"""Independent, bounded planar dynamics adapter and interval comparison."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..hypothesis.canonical import validate_sha256


class BackendError(ValueError):
    """Dynamics input or backend comparison is outside its declared domain."""


def _finite(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise BackendError(f"{name} must be a finite number")
    result = float(value)
    if positive and result <= 0:
        raise BackendError(f"{name} must be positive")
    return result


@dataclass(frozen=True)
class BackendMetric:
    name: str
    unit: str
    value: float
    lower: float
    upper: float
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not isinstance(self.unit, str) or self.status not in {"passed", "failed", "indeterminate"}:
            raise BackendError("backend metric fields are invalid")
        value, lower, upper = (_finite(item, name) for item, name in ((self.value, "value"), (self.lower, "lower"), (self.upper, "upper")))
        if lower > value or value > upper:
            raise BackendError("metric interval must contain its value")
        object.__setattr__(self, "value", value); object.__setattr__(self, "lower", lower); object.__setattr__(self, "upper", upper)


@dataclass(frozen=True)
class BackendResult:
    model_sha256: str
    trajectory_sha256: str
    status: str
    metrics: tuple[BackendMetric, ...]
    validity_domain: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_sha256(self.model_sha256, "model_sha256"); validate_sha256(self.trajectory_sha256, "trajectory_sha256")
        if self.status not in {"passed", "failed", "indeterminate"} or not self.metrics:
            raise BackendError("backend result status or metrics are invalid")
        if not all(isinstance(item, BackendMetric) for item in self.metrics):
            raise BackendError("metrics must contain BackendMetric records")
        names = [item.name for item in self.metrics]
        if len(names) != len(set(names)):
            raise BackendError("metrics contains duplicate names")
        if not self.validity_domain or any(not isinstance(item, str) or not item for item in self.validity_domain):
            raise BackendError("validity_domain must be a non-empty string tuple")
        object.__setattr__(self, "metrics", tuple(sorted(self.metrics, key=lambda item: item.name)))
        object.__setattr__(self, "validity_domain", tuple(sorted(set(self.validity_domain))))


def evaluate_independent_dynamics(data: object) -> BackendResult:
    """Evaluate a planar differential drive / endpoint fixture without Gazebo."""
    if not isinstance(data, dict) or set(data) != {
        "model_sha256", "trajectory_sha256", "units", "timestamps_ns", "left_wheel_rad_s", "right_wheel_rad_s",
        "wheel_radius_m", "wheel_separation_m", "wheel_speed_limit_rad_s", "mass_kg", "slope_rad",
        "brake_deceleration_m_s2", "joint_final_rad", "joint_target_rad", "joint_error_limit_rad",
    }:
        raise BackendError("dynamics input fields are not closed")
    try:
        validate_sha256(data["model_sha256"], "model_sha256")
        validate_sha256(data["trajectory_sha256"], "trajectory_sha256")
    except ValueError as exc:
        raise BackendError(str(exc)) from None
    if data["units"] != "si":
        raise BackendError("units must be si")
    stamps, left, right = data["timestamps_ns"], data["left_wheel_rad_s"], data["right_wheel_rad_s"]
    if not all(isinstance(item, list) for item in (stamps, left, right)) or len(stamps) < 3 or len(stamps) != len(left) or len(left) != len(right):
        raise BackendError("time grid and wheel series must have equal length of at least three")
    if any(type(item) is not int or item < 0 for item in stamps) or any(stamps[index] <= stamps[index - 1] for index in range(1, len(stamps))):
        raise BackendError("timestamps_ns must be strictly increasing non-negative integers")
    left, right = [_finite(item, "left_wheel_rad_s") for item in left], [_finite(item, "right_wheel_rad_s") for item in right]
    radius, separation, speed_limit, mass, brake = (_finite(data[key], key, positive=True) for key in ("wheel_radius_m", "wheel_separation_m", "wheel_speed_limit_rad_s", "mass_kg", "brake_deceleration_m_s2"))
    slope = _finite(data["slope_rad"], "slope_rad")
    if slope < 0 or slope > math.pi / 6:
        raise BackendError("slope_rad must be within the uphill planar validity domain")
    final, target = data["joint_final_rad"], data["joint_target_rad"]
    if not isinstance(final, list) or not isinstance(target, list) or not final or len(final) != len(target):
        raise BackendError("joint final and target arrays must have equal nonzero length")
    error_limit = _finite(data["joint_error_limit_rad"], "joint_error_limit_rad", positive=True)
    final, target = [_finite(item, "joint_final_rad") for item in final], [_finite(item, "joint_target_rad") for item in target]
    distance = yaw = 0.0
    for index in range(1, len(stamps)):
        dt = (stamps[index] - stamps[index - 1]) / 1_000_000_000
        linear = radius * (left[index - 1] + right[index - 1]) / 2
        angular = radius * (right[index - 1] - left[index - 1]) / separation
        distance += linear * dt; yaw += angular * dt
    peak_speed = max(abs(value) for value in left + right)
    braking = (radius * (left[-1] + right[-1]) / 2) ** 2 / (2 * brake)
    joint_error = max(abs(value - target[index]) for index, value in enumerate(final))
    values = (("base_distance_m", "m", distance, True), ("base_yaw_rad", "rad", yaw, True), ("braking_distance_m", "m", braking, True), ("wheel_speed_rad_s", "rad_s", peak_speed, peak_speed <= speed_limit), ("final_joint_error_rad", "rad", joint_error, joint_error <= error_limit))
    metrics = tuple(BackendMetric(name, unit, value, value, value, "passed" if passed else "failed") for name, unit, value, passed in values)
    return BackendResult(data["model_sha256"], data["trajectory_sha256"], "passed" if all(item.status == "passed" for item in metrics) else "failed", metrics, ("level_ground",) if slope == 0 else ("uphill_planar",))


def evaluate_trace_kinematics(data: object) -> BackendResult:
    """Derive a primary result from a uniformly sampled wheel trace.

    Unlike the independent adapter, this deliberately uses trapezoidal
    integration of endpoint wheel speeds.  It is a separate implementation so
    the cross-check cannot silently compare one function's output to itself.
    """
    if not isinstance(data, dict):
        raise BackendError("trace dynamics input must be an object")
    # Reuse the strict input-domain validator, then perform a distinct numerical
    # reduction over already validated canonical scalar/list values.
    checked = evaluate_independent_dynamics(data)
    stamps = data["timestamps_ns"]
    left = data["left_wheel_rad_s"]
    right = data["right_wheel_rad_s"]
    radius = float(data["wheel_radius_m"])
    separation = float(data["wheel_separation_m"])
    distance = yaw = 0.0
    for index in range(1, len(stamps)):
        dt = (stamps[index] - stamps[index - 1]) / 1_000_000_000
        linear_previous = radius * (left[index - 1] + right[index - 1]) / 2
        linear_current = radius * (left[index] + right[index]) / 2
        angular_previous = radius * (right[index - 1] - left[index - 1]) / separation
        angular_current = radius * (right[index] - left[index]) / separation
        distance += (linear_previous + linear_current) * dt / 2
        yaw += (angular_previous + angular_current) * dt / 2
    replaced = []
    for metric in checked.metrics:
        if metric.name == "base_distance_m":
            replaced.append(BackendMetric(metric.name, metric.unit, distance, distance, distance, metric.status))
        elif metric.name == "base_yaw_rad":
            replaced.append(BackendMetric(metric.name, metric.unit, yaw, yaw, yaw, metric.status))
        else:
            replaced.append(metric)
    return BackendResult(
        checked.model_sha256,
        checked.trajectory_sha256,
        checked.status,
        tuple(replaced),
        checked.validity_domain,
    )


def compare_backends(primary: BackendResult, independent: BackendResult, tolerances: object) -> BackendResult:
    if not isinstance(primary, BackendResult) or not isinstance(independent, BackendResult) or not isinstance(tolerances, dict):
        raise BackendError("backends and tolerances have invalid types")
    if primary.model_sha256 != independent.model_sha256 or primary.trajectory_sha256 != independent.trajectory_sha256:
        raise BackendError("backend model or trajectory hash mismatch")
    if primary.validity_domain != independent.validity_domain:
        return BackendResult(primary.model_sha256, primary.trajectory_sha256, "indeterminate", primary.metrics, primary.validity_domain)
    first, second = {metric.name: metric for metric in primary.metrics}, {metric.name: metric for metric in independent.metrics}
    if set(first) != set(second) or set(tolerances) != set(first):
        raise BackendError("backends and tolerances must declare the same metric set")
    output = []
    for name in sorted(first):
        tolerance = _finite(tolerances[name], f"tolerances[{name}]", positive=True)
        a, b = first[name], second[name]
        if a.unit != b.unit:
            raise BackendError(f"metric unit mismatch: {name}")
        gap = max(a.lower, b.lower) - min(a.upper, b.upper)
        passed = gap <= tolerance and a.status == b.status == "passed"
        output.append(BackendMetric(name, a.unit, abs(a.value - b.value), 0.0, max(abs(a.value - b.value), gap), "passed" if passed else "failed"))
    return BackendResult(primary.model_sha256, primary.trajectory_sha256, "passed" if all(item.status == "passed" for item in output) else "failed", tuple(output), primary.validity_domain)
