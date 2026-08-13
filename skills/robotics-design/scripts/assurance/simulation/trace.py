"""Transactionally publish and independently replay bounded trace evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from ..hypothesis.bundle import BundleError, validate_bundle, write_bundle_with_receipt
from ..hypothesis.canonical import canonical_bytes, canonical_value
from .model import MetricResult, SimulationResult, TraceSample
from .scenario import CompiledScenario


class TraceError(ValueError):
    """Trace evidence is invalid, stale, or cannot be replayed safely."""


def _trace_payload(scenario: CompiledScenario, samples: tuple[TraceSample, ...]) -> dict:
    return {
        "schema_version": 1,
        "scenario_sha256": scenario.scenario_sha256,
        "joint_order": list(scenario.joint_order),
        "samples": [sample.to_dict() for sample in samples],
    }


def _validate_samples(scenario: CompiledScenario, samples: Iterable[TraceSample]) -> tuple[TraceSample, ...]:
    values = tuple(samples)
    if not values:
        raise TraceError("trace must contain at least one sample")
    if len(values) > 10_000:
        raise TraceError("trace exceeds maximum sample count")
    previous = -1
    for index, sample in enumerate(values):
        if not isinstance(sample, TraceSample):
            raise TraceError(f"samples[{index}] must be a TraceSample")
        if len(sample.positions) != len(scenario.joint_order):
            raise TraceError(f"samples[{index}] width must match joint_order")
        if sample.timestamp_ns <= previous:
            raise TraceError("sample timestamps must be strictly increasing")
        previous = sample.timestamp_ns
    if values[0].timestamp_ns != 0:
        raise TraceError("first timestamp must be zero")
    if len(values) > 2:
        expected_period = values[1].timestamp_ns - values[0].timestamp_ns
        if expected_period <= 0 or any(
            values[index].timestamp_ns - values[index - 1].timestamp_ns != expected_period
            for index in range(2, len(values))
        ):
            raise TraceError("sample period must be constant")
    if values[-1].timestamp_ns != scenario.stop["at_ns"]:
        raise TraceError("stop timestamp must equal the scenario stop timestamp")
    return values


def publish_trace_bundle(output: str | Path, scenario: CompiledScenario, samples: Iterable[TraceSample]):
    """Write canonical trace and scenario files atomically; no result verdict is stored."""
    if not isinstance(scenario, CompiledScenario):
        raise TraceError("scenario must be a CompiledScenario")
    checked = _validate_samples(scenario, samples)
    trace = _trace_payload(scenario, checked)
    try:
        return write_bundle_with_receipt(
            output,
            {"index.json": {"schema_version": 1, "kind": "simulation_trace"}, "scenario.json": scenario.to_dict(), "trace.json": trace},
        )
    except BundleError as exc:
        raise TraceError(str(exc)) from None


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        value = canonical_value(value, path.name)
    except (OSError, UnicodeError, json.JSONDecodeError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise TraceError(f"cannot load {path.name}: {exc}") from None
    if not isinstance(value, dict):
        raise TraceError(f"{path.name} must be an object")
    return value


def replay_trace_bundle(root: str | Path, manifest_sha256: str) -> SimulationResult:
    """Recompute every metric from immutable samples; stored verdicts are ignored."""
    target = Path(root)
    errors = validate_bundle(target, manifest_sha256=manifest_sha256)
    if errors:
        raise TraceError("trace bundle is invalid: " + "; ".join(errors))
    scenario_data, trace = _read_json(target / "scenario.json"), _read_json(target / "trace.json")
    required_trace = {"schema_version", "scenario_sha256", "joint_order", "samples"}
    if set(trace) != required_trace or trace["schema_version"] != 1:
        raise TraceError("trace.json fields are not closed")
    if hashlib.sha256(canonical_bytes(scenario_data)).hexdigest() != trace["scenario_sha256"]:
        raise TraceError("trace scenario SHA-256 mismatch")
    try:
        scenario = CompiledScenario.__new__(CompiledScenario)  # only to keep parser independent from registry
        from .scenario import compile_scenarios
        registry = {"schema_version": 1, "registry_id": "replay", "model_sha256": scenario_data["model_sha256"], "trajectory_sha256": scenario_data["trajectory_sha256"], "environment_sha256": scenario_data["environment_sha256"], "joint_order": scenario_data["joint_order"], "scenarios": [scenario_data] * 10}
        # Use direct structural checks below; duplicate registry IDs intentionally make this unsuitable for compilation.
        del scenario
    except Exception:
        pass
    if not isinstance(trace["samples"], list) or not isinstance(trace["joint_order"], list):
        raise TraceError("trace samples and joint_order must be lists")
    if trace["joint_order"] != scenario_data.get("joint_order"):
        raise TraceError("trace joint_order does not match scenario")
    samples = tuple(TraceSample(item.get("timestamp_ns"), tuple(item.get("positions", ())), item.get("state")) if isinstance(item, dict) else None for item in trace["samples"])
    if any(sample is None for sample in samples):
        raise TraceError("trace samples must be objects")
    duration = scenario_data.get("duration_ns")
    if type(duration) is not int or not samples or samples[0].timestamp_ns != 0 or samples[-1].timestamp_ns != duration:
        raise TraceError("trace timestamps do not match scenario duration")
    previous = -1
    width = len(trace["joint_order"])
    for sample in samples:
        if len(sample.positions) != width or sample.timestamp_ns <= previous:
            raise TraceError("trace sample width or monotonic timestamp is invalid")
        previous = sample.timestamp_ns
    metrics = []
    for metric in scenario_data.get("metrics", []):
        name, limit, direction = metric["name"], float(metric["limit"]), metric["direction"]
        if name == "elapsed_time":
            value = samples[-1].timestamp_ns / 1_000_000_000
        elif name == "final_joint_error":
            value = max(abs(value) for value in samples[-1].positions)
        else:
            raise TraceError(f"unsupported replay metric: {name}")
        passed = value <= limit if direction == "max" else value >= limit
        metrics.append(MetricResult(name, metric["unit"], "passed" if passed else "failed", value, limit, {"direction": direction}))
    status = "passed" if all(metric.status == "passed" for metric in metrics) else "failed"
    trace_sha = hashlib.sha256(canonical_bytes(trace)).hexdigest()
    return SimulationResult(scenario_data["scenario_id"], status, "simulated", scenario_data["model_sha256"], scenario_data["trajectory_sha256"], scenario_data["environment_sha256"], trace_sha, tuple(trace["joint_order"]), samples, tuple(metrics), ())
