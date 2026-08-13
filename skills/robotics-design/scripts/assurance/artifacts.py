"""Safe artifact observation and owner-to-mirror drift comparison."""

from __future__ import annotations

import math
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .model import Diagnostic
from .units import QuantityError, to_si


UNSAFE_XML = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
MAX_DECLARED_JSON_BYTES = 5 * 1024 * 1024
MAX_DECLARED_JSON_DEPTH = 64
MAX_DECLARED_JSON_INTEGER_DIGITS = 308


def _diagnostic(code: str, severity: str, path: str, message: str) -> Diagnostic:
    return Diagnostic(code, severity, path, message)


def _number(value: Any, path: str, diagnostics: list[Diagnostic]) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        diagnostics.append(
            _diagnostic("ARTIFACT.NUMBER", "error", path, "expected a finite number")
        )
        return None
    if not math.isfinite(result):
        diagnostics.append(
            _diagnostic("ARTIFACT.NUMBER", "error", path, "expected a finite number")
        )
        return None
    return result


def _vector(
    value: Any,
    count: int,
    path: str,
    diagnostics: list[Diagnostic],
    default: str | None = None,
) -> list[float] | None:
    raw = default if value is None else value
    if not isinstance(raw, str):
        diagnostics.append(
            _diagnostic("ARTIFACT.VECTOR", "error", path, f"expected {count} numbers")
        )
        return None
    parts = raw.split()
    if len(parts) != count:
        diagnostics.append(
            _diagnostic("ARTIFACT.VECTOR", "error", path, f"expected {count} numbers")
        )
        return None
    result = [_number(item, path, diagnostics) for item in parts]
    if any(item is None for item in result):
        return None
    return [float(item) for item in result if item is not None]


