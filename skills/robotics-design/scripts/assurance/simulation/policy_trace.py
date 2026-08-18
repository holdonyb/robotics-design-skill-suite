"""Bounded portable runner for policy-action-bound trace evidence."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..hypothesis.bundle import BundleError, write_bundle_with_receipt
from ..hypothesis.canonical import canonical_bytes, canonical_value, validate_sha256
from .model import TraceSample
from .replay_features import ReplayFeatures, extract_replay_features
from .trace import TraceError, _read_json, _trace_payload, replay_trace_bundle
from .trusted_registry import TrustedScenarioRegistry


class PolicyTraceError(ValueError):
    """A policy trace is not the exact bounded runner output requested."""


_ACTION_FIELDS = {"timestamp_ns", "linear_m_s", "angular_rad_s"}
_PROFILE_FIELDS = {"wheel_radius_m", "wheel_separation_m"}


def _finite(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise PolicyTraceError(f"{name} must be finite")
    result = float(value)
    if positive and result <= 0:
        raise PolicyTraceError(f"{name} must be positive")
    return result


def _profile(radius: object, separation: object) -> dict[str, float]:
    return {
        "wheel_radius_m": _finite(radius, "wheel_radius_m", positive=True),
        "wheel_separation_m": _finite(separation, "wheel_separation_m", positive=True),
    }


def _action(value: object, name: str) -> dict[str, float | int]:
    if not isinstance(value, Mapping) or set(value) != _ACTION_FIELDS:
        raise PolicyTraceError(f"{name} fields are invalid")
    timestamp = value["timestamp_ns"]
    if type(timestamp) is not int or timestamp < 0:
        raise PolicyTraceError(f"{name}.timestamp_ns must be a non-negative integer")
    return {
        "timestamp_ns": timestamp,
        "linear_m_s": _finite(value["linear_m_s"], f"{name}.linear_m_s"),
        "angular_rad_s": _finite(value["angular_rad_s"], f"{name}.angular_rad_s"),
    }


def _grid(scenario) -> tuple[int, int, int]:
    stop = scenario.stop["at_ns"]
    if stop % 2:
        raise PolicyTraceError("reference runner requires an even stop timestamp")
    return (0, stop // 2, stop)


def _expand_actions(scenario, actions: object) -> tuple[dict[str, float | int], ...]:
    if not isinstance(actions, list) or not actions:
        raise PolicyTraceError("actions must be a non-empty list")
    checked = tuple(_action(item, f"actions[{index}]") for index, item in enumerate(actions))
    grid = _grid(scenario)
    if len(checked) != len(grid) or tuple(item["timestamp_ns"] for item in checked) != grid:
        raise PolicyTraceError("actions must exactly match the runner timestamp grid")
    return checked


def _samples(scenario, actions: tuple[dict[str, float | int], ...], profile: dict[str, float]) -> tuple[TraceSample, ...]:
    values = []
    radius, separation = profile["wheel_radius_m"], profile["wheel_separation_m"]
    for index, action in enumerate(actions):
        linear, angular = float(action["linear_m_s"]), float(action["angular_rad_s"])
        # The reference fixture's declared fault-stop makes the base immobile
        # from its timestamp forward.  Unknown faults are not silently
        # simulated: scenario compilation permits them, but this narrow runner
        # only claims the explicit fault-stop disposition.
        fault_stop = any(
            item["fault_id"] == "fault-stop" and item["at_ns"] <= action["timestamp_ns"]
            for item in scenario.faults
        )
        if fault_stop:
            linear = angular = 0.0
        left = (linear - angular * separation / 2) / radius
        right = (linear + angular * separation / 2) / radius
        mode = ("start", "running", "duration_elapsed")[index]
        values.append(TraceSample(int(action["timestamp_ns"]), (0.0,) * len(scenario.joint_order), {
            "mode": mode, "left_wheel_rad_s": left, "right_wheel_rad_s": right,
        }))
    return tuple(values)


@dataclass(frozen=True)
class TrustedTraceAssignment:
    registry_sha256: str
    scenario_id: str
    policy_sha256: str
    action_sha256: str
    bundle_root: Path
    manifest_sha256: str


@dataclass(frozen=True)
class PolicyTraceReplay:
    scenario_id: str
    policy_sha256: str
    action_sha256: str
    trace_sha256: str
    features: ReplayFeatures
    artifact_sha256: str | None = None


@dataclass(frozen=True)
class TrustedPolicyTraceContext:
    """Reference root and controlled output/profile for one evaluation."""

    reference_root: Path
    output_root: Path

    def __post_init__(self) -> None:
        reference_root = Path(self.reference_root)
        if reference_root.is_symlink() or not reference_root.is_dir():
            raise PolicyTraceError("reference_root is missing, not a directory, or a symlink")
        object.__setattr__(self, "reference_root", reference_root)
        root = Path(self.output_root)
        if root.is_symlink():
            raise PolicyTraceError("policy trace output_root must not be a symlink")
        object.__setattr__(self, "output_root", root)


def run_reference_policy_trace(
    registry: TrustedScenarioRegistry,
    scenario_id: str,
    policy_sha256: str,
    actions: object,
    output: str | Path,
    *,
    wheel_radius_m: object,
    wheel_separation_m: object,
    artifact_sha256: str | None = None,
) -> TrustedTraceAssignment:
    """Publish the runner's deterministic trace for exactly one policy action grid."""
    if not isinstance(registry, TrustedScenarioRegistry):
        raise PolicyTraceError("registry must be a TrustedScenarioRegistry")
    try:
        policy_sha256 = validate_sha256(policy_sha256, "policy_sha256")
        if artifact_sha256 is not None:
            artifact_sha256 = validate_sha256(artifact_sha256, "artifact_sha256")
        scenario = registry.scenario_by_id(scenario_id)
    except ValueError as exc:
        raise PolicyTraceError(str(exc)) from None
    profile = _profile(wheel_radius_m, wheel_separation_m)
    checked_actions = _expand_actions(scenario, actions)
    action_sha256 = hashlib.sha256(canonical_bytes(list(checked_actions))).hexdigest()
    trace = _trace_payload(scenario, _samples(scenario, checked_actions, profile))
    trace.update({
        "registry_sha256": registry.registry_sha256,
        "policy_sha256": policy_sha256,
        "actions": list(checked_actions),
        "runner_profile": profile,
    })
    if artifact_sha256 is not None:
        trace["artifact_sha256"] = artifact_sha256
    try:
        receipt = write_bundle_with_receipt(output, {
            "index.json": {"schema_version": 1, "kind": "trusted_policy_trace_v1"},
            "scenario.json": scenario.to_dict(),
            "trace.json": trace,
        })
    except BundleError as exc:
        raise PolicyTraceError(str(exc)) from None
    return TrustedTraceAssignment(registry.registry_sha256, scenario.scenario_id, policy_sha256, action_sha256, receipt.path, receipt.manifest_sha256)


