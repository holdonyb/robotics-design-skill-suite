"""Simulation assurance records and gates."""

from .model import (
    EVIDENCE_LEVELS,
    ArtifactRecord,
    EnvironmentLock,
    MetricResult,
    ScenarioSpec,
    SimulationAdmission,
    SimulationResult,
    TraceSample,
    TrajectoryRecord,
)
from .admission import evaluate_simulation_admission
from .artifacts import validate_artifact_manifest
from .schema import load_simulation_contract, validate_simulation_contract
from .scenario import CompiledScenario, ScenarioError, compile_scenarios, load_scenario_registry
from .trace import TraceError, publish_trace_bundle, replay_trace_bundle
from .backend import BackendError, BackendMetric, BackendResult, compare_backends, evaluate_independent_dynamics
from .calibration import CalibrationError, CalibrationResult, fit_calibration, load_calibration_dataset

__all__ = [
    "EVIDENCE_LEVELS",
    "ArtifactRecord",
    "EnvironmentLock",
    "MetricResult",
    "ScenarioSpec",
    "SimulationAdmission",
    "SimulationResult",
    "TraceSample",
    "TrajectoryRecord",
    "evaluate_simulation_admission",
    "validate_artifact_manifest",
    "load_simulation_contract",
    "validate_simulation_contract",
    "CompiledScenario",
    "ScenarioError",
    "compile_scenarios",
    "load_scenario_registry",
    "TraceError",
    "publish_trace_bundle",
    "replay_trace_bundle",
    "BackendError",
    "BackendMetric",
    "BackendResult",
    "compare_backends",
    "evaluate_independent_dynamics",
    "CalibrationError",
    "CalibrationResult",
    "fit_calibration",
    "load_calibration_dataset",
]
