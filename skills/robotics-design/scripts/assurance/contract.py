"""Structural and semantic validation for robot design contract schema v1."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .model import EvidenceLevel
from .plugin_contracts import validate_plugin_inputs
from .units import QuantityError, to_si


SCHEMA_VERSION = 1
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STATUSES = frozenset({"draft", "rejected", "promoted"})
CONFIDENCE = frozenset({"low", "medium", "high"})
COMPONENT_STATES = frozenset(
    {"verified_part", "qualified_substitute", "engineering_placeholder", "missing"}
)
ROLE_LIMIT_DIMENSIONS: dict[str, dict[str, str]] = {
    "traction_motor": {
        "continuous_torque": "torque",
        "peak_torque": "torque",
        "max_speed": "angular_velocity",
        "continuous_current": "current",
        "winding_resistance": "resistance",
        "thermal_resistance": "thermal_resistance",
        "max_winding_temperature": "temperature",
    },
    "motor": {
        "continuous_torque": "torque",
        "peak_torque": "torque",
        "max_speed": "angular_velocity",
        "continuous_current": "current",
        "winding_resistance": "resistance",
        "thermal_resistance": "thermal_resistance",
        "max_winding_temperature": "temperature",
    },
    "reducer": {
        "gear_ratio": "dimensionless",
        "efficiency": "dimensionless",
        "continuous_output_torque": "torque",
    },
    "wheel": {"radius": "length", "rated_load": "force"},
    "bearing": {
        "static_load": "force",
        "dynamic_load": "force",
        "pitch_diameter": "length",
    },
    "motor_driver": {"continuous_current": "current", "peak_current": "current"},
    "battery": {
        "nominal_voltage": "voltage",
        "continuous_current": "current",
        "peak_current": "current",
        "usable_energy": "energy",
    },
    "bms": {"continuous_current": "current", "peak_current": "current"},
    "main_protection": {"rated_current": "current"},
    "contactor": {"continuous_current": "current"},
    "dc_converter": {"continuous_power": "power"},
    "brake": {"holding_torque": "torque"},
    "cable": {"continuous_current": "current", "bend_radius": "length"},
    "connector": {"continuous_current": "current"},
    "strain_relief": {"retention_force": "force"},
    "cable_management": {"minimum_bend_radius": "length"},
}
for _role_limits in ROLE_LIMIT_DIMENSIONS.values():
    _role_limits["mass"] = "mass"
ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "status",
        "requirements",
        "assumptions",
        "quantities",
        "components",
        "architecture",
        "artifacts",
        "analyses",
        "evidence",
    }
)
RECORD_FIELDS = {
    "requirements": frozenset({"id", "statement", "verification", "owner"}),
    "assumptions": frozenset(
        {
            "id",
            "statement",
            "confidence",
            "owner",
            "validation",
            "decision_deadline",
        }
    ),
    "quantities": frozenset(
        {
            "id",
            "dimension",
            "value",
            "owner",
            "source",
            "evidence_level",
            "tolerance",
            "observation",
        }
    ),
    "components": frozenset(
        {
            "id",
            "role",
            "state",
            "interfaces",
            "manufacturer",
            "part_number",
            "source_url",
            "source_date",
            "source_evidence",
            "limits",
            "supports_claims",
            "bindings",
        }
    ),
    "artifacts": frozenset({"id", "kind", "path", "sha256"}),
    "analyses": frozenset({"id", "plugin", "covers", "inputs"}),
    "evidence": frozenset(
        {
            "id",
            "kind",
            "level",
            "source",
            "locator",
            "observed_date",
            "supports",
            "authority",
            "certificate_id",
        }
    ),
}
ARCHITECTURE_FIELDS = frozenset(
    {"features", "drive_units", "actuators", "moving_cables", "claimed_safety_functions"}
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_safe_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and hostname not in {"localhost", "127.0.0.1", "::1"}
        and not hostname.endswith((".invalid", ".localhost", ".test"))
    )


def _parse_past_or_present_date(value: Any) -> tuple[date | None, str | None]:
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, "must be an ISO calendar date"
    if parsed > date.today():
        return parsed, "must not be in the future"
    return parsed, None


def _unknown_fields(
    value: dict[str, Any], allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")


def _records(data: dict[str, Any], name: str, errors: list[str]) -> list[dict[str, Any]]:
    value = data.get(name)
    if not isinstance(value, list):
        errors.append(f"{name} must be a list")
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        path = f"{name}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        _unknown_fields(item, RECORD_FIELDS[name], path, errors)
        record_id = item.get("id")
        if not _nonempty(record_id) or not ID.fullmatch(record_id):
            errors.append(f"{path}.id must match {ID.pattern}")
        elif record_id in seen:
            errors.append(f"{name} has duplicate id {record_id}")
        else:
            seen.add(record_id)
        records.append(item)
    return records


def _string_list(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty(item) for item in value):
        errors.append(f"{path} must be a list of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{path} must not contain duplicates")
    return value


def _file_record(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must contain path and sha256")
        return
    unknown = sorted(set(value) - {"path", "sha256"})
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")
    raw_path = value.get("path")
    digest = value.get("sha256")
    if not _nonempty(raw_path):
        errors.append(f"{path}.path must be a non-empty relative path")
    else:
        candidate = PurePosixPath(raw_path.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"{path}.path must be a non-escaping relative path")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append(f"{path}.sha256 must be a lowercase SHA-256 digest")


def _validate_analysis_input(
    value: Any, path: str, quantity_ids: set[str], errors: list[str]
) -> None:
    if isinstance(value, str):
        if not value.strip():
            errors.append(f"{path} must not be an empty string")
        elif value.startswith("quantity:") and value[9:] not in quantity_ids:
            errors.append(f"{path} references unknown quantity: {value}")
        return
    if isinstance(value, dict):
        for key, child in sorted(value.items()):
            if not _nonempty(key):
                errors.append(f"{path} object keys must be non-empty strings")
            else:
                _validate_analysis_input(child, f"{path}.{key}", quantity_ids, errors)
        return
    if isinstance(value, list):
        if not value:
            errors.append(f"{path} list must not be empty")
        for index, child in enumerate(value):
            _validate_analysis_input(child, f"{path}[{index}]", quantity_ids, errors)
        return
    errors.append(
        f"{path} must use quantity references for physical values; bare literals are forbidden"
    )


def validate_contract(data: Any) -> list[str]:
    """Return sorted actionable errors for schema v1; empty means valid."""

    if not isinstance(data, dict):
        return ["contract root must be a JSON object"]

    errors: list[str] = []
    _unknown_fields(data, ROOT_FIELDS, "root", errors)
    schema_version = data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != SCHEMA_VERSION
    ):
        errors.append("schema_version must be integer 1")
    if not _nonempty(data.get("candidate_id")) or not ID.fullmatch(
        str(data.get("candidate_id", ""))
    ):
        errors.append(f"candidate_id must match {ID.pattern}")
    if not isinstance(data.get("status"), str) or data.get("status") not in STATUSES:
        errors.append("status must be one of: draft, promoted, rejected")

    collections = {
        name: _records(data, name, errors)
        for name in RECORD_FIELDS
    }
    obligation_collections = (
        "requirements",
        "quantities",
        "components",
        "artifacts",
        "analyses",
        "evidence",
    )
    if not any(collections[name] for name in obligation_collections):
        errors.append(
            "physical contract must contain at least one engineering obligation"
        )

    architecture = data.get("architecture")
    if not isinstance(architecture, dict):
        errors.append("architecture must be an object")
    else:
        _unknown_fields(architecture, ARCHITECTURE_FIELDS, "architecture", errors)
        for field in ARCHITECTURE_FIELDS:
            _string_list(architecture.get(field), f"architecture.{field}", errors)

    artifact_ids = {
        item.get("id") for item in collections["artifacts"] if _nonempty(item.get("id"))
    }
    component_ids = {
        item.get("id") for item in collections["components"] if _nonempty(item.get("id"))
    }
    evidence_ids = {
        item.get("id") for item in collections["evidence"] if _nonempty(item.get("id"))
    }
    evidence_by_id = {
        item.get("id"): item
        for item in collections["evidence"]
        if _nonempty(item.get("id"))
    }
    quantity_ids = {
        item.get("id") for item in collections["quantities"] if _nonempty(item.get("id"))
    }
    quantities_by_id = {
        item.get("id"): item
        for item in collections["quantities"]
        if _nonempty(item.get("id"))
    }
    requirement_ids = {
        item.get("id")
        for item in collections["requirements"]
        if _nonempty(item.get("id"))
    }
    known_owners = {"project:system"}
    known_owners.update(f"artifact:{item}" for item in artifact_ids)
    known_owners.update(f"component:{item}" for item in component_ids)
    architecture_responsibilities: set[str] = set()
    if isinstance(architecture, dict):
        for field, prefix in (
            ("features", "feature"),
            ("drive_units", "drive"),
            ("actuators", "actuator"),
            ("moving_cables", "moving_cable"),
            ("claimed_safety_functions", "safety_function"),
        ):
            values = architecture.get(field)
            if isinstance(values, list):
                architecture_responsibilities.update(
                    f"{prefix}:{item}" for item in values if _nonempty(item)
                )
    known_analysis_coverage = set(architecture_responsibilities)
    known_analysis_coverage.update(
        f"requirement:{item}" for item in requirement_ids
    )

    for name in ("requirements", "assumptions", "quantities"):
        for index, item in enumerate(collections[name]):
            owner = item.get("owner")
            if not isinstance(owner, str) or owner not in known_owners:
                errors.append(
                    f"{name}[{index}].owner references unknown owner: {owner}"
                )

    for index, item in enumerate(collections["requirements"]):
        for field in ("statement", "verification", "owner"):
            if not _nonempty(item.get(field)):
                errors.append(f"requirements[{index}].{field} must be a non-empty string")

    for index, item in enumerate(collections["assumptions"]):
        for field in ("statement", "owner", "validation", "decision_deadline"):
            if not _nonempty(item.get(field)):
                errors.append(f"assumptions[{index}].{field} must be a non-empty string")
        if (
            not isinstance(item.get("confidence"), str)
            or item.get("confidence") not in CONFIDENCE
        ):
            errors.append(
                f"assumptions[{index}].confidence must be one of: high, low, medium"
            )

    for index, item in enumerate(collections["quantities"]):
        dimension = item.get("dimension")
        if not _nonempty(dimension):
            errors.append(f"quantities[{index}].dimension must be a non-empty string")
        else:
            try:
                to_si(item.get("value"), dimension, f"quantities[{index}].value")
            except QuantityError as exc:
                errors.append(str(exc))
            if "tolerance" in item:
                try:
                    to_si(
                        item.get("tolerance"),
                        dimension,
                        f"quantities[{index}].tolerance",
                    )
                except QuantityError as exc:
                    errors.append(str(exc))
        source = item.get("source")
        if (
            not isinstance(source, str)
            or source not in {f"evidence:{item_id}" for item_id in evidence_ids}
        ):
            errors.append(f"quantities[{index}].source references unknown evidence: {source}")
        try:
            EvidenceLevel(item.get("evidence_level"))
        except (TypeError, ValueError):
            errors.append(f"quantities[{index}].evidence_level is invalid")
        observation = item.get("observation")
        if observation is not None:
            if not _nonempty(observation) or not re.fullmatch(
                r"artifact:[A-Za-z][A-Za-z0-9_.-]*#[A-Za-z0-9_.-]+",
                observation,
            ):
                errors.append(
                    f"quantities[{index}].observation must be artifact:ID#normalized.path"
                )
            elif observation.split("#", 1)[0][9:] not in artifact_ids:
                errors.append(
                    f"quantities[{index}].observation references unknown artifact: {observation}"
                )

    for index, item in enumerate(collections["components"]):
        for field in ("role", "state"):
            if not _nonempty(item.get(field)):
                errors.append(f"components[{index}].{field} must be a non-empty string")
        if (
            not isinstance(item.get("state"), str)
            or item.get("state") not in COMPONENT_STATES
        ):
            errors.append(
                f"components[{index}].state must be a supported component state"
            )
        _string_list(item.get("interfaces"), f"components[{index}].interfaces", errors)
        bindings = _string_list(
            item.get("bindings"), f"components[{index}].bindings", errors
        )
        for binding in bindings:
            if binding not in architecture_responsibilities:
                errors.append(
                    f"components[{index}].bindings references unknown architecture responsibility: {binding}"
                )
        component_state = item.get("state")
        verified_component = isinstance(component_state, str) and component_state in {
            "verified_part",
            "qualified_substitute",
        }
        if "supports_claims" in item or verified_component:
            supported_claims = _string_list(
                item.get("supports_claims"),
                f"components[{index}].supports_claims",
                errors,
            )
            if verified_component and not supported_claims:
                errors.append(
                    f"components[{index}].supports_claims must be a non-empty claim edge for verified components"
                )
            for claim_id in supported_claims:
                if claim_id not in requirement_ids:
                    errors.append(
                        f"components[{index}].supports_claims references unknown "
                        f"requirement: {claim_id}"
                    )
        if verified_component:
            source_url = item.get("source_url")
            if not _is_safe_http_url(source_url):
                errors.append(
                    f"components[{index}].source_url must be an absolute HTTP(S) URL"
                )
            source_date = item.get("source_date")
            _, source_date_error = _parse_past_or_present_date(source_date)
            if source_date_error:
                errors.append(
                    f"components[{index}].source_date {source_date_error}"
                )
            source_evidence = item.get("source_evidence")
            evidence_id = (
                source_evidence[9:]
                if isinstance(source_evidence, str)
                and source_evidence.startswith("evidence:")
                else None
            )
            component_evidence = evidence_by_id.get(evidence_id)
            if component_evidence is None:
                errors.append(
                    f"components[{index}].source_evidence must reference an existing evidence record"
                )
            else:
                supported_target = f"component:{item.get('id')}"
                supports = component_evidence.get("supports", [])
                if not isinstance(supports, list) or supported_target not in supports:
                    errors.append(
                        f"components[{index}].source_evidence {source_evidence} does not support {supported_target}"
                    )
                try:
                    component_level = EvidenceLevel(component_evidence.get("level"))
                except (TypeError, ValueError):
                    component_level = None
                if component_evidence.get("kind") != "component_catalog_v1":
                    errors.append(
                        f"components[{index}].source evidence kind must be component_catalog_v1"
                    )
                if component_level not in {
                    EvidenceLevel.PARSED,
                    EvidenceLevel.CERTIFIED,
                }:
                    errors.append(
                        f"components[{index}].source_evidence must use parsed or certified provenance evidence"
                    )
                if component_evidence.get("locator") != source_url:
                    errors.append(
                        f"components[{index}].source_evidence locator must match component source_url"
                    )
                if component_evidence.get("observed_date") != source_date:
                    errors.append(
                        f"components[{index}].source_evidence observed_date must match component source_date"
                    )
            limits = item.get("limits")
            if not isinstance(limits, dict) or not limits:
                errors.append(f"components[{index}].limits must be a non-empty object")
            else:
                role = item.get("role")
                role_schema = ROLE_LIMIT_DIMENSIONS.get(role, {})
                unsupported_limits = sorted(set(limits) - set(role_schema))
                if unsupported_limits:
                    errors.append(
                        f"components[{index}].limits has unsupported fields for role {role}: "
                        + ", ".join(unsupported_limits)
                    )
                for limit_name, reference in sorted(limits.items()):
                    limit_path = f"components[{index}].limits.{limit_name}"
                    if not _nonempty(limit_name):
                        errors.append(
                            f"components[{index}].limits keys must be non-empty strings"
                        )
                        continue
                    if (
                        not isinstance(reference, str)
                        or not reference.startswith("quantity:")
                        or reference[9:] not in quantity_ids
                    ):
                        errors.append(
                            f"{limit_path} must reference a quantity owned by the component"
                        )
                        continue
                    quantity = quantities_by_id[reference[9:]]
                    if quantity.get("owner") != f"component:{item.get('id')}":
                        errors.append(
                            f"{limit_path} quantity must be owned by component:{item.get('id')}"
                        )
                    if source_evidence is not None and quantity.get("source") != source_evidence:
                        errors.append(
                            f"{limit_path} quantity must use the component source evidence {source_evidence}"
                        )
                    try:
                        limit_level = EvidenceLevel(quantity.get("evidence_level"))
                    except (TypeError, ValueError):
                        limit_level = None
                    if limit_level not in {
                        EvidenceLevel.PARSED,
                        EvidenceLevel.CERTIFIED,
                    }:
                        errors.append(
                            f"{limit_path} limit quantity evidence_level must be parsed or certified"
                        )
                    expected_dimension = role_schema.get(limit_name)
                    if (
                        expected_dimension is not None
                        and quantity.get("dimension") != expected_dimension
                    ):
                        errors.append(
                            f"{limit_path} expects dimension {expected_dimension}, "
                            f"but {reference} declares {quantity.get('dimension')}"
                        )

    for index, item in enumerate(collections["artifacts"]):
        if not _nonempty(item.get("kind")):
            errors.append(f"artifacts[{index}].kind must be a non-empty string")
        _file_record(
            {"path": item.get("path"), "sha256": item.get("sha256")},
            f"artifacts[{index}]",
            errors,
        )

    for index, item in enumerate(collections["analyses"]):
        plugin = item.get("plugin")
        if not _nonempty(plugin):
            errors.append(f"analyses[{index}].plugin must be a non-empty string")
        inputs = item.get("inputs")
        if not isinstance(inputs, dict):
            errors.append(f"analyses[{index}].inputs must be an object")
            continue
        covers = _string_list(
            item.get("covers"), f"analyses[{index}].covers", errors
        )
        for coverage in covers:
            if coverage not in known_analysis_coverage:
                errors.append(
                    f"analyses[{index}].covers references unknown responsibility: {coverage}"
                )
        # Component mass closure owns its fully closed nested grammar, including a
        # legitimate empty ``components`` list before a placeholder is replaced by
        # a selected part.  Its plug-in validator below still verifies every
        # quantity reference and rejects all other malformed shapes.
        if plugin != "component_mass_closure_v1":
            for name, reference in sorted(inputs.items()):
                if not _nonempty(name):
                    errors.append(f"analyses[{index}].inputs keys must be non-empty strings")
                else:
                    _validate_analysis_input(
                        reference,
                        f"analyses[{index}].inputs.{name}",
                        quantity_ids,
                        errors,
                    )
        errors.extend(
            validate_plugin_inputs(
                item.get("plugin"),
                inputs,
                quantities_by_id,
                f"analyses[{index}]({item.get('plugin')}).inputs",
            )
        )

    known_supports = {f"quantity:{item_id}" for item_id in quantity_ids}
    known_supports.update(f"artifact:{item_id}" for item_id in artifact_ids)
    known_supports.update(f"component:{item_id}" for item_id in component_ids)
    evidence_levels: dict[str, EvidenceLevel] = {}
    for index, item in enumerate(collections["evidence"]):
        try:
            level = EvidenceLevel(item.get("level"))
            if _nonempty(item.get("id")):
                evidence_levels[item["id"]] = level
        except (TypeError, ValueError):
            level = None
            errors.append(f"evidence[{index}].level is invalid")
        _file_record(item.get("source"), f"evidence[{index}].source", errors)
        locator = item.get("locator")
        if locator is not None and not _is_safe_http_url(locator):
            errors.append(
                f"evidence[{index}].locator must be an absolute HTTP(S) URL"
            )
        observed_date = item.get("observed_date")
        if observed_date is not None:
            _, observed_date_error = _parse_past_or_present_date(observed_date)
            if observed_date_error:
                errors.append(
                    f"evidence[{index}].observed_date {observed_date_error}"
                )
        supports = _string_list(item.get("supports"), f"evidence[{index}].supports", errors)
        for reference in supports:
            if reference not in known_supports:
                errors.append(
                    f"evidence[{index}].supports references unknown target: {reference}"
                )
        if level == EvidenceLevel.CERTIFIED:
            for field in ("authority", "certificate_id"):
                if not _nonempty(item.get(field)):
                    errors.append(
                        f"evidence[{index}].{field} must be a non-empty string for certified evidence"
                    )

    evidence_supports = {
        item.get("id"): {
            support for support in item.get("supports", []) if _nonempty(support)
        }
        for item in collections["evidence"]
        if _nonempty(item.get("id")) and isinstance(item.get("supports"), list)
    }
    for index, item in enumerate(collections["quantities"]):
        source = item.get("source")
        if not isinstance(source, str) or not source.startswith("evidence:"):
            continue
        evidence_id = source[9:]
        target = f"quantity:{item.get('id')}"
        if evidence_id in evidence_supports and target not in evidence_supports[evidence_id]:
            errors.append(
                f"quantities[{index}].source {source} does not support {target}"
            )
        try:
            quantity_level = EvidenceLevel(item.get("evidence_level"))
        except (TypeError, ValueError):
            continue
        source_level = evidence_levels.get(evidence_id)
        if source_level is not None and quantity_level > source_level:
            errors.append(
                f"quantities[{index}].evidence_level {quantity_level.value} "
                f"exceeds source evidence level {source_level.value}"
            )

    return sorted(set(errors))


def load_contract(path: Path) -> tuple[Any | None, list[str]]:
    """Load UTF-8 JSON and return data plus actionable validation errors."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"contract does not exist: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"contract is not valid JSON: {exc}"]
    except UnicodeError as exc:
        return None, [f"contract is not valid UTF-8: {exc}"]
    except OSError as exc:
        return None, [f"cannot read contract: {exc}"]
    return data, validate_contract(data)
