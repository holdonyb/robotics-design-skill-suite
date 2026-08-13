"""Bounded discrete uncertainty cases, sensitivity, and counterexamples."""

from __future__ import annotations

import copy
import hashlib
import itertools
import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from ..units import QuantityError, to_si
from .canonical import canonical_bytes, canonical_value, validate_candidate_id, validate_identifier, validate_integer


_TARGET_RE = re.compile(r"^quantity:([A-Za-z0-9][A-Za-z0-9_:/+@-]*)\.value$")
_MAX_EVALUATIONS = 1_000_000


class UncertaintyError(ValueError):
    """Raised for invalid uncertainty declarations or evaluation results."""


def _freeze(value: object) -> Any:
    checked = canonical_value(value)
    if isinstance(checked, dict):
        return MappingProxyType({key: _freeze(item) for key, item in checked.items()})
    if isinstance(checked, list):
        return tuple(_freeze(item) for item in checked)
    return checked


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _case_id(candidate_id: str, values: object) -> str:
    digest = hashlib.sha256(canonical_bytes({"candidate_id": candidate_id, "values": values})).hexdigest()
    return "case-" + digest[:24]


@dataclass(frozen=True)
class UncertaintyCase:
    candidate_id: str
    values: Mapping[str, object]
    nominal: bool
    hard: bool
    distance: float
    case_id: str = ""

    def __post_init__(self) -> None:
        try:
            candidate = validate_candidate_id(self.candidate_id)
            checked = canonical_value(self.values, "values")
        except ValueError as exc:
            raise UncertaintyError(str(exc)) from None
        if not isinstance(checked, dict):
            raise UncertaintyError("values must be an object")
        if type(self.nominal) is not bool or type(self.hard) is not bool:
            raise UncertaintyError("nominal and hard must be booleans")
        if not isinstance(self.distance, (int, float)) or isinstance(self.distance, bool) or not math.isfinite(float(self.distance)) or self.distance < 0:
            raise UncertaintyError("distance must be a finite non-negative number")
        if self.nominal != (not checked):
            raise UncertaintyError("nominal must be true exactly when values is empty")
        expected = _case_id(candidate, checked)
        if self.case_id and self.case_id != expected:
            raise UncertaintyError("case_id does not match candidate and values")
        object.__setattr__(self, "candidate_id", candidate)
        object.__setattr__(self, "values", _freeze(checked))
        object.__setattr__(self, "distance", float(self.distance))
        object.__setattr__(self, "case_id", expected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "candidate_id": self.candidate_id,
            "values": _thaw(self.values),
            "nominal": self.nominal,
            "hard": self.hard,
            "distance": self.distance,
        }


@dataclass(frozen=True)
class SensitivityRecord:
    case_id: str
    objective_deltas: Mapping[str, float]
    newly_blocking_diagnostic_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not re.fullmatch(r"case-[0-9a-f]{24}", self.case_id):
            raise UncertaintyError("case_id must match case-[0-9a-f]{24}")
        if not isinstance(self.objective_deltas, Mapping):
            raise UncertaintyError("objective_deltas must be an object")
        deltas: dict[str, float] = {}
        for key, value in self.objective_deltas.items():
            try:
                identifier = validate_identifier(key, "objective identifier")
            except ValueError as exc:
                raise UncertaintyError(str(exc)) from None
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise UncertaintyError(f"objective delta {identifier} must be finite")
            deltas[identifier] = float(value)
        codes = _diagnostic_codes(self.newly_blocking_diagnostic_codes, "newly_blocking_diagnostic_codes")
        object.__setattr__(self, "objective_deltas", MappingProxyType(dict(sorted(deltas.items()))))
        object.__setattr__(self, "newly_blocking_diagnostic_codes", codes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "objective_deltas": dict(self.objective_deltas),
            "newly_blocking_diagnostic_codes": list(self.newly_blocking_diagnostic_codes),
        }


