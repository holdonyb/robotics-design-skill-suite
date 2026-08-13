"""End-to-end bounded hypothesis orchestration and evidence publication."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from ..contract import validate_contract
from .bundle import BundleError, write_bundle_with_receipt
from .canonical import canonical_bytes, canonical_value, validate_integer
from .model import CandidateLineage, HypothesisResult
from .objectives import ObjectiveVector, extract_vector, pareto_fronts
from .overlay import OverlayError, ResolvedCandidate, generate_candidates
from .repair import RepairError, repair, select_repair
from .schema import load_space
from .scheduler import KNOWN_STAGE_ORDER, HypothesisScheduler, SchedulerError
from .uncertainty import (
    UncertaintyError,
    apply_case,
    evaluate_sensitivity,
    ordered_cases,
    search_counterexample,
)


_MAX_BASE_BYTES = 5 * 1024 * 1024
_TOOL_VERSION = "0.4.0"


class EngineError(ValueError):
    """Raised for actionable hypothesis-engine boundary failures."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {token}")


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number is not allowed: {token}")
    return value


def _parse_int(token: str) -> int:
    if len(token.removeprefix("-")) > 308:
        raise ValueError("JSON integers may contain at most 308 digits")
    return int(token)


def _load_base(space: dict[str, Any], source: Path) -> tuple[Path, dict[str, Any]]:
    record = space["base_contract"]
    root = source.parent.resolve()
    path = (root / record["path"]).resolve()
    try:
        if not path.is_relative_to(root):
            raise EngineError("base contract path escapes hypothesis-space directory")
        if path.stat().st_size > _MAX_BASE_BYTES:
            raise EngineError("base contract exceeds maximum size of 5 MiB")
        raw = path.read_bytes()
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_parse_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
        checked = canonical_value(data, "base contract")
    except EngineError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise EngineError(f"cannot load base contract: {exc}") from None
    if not isinstance(checked, dict):
        raise EngineError("base contract root must be an object")
    digest = hashlib.sha256(canonical_bytes(checked)).hexdigest()
    if digest != record["sha256"]:
        raise EngineError(
            "base contract SHA-256 mismatch: "
            f"declared {record['sha256']}, observed {digest}"
        )
    return path, checked


def _evaluation_key(
    candidate: ResolvedCandidate,
    space_sha256: str,
    stages: tuple[str, ...],
    tool_versions: dict[str, str],
) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "candidate_id": candidate.candidate_id,
                "resolved_contract_sha256": candidate.resolved_contract_sha256,
                "space_sha256": space_sha256,
                "stages": list(stages),
                "tool_versions": dict(sorted(tool_versions.items())),
            }
        )
    ).hexdigest()


def _physical_stage(stages: tuple[Any, ...]) -> Any | None:
    return next((stage for stage in stages if stage.name == "physical_v030"), None)


