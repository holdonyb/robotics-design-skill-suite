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

ARM_LOAD_ENVELOPE_FIELDS = frozenset(
    {
        "joint_order",
        "joints",
        "links",
        "payload",
        "load_cases",
        "continuous_safety_factor",
        "brake_safety_factor",
        "rated_continuous_torque_nm",
        "brake_holding_torque_nm",
        "motor_continuous_torque_nm",
        "reducer_gear_ratio",
        "reducer_efficiency",
    }
)

KNOWN_PLUGINS = frozenset(
    (
        *FLAT_PLUGIN_DIMENSIONS,
        "arm_gravity_v1",
        "arm_load_envelope_v1",
        "bearing_static_v1",
        "component_mass_closure_v1",
    )
)


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


def _identifier(value: Any, path: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
        return None
    return value


def _validate_component_mass_closure_inputs(
    inputs: Any,
    quantities: dict[str, dict[str, Any]],
    path: str,
) -> list[str]:
    """Validate closed component-to-link mass-accounting records."""

    errors: list[str] = []
    if not _closed_object(inputs, {"links"}, path, errors):
        return errors
    links = inputs["links"]
    if not isinstance(links, list) or not links:
        return [*errors, f"{path}.links must be a non-empty list"]

    link_ids: set[str] = set()
    component_ids: set[str] = set()
    for link_index, link in enumerate(links):
        link_path = f"{path}.links[{link_index}]"
        fields = {"id", "link_mass_kg", "structural_residual_mass_kg", "components"}
        if not _closed_object(link, fields, link_path, errors):
            continue
        link_id = _identifier(link["id"], f"{link_path}.id", errors)
        if link_id is not None:
            if link_id in link_ids:
                errors.append(f"{link_path}.id duplicates {link_id}")
            link_ids.add(link_id)
        _quantity_reference(
            link["link_mass_kg"], "mass", f"{link_path}.link_mass_kg", quantities, errors
        )
        _quantity_reference(
            link["structural_residual_mass_kg"],
            "mass",
            f"{link_path}.structural_residual_mass_kg",
            quantities,
            errors,
        )
        components = link["components"]
        if not isinstance(components, list):
            errors.append(f"{link_path}.components must be a list")
            continue
        for component_index, component in enumerate(components):
            component_path = f"{link_path}.components[{component_index}]"
            if not _closed_object(component, {"id", "mass_kg"}, component_path, errors):
                continue
            component_id = _identifier(component["id"], f"{component_path}.id", errors)
            if component_id is not None:
                if component_id in component_ids:
                    errors.append(
                        f"{component_path}.id duplicates component contribution {component_id}"
                    )
                component_ids.add(component_id)
            _quantity_reference(
                component["mass_kg"], "mass", f"{component_path}.mass_kg", quantities, errors
            )
    return errors


def _quantity_vector(
    value: Any,
    dimension: str,
    count: int,
    path: str,
    quantities: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if not isinstance(value, list) or len(value) != count:
        errors.append(f"{path} must be a list of exactly {count} quantity references")
        return
    for index, item in enumerate(value):
        _quantity_reference(item, dimension, f"{path}[{index}]", quantities, errors)


def _load_envelope_rating_records(
    value: Any,
    field: str,
    dimension: str,
    joint_ids: set[str],
    path: str,
    quantities: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}.{field} must be a list")
        return
    seen: set[str] = set()
    for index, record in enumerate(value):
        record_path = f"{path}.{field}[{index}]"
        if not _closed_object(record, {"id", "value"}, record_path, errors):
            continue
        identifier = _identifier(record["id"], f"{record_path}.id", errors)
        if identifier is None:
            continue
        if identifier in seen:
            errors.append(f"{record_path}.id duplicates {identifier}")
        seen.add(identifier)
        _quantity_reference(record["value"], dimension, f"{record_path}.value", quantities, errors)
    if seen != joint_ids:
        errors.append(f"{path}.{field} must contain exactly one record for each joint_order id")


def _validate_arm_load_envelope_inputs(
    inputs: Any,
    quantities: dict[str, dict[str, Any]],
    path: str,
) -> list[str]:
    errors: list[str] = []
    if not _closed_object(inputs, set(ARM_LOAD_ENVELOPE_FIELDS), path, errors):
        return errors

    joint_order = inputs["joint_order"]
    if not isinstance(joint_order, list) or not joint_order:
        return [*errors, f"{path}.joint_order must be a non-empty list"]
    ordered_ids: list[str] = []
    for index, item in enumerate(joint_order):
        identifier = _identifier(item, f"{path}.joint_order[{index}]", errors)
        if identifier is not None:
            ordered_ids.append(identifier)
    if len(set(ordered_ids)) != len(ordered_ids):
        errors.append(f"{path}.joint_order must not contain duplicate joint ids")
    joint_ids = set(ordered_ids)

    joints = inputs["joints"]
    if not isinstance(joints, list) or len(joints) != len(joint_order):
        errors.append(f"{path}.joints must contain exactly one record for each joint_order id")
    else:
        seen_joint_ids: list[str] = []
        expected_parent = "base_link"
        children: list[str] = []
        for index, joint in enumerate(joints):
            joint_path = f"{path}.joints[{index}]"
            expected_fields = {
                "id", "parent", "child", "origin_xyz_m", "origin_rpy_rad", "axis_xyz"
            }
            if not _closed_object(joint, expected_fields, joint_path, errors):
                continue
            identifier = _identifier(joint["id"], f"{joint_path}.id", errors)
            parent = _identifier(joint["parent"], f"{joint_path}.parent", errors)
            child = _identifier(joint["child"], f"{joint_path}.child", errors)
            if identifier is not None:
                seen_joint_ids.append(identifier)
                if index < len(ordered_ids) and identifier != ordered_ids[index]:
                    errors.append(f"{joint_path}.id must equal joint_order[{index}]")
            if parent is not None and parent != expected_parent:
                errors.append(f"{joint_path}.parent must equal preceding chain link {expected_parent}")
            if child is not None:
                children.append(child)
                expected_parent = child
            _quantity_vector(joint["origin_xyz_m"], "length", 3, f"{joint_path}.origin_xyz_m", quantities, errors)
            _quantity_vector(joint["origin_rpy_rad"], "angle", 3, f"{joint_path}.origin_rpy_rad", quantities, errors)
            _quantity_vector(joint["axis_xyz"], "dimensionless", 3, f"{joint_path}.axis_xyz", quantities, errors)
        if set(seen_joint_ids) != joint_ids or len(set(seen_joint_ids)) != len(seen_joint_ids):
            errors.append(f"{path}.joints must map one-to-one and in order to joint_order")
        if len(set(children)) != len(children):
            errors.append(f"{path}.joints children must be unique")
    expected_links = {
        joint.get("child") for joint in joints if isinstance(joint, dict) and isinstance(joint.get("child"), str)
    } if isinstance(joints, list) else set()

    links = inputs["links"]
    if not isinstance(links, list):
        errors.append(f"{path}.links must be a list")
    else:
        seen_links: set[str] = set()
        for index, link in enumerate(links):
            link_path = f"{path}.links[{index}]"
            if not _closed_object(link, {"id", "mass_kg", "com_xyz_m"}, link_path, errors):
                continue
            identifier = _identifier(link["id"], f"{link_path}.id", errors)
            if identifier is not None:
                if identifier in seen_links:
                    errors.append(f"{link_path}.id duplicates {identifier}")
                seen_links.add(identifier)
            _quantity_reference(link["mass_kg"], "mass", f"{link_path}.mass_kg", quantities, errors)
            _quantity_vector(link["com_xyz_m"], "length", 3, f"{link_path}.com_xyz_m", quantities, errors)
        if seen_links != expected_links:
            errors.append(f"{path}.links must contain exactly the joint child links")

    payload = inputs["payload"]
    if _closed_object(payload, {"mass_kg", "parent", "origin_xyz_m"}, f"{path}.payload", errors):
        _quantity_reference(payload["mass_kg"], "mass", f"{path}.payload.mass_kg", quantities, errors)
        parent = _identifier(payload["parent"], f"{path}.payload.parent", errors)
        if parent is not None and parent not in expected_links:
            errors.append(f"{path}.payload.parent must name a joint child link")
        _quantity_vector(payload["origin_xyz_m"], "length", 3, f"{path}.payload.origin_xyz_m", quantities, errors)

    load_cases = inputs["load_cases"]
    if not isinstance(load_cases, list) or not load_cases:
        errors.append(f"{path}.load_cases must be a non-empty list")
    else:
        case_ids: set[str] = set()
        for index, case in enumerate(load_cases):
            case_path = f"{path}.load_cases[{index}]"
            if not _closed_object(case, {"id", "joint_positions_rad", "gravity_xyz_m_s2"}, case_path, errors):
                continue
            identifier = _identifier(case["id"], f"{case_path}.id", errors)
            if identifier is not None:
                if identifier in case_ids:
                    errors.append(f"{case_path}.id duplicates {identifier}")
                case_ids.add(identifier)
            _quantity_vector(case["joint_positions_rad"], "angle", len(joint_order), f"{case_path}.joint_positions_rad", quantities, errors)
            _quantity_vector(case["gravity_xyz_m_s2"], "acceleration", 3, f"{case_path}.gravity_xyz_m_s2", quantities, errors)

    _quantity_reference(inputs["continuous_safety_factor"], "dimensionless", f"{path}.continuous_safety_factor", quantities, errors)
    _quantity_reference(inputs["brake_safety_factor"], "dimensionless", f"{path}.brake_safety_factor", quantities, errors)
    _load_envelope_rating_records(inputs["rated_continuous_torque_nm"], "rated_continuous_torque_nm", "torque", joint_ids, path, quantities, errors)
    _load_envelope_rating_records(inputs["brake_holding_torque_nm"], "brake_holding_torque_nm", "torque", joint_ids, path, quantities, errors)
    _load_envelope_rating_records(inputs["motor_continuous_torque_nm"], "motor_continuous_torque_nm", "torque", joint_ids, path, quantities, errors)
    _load_envelope_rating_records(inputs["reducer_gear_ratio"], "reducer_gear_ratio", "dimensionless", joint_ids, path, quantities, errors)
    _load_envelope_rating_records(inputs["reducer_efficiency"], "reducer_efficiency", "dimensionless", joint_ids, path, quantities, errors)
    return errors


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
    if plugin == "thermal_duty_v1":
        optional_driver_current = "driver_continuous_current_a"
        dimensions = THERMAL_DIMENSIONS
        if not isinstance(inputs, dict):
            errors.append(f"{path} must be an object")
            return errors
        missing = sorted(set(dimensions) - set(inputs))
        unknown = sorted(set(inputs) - {*dimensions, optional_driver_current})
        if missing:
            errors.append(f"{path} is missing required fields: {', '.join(missing)}")
        if unknown:
            errors.append(f"{path} has unknown fields: {', '.join(unknown)}")
        if missing or unknown:
            return errors
        for field, dimension in dimensions.items():
            _quantity_reference(
                inputs[field], dimension, f"{path}.{field}", quantities, errors
            )
        if optional_driver_current in inputs:
            _quantity_reference(
                inputs[optional_driver_current],
                "current",
                f"{path}.{optional_driver_current}",
                quantities,
                errors,
            )
        return errors
    if plugin in FLAT_PLUGIN_DIMENSIONS:
        dimensions = FLAT_PLUGIN_DIMENSIONS[plugin]
        if not _closed_object(inputs, set(dimensions), path, errors):
            return errors
        for field, dimension in dimensions.items():
            _quantity_reference(
                inputs[field], dimension, f"{path}.{field}", quantities, errors
            )
        return errors

    if plugin == "arm_load_envelope_v1":
        return _validate_arm_load_envelope_inputs(inputs, quantities, path)

    if plugin == "component_mass_closure_v1":
        return _validate_component_mass_closure_inputs(inputs, quantities, path)

    if plugin == "bearing_static_v1":
        if not _closed_object(inputs, {"joints"}, path, errors):
            return errors
        joints = inputs["joints"]
        if not isinstance(joints, list) or not joints:
            return [*errors, f"{path}.joints must be a non-empty list"]
        dimensions = {"radial_load_n": "force", "axial_load_n": "force", "moment_nm": "torque", "pitch_diameter_m": "length", "static_load_rating_n": "force", "safety_factor": "dimensionless"}
        for index, joint in enumerate(joints):
            joint_path = f"{path}.joints[{index}]"
            if not _closed_object(joint, {"id", *dimensions}, joint_path, errors):
                continue
            _identifier(joint["id"], f"{joint_path}.id", errors)
            for field, dimension in dimensions.items():
                _quantity_reference(joint[field], dimension, f"{joint_path}.{field}", quantities, errors)
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
        required.add(("arm_load_envelope_v1", f"actuator:{actuator}"))
        required.add(("thermal_duty_v1", f"actuator:{actuator}"))
    for drive in architecture.get("drive_units", []):
        required.add(("thermal_duty_v1", f"drive:{drive}"))
    return required
