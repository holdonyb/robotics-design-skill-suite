"""Immutable semantic overlays and deterministic candidate generation."""

from __future__ import annotations

import copy
import hashlib
import itertools
import re
from dataclasses import dataclass, field
from typing import Any

from ..contract import validate_contract
from .canonical import canonical_bytes, canonical_value
from .model import CandidateDecision
from .schema import validate_space


_SEMANTIC_ID = r"[A-Za-z0-9][A-Za-z0-9_:/+@-]*"
_QUANTITY_TARGET = re.compile(rf"^quantity:({_SEMANTIC_ID})\.(value|tolerance)$")
_REPLACEMENT_TARGET = re.compile(r"^(component|evidence):([A-Za-z0-9][A-Za-z0-9_:/+@-]*)$")
_ARCHITECTURE_TARGETS = frozenset(
    {
        "architecture.features",
        "architecture.drive_units",
        "architecture.actuators",
        "architecture.moving_cables",
        "architecture.claimed_safety_functions",
    }
)


class OverlayError(ValueError):
    """Raised when a design overlay cannot be applied unambiguously."""


@dataclass(frozen=True)
class ResolvedCandidate:
    """A decision and its complete, content-addressed contract resolution."""

    decision: CandidateDecision
    _resolved_contract: dict[str, Any] = field(repr=False)
    resolved_contract_sha256: str
    contract_errors: tuple[str, ...]
    alias_of: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CandidateDecision):
            raise OverlayError("decision must be a CandidateDecision")
        try:
            checked = canonical_value(self._resolved_contract, "resolved_contract")
        except ValueError as exc:
            raise OverlayError(str(exc)) from None
        if not isinstance(checked, dict):
            raise OverlayError("resolved_contract must be an object")
        object.__setattr__(self, "_resolved_contract", checked)
        if (
            not isinstance(self.resolved_contract_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.resolved_contract_sha256)
        ):
            raise OverlayError("resolved_contract_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.contract_errors, tuple) or any(
            not isinstance(item, str) for item in self.contract_errors
        ):
            raise OverlayError("contract_errors must be a tuple of strings")
        object.__setattr__(self, "contract_errors", tuple(sorted(set(self.contract_errors))))

    @property
    def candidate_id(self) -> str:
        return self.decision.candidate_id

    @property
    def resolved_contract(self) -> dict[str, Any]:
        return copy.deepcopy(self._resolved_contract)


def _record_by_id(contract: dict[str, Any], collection: str, identifier: str) -> tuple[list[Any], int]:
    records = contract.get(collection)
    if not isinstance(records, list):
        raise OverlayError(f"contract {collection} must be a list")
    matches = [index for index, item in enumerate(records) if isinstance(item, dict) and item.get("id") == identifier]
    singular = {"quantities": "quantity", "components": "component", "evidence": "evidence"}[collection]
    target = f"{singular}:{identifier}"
    if not matches:
        raise OverlayError(f"semantic target {target} does not exist")
    if len(matches) != 1:
        raise OverlayError(f"semantic target {target} is not unique")
    return records, matches[0]


def apply_operation(base_contract: object, operation: object) -> dict[str, Any]:
    """Apply one closed operation to a deep copy of a complete contract."""

    if not isinstance(base_contract, dict):
        raise OverlayError("base contract must be an object")
    if not isinstance(operation, dict) or set(operation) != {"target", "value"}:
        raise OverlayError("operation must contain exactly target and value")
    target = operation.get("target")
    if not isinstance(target, str):
        raise OverlayError("operation target must be a string")
    try:
        value = canonical_value(operation.get("value"), "operation.value")
    except ValueError as exc:
        raise OverlayError(str(exc)) from None

    resolved = copy.deepcopy(base_contract)
    quantity = _QUANTITY_TARGET.fullmatch(target)
    replacement = _REPLACEMENT_TARGET.fullmatch(target)
    if quantity:
        identifier, field_name = quantity.groups()
        records, index = _record_by_id(resolved, "quantities", identifier)
        records[index][field_name] = copy.deepcopy(value)
        return resolved
    if replacement:
        collection, identifier = replacement.groups()
        if not isinstance(value, dict) or value.get("id") != identifier:
            raise OverlayError(f"replacement for {target} must be a whole object with the same id")
        collection_name = "components" if collection == "component" else "evidence"
        records, index = _record_by_id(resolved, collection_name, identifier)
        records[index] = copy.deepcopy(value)
        return resolved
    if target in _ARCHITECTURE_TARGETS:
        architecture = resolved.get("architecture")
        field_name = target.removeprefix("architecture.")
        if not isinstance(architecture, dict) or field_name not in architecture:
            raise OverlayError(f"semantic target {target} does not exist")
        if not isinstance(value, list):
            raise OverlayError(f"replacement for {target} must be a list")
        architecture[field_name] = copy.deepcopy(value)
        return resolved
    raise OverlayError(f"unsupported semantic target: {target}")


def _space_axes(space: dict[str, Any]) -> list[dict[str, Any]]:
    axes = space.get("axes")
    if not isinstance(axes, list):
        raise OverlayError("axes must be a list")
    return sorted(axes, key=lambda item: item["id"])


def generate_candidates(
    space: object,
    base_contract: object,
    *,
    seed: object,
) -> tuple[ResolvedCandidate, ...]:
    """Resolve the bounded Cartesian design space in canonical order."""

    errors = validate_space(space)
    if errors:
        raise OverlayError("invalid hypothesis space: " + "; ".join(errors))
    if not isinstance(space, dict) or not isinstance(base_contract, dict):
        raise OverlayError("space and base_contract must be objects")

    axes = _space_axes(space)
    choices_by_axis = [sorted(axis["choices"], key=lambda item: item["id"]) for axis in axes]
    product = 1
    for choices in choices_by_axis:
        product *= len(choices)
        if product > space["max_candidates"]:
            raise OverlayError(
                f"axes Cartesian product {product} exceeds max_candidates {space['max_candidates']}"
            )

    base_sha256 = space["base_contract"]["sha256"]
    resolved_candidates: list[ResolvedCandidate] = []
    first_by_hash: dict[str, str] = {}
    for selected in itertools.product(*choices_by_axis):
        assignments = {
            axis["id"]: choice["id"] for axis, choice in zip(axes, selected)
        }
        try:
            decision = CandidateDecision(
                base_sha256=base_sha256,
                assignments=assignments,
                seed=seed,
            )
        except ValueError as exc:
            raise OverlayError(str(exc)) from None

        resolved = copy.deepcopy(base_contract)
        for choice in selected:
            for operation in choice["operations"]:
                resolved = apply_operation(resolved, operation)
        resolved["candidate_id"] = decision.candidate_id
        contract_errors = tuple(validate_contract(resolved))
        hash_payload = {
            key: copy.deepcopy(value)
            for key, value in resolved.items()
            if key != "candidate_id"
        }
        resolved_sha256 = hashlib.sha256(canonical_bytes(hash_payload)).hexdigest()
        alias_of = first_by_hash.get(resolved_sha256)
        if alias_of is None:
            first_by_hash[resolved_sha256] = decision.candidate_id
        resolved_candidates.append(
            ResolvedCandidate(
                decision=decision,
                _resolved_contract=resolved,
                resolved_contract_sha256=resolved_sha256,
                contract_errors=contract_errors,
                alias_of=alias_of,
            )
        )
    return tuple(resolved_candidates)