def replay_policy_trace_bundle(
    root: str | Path,
    manifest_sha256: str,
    registry: TrustedScenarioRegistry,
    expected_policy_sha256: str,
    *,
    expected_actions: object | None = None,
    expected_artifact_sha256: str | None = None,
) -> PolicyTraceReplay:
    """Replay only a trace whose registry, policy and runner state all agree."""
    if not isinstance(registry, TrustedScenarioRegistry):
        raise PolicyTraceError("registry must be a TrustedScenarioRegistry")
    try:
        expected_policy_sha256 = validate_sha256(expected_policy_sha256, "expected policy_sha256")
        if expected_artifact_sha256 is not None:
            expected_artifact_sha256 = validate_sha256(expected_artifact_sha256, "expected artifact_sha256")
        replay = replay_trace_bundle(root, manifest_sha256)
        trace = _read_json(Path(root) / "trace.json")
        scenario = registry.scenario_by_id(replay.scenario_id)
    except (OSError, TraceError, ValueError) as exc:
        raise PolicyTraceError(f"cannot replay trusted policy trace: {exc}") from None
    expected_fields = {"schema_version", "scenario_sha256", "joint_order", "samples", "registry_sha256", "policy_sha256", "actions", "runner_profile"}
    artifact_fields = expected_fields | {"artifact_sha256"}
    if set(trace) not in {frozenset(expected_fields), frozenset(artifact_fields)}:
        raise PolicyTraceError("trusted policy trace fields are not closed")
    if trace["registry_sha256"] != registry.registry_sha256:
        raise PolicyTraceError("trace registry receipt does not match trusted registry")
    if trace["policy_sha256"] != expected_policy_sha256:
        raise PolicyTraceError("trace policy identity does not match evaluation request")
    artifact_sha256 = trace.get("artifact_sha256")
    if artifact_sha256 is not None:
        try:
            artifact_sha256 = validate_sha256(artifact_sha256, "trace artifact_sha256")
        except ValueError as exc:
            raise PolicyTraceError(str(exc)) from None
    if artifact_sha256 != expected_artifact_sha256:
        raise PolicyTraceError("trace artifact identity does not match evaluation request")
    profile_raw = trace["runner_profile"]
    if not isinstance(profile_raw, dict) or set(profile_raw) != _PROFILE_FIELDS:
        raise PolicyTraceError("trace runner profile fields are invalid")
    profile = _profile(profile_raw["wheel_radius_m"], profile_raw["wheel_separation_m"])
    try:
        actions = _expand_actions(scenario, trace["actions"])
    except PolicyTraceError as exc:
        raise PolicyTraceError("trace actions are invalid: " + str(exc)) from None
    if expected_actions is not None and actions != _expand_actions(scenario, expected_actions):
        raise PolicyTraceError("trace actions do not match evaluation request")
    if tuple(sample.to_dict() for sample in replay.samples) != tuple(sample.to_dict() for sample in _samples(scenario, actions, profile)):
        raise PolicyTraceError("trace samples are not the deterministic runner output")
    action_sha256 = hashlib.sha256(canonical_bytes(list(actions))).hexdigest()
    try:
        features = extract_replay_features(replay, require_passed=False)
    except ValueError as exc:
        raise PolicyTraceError("trusted policy trace features are invalid: " + str(exc)) from None
    return PolicyTraceReplay(replay.scenario_id, expected_policy_sha256, action_sha256, replay.trace_sha256, features, artifact_sha256)