def _report(stage: Any | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    output = stage.to_dict().get("output")
    report = output.get("report") if isinstance(output, dict) else None
    return report if isinstance(report, dict) else None


def _diagnostic_codes(stage: Any | None) -> list[str]:
    if stage is None:
        return []
    return sorted(
        {
            item.get("code")
            for item in stage.to_dict().get("diagnostics", [])
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        }
    )


def _lineage(
    candidate: ResolvedCandidate,
    *,
    evaluation_key: str,
    status: str,
) -> CandidateLineage:
    return CandidateLineage(
        candidate_id=candidate.candidate_id,
        parent_id=candidate.decision.parent_id,
        assignments=dict(candidate.decision.assignments),
        repair_rule_id=candidate.decision.repair_rule_id,
        resolved_contract_sha256=candidate.resolved_contract_sha256,
        evaluation_key=evaluation_key,
        status=status,
        alias_of=candidate.alias_of,
    )


def _case_candidate(candidate: ResolvedCandidate, contract: dict[str, Any]) -> ResolvedCandidate:
    content = {key: value for key, value in contract.items() if key != "candidate_id"}
    digest = hashlib.sha256(canonical_bytes(content)).hexdigest()
    return ResolvedCandidate(
        candidate.decision,
        contract,
        digest,
        tuple(validate_contract(contract)),
        # Uncertainty probes are evaluations, not lineage children. A probe may
        # legitimately revisit an ancestor's content and must not be mistaken
        # for a repair cycle.
        ancestry_resolution_hashes=(),
    )


def _uncertainty_work(uncertainties: list[dict[str, Any]]) -> tuple[int, int]:
    """Return total cases and extra contract/physical case evaluations."""

    declarations = sorted(uncertainties, key=lambda item: item["id"])
    product = 1
    singleton_count = 0
    for declaration in declarations:
        value_count = len(declaration["values"])
        product *= value_count
        singleton_count += value_count
    # With one declaration, the Cartesian cases are exactly the singleton OAT
    # cases and share the memoized callback. With multiple declarations their
    # key sets differ, so the sets are disjoint.
    unique_non_nominal = product if len(declarations) == 1 else product + singleton_count
    return product + 1, 2 * unique_non_nominal


def _evaluate_uncertainties(
    candidate: ResolvedCandidate,
    physical: Any | None,
    report: dict[str, Any] | None,
    space: dict[str, Any],
    *,
    seed: int,
    scheduler: HypothesisScheduler,
    cache_dir: Path,
    files: dict[str, Any],
    vectors: dict[str, ObjectiveVector],
    blocking_diagnostics: list[dict[str, str]],
) -> bool:
    """Evaluate one candidate's uncertainty set and return hard-block status."""

    contract = candidate.resolved_contract
    candidate_id = candidate.candidate_id
    nominal_passed = physical is not None and physical.status == "passed"
    total_cases, _ = _uncertainty_work(space["uncertainties"])
    cases = ordered_cases(
        candidate_id,
        contract,
        space["uncertainties"],
        seed=seed,
        max_evaluations=total_cases,
    )
    files[f"candidates/{candidate_id}/cases.json"] = [
        case.to_dict() for case in cases
    ]
    if not nominal_passed:
        files[f"candidates/{candidate_id}/counterexample.json"] = {
            "status": "skipped",
            "reason": "nominal candidate is already blocked",
        }
        files[f"candidates/{candidate_id}/sensitivity.json"] = []
        return False

    outcomes: dict[str, dict[str, Any]] = {}

    def evaluate_case(case: Any) -> dict[str, Any]:
        if case.case_id in outcomes:
            return outcomes[case.case_id]
        if case.nominal:
            case_stage = physical
            case_report = report
            case_contract = contract
        else:
            case_contract = apply_case(contract, case)
            varied = _case_candidate(candidate, case_contract)
            case_stages = scheduler.evaluate(
                varied,
                cache_dir,
                stages=("contract_v1", "physical_v030"),
                uncertainty_case=case.to_dict(),
            )
            case_stage = _physical_stage(case_stages)
            case_report = _report(case_stage)
        objective_values: dict[str, float] = {}
        if case_report is not None and space["objectives"]:
            vector = extract_vector(
                candidate_id,
                case_contract,
                case_report,
                space["objectives"],
            )
            objective_values = dict(vector.values)
        outcomes[case.case_id] = {
            "promotable": case_stage is not None and case_stage.status == "passed",
            "diagnostic_codes": _diagnostic_codes(case_stage),
            "objectives": objective_values,
        }
        return outcomes[case.case_id]

    counterexample = search_counterexample(cases, evaluate_case)
    sensitivity = evaluate_sensitivity(cases, evaluate_case)
    hard_blocked = counterexample.blocking
    if hard_blocked and counterexample.case is not None:
        codes = counterexample.diagnostic_codes or (
            "HYP.UNCERTAINTY.HARD_COUNTEREXAMPLE",
        )
        for code in codes:
            blocking_diagnostics.append(
                {
                    "stage": "counterexample_v1",
                    "code": code,
                    "path": f"uncertainty:{counterexample.case.case_id}",
                    "message": "hard uncertainty case blocks candidate promotion",
                }
            )
    if hard_blocked and candidate_id in vectors:
        vector = vectors[candidate_id]
        vectors[candidate_id] = ObjectiveVector(
            candidate_id,
            dict(vector.values),
            {"candidate": "hard uncertainty counterexample blocks candidate"},
            False,
        )
        files[f"candidates/{candidate_id}/objectives.json"] = vectors[
            candidate_id
        ].to_dict()
    files[f"candidates/{candidate_id}/counterexample.json"] = (
        counterexample.to_dict()
    )
    files[f"candidates/{candidate_id}/sensitivity.json"] = [
        item.to_dict() for item in sensitivity
    ]
    return hard_blocked


def run_space(
    space_path: str | Path,
    output: str | Path,
    *,
    seed: object,
    force: bool = False,
) -> dict[str, Any]:
    """Evaluate a closed space and atomically publish a reproducible bundle."""

    source = Path(space_path)
    space, errors = load_space(source)
    if errors:
        raise EngineError("; ".join(errors))
    assert isinstance(space, dict)
    try:
        checked_seed = validate_integer(seed, "seed")
    except ValueError as exc:
        raise EngineError(str(exc)) from None
    base_path, base = _load_base(space, source)
    try:
        candidates = generate_candidates(space, base, seed=checked_seed)
    except OverlayError as exc:
        raise EngineError(str(exc)) from None

    declared_stages = tuple(space["evaluation"]["stages"])
    nonaliases = sum(candidate.alias_of is None for candidate in candidates)
    baseline_evaluations = nonaliases * len(declared_stages)
    maximum_evaluations = space["evaluation"]["max_stage_evaluations"]
    if baseline_evaluations > maximum_evaluations:
        raise EngineError(
            f"baseline stage evaluations {baseline_evaluations} exceed "
            f"max_stage_evaluations {maximum_evaluations}"
        )

    scheduler = HypothesisScheduler(
        max_stage_evaluations=maximum_evaluations,
        artifact_root=base_path.parent,
    )
    space_sha256 = hashlib.sha256(canonical_bytes(space)).hexdigest()
    tool_versions = dict(sorted(scheduler.tool_versions.items()))
    tool_versions["hypothesis_engine"] = _TOOL_VERSION
    files: dict[str, Any] = {}
    lineage: list[CandidateLineage] = []
    vectors: dict[str, ObjectiveVector] = {}
    screening_vectors: dict[str, ObjectiveVector] = {}
    canonical_keys: dict[str, str] = {}
    blocking_diagnostics: list[dict[str, str]] = []
    accepted_count = 0

    try:
        with tempfile.TemporaryDirectory(prefix="hypothesis-cache-") as cache_raw:
            cache_dir = Path(cache_raw)
            processed_nonaliases = 0
            for candidate in candidates:
                contract = candidate.resolved_contract
                candidate_id = candidate.candidate_id
                files[f"candidates/{candidate_id}/contract.json"] = contract

                if candidate.alias_of is not None:
                    target_key = canonical_keys.get(candidate.alias_of)
                    if target_key is None:
                        raise EngineError(
                            f"alias target was not evaluated before alias: {candidate.alias_of}"
                        )
                    lineage.append(
                        _lineage(candidate, evaluation_key=target_key, status="alias")
                    )
                    continue

                future_nonaliases = nonaliases - processed_nonaliases - 1
                processed_nonaliases += 1
                evaluation_key = _evaluation_key(
                    candidate, space_sha256, declared_stages, tool_versions
                )
                canonical_keys[candidate_id] = evaluation_key
                stages = scheduler.evaluate(
                    candidate, cache_dir, stages=declared_stages
                )
                files[f"candidates/{candidate_id}/stages.json"] = [
                    stage.to_dict() for stage in stages
                ]
                for emitted_stage in stages:
                    for diagnostic in emitted_stage.to_dict().get("diagnostics", []):
                        if (
                            isinstance(diagnostic, dict)
                            and diagnostic.get("severity") in {"error", "indeterminate"}
                            and all(
                                isinstance(diagnostic.get(field), str)
                                and diagnostic[field]
                                for field in ("code", "path", "message")
                            )
                        ):
                            blocking_diagnostics.append(
                                {
                                    "stage": emitted_stage.name,
                                    "code": diagnostic["code"],
                                    "path": diagnostic["path"],
                                    "message": diagnostic["message"],
                                }
                            )
                physical = _physical_stage(stages)
                report = _report(physical)
                nominal_passed = physical is not None and physical.status == "passed"
                hard_blocked = False

                if report is not None and space["objectives"]:
                    vector = extract_vector(
                        candidate_id, contract, report, space["objectives"]
                    )
                    vectors[candidate_id] = vector
                    files[f"candidates/{candidate_id}/objectives.json"] = vector.to_dict()
                    blocking_codes = {
                        item.get("code")
                        for item in report.get("diagnostics", [])
                        if isinstance(item, dict)
                        and item.get("severity") in {"error", "indeterminate"}
                    }
                    analyses_pass = all(
                        isinstance(item, dict) and item.get("passed") is True
                        for item in report.get("analyses", [])
                    )
                    if (
                        analyses_pass
                        and blocking_codes == {"BOM.PLACEHOLDER_BLOCKS_CLAIM"}
                        and set(vector.values)
                        == {item["id"] for item in space["objectives"]}
                    ):
                        screening_vectors[candidate_id] = ObjectiveVector(
                            candidate_id, dict(vector.values), {}, True
                        )

                if space["uncertainties"]:
                    total_cases, required_extra = _uncertainty_work(
                        space["uncertainties"]
                    )
                    reserved_for_future = future_nonaliases * len(declared_stages)
                    available_extra = (
                        maximum_evaluations
                        - scheduler.evaluation_count
                        - reserved_for_future
                    )
                    if nominal_passed and required_extra > available_extra:
                        raise EngineError(
                            "uncertainty evaluations require "
                            f"{required_extra} stage evaluations but only "
                            f"{max(0, available_extra)} remain after reserving "
                            f"{reserved_for_future} for future nominal candidates"
                        )
                    hard_blocked = _evaluate_uncertainties(
                        candidate,
                        physical,
                        report,
                        space,
                        seed=checked_seed,
                        scheduler=scheduler,
                        cache_dir=cache_dir,
                        files=files,
                        vectors=vectors,
                        blocking_diagnostics=blocking_diagnostics,
                    )

                accepted = nominal_passed and not hard_blocked
                accepted_count += int(accepted)
                lineage.append(
                    _lineage(
                        candidate,
                        evaluation_key=evaluation_key,
                        status="accepted" if accepted else "rejected",
                    )
                )

                if (
                    not nominal_passed
                    and physical is not None
                    and space["repair_rules"]
                    and len(lineage) < space["max_candidates"]
                ):
                    minimum_child_stages = sum(
                        stage == "contract_v1"
                        or stage
                        in {
                            "physical_v030",
                            "uncertainty_v1",
                            "counterexample_v1",
                            "objectives_v1",
                        }
                        for stage in declared_stages
                    )
                    if space["uncertainties"]:
                        _, uncertainty_stages = _uncertainty_work(
                            space["uncertainties"]
                        )
                        minimum_child_stages += uncertainty_stages
                    reserved_for_future = future_nonaliases * len(declared_stages)
                    available_for_repair = (
                        maximum_evaluations
                        - scheduler.evaluation_count
                        - reserved_for_future
                    )
                    candidate_capacity = (
                        space["max_candidates"] - len(lineage) - future_nonaliases
                    )
                    if (
                        candidate_capacity <= 0
                        or available_for_repair < minimum_child_stages
                    ):
                        files[f"candidates/{candidate_id}/repair-skipped.json"] = {
                            "status": "skipped",
                            "reason": (
                                "repair budget reserved for future nominal candidates"
                            ),
                            "available_stage_evaluations": max(
                                0, available_for_repair
                            ),
                            "required_stage_evaluations": minimum_child_stages,
                            "available_candidate_slots": max(0, candidate_capacity),
                        }
                        continue
                    diagnostics = [
                        dict(item, stage="physical_v030")
                        for item in physical.to_dict().get("diagnostics", [])
                        if isinstance(item, dict)
                    ]
                    repairable_codes = {
                        rule["diagnostic_code"] for rule in space["repair_rules"]
                    }
                    repairable_diagnostics = [
                        item
                        for item in diagnostics
                        if item.get("code") in repairable_codes
                    ]
                    try:
                        diagnostic, rule = select_repair(
                            repairable_diagnostics, space["repair_rules"]
                        )
                        child, trace = repair(
                            candidate,
                            diagnostic,
                            rule,
                            seen_hashes={candidate.resolved_contract_sha256},
                            failed_stage="physical_v030",
                        )
                    except RepairError:
                        child = None
                    if child is not None:
                        child_stages_requested = tuple(
                            stage
                            for stage in declared_stages
                            if stage == "contract_v1" or stage in trace.rerun_stages
                        )
                        if "contract_v1" not in child_stages_requested:
                            child_stages_requested = (
                                "contract_v1",
                                *child_stages_requested,
                            )
                        child_stages = scheduler.evaluate(
                            child, cache_dir, stages=child_stages_requested
                        )
                        child_id = child.candidate_id
                        child_physical = _physical_stage(child_stages)
                        child_report = _report(child_physical)
                        child_nominal_passed = (
                            child_physical is not None
                            and child_physical.status == "passed"
                        )
                        child_key = _evaluation_key(
                            child,
                            space_sha256,
                            child_stages_requested,
                            tool_versions,
                        )
                        files[f"candidates/{child_id}/contract.json"] = (
                            child.resolved_contract
                        )
                        files[f"candidates/{child_id}/stages.json"] = [
                            stage.to_dict() for stage in child_stages
                        ]
                        trace_data = trace.to_dict()
                        trace_data["remaining_blockers"] = _diagnostic_codes(
                            child_physical
                        )
                        if child_report is not None and space["objectives"]:
                            child_vector = extract_vector(
                                child_id,
                                child.resolved_contract,
                                child_report,
                                space["objectives"],
                            )
                            vectors[child_id] = child_vector
                            files[f"candidates/{child_id}/objectives.json"] = (
                                child_vector.to_dict()
                            )
                        child_hard_blocked = False
                        if space["uncertainties"]:
                            child_hard_blocked = _evaluate_uncertainties(
                                child,
                                child_physical,
                                child_report,
                                space,
                                seed=checked_seed,
                                scheduler=scheduler,
                                cache_dir=cache_dir,
                                files=files,
                                vectors=vectors,
                                blocking_diagnostics=blocking_diagnostics,
                            )
                        child_accepted = (
                            child_nominal_passed and not child_hard_blocked
                        )
                        trace_data["outcome"] = (
                            "accepted" if child_accepted else "rejected"
                        )
                        if child_hard_blocked:
                            trace_data["remaining_blockers"] = [
                                "HYP.UNCERTAINTY.HARD_COUNTEREXAMPLE"
                            ]
                        files[f"candidates/{child_id}/repair-trace.json"] = trace_data
                        lineage.append(
                            _lineage(
                                child,
                                evaluation_key=child_key,
                                status=(
                                    "accepted" if child_accepted else "rejected"
                                ),
                            )
                        )
                        accepted_count += int(child_accepted)

        directions = {
            item["id"]: item["direction"] for item in space["objectives"]
        }
        pareto = (
            pareto_fronts(vectors, directions).to_dict()
            if directions
            else {"fronts": [], "dominance_edges": [], "ineligible": []}
        )
        files["pareto.json"] = pareto
        screening_pareto = (
            pareto_fronts(screening_vectors, directions).to_dict()
            if directions and screening_vectors
            else {"fronts": [], "dominance_edges": [], "ineligible": []}
        )
        files["screening-pareto.json"] = screening_pareto
        result = HypothesisResult(
            space_id=space["space_id"],
            space_sha256=space_sha256,
            seed=checked_seed,
            candidates=tuple(lineage),
            stages=(),
            metadata={
                "schema_version": 1,
                "tool_versions": tool_versions,
                "candidate_count": len(lineage),
                "accepted_count": accepted_count,
                "stage_evaluations": scheduler.evaluation_count,
            },
        )
        index = result.to_dict()
        index["schema_version"] = 1
        index["candidate_count"] = len(lineage)
        index["accepted_count"] = accepted_count
        index["tool_versions"] = tool_versions
        files["index.json"] = index
        receipt = write_bundle_with_receipt(output, files, force=force)
        index["bundle_manifest_sha256"] = receipt.manifest_sha256
        index["pareto_front_count"] = len(pareto["fronts"])
        if blocking_diagnostics:
            stage_order = {
                stage: index for index, stage in enumerate(KNOWN_STAGE_ORDER)
            }
            index["earliest_blocking_diagnostic"] = sorted(
                blocking_diagnostics,
                key=lambda item: (
                    stage_order[item["stage"]],
                    item["code"],
                    item["path"],
                    item["message"],
                ),
            )[0]
        return index
    except EngineError:
        raise
    except (
        BundleError,
        OverlayError,
        RepairError,
        SchedulerError,
        UncertaintyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise EngineError(str(exc)) from None
