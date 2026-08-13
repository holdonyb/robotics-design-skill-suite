"""Fail-closed analytical admission gate for simulation consumers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from ..hypothesis.canonical import canonical_bytes, canonical_value, validate_candidate_id, validate_identifier
from .model import SimulationAdmission


_HYPOTHESIS_FIELDS = {
    "candidate_id",
    "resolved_contract_sha256",
    "contract_passed",
    "physical_passed",
    "hard_counterexample",
    "complete",
    "blocking_diagnostics",
}
_PHYSICAL_FIELDS = {"candidate_id", "promotable", "diagnostics", "analyses", "metadata"}
_DIAGNOSTIC_FIELDS = {"code", "severity", "path", "message", "evidence_ids"}
_ANALYSIS_REQUIRED_FIELDS = {"name", "version", "passed", "outputs"}
_ANALYSIS_FIELDS = _ANALYSIS_REQUIRED_FIELDS | {
    "analysis_id",
    "evidence_level",
    "inputs",
    "validity_assumptions",
}
_ALLOWED_PLACEHOLDER_BLOCKERS = frozenset({"BOM.PLACEHOLDER_BLOCKS_CLAIM"})
_BLOCKING_SEVERITIES = frozenset({"error", "indeterminate"})
_ANALYTICAL_EVIDENCE_LEVELS = frozenset({"assumed", "generated", "parsed", "calculated"})


def _decision(
    candidate_id: str,
    resolved_contract_sha256: str,
    blockers: set[str],
) -> SimulationAdmission:
    admitted = bool(blockers) and blockers <= _ALLOWED_PLACEHOLDER_BLOCKERS
    return SimulationAdmission(
        candidate_id=candidate_id,
        resolved_contract_sha256=resolved_contract_sha256,
        status="simulation_admitted" if admitted else "rejected",
        evidence_level="simulation_admitted" if admitted else "calculated",
        hardware_promotable=False,
        remaining_blockers=tuple(sorted(blockers)),
    )


def evaluate_simulation_admission(
    physical_report: Mapping[str, Any],
    hypothesis_report: Mapping[str, Any],
    resolved_contract: Mapping[str, Any],
) -> SimulationAdmission:
    """Admit only placeholder-blocked, analytically clean, identity-bound candidates.

    The returned receipt can never claim hardware promotion. Malformed nested report
    data is converted into deterministic admission blockers rather than escaping.
    """

    if not all(
        isinstance(item, Mapping)
        for item in (physical_report, hypothesis_report, resolved_contract)
    ):
        raise ValueError("physical_report, hypothesis_report, and resolved_contract must be mappings")
    try:
        physical = canonical_value(physical_report, "physical_report")
        hypothesis = canonical_value(hypothesis_report, "hypothesis_report")
        contract = canonical_value(resolved_contract, "resolved_contract")
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"admission inputs must be canonical JSON: {exc}") from None
    contract_content = {key: value for key, value in contract.items() if key != "candidate_id"}
    expected_hash = hashlib.sha256(canonical_bytes(contract_content)).hexdigest()
    full_contract_hash = hashlib.sha256(canonical_bytes(contract)).hexdigest()

    physical_candidate = physical.get("candidate_id")
    hypothesis_candidate = hypothesis.get("candidate_id")
    try:
        candidate = validate_candidate_id(physical_candidate)
    except ValueError:
        candidate = validate_candidate_id(hypothesis_candidate)

    blockers: set[str] = set()
    if set(physical) != _PHYSICAL_FIELDS:
        blockers.add("SIM.ADMISSION.MALFORMED")
    if set(hypothesis) != _HYPOTHESIS_FIELDS:
        blockers.add("SIM.ADMISSION.MALFORMED")
    if physical_candidate != hypothesis_candidate:
        blockers.add("SIM.ADMISSION.IDENTITY")
    if contract.get("candidate_id") != physical_candidate:
        blockers.add("SIM.ADMISSION.IDENTITY")
    if hypothesis.get("resolved_contract_sha256") != expected_hash:
        blockers.add("SIM.ADMISSION.HASH")

    for field, code in (
        ("contract_passed", "SIM.ADMISSION.CONTRACT"),
        ("complete", "SIM.ADMISSION.INCOMPLETE"),
    ):
        if hypothesis.get(field) is not True:
            blockers.add(code)
    if hypothesis.get("physical_passed") is not False:
        blockers.add("SIM.ADMISSION.PHYSICAL_STATE")
    if hypothesis.get("hard_counterexample") is not False:
        blockers.add("SIM.ADMISSION.HARD_COUNTEREXAMPLE")

    metadata = physical.get("metadata")
    if not isinstance(metadata, dict):
        blockers.add("SIM.ADMISSION.MALFORMED")
    elif metadata.get("contract_sha256") != full_contract_hash:
        blockers.add("SIM.ADMISSION.HASH")

    physical_blockers: set[str] = set()
    diagnostics = physical.get("diagnostics")
    if not isinstance(diagnostics, list) or not diagnostics:
        blockers.add("SIM.ADMISSION.MALFORMED")
    else:
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if set(diagnostic) != _DIAGNOSTIC_FIELDS:
                blockers.add("SIM.ADMISSION.MALFORMED")
            if any(
                not isinstance(diagnostic.get(field), str) or not diagnostic.get(field).strip()
                for field in ("path", "message")
            ):
                blockers.add("SIM.ADMISSION.MALFORMED")
            evidence_ids = diagnostic.get("evidence_ids")
            if not isinstance(evidence_ids, list) or any(
                not isinstance(item, str) or not item.strip() for item in evidence_ids
            ) or len(evidence_ids) != len(set(evidence_ids)):
                blockers.add("SIM.ADMISSION.MALFORMED")
            code = diagnostic.get("code")
            severity = diagnostic.get("severity")
            try:
                checked_code = validate_identifier(code, "diagnostic.code")
            except ValueError:
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if severity in _BLOCKING_SEVERITIES:
                physical_blockers.add(checked_code)
            elif severity not in {"info", "warning"}:
                blockers.add("SIM.ADMISSION.MALFORMED")

    analyses = physical.get("analyses")
    if not isinstance(analyses, list) or not analyses:
        blockers.add("SIM.ADMISSION.ANALYSIS")
    else:
        seen_analyses: set[tuple[str, str]] = set()
        for analysis in analyses:
            if not isinstance(analysis, dict) or analysis.get("passed") is not True:
                blockers.add("SIM.ADMISSION.ANALYSIS")
                continue
            if not _ANALYSIS_REQUIRED_FIELDS <= set(analysis) or not set(analysis) <= _ANALYSIS_FIELDS:
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if not isinstance(analysis.get("outputs"), dict):
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if "inputs" in analysis and not isinstance(analysis.get("inputs"), dict):
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if "validity_assumptions" in analysis and not isinstance(analysis.get("validity_assumptions"), list):
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if "analysis_id" in analysis:
                try:
                    validate_identifier(analysis.get("analysis_id"), "analysis.analysis_id")
                except ValueError:
                    blockers.add("SIM.ADMISSION.MALFORMED")
                    continue
            if "evidence_level" in analysis and analysis.get("evidence_level") not in _ANALYTICAL_EVIDENCE_LEVELS:
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            name = analysis.get("name")
            version = analysis.get("version", "")
            if not isinstance(name, str) or not name or not isinstance(version, str):
                blockers.add("SIM.ADMISSION.ANALYSIS")
                continue
            identity = (name, version)
            if identity in seen_analyses:
                blockers.add("SIM.ADMISSION.MALFORMED")
                blockers.add("SIM.ADMISSION.ANALYSIS")
            seen_analyses.add(identity)

    claimed_blockers = hypothesis.get("blocking_diagnostics")
    claimed: set[str] = set()
    if not isinstance(claimed_blockers, list):
        blockers.add("SIM.ADMISSION.MALFORMED")
    else:
        for code in claimed_blockers:
            try:
                checked = validate_identifier(code, "blocking_diagnostics[]")
            except ValueError:
                blockers.add("SIM.ADMISSION.MALFORMED")
                continue
            if checked in claimed:
                blockers.add("SIM.ADMISSION.MALFORMED")
            claimed.add(checked)
    if claimed != physical_blockers:
        blockers.add("SIM.ADMISSION.BLOCKER_INVENTORY")

    blockers.update(physical_blockers)
    if not physical_blockers:
        blockers.add("SIM.ADMISSION.NO_PLACEHOLDER_BLOCKER")
    if any(code not in _ALLOWED_PLACEHOLDER_BLOCKERS for code in physical_blockers):
        blockers.add("SIM.ADMISSION.NONPLACEHOLDER")
    if physical.get("promotable") is not False:
        blockers.add("SIM.ADMISSION.PHYSICAL_STATE")

    return _decision(candidate, expected_hash, blockers)