@dataclass(frozen=True)
class CounterexampleResult:
    blocking: bool
    case: UncertaintyCase | None
    diagnostic_codes: tuple[str, ...]
    soft_risks: tuple[UncertaintyCase, ...]

    def __post_init__(self) -> None:
        if type(self.blocking) is not bool:
            raise UncertaintyError("blocking must be a boolean")
        if self.blocking != (self.case is not None):
            raise UncertaintyError("blocking must be true exactly when case is present")
        if self.case is not None and (not isinstance(self.case, UncertaintyCase) or not self.case.hard):
            raise UncertaintyError("blocking case must be a hard UncertaintyCase")
        codes = _diagnostic_codes(self.diagnostic_codes, "diagnostic_codes")
        if not isinstance(self.soft_risks, tuple) or any(not isinstance(item, UncertaintyCase) or item.hard for item in self.soft_risks):
            raise UncertaintyError("soft_risks must contain only soft UncertaintyCase records")
        object.__setattr__(self, "diagnostic_codes", codes)
        object.__setattr__(self, "soft_risks", tuple(sorted(self.soft_risks, key=lambda item: (item.distance, item.case_id))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocking": self.blocking,
            "case": None if self.case is None else self.case.to_dict(),
            "diagnostic_codes": list(self.diagnostic_codes),
            "soft_risks": [item.to_dict() for item in self.soft_risks],
        }


def _diagnostic_codes(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise UncertaintyError(f"{path} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise UncertaintyError(f"{path} must not contain duplicates")
    return tuple(sorted(value))


def _quantity_index(contract: object) -> dict[str, dict[str, Any]]:
    if not isinstance(contract, dict):
        raise UncertaintyError("contract must be an object")
    quantities = contract.get("quantities")
    if not isinstance(quantities, list):
        raise UncertaintyError("contract.quantities must be a list")
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(quantities):
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise UncertaintyError(f"contract.quantities[{index}] must have a string id")
        identifier = record["id"]
        if identifier in result:
            raise UncertaintyError(f"contract.quantities has duplicate id: {identifier}")
        if not isinstance(record.get("dimension"), str) or "value" not in record:
            raise UncertaintyError(f"contract quantity {identifier} must have dimension and value")
        try:
            to_si(record["value"], record["dimension"], f"quantity:{identifier}.value")
        except QuantityError as exc:
            raise UncertaintyError(str(exc)) from None
        result[identifier] = record
    return result


def _declarations(contract: object, uncertainties: object) -> list[dict[str, Any]]:
    quantities = _quantity_index(contract)
    if not isinstance(uncertainties, (list, tuple)):
        raise UncertaintyError("uncertainties must be a list")
    declared = []
    identifiers: set[str] = set()
    targets: set[str] = set()
    for index, raw in enumerate(uncertainties):
        path = f"uncertainties[{index}]"
        if not isinstance(raw, dict) or set(raw) != {"id", "target", "values", "hard"}:
            raise UncertaintyError(f"{path} must contain exactly id, target, values, and hard")
        try:
            identifier = validate_identifier(raw["id"], f"{path}.id")
        except ValueError as exc:
            raise UncertaintyError(str(exc)) from None
        if identifier in identifiers:
            raise UncertaintyError(f"uncertainties has duplicate id: {identifier}")
        identifiers.add(identifier)
        target = raw["target"]
        match = _TARGET_RE.fullmatch(target) if isinstance(target, str) else None
        if match is None:
            raise UncertaintyError(f"{path}.target must select quantity:ID.value")
        if target in targets:
            raise UncertaintyError(f"uncertainties has duplicate target: {target}")
        targets.add(target)
        quantity_id = match.group(1)
        if quantity_id not in quantities:
            raise UncertaintyError(f"uncertainty target {target} does not exist")
        if type(raw["hard"]) is not bool:
            raise UncertaintyError(f"{path}.hard must be a boolean")
        values = raw["values"]
        if not isinstance(values, (list, tuple)) or not values:
            raise UncertaintyError(f"{path}.values must be a non-empty list")
        quantity = quantities[quantity_id]
        nominal_si = to_si(quantity["value"], quantity["dimension"], target)
        nominal_unit = quantity["value"]["unit"]
        checked_values = []
        seen: set[bytes] = set()
        deviations = []
        for value_index, value in enumerate(values):
            try:
                checked = canonical_value(value, f"{path}.values[{value_index}]")
                si_value = to_si(checked, quantity["dimension"], f"{path}.values[{value_index}]")
            except (ValueError, QuantityError) as exc:
                raise UncertaintyError(str(exc)) from None
            if checked.get("unit") != nominal_unit:
                raise UncertaintyError(f"{path}.values[{value_index}] must preserve declared unit {nominal_unit}")
            encoded = canonical_bytes(checked)
            if encoded in seen:
                raise UncertaintyError(f"{path}.values has duplicate canonical value")
            seen.add(encoded)
            checked_values.append(checked)
            deviations.append(abs(si_value - nominal_si))
        declared.append({
            "id": identifier, "target": target, "values": tuple(checked_values), "hard": raw["hard"],
            "nominal_si": nominal_si, "dimension": quantity["dimension"], "max_deviation": max(deviations),
        })
    return sorted(declared, key=lambda item: item["id"])


def ordered_cases(candidate_id: object, contract: object, uncertainties: object, *, seed: object, max_evaluations: object) -> tuple[UncertaintyCase, ...]:
    """Create nominal plus a bounded Cartesian set in deterministic seeded order."""

    try:
        candidate = validate_candidate_id(candidate_id)
        checked_seed = validate_integer(seed, "seed")
        budget = validate_integer(max_evaluations, "max_evaluations", positive=True)
    except ValueError as exc:
        raise UncertaintyError(str(exc)) from None
    if budget > _MAX_EVALUATIONS:
        raise UncertaintyError(f"max_evaluations must be at most {_MAX_EVALUATIONS}")
    declarations = _declarations(contract, uncertainties)
    product = 1
    for declaration in declarations:
        count = len(declaration["values"])
        if product > (budget - 1) // count:
            raise UncertaintyError(f"uncertainty Cartesian product exceeds max_evaluations {budget}")
        product *= count
    total = 1 if not declarations else product + 1
    if total > budget:
        raise UncertaintyError(f"uncertainty evaluation count {total} exceeds max_evaluations {budget}")

    nominal = UncertaintyCase(candidate, {}, True, False, 0.0)
    if not declarations:
        return (nominal,)
    generated = []
    for selected in itertools.product(*(item["values"] for item in declarations)):
        values = {item["target"]: copy.deepcopy(value) for item, value in zip(declarations, selected)}
        distance_terms = []
        hard = False
        for item, value in zip(declarations, selected):
            observed = to_si(value, item["dimension"], item["target"])
            denominator = item["max_deviation"]
            deviation = abs(observed - item["nominal_si"])
            distance_terms.append(0.0 if denominator == 0 else deviation / denominator)
            hard = hard or (item["hard"] and deviation > 0.0)
        generated.append(UncertaintyCase(
            candidate, values, False, hard,
            math.sqrt(sum(value * value for value in distance_terms)),
        ))
    seed_payload = {"candidate_id": candidate, "seed": checked_seed}
    generated.sort(key=lambda item: (hashlib.sha256(canonical_bytes([seed_payload, item.case_id])).digest(), item.case_id))
    return (nominal, *generated)


def apply_case(contract: object, case: UncertaintyCase) -> dict[str, Any]:
    """Apply a case to a deep copy while preserving quantity unit and dimension."""

    quantities = _quantity_index(contract)
    if not isinstance(contract, dict) or not isinstance(case, UncertaintyCase):
        raise UncertaintyError("contract and case types are invalid")
    if contract.get("candidate_id") != case.candidate_id:
        raise UncertaintyError("case candidate_id does not match contract")
    result = copy.deepcopy(contract)
    result_by_id = {record["id"]: record for record in result["quantities"]}
    for target, raw_value in case.values.items():
        match = _TARGET_RE.fullmatch(target)
        if match is None or match.group(1) not in quantities:
            raise UncertaintyError(f"case target {target} does not exist")
        quantity = quantities[match.group(1)]
        value = _thaw(raw_value)
        try:
            to_si(value, quantity["dimension"], target)
        except QuantityError as exc:
            raise UncertaintyError(str(exc)) from None
        if value["unit"] != quantity["value"]["unit"]:
            raise UncertaintyError(f"case target {target} must preserve declared unit")
        result_by_id[match.group(1)]["value"] = value
    return result


def _outcome(callback: Callable[[UncertaintyCase], object], case: UncertaintyCase) -> dict[str, Any]:
    try:
        value = callback(case)
    except Exception as exc:
        raise UncertaintyError(f"evaluation callback failed for {case.case_id}: {exc}") from None
    if not isinstance(value, dict) or set(value) != {"promotable", "diagnostic_codes", "objectives"} or type(value.get("promotable")) is not bool:
        raise UncertaintyError(f"evaluation result for {case.case_id} must contain promotable, diagnostic_codes, and objectives")
    codes = _diagnostic_codes(value["diagnostic_codes"], "evaluation diagnostic_codes")
    objectives = value["objectives"]
    if not isinstance(objectives, dict):
        raise UncertaintyError("evaluation objectives must be an object")
    checked_objectives: dict[str, float] = {}
    for key, item in objectives.items():
        try:
            identifier = validate_identifier(key, "objective identifier")
        except ValueError as exc:
            raise UncertaintyError(str(exc)) from None
        if not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(float(item)):
            raise UncertaintyError(f"objective {identifier} must be finite")
        checked_objectives[identifier] = float(item)
    return {"promotable": value["promotable"], "diagnostic_codes": codes, "objectives": checked_objectives}


def _validate_cases(cases: object) -> tuple[UncertaintyCase, ...]:
    if not isinstance(cases, (list, tuple)) or not cases or any(not isinstance(item, UncertaintyCase) for item in cases):
        raise UncertaintyError("cases must be a non-empty list of UncertaintyCase records")
    checked = tuple(cases)
    nominal = [item for item in checked if item.nominal]
    if len(nominal) != 1 or checked[0] is not nominal[0]:
        raise UncertaintyError("cases must contain exactly one nominal case first")
    if len({item.case_id for item in checked}) != len(checked):
        raise UncertaintyError("cases contains duplicate case_id")
    if len({item.candidate_id for item in checked}) != 1:
        raise UncertaintyError("cases must belong to one candidate")
    return checked


def search_counterexample(cases: object, evaluate: Callable[[UncertaintyCase], object]) -> CounterexampleResult:
    """Return the nearest hard blocker and retain every failing soft case."""

    checked = _validate_cases(cases)
    if not callable(evaluate):
        raise UncertaintyError("evaluate must be callable")
    nominal_outcome = _outcome(evaluate, checked[0])
    if not nominal_outcome["promotable"]:
        raise UncertaintyError("candidate is already blocked at nominal case")
    evaluation_order = tuple(sorted(checked[1:], key=lambda item: (item.distance, item.case_id)))
    outcomes = {checked[0].case_id: nominal_outcome}
    outcomes.update({case.case_id: _outcome(evaluate, case) for case in evaluation_order})
    hard_failures = sorted(
        (case for case in checked[1:] if case.hard and not outcomes[case.case_id]["promotable"]),
        key=lambda item: (item.distance, item.case_id),
    )
    soft = tuple(
        case for case in checked[1:] if not case.hard and not outcomes[case.case_id]["promotable"]
    )
    selected = hard_failures[0] if hard_failures else None
    codes = () if selected is None else outcomes[selected.case_id]["diagnostic_codes"]
    return CounterexampleResult(selected is not None, selected, codes, soft)


def evaluate_sensitivity(cases: object, evaluate: Callable[[UncertaintyCase], object]) -> tuple[SensitivityRecord, ...]:
    """Compare every declared case with nominal objectives and blocking codes."""

    checked = _validate_cases(cases)
    if not callable(evaluate):
        raise UncertaintyError("evaluate must be callable")
    nominal = _outcome(evaluate, checked[0])
    singleton_values: dict[bytes, tuple[str, Any]] = {}
    for case in checked[1:]:
        for target, value in case.values.items():
            canonical = canonical_bytes({target: _thaw(value)})
            singleton_values.setdefault(canonical, (target, value))
    probes = tuple(
        UncertaintyCase(
            checked[0].candidate_id,
            {target: _thaw(value)},
            False,
            False,
            0.0,
        )
        for _, (target, value) in sorted(singleton_values.items())
    )
    records = []
    for case in probes:
        outcome = _outcome(evaluate, case)
        if set(outcome["objectives"]) != set(nominal["objectives"]):
            raise UncertaintyError(f"evaluation objectives for {case.case_id} do not match nominal")
        deltas = {key: outcome["objectives"][key] - nominal["objectives"][key] for key in nominal["objectives"]}
        newly_blocking = tuple(sorted(set(outcome["diagnostic_codes"]) - set(nominal["diagnostic_codes"]))) if not outcome["promotable"] else ()
        records.append(SensitivityRecord(case.case_id, deltas, newly_blocking))
    return tuple(sorted(records, key=lambda item: item.case_id))


__all__ = [
    "CounterexampleResult", "SensitivityRecord", "UncertaintyCase", "UncertaintyError",
    "apply_case", "evaluate_sensitivity", "ordered_cases", "search_counterexample",
]
