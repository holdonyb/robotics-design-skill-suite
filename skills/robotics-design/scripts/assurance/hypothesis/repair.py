"""Owner-correct immutable repair lineage for rejected robot hypotheses."""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..contract import validate_contract
from .canonical import canonical_bytes, validate_identifier, validate_integer
from .model import CandidateDecision
from .overlay import OverlayError, ResolvedCandidate, apply_operation
from .scheduler import KNOWN_STAGE_ORDER, default_registry


_QUANTITY_PATH = re.compile(r"(?:^|[./])quantity:([A-Za-z0-9][A-Za-z0-9_:/+@-]*)(?:[./]|$)")
_COMPONENT_PATH = re.compile(r"(?:^|[./])component:([A-Za-z0-9][A-Za-z0-9_:/+@-]*)(?:[./]|$)")
_FORBIDDEN_PREFIXES = (
    "requirement", "requirements", "assumption", "assumptions", "analysis",
    "analyses", "artifact", "artifacts", "schema_version", "candidate_id", "status",
)


class RepairError(ValueError):
    """Raised when a repair is ambiguous, unowned, cyclic, or over budget."""


@dataclass(frozen=True)
class RepairTrace:
    trigger_code: str
    trigger_path: str
    trigger_message: str
    owner: str
    rule_id: str
    before_hash: str
    after_hash: str
    rerun_stages: tuple[str, ...]
    outcome: str = "pending"
    remaining_blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("trigger_code", "trigger_path", "trigger_message", "owner", "rule_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise RepairError(f"{field_name} must be a non-empty string")
        if not re.fullmatch(r"[0-9a-f]{64}", self.before_hash) or not re.fullmatch(r"[0-9a-f]{64}", self.after_hash):
            raise RepairError("before_hash and after_hash must be SHA-256 digests")
        if not isinstance(self.rerun_stages, tuple) or any(stage not in KNOWN_STAGE_ORDER for stage in self.rerun_stages):
            raise RepairError("rerun_stages must contain known stages")
        if not isinstance(self.remaining_blockers, tuple) or any(not isinstance(item, str) or not item for item in self.remaining_blockers):
            raise RepairError("remaining_blockers must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_code": self.trigger_code,
            "trigger_path": self.trigger_path,
            "trigger_message": self.trigger_message,
            "owner": self.owner,
            "rule_id": self.rule_id,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "rerun_stages": list(self.rerun_stages),
            "outcome": self.outcome,
            "remaining_blockers": list(self.remaining_blockers),
        }


def _record(contract: dict[str, Any], collection: str, identifier: str) -> dict[str, Any]:
    values = contract.get(collection)
    if not isinstance(values, list):
        raise RepairError(f"contract {collection} must be a list")
    matches = [item for item in values if isinstance(item, dict) and item.get("id") == identifier]
    if len(matches) != 1:
        raise RepairError(f"repair owner target {collection}:{identifier} is missing or ambiguous")
    return matches[0]


def _owner(contract: dict[str, Any], diagnostic: dict[str, str]) -> tuple[str, set[str]]:
    path = diagnostic["path"]
    quantity_match = _QUANTITY_PATH.search(path)
    component_match = _COMPONENT_PATH.search(path)
    owned_targets: set[str] = set()
    if quantity_match:
        quantity_id = quantity_match.group(1)
        quantity = _record(contract, "quantities", quantity_id)
        owner = quantity.get("owner")
        if not isinstance(owner, str) or not owner.startswith("component:"):
            raise RepairError(f"diagnostic quantity {quantity_id} has no component owner")
        component_id = owner.removeprefix("component:")
        component = _record(contract, "components", component_id)
        owned_targets.update({f"quantity:{quantity_id}.value", f"quantity:{quantity_id}.tolerance", owner})
    elif component_match:
        component_id = component_match.group(1)
        component = _record(contract, "components", component_id)
        owner = f"component:{component_id}"
        owned_targets.add(owner)
        for quantity in contract.get("quantities", []):
            if isinstance(quantity, dict) and quantity.get("owner") == owner and isinstance(quantity.get("id"), str):
                owned_targets.update({f"quantity:{quantity['id']}.value", f"quantity:{quantity['id']}.tolerance"})
    else:
        raise RepairError("diagnostic path cannot resolve an authoritative owner")

    evidence_refs: set[str] = set()
    for key in ("source_evidence", "evidence"):
        value = component.get(key)
        if isinstance(value, str):
            evidence_refs.add(value)
        elif isinstance(value, list):
            evidence_refs.update(item for item in value if isinstance(item, str))
    for value in evidence_refs:
        evidence_id = value.removeprefix("evidence:")
        _record(contract, "evidence", evidence_id)
        owned_targets.add(f"evidence:{evidence_id}")
    return owner, owned_targets


def _checked_diagnostic(diagnostic: object) -> dict[str, str]:
    if not isinstance(diagnostic, dict) or not {"code", "path", "message"}.issubset(diagnostic):
        raise RepairError("diagnostic must contain code, path, and message")
    result = {key: diagnostic[key] for key in ("code", "path", "message")}
    if any(not isinstance(value, str) or not value.strip() for value in result.values()):
        raise RepairError("diagnostic code, path, and message must be non-empty strings")
    return result


def _checked_rule(rule: object) -> dict[str, Any]:
    fields = {"id", "diagnostic_code", "owner_prefix", "operations", "max_applications"}
    if not isinstance(rule, dict) or set(rule) != fields:
        raise RepairError("repair rule must contain exactly id, diagnostic_code, owner_prefix, operations, and max_applications")
    try:
        identifier = validate_identifier(rule["id"], "repair rule id")
        maximum = validate_integer(rule["max_applications"], "max_applications", positive=True)
    except ValueError as exc:
        raise RepairError(str(exc)) from None
    if maximum > 100:
        raise RepairError("max_applications must be at most 100")
    if not isinstance(rule["diagnostic_code"], str) or not rule["diagnostic_code"]:
        raise RepairError("diagnostic_code must be a non-empty string")
    if not isinstance(rule["owner_prefix"], str) or not rule["owner_prefix"]:
        raise RepairError("owner_prefix must be a non-empty string")
    if not isinstance(rule["operations"], list) or not rule["operations"]:
        raise RepairError("repair operations must be a non-empty list")
    result = copy.deepcopy(rule)
    result["id"] = identifier
    return result


def _preserves_replacement_obligations(
    contract: dict[str, Any], target: str, replacement: object
) -> None:
    if target.startswith("component:"):
        before = _record(contract, "components", target.removeprefix("component:"))
        obligation_fields = {
            "role", "state", "interfaces", "source_evidence", "limits",
            "supports_claims", "bindings",
        }
    elif target.startswith("evidence:"):
        before = _record(contract, "evidence", target.removeprefix("evidence:"))
        obligation_fields = {
            "kind", "level", "source", "supports", "authority", "certificate_id",
        }
    else:
        return
    if not isinstance(replacement, dict):
        raise RepairError(f"whole replacement for {target} must be an object")
    for field_name in sorted(obligation_fields & set(before)):
        if field_name not in replacement:
            raise RepairError(
                f"repair replacement for {target} deletes obligation field {field_name}"
            )
    for list_field in ("interfaces", "supports_claims", "bindings", "supports"):
        old_value = before.get(list_field)
        new_value = replacement.get(list_field)
        if isinstance(old_value, list) and (
            not isinstance(new_value, list) or not set(old_value).issubset(new_value)
        ):
            raise RepairError(
                f"repair replacement for {target} weakens obligation field {list_field}"
            )
    for fixed_field in (
        "role", "state", "source_evidence", "kind", "level", "authority",
        "certificate_id",
    ):
        if fixed_field in before and replacement.get(fixed_field) != before.get(fixed_field):
            raise RepairError(
                f"repair replacement for {target} may not rewrite obligation field {fixed_field}"
            )
    if "limits" in before and replacement.get("limits") != before.get("limits"):
        raise RepairError(f"repair replacement for {target} may not rewrite owned limits")
    if "source" in before and replacement.get("source") != before.get("source"):
        raise RepairError(f"repair replacement for {target} may not rewrite evidence source")


def _rerun_stages(failed_stage: str) -> tuple[str, ...]:
    if failed_stage not in KNOWN_STAGE_ORDER:
        raise RepairError(f"unknown stage: {failed_stage}")
    registry = default_registry()
    downstream = {failed_stage}
    changed = True
    while changed:
        changed = False
        for stage, spec in registry.items():
            if stage not in downstream and any(dep in downstream for dep in spec.dependencies):
                downstream.add(stage)
                changed = True
    return tuple(stage for stage in KNOWN_STAGE_ORDER if stage in downstream)


def repair(
    parent: object,
    diagnostic: object,
    rule: object,
    *,
    seen_hashes: object,
    failed_stage: str,
    rule_applications: Mapping[str, int] | None = None,
    depth: int = 0,
    max_depth: int = 100,
) -> tuple[ResolvedCandidate, RepairTrace]:
    """Apply one owner-authorized rule and return an immutable child and trace."""

    if not isinstance(parent, ResolvedCandidate):
        raise RepairError("parent must be a ResolvedCandidate")
    checked_diagnostic = _checked_diagnostic(diagnostic)
    checked_rule = _checked_rule(rule)
    if checked_rule["diagnostic_code"] != checked_diagnostic["code"]:
        raise RepairError("repair rule does not match diagnostic code")
    if not isinstance(seen_hashes, (set, frozenset)) or any(not isinstance(item, str) for item in seen_hashes):
        raise RepairError("seen_hashes must be a set of SHA-256 strings")
    try:
        checked_depth = validate_integer(depth, "depth")
        checked_max_depth = validate_integer(max_depth, "max_depth", positive=True)
    except ValueError as exc:
        raise RepairError(str(exc)) from None
    if checked_depth < 0 or checked_depth >= checked_max_depth:
        raise RepairError(f"global repair depth {checked_max_depth} would be exceeded")
    rerun_stages = _rerun_stages(failed_stage)
    applications = {} if rule_applications is None else dict(rule_applications)
    count = applications.get(checked_rule["id"], 0)
    if type(count) is not int or count < 0:
        raise RepairError("rule application count must be a non-negative integer")
    if count >= checked_rule["max_applications"]:
        raise RepairError(f"repair rule max_applications {checked_rule['max_applications']} reached")

    contract = parent.resolved_contract
    owner, allowed_targets = _owner(contract, checked_diagnostic)
    if not owner.startswith(checked_rule["owner_prefix"]):
        raise RepairError("repair rule owner_prefix does not match diagnostic owner")
    targets: list[str] = []
    for operation in checked_rule["operations"]:
        target = operation.get("target") if isinstance(operation, dict) else None
        if not isinstance(target, str):
            raise RepairError("repair operation target must be a string")
        if target.startswith(_FORBIDDEN_PREFIXES):
            raise RepairError(f"forbidden repair target: {target}")
        if target not in allowed_targets:
            raise RepairError(f"repair target {target} is outside diagnostic owner {owner}")
        if target in targets:
            raise RepairError(f"repair operations have duplicate target: {target}")
        targets.append(target)
        _preserves_replacement_obligations(contract, target, operation.get("value"))

    before_hash = hashlib.sha256(canonical_bytes({target: _target_value(contract, target) for target in sorted(targets)})).hexdigest()
    resolved = contract
    try:
        for operation in checked_rule["operations"]:
            resolved = apply_operation(resolved, operation)
    except OverlayError as exc:
        raise RepairError(str(exc)) from None
    operation_digest = hashlib.sha256(
        canonical_bytes(checked_rule["operations"])
    ).hexdigest()[:16]
    repair_identity = f"{checked_rule['id']}@{operation_digest}"
    decision = CandidateDecision(
        base_sha256=parent.decision.base_sha256,
        assignments=dict(parent.decision.assignments),
        seed=parent.decision.seed,
        parent_id=parent.candidate_id,
        repair_rule_id=repair_identity,
    )
    resolved["candidate_id"] = decision.candidate_id
    hash_payload = {key: value for key, value in resolved.items() if key != "candidate_id"}
    after_hash = hashlib.sha256(canonical_bytes(hash_payload)).hexdigest()
    if after_hash == parent.resolved_contract_sha256:
        raise RepairError("repair does not change resolved contract")
    lineage_hashes = set(parent.ancestry_resolution_hashes) | {
        parent.resolved_contract_sha256
    }
    if after_hash in lineage_hashes or after_hash in seen_hashes:
        raise RepairError(f"repair creates seen resolution hash cycle: {after_hash}")
    parent_errors = tuple(validate_contract(contract))
    child_errors = tuple(validate_contract(resolved))
    newly_introduced = sorted(set(child_errors) - set(parent_errors))
    if newly_introduced:
        raise RepairError(
            "repair introduces contract errors: " + "; ".join(newly_introduced)
        )
    child = ResolvedCandidate(
        decision,
        resolved,
        after_hash,
        child_errors,
        ancestry_resolution_hashes=(
            *parent.ancestry_resolution_hashes,
            parent.resolved_contract_sha256,
        ),
    )
    trace = RepairTrace(
        checked_diagnostic["code"],
        checked_diagnostic["path"],
        checked_diagnostic["message"],
        owner,
        checked_rule["id"],
        before_hash,
        after_hash,
        rerun_stages,
    )
    return child, trace


def _target_value(contract: dict[str, Any], target: str) -> Any:
    if target.startswith("quantity:"):
        prefix, field = target.rsplit(".", 1)
        record = _record(contract, "quantities", prefix.removeprefix("quantity:"))
        return copy.deepcopy(record.get(field))
    if target.startswith("component:"):
        return copy.deepcopy(_record(contract, "components", target.removeprefix("component:")))
    if target.startswith("evidence:"):
        return copy.deepcopy(_record(contract, "evidence", target.removeprefix("evidence:")))
    raise RepairError(f"unsupported repair target: {target}")


def select_repair(
    diagnostics: object,
    rules: object,
    *,
    stage_order: Iterable[str] = KNOWN_STAGE_ORDER,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select the earliest blocking diagnostic and lowest-ID matching rule."""

    if not isinstance(diagnostics, (list, tuple)) or not isinstance(rules, (list, tuple)):
        raise RepairError("diagnostics and rules must be lists")
    order = tuple(stage_order)
    if len(set(order)) != len(order) or any(stage not in KNOWN_STAGE_ORDER for stage in order):
        raise RepairError("stage_order must contain unique known stages")
    priority = {stage: index for index, stage in enumerate(order)}
    checked_diagnostics = []
    for input_index, raw in enumerate(diagnostics):
        diagnostic = _checked_diagnostic(raw)
        stage = raw.get("stage") if isinstance(raw, dict) else None
        severity = raw.get("severity") if isinstance(raw, dict) else None
        if stage not in priority:
            raise RepairError(f"unknown stage: {stage}")
        if severity not in {"error", "indeterminate"}:
            continue
        checked_diagnostics.append((priority[stage], diagnostic["code"], diagnostic["path"], diagnostic["message"], input_index, raw))
    if not checked_diagnostics:
        raise RepairError("no blocking diagnostic is available for repair")
    selected = min(checked_diagnostics, key=lambda item: item[:-1])[-1]
    matching = sorted(
        (_checked_rule(item) for item in rules if isinstance(item, dict) and item.get("diagnostic_code") == selected["code"]),
        key=lambda item: item["id"],
    )
    if not matching:
        raise RepairError(f"no repair rule matches diagnostic {selected['code']}")
    return copy.deepcopy(selected), matching[0]


__all__ = ["RepairError", "RepairTrace", "repair", "select_repair"]
