"""Mandatory physical-role inference and component-ledger validation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .model import Diagnostic


FEATURE_ROLES: dict[str, set[str]] = {
    "differential_drive": {
        "traction_motor",
        "reducer",
        "wheel",
        "bearing",
        "motor_driver",
    },
    "battery_powered": {
        "battery",
        "bms",
        "main_protection",
        "contactor",
        "dc_converter",
    },
}
ACTUATOR_ROLES = {"motor", "reducer", "bearing", "motor_driver"}
CABLE_ROLES = {"cable", "connector", "strain_relief", "cable_management"}
SAFETY_FUNCTION_ROLES = {"holding_brake": {"brake"}}
VERIFIED_IDENTITY_FIELDS = (
    "manufacturer",
    "part_number",
    "source_url",
    "source_date",
    "limits",
)


def required_roles(architecture: dict[str, Any]) -> dict[str, set[str]]:
    """Infer mandatory component roles from declared architecture features."""

    result: dict[str, set[str]] = {}
    for feature in architecture.get("features", []):
        if feature in FEATURE_ROLES:
            result[f"feature:{feature}"] = set(FEATURE_ROLES[feature])
    for actuator in architecture.get("actuators", []):
        result[f"actuator:{actuator}"] = set(ACTUATOR_ROLES)
    for cable in architecture.get("moving_cables", []):
        result[f"moving_cable:{cable}"] = set(CABLE_ROLES)
    for safety_function in architecture.get("claimed_safety_functions", []):
        if safety_function in SAFETY_FUNCTION_ROLES:
            result[f"safety_function:{safety_function}"] = set(
                SAFETY_FUNCTION_ROLES[safety_function]
            )
    return result


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_ledger(contract: dict[str, Any]) -> list[Diagnostic]:
    """Return stable diagnostics for component identity, coverage, and binding."""

    diagnostics: list[Diagnostic] = []
    components = contract.get("components")
    if not isinstance(components, list):
        return [
            Diagnostic(
                "BOM.INVALID_LEDGER",
                "error",
                "components",
                "components must be a list",
            )
        ]

    valid_records = [item for item in components if isinstance(item, dict)]
    ids = [item.get("id") for item in valid_records if _nonempty(item.get("id"))]
    for component_id, count in sorted(Counter(ids).items()):
        if count > 1:
            diagnostics.append(
                Diagnostic(
                    "BOM.DUPLICATE_ID",
                    "error",
                    "components",
                    f"component id appears {count} times: {component_id}",
                )
            )

    interface_owners: dict[str, list[str]] = {}
    bound_roles: dict[str, set[str]] = {}
    for index, item in enumerate(valid_records):
        path = f"components[{index}]"
        component_id = str(item.get("id", index))
        state = item.get("state")
        role = item.get("role")
        bindings = item.get("bindings", [])
        if _nonempty(role) and state != "missing" and isinstance(bindings, list):
            for binding in bindings:
                if _nonempty(binding):
                    bound_roles.setdefault(binding, set()).add(role)

        actuator_bindings = [
            value
            for value in bindings
            if _nonempty(value) and value.startswith("actuator:")
        ] if isinstance(bindings, list) else []
        if role in {"motor", "reducer", "bearing"} and len(actuator_bindings) > 1:
            diagnostics.append(
                Diagnostic(
                    "BOM.MULTI_ACTUATOR_COMPONENT",
                    "error",
                    f"{path}.bindings",
                    f"component {component_id} cannot serve multiple actuators: "
                    + ", ".join(sorted(actuator_bindings)),
                )
            )

        interfaces = item.get("interfaces", [])
        if isinstance(interfaces, list):
            for interface in interfaces:
                if _nonempty(interface):
                    interface_owners.setdefault(interface, []).append(component_id)

        if state in {"verified_part", "qualified_substitute"}:
            missing_fields = [
                field
                for field in VERIFIED_IDENTITY_FIELDS
                if not (
                    isinstance(item.get(field), dict)
                    and bool(item.get(field))
                    if field == "limits"
                    else _nonempty(item.get(field))
                )
            ]
            if missing_fields:
                diagnostics.append(
                    Diagnostic(
                        "BOM.UNVERIFIED_PART",
                        "error",
                        path,
                        "verified identity is missing: " + ", ".join(missing_fields),
                    )
                )

        supports = item.get("supports_claims", [])
        if state == "engineering_placeholder" and isinstance(supports, list) and supports:
            diagnostics.append(
                Diagnostic(
                    "BOM.PLACEHOLDER_BLOCKS_CLAIM",
                    "indeterminate",
                    path,
                    f"engineering placeholder {component_id} supports promoted claims: "
                    + ", ".join(sorted(str(value) for value in supports)),
                )
            )
        if state == "missing":
            diagnostics.append(
                Diagnostic(
                    "BOM.MISSING_ROLE",
                    "error",
                    path,
                    f"component {component_id} is explicitly missing for role {role}",
                )
            )

    for interface, owners in sorted(interface_owners.items()):
        if len(owners) > 1:
            diagnostics.append(
                Diagnostic(
                    "BOM.UNBOUND_INTERFACE",
                    "error",
                    "components.interfaces",
                    f"interface has multiple component owners: {interface} -> {', '.join(sorted(owners))}",
                )
            )

    architecture = contract.get("architecture")
    if not isinstance(architecture, dict):
        diagnostics.append(
            Diagnostic(
                "BOM.INVALID_ARCHITECTURE",
                "error",
                "architecture",
                "architecture must be an object",
            )
        )
    else:
        for source, roles in sorted(required_roles(architecture).items()):
            for role in sorted(roles - bound_roles.get(source, set())):
                diagnostics.append(
                    Diagnostic(
                        "BOM.MISSING_ROLE",
                        "error",
                        f"architecture.{source}",
                        f"{source} requires missing component role {role}",
                    )
                )

    return sorted(
        diagnostics,
        key=lambda item: (item.code, item.path, item.message, item.severity),
    )
