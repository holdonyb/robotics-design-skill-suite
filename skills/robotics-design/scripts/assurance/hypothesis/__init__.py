"""Deterministic records and identities for bounded design hypotheses."""

from .canonical import candidate_id, canonical_bytes, seeded_order
from .model import (
    CandidateDecision,
    CandidateLineage,
    HypothesisResult,
    StageResult,
    StageSpec,
)
from .schema import load_space, validate_space
from .overlay import OverlayError, ResolvedCandidate, apply_operation, generate_candidates
from .scheduler import HypothesisScheduler, SchedulerError, default_registry
from .uncertainty import (
    CounterexampleResult,
    SensitivityRecord,
    UncertaintyCase,
    UncertaintyError,
    apply_case,
    evaluate_sensitivity,
    ordered_cases,
    search_counterexample,
)
from .objectives import ObjectiveVector, ParetoResult, extract_vector, pareto_fronts
from .repair import RepairError, RepairTrace, repair, select_repair
from .bundle import (
    BundleError,
    BundleReceipt,
    validate_bundle,
    write_bundle,
    write_bundle_with_receipt,
)
from .engine import EngineError, run_space

__all__ = [
    "CandidateDecision",
    "CandidateLineage",
    "HypothesisResult",
    "StageResult",
    "StageSpec",
    "candidate_id",
    "canonical_bytes",
    "seeded_order",
    "load_space",
    "validate_space",
    "OverlayError",
    "ResolvedCandidate",
    "apply_operation",
    "generate_candidates",
    "HypothesisScheduler",
    "SchedulerError",
    "default_registry",
    "CounterexampleResult",
    "SensitivityRecord",
    "UncertaintyCase",
    "UncertaintyError",
    "apply_case",
    "evaluate_sensitivity",
    "ordered_cases",
    "search_counterexample",
    "ObjectiveVector",
    "ParetoResult",
    "extract_vector",
    "pareto_fronts",
    "RepairError",
    "RepairTrace",
    "repair",
    "select_repair",
    "BundleError",
    "BundleReceipt",
    "validate_bundle",
    "write_bundle",
    "write_bundle_with_receipt",
    "EngineError",
    "run_space",
]
