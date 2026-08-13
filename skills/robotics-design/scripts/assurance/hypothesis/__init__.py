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
]