def observe_urdf(path: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Parse a bounded URDF subset without resolving external XML content."""

    diagnostics: list[Diagnostic] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, [
            _diagnostic("ARTIFACT.MISSING", "error", str(path), "URDF file does not exist")
        ]
    except (OSError, UnicodeError) as exc:
        return None, [
            _diagnostic("ARTIFACT.READ", "error", str(path), f"cannot read UTF-8 URDF: {exc}")
        ]
    if UNSAFE_XML.search(text):
        return None, [
            _diagnostic(
                "ARTIFACT.XML_UNSAFE",
                "error",
                str(path),
                "DTD and entity declarations are not permitted",
            )
        ]
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return None, [
            _diagnostic("ARTIFACT.XML", "error", str(path), f"invalid URDF XML: {exc}")
        ]
    if root.tag != "robot":
        return None, [
            _diagnostic("ARTIFACT.URDF_ROOT", "error", str(path), "URDF root must be robot")
        ]

    observation: dict[str, Any] = {
        "robot_name": root.get("name", ""),
        "links": {},
        "joints": {},
        "transmission_joints": [],
    }
    for link_index, link in enumerate(root.findall("link")):
        name = link.get("name")
        link_path = f"links[{link_index}]"
        if not name or name in observation["links"]:
            diagnostics.append(
                _diagnostic("ARTIFACT.DUPLICATE", "error", link_path, "link name is missing or duplicate")
            )
            continue
        record: dict[str, Any] = {}
        inertial = link.find("inertial")
        if inertial is not None:
            origin = inertial.find("origin")
            if origin is not None:
                record["inertial_origin"] = {
                    "xyz": _vector(origin.get("xyz"), 3, f"{link_path}.inertial.origin.xyz", diagnostics, "0 0 0"),
                    "rpy": _vector(origin.get("rpy"), 3, f"{link_path}.inertial.origin.rpy", diagnostics, "0 0 0"),
                }
            mass = inertial.find("mass")
            if mass is not None:
                record["mass_kg"] = _number(
                    mass.get("value"), f"{link_path}.inertial.mass", diagnostics
                )
            inertia = inertial.find("inertia")
            if inertia is not None:
                values: dict[str, float | None] = {}
                for field in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz"):
                    values[field] = _number(
                        inertia.get(field), f"{link_path}.inertial.inertia.{field}", diagnostics
                    )
                record["inertia_kg_m2"] = values
        observation["links"][name] = record

    for joint_index, joint in enumerate(root.findall("joint")):
        name = joint.get("name")
        joint_path = f"joints[{joint_index}]"
        if not name or name in observation["joints"]:
            diagnostics.append(
                _diagnostic("ARTIFACT.DUPLICATE", "error", joint_path, "joint name is missing or duplicate")
            )
            continue
        parent = joint.find("parent")
        child = joint.find("child")
        origin = joint.find("origin")
        axis = joint.find("axis")
        limit = joint.find("limit")
        record = {
            "type": joint.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
            "origin": {
                "xyz": _vector(
                    origin.get("xyz") if origin is not None else None,
                    3,
                    f"{joint_path}.origin.xyz",
                    diagnostics,
                    "0 0 0",
                ),
                "rpy": _vector(
                    origin.get("rpy") if origin is not None else None,
                    3,
                    f"{joint_path}.origin.rpy",
                    diagnostics,
                    "0 0 0",
                ),
            },
            "axis": _vector(
                axis.get("xyz") if axis is not None else None,
                3,
                f"{joint_path}.axis",
                diagnostics,
                "1 0 0",
            ),
            "limit": {},
        }
        if limit is not None:
            for field in ("lower", "upper", "effort", "velocity"):
                if limit.get(field) is not None:
                    record["limit"][field] = _number(
                        limit.get(field), f"{joint_path}.limit.{field}", diagnostics
                    )
        observation["joints"][name] = record

    transmission_joints: set[str] = set()
    for transmission in root.findall("transmission"):
        for joint in transmission.findall("joint"):
            name = joint.get("name")
            if name:
                transmission_joints.add(name)
    observation["transmission_joints"] = sorted(transmission_joints)

    if diagnostics:
        return None, sorted(diagnostics, key=lambda item: (item.code, item.path, item.message))
    return observation, []


def observe_declared_json(
    path: Path,
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load a bounded JSON observation tree for CAD/BOM/SDF/SRDF/ROS adapters."""

    try:
        if path.stat().st_size > MAX_DECLARED_JSON_BYTES:
            return None, [
                _diagnostic(
                    "ARTIFACT.JSON_SIZE",
                    "error",
                    str(path),
                    f"declared JSON exceeds {MAX_DECLARED_JSON_BYTES} bytes",
                )
            ]
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [
            _diagnostic(
                "ARTIFACT.READ", "error", str(path), f"cannot read UTF-8 JSON: {exc}"
            )
        ]

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number is forbidden: {value}")

    class DeclaredJsonNumberError(ValueError):
        pass

    def bounded_int(value: str) -> int:
        digits = value.lstrip("-")
        if len(digits) > MAX_DECLARED_JSON_INTEGER_DIGITS:
            raise DeclaredJsonNumberError(
                "JSON integer exceeds "
                f"{MAX_DECLARED_JSON_INTEGER_DIGITS} decimal digits"
            )
        return int(value)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        data = json.loads(
            text,
            parse_constant=reject_constant,
            parse_int=bounded_int,
            object_pairs_hook=unique_object,
        )
    except DeclaredJsonNumberError as exc:
        return None, [
            _diagnostic(
                "ARTIFACT.JSON_NUMBER",
                "error",
                str(path),
                f"invalid declared JSON number: {exc}",
            )
        ]
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        return None, [
            _diagnostic("ARTIFACT.JSON", "error", str(path), f"invalid declared JSON: {exc}")
        ]
    if not isinstance(data, dict):
        return None, [
            _diagnostic(
                "ARTIFACT.JSON_ROOT",
                "error",
                str(path),
                "declared JSON observation root must be an object",
            )
        ]

    def depth(value: Any, level: int = 0) -> int:
        if level > MAX_DECLARED_JSON_DEPTH:
            return level
        if isinstance(value, dict):
            return max((depth(item, level + 1) for item in value.values()), default=level)
        if isinstance(value, list):
            return max((depth(item, level + 1) for item in value), default=level)
        return level

    if depth(data) > MAX_DECLARED_JSON_DEPTH:
        return None, [
            _diagnostic(
                "ARTIFACT.JSON_DEPTH",
                "error",
                str(path),
                f"declared JSON exceeds nesting depth {MAX_DECLARED_JSON_DEPTH}",
            )
        ]

    def has_nonfinite(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            try:
                return not math.isfinite(float(value))
            except OverflowError:
                return True
        if isinstance(value, dict):
            return any(has_nonfinite(item) for item in value.values())
        if isinstance(value, list):
            return any(has_nonfinite(item) for item in value)
        return False

    if has_nonfinite(data):
        return None, [
            _diagnostic(
                "ARTIFACT.JSON_NUMBER",
                "error",
                str(path),
                "declared JSON contains a non-finite number",
            )
        ]
    return data, []


def _lookup(value: Any, dotted_path: str) -> tuple[bool, Any]:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def compare_observations(
    contract: dict[str, Any], observations: dict[str, Any]
) -> list[Diagnostic]:
    """Compare contract-owned SI quantities and actuator bindings to observations."""

    diagnostics: list[Diagnostic] = []
    for index, quantity in enumerate(contract.get("quantities", [])):
        if not isinstance(quantity, dict) or "observation" not in quantity:
            continue
        reference = quantity.get("observation")
        path = f"quantities[{index}].observation"
        if not isinstance(reference, str) or not reference.startswith("artifact:") or "#" not in reference:
            diagnostics.append(
                _diagnostic("DRIFT.REFERENCE", "error", path, "invalid observation reference")
            )
            continue
        artifact_ref, dotted = reference.split("#", 1)
        artifact_id = artifact_ref[9:]
        if artifact_id not in observations:
            diagnostics.append(
                _diagnostic("DRIFT.MISSING", "error", path, f"artifact observation is missing: {artifact_id}")
            )
            continue
        found, observed = _lookup(observations[artifact_id], dotted)
        if not found:
            diagnostics.append(
                _diagnostic("DRIFT.MISSING", "error", path, f"normalized observation is missing: {dotted}")
            )
            continue
        if not isinstance(observed, (int, float)) or isinstance(observed, bool) or not math.isfinite(float(observed)):
            diagnostics.append(
                _diagnostic("DRIFT.TYPE", "error", path, f"normalized observation is not a finite SI number: {dotted}")
            )
            continue
        try:
            expected = to_si(quantity.get("value"), quantity.get("dimension"), f"quantities[{index}].value")
            tolerance = (
                to_si(quantity["tolerance"], quantity.get("dimension"), f"quantities[{index}].tolerance")
                if "tolerance" in quantity
                else 0.0
            )
        except QuantityError as exc:
            diagnostics.append(_diagnostic("DRIFT.CONTRACT", "error", path, str(exc)))
            continue
        difference = abs(float(observed) - expected)
        if difference > tolerance:
            diagnostics.append(
                _diagnostic(
                    "DRIFT.VALUE",
                    "error",
                    path,
                    f"{dotted} differs by {difference:.12g} SI; tolerance is {tolerance:.12g}",
                )
            )

    actuators = contract.get("architecture", {}).get("actuators", [])
    urdf_ids = {
        artifact.get("id")
        for artifact in contract.get("artifacts", [])
        if isinstance(artifact, dict) and artifact.get("kind") in {"urdf", "xacro"}
    }
    transmission_joints: set[str] = set()
    for artifact_id in urdf_ids:
        observation = observations.get(artifact_id)
        if isinstance(observation, dict):
            joints = observation.get("transmission_joints", [])
            if isinstance(joints, list):
                transmission_joints.update(item for item in joints if isinstance(item, str))
    for actuator in actuators if isinstance(actuators, list) else []:
        if isinstance(actuator, str) and actuator not in transmission_joints:
            diagnostics.append(
                _diagnostic(
                    "DRIFT.MISSING_TRANSMISSION",
                    "error",
                    "architecture.actuators",
                    f"actuated joint has no observed URDF transmission: {actuator}",
                )
            )
    return sorted(diagnostics, key=lambda item: (item.code, item.path, item.message))
