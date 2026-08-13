"""Closed input-dimension and coverage contracts for assurance plug-ins."""

from __future__ import annotations

from typing import Any


DRIVETRAIN_DIMENSIONS = {
    "base_mass_kg": "mass",
    "payload_mass_kg": "mass",
    "rolling_resistance": "dimensionless",
    "slope_rad": "angle",
    "acceleration_m_s2": "acceleration",
    "wheel_radius_m": "length",
    "driven_wheels": "dimensionless",
    "gear_ratio": "dimensionless",
    "efficiency": "dimensionless",
    "target_speed_m_s": "speed",
    "motor_continuous_torque_nm": "torque",
    "motor_peak_torque_nm": "torque",
    "motor_max_speed_rad_s": "angular_velocity",
    "duty_cycle": "dimensionless",
}

BATTERY_DIMENSIONS = {
    "voltage_v": "voltage",
    "peak_power_w": "power",
    "continuous_power_w": "power",
    "max_continuous_current_a": "current",
    "max_peak_current_a": "current",
    "usable_energy_j": "energy",
    "required_runtime_s": "time",
}

STABILITY_DIMENSIONS = {
    "support_min_x_m": "length",
    "support_max_x_m": "length",
    "support_min_y_m": "length",
    "support_max_y_m": "length",
    "com_x_m": "length",
    "com_y_m": "length",
    "com_height_m": "length",
    "slope_x_rad": "angle",
    "slope_y_rad": "angle",
}

THERMAL_DIMENSIONS = {
    "ambient_temperature_k": "temperature",
    "winding_resistance_ohm": "resistance",
    "on_current_a": "current",
    "duty_cycle": "dimensionless",
    "thermal_resistance_k_per_w": "thermal_resistance",
    "max_winding_temperature_k": "temperature",
}

FLAT_PLUGIN_DIMENSIONS = {
    "drivetrain_v1": DRIVETRAIN_DIMENSIONS,
    "battery_v1": BATTERY_DIMENSIONS,
    "stability_v1": STABILITY_DIMENSIONS,
    "thermal_duty_v1": THERMAL_DIMENSIONS,
}

ARM_JOINT_DIMENSIONS = {
    "rated_continuous_torque_nm": "torque",
    "brake_holding_torque_nm": "torque",
    "safety_factor": "dimensionless",
}

ARM_LOAD_DIMENSIONS = {
    "mass_kg": "mass",
    "horizontal_lever_m": "length",
}

KNOWN_PLUGINS = frozenset((*FLAT_PLUGIN_DIMENSIONS, "arm_gravity_v1"))


def _quantity_reference(
    value: Any,
    expected_dimension: str,
    path: str,
    quantities: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if not isinstance(value, str) or not value.startswith("quantity:"):
        errors.append(
            f"{path} must reference a quantity with dimension {expected_dimension}"
        )
        return
    quantity_id = value[9:]
    quantity = quantities.get(quantity_id)
    if quantity is None:
        errors.append(f"{path} references unknown quantity: {value}")
        return
    actual = quantity.get("dimension")
    if actual != expected_dimension:
        errors.append(
            f"{path} expects dimension {expected_dimension}, but {value} declares {actual}"
        )


def _closed_object(
    value: Any, expected_fields: set[str], path: str, errors: list[str]
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return False
    missing = sorted(expected_fields - set(value))
    unknown = sorted(set(value) - expected_fields)
    if missing:
        errors.append(f"{path} is missing required fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")
    return not missing and not unknown


def validate_plugin_inputs(
    plugin: Any,
    inputs: Any,
    quantities: dict[str, dict[str, Any]],
    path: str,
) -> list[str]:
    """Validate a known plug-in's closed shape and quantity dimensions."""

    if plugin not in KNOWN_PLUGINS:
        return []
    errors: list[str] = []
    if plugin in FLAT_PLUGIN_DIMENSIONS:
        dimensions = FLAT_PLUGIN_DIMENSIONS[plugin]
        if not _closed_object(inputs, set(dimensions), path, errors):
            return errors
        for field, dimension in dimensions.items():
            _quantity_reference(
                inputs[field], dimension, f"{path}.{field}", quantities, errors
            )
        return errors

    if not _closed_object(inputs, {"joints"}, path, errors):
        return errors
    joints = inputs["joints"]
    if not isinstance(joints, list) or not joints:
        return [*errors, f"{path}.joints must be a non-empty list"]
    expected_joint_fields = {"id", "loads", *ARM_JOINT_DIMENSIONS}
    for joint_index, joint in enumerate(joints):
        joint_path = f"{path}.joints[{joint_index}]"
        if not _closed_object(joint, expected_joint_fields, joint_path, errors):
            continue
        if not isinstance(joint["id"], str) or not joint["id"].strip():
            errors.append(f"{joint_path}.id must be a non-empty joint id")
        for field, dimension in ARM_JOINT_DIMENSIONS.items():
            _quantity_reference(
                joint[field], dimension, f"{joint_path}.{field}", quantities, errors
            )
        loads = joint["loads"]
        if not isinstance(loads, list) or not loads:
            errors.append(f"{joint_path}.loads must be a non-empty list")
            continue
        for load_index, load in enumerate(loads):
            load_path = f"{joint_path}.loads[{load_index}]"
            if not _closed_object(load, set(ARM_LOAD_DIMENSIONS), load_path, errors):
                continue
            for field, dimension in ARM_LOAD_DIMENSIONS.items():
                _quantity_reference(
                    load[field], dimension, f"{load_path}.{field}", quantities, errors
                )
    return errors


def required_analysis_coverage(architecture: dict[str, Any]) -> set[tuple[str, str]]:
    """Return required (plug-in, responsibility) coverage edges."""

    required: set[tuple[str, str]] = set()
    features = architecture.get("features", [])
    if "differential_drive" in features:
        required.update(
            {
                ("drivetrain_v1", "feature:differential_drive"),
                ("stability_v1", "feature:differential_drive"),
            }
        )
        for drive in architecture.get("drive_units", []):
            required.add(("drivetrain_v1", f"drive:{drive}"))
    if "battery_powered" in features:
        required.add(("battery_v1", "feature:battery_powered"))
    for actuator in architecture.get("actuators", []):
        required.add(("arm_gravity_v1", f"actuator:{actuator}"))
    return required
