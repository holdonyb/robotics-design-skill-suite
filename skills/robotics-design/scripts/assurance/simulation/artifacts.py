"""Manifest, semantic drift, and filesystem validation for generated robot artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from ..hypothesis.canonical import canonical_bytes, validate_sha256


_EXPECTED_OUTPUTS = {
    "model/generated/reference_mobile_manipulator.step",
    "model/generated/reference_mobile_manipulator.urdf",
    "model/generated/reference_mobile_manipulator.sdf",
    "model/generated/reference_mobile_manipulator.srdf",
    "model/generated/controllers.yaml",
    "model/generated/bridge.yaml",
    "model/generated/view.rviz",
    "model/generated/package.xml",
    "model/generated/CMakeLists.txt",
}
_ROOT_FIELDS = {"schema_version", "generator", "geometry_source", "physical_source", "contract_source", "assumptions_source", "outputs"}
_SOURCE_FIELDS = {"path", "sha256"}
_OUTPUT_FIELDS = {"path", "sha256", "source_sha256", "physical_source_sha256", "contract_source_sha256", "assumptions_source_sha256"}
_GENERATOR = {"name": "reference-model-generator", "version": "0.5.0"}
_MAX_MANIFEST_BYTES = 5 * 1024 * 1024


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        return None
    return path.as_posix()


def _numbers(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in value.split())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _geometry_schema_errors(geometry: object) -> list[str]:
    errors: list[str] = []

    def closed(value: object, fields: set[str], path: str) -> dict[str, Any] | None:
        if not isinstance(value, dict) or set(value) != fields:
            errors.append(f"geometry {path} fields are not closed")
            return None
        return value

    def records(value: object, fields: set[str], path: str, count: int) -> list[dict[str, Any]]:
        if not isinstance(value, list) or len(value) != count:
            errors.append(f"geometry {path} must contain exactly {count} records")
            return []
        result = []
        for index, item in enumerate(value):
            observed = closed(item, fields, f"{path}[{index}]")
            if observed is not None:
                result.append(observed)
        return result

    root = closed(
        geometry,
        {"schema_version", "robot_name", "units", "assumptions", "base", "wheels", "arm_links", "arm_joints", "tool", "sensors", "ros2_control", "moveit"},
        "root",
    )
    if root is None:
        return errors
    if root.get("schema_version") != 1 or type(root.get("schema_version")) is not int:
        errors.append("geometry schema_version must be integer 1")
    closed(root.get("units"), {"angle", "length", "mass"}, "units")
    base = closed(root.get("base"), {"link", "size_m", "origin_xyz_m", "arm_mount", "physical_owner"}, "base")
    if base is not None:
        closed(base.get("arm_mount"), {"radius_m", "height_m", "origin_xyz_m"}, "base.arm_mount")
    records(root.get("wheels"), {"link", "joint", "origin_xyz_m", "axis", "radius_m", "width_m"}, "wheels", 2)
    records(root.get("arm_links"), {"link", "length_m", "radius_m", "physical_owner"}, "arm_links", 6)
    records(
        root.get("arm_joints"),
        {"joint", "parent", "child", "origin_xyz_m", "axis", "lower_rad", "upper_rad", "effort_nm", "velocity_rad_s"},
        "arm_joints",
        6,
    )
    closed(root.get("tool"), {"link", "parent", "joint", "origin_xyz_m"}, "tool")
    records(root.get("sensors"), {"name", "type", "parent", "frame", "update_rate_hz"}, "sensors", 1)
    closed(
        root.get("ros2_control"),
        {"plugin", "arm_command_interfaces", "arm_state_interfaces", "wheel_command_interfaces", "wheel_state_interfaces"},
        "ros2_control",
    )
    closed(root.get("moveit"), {"group", "base_link", "tip_link", "home_rad"}, "moveit")
    return errors


def _positive_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _semantic_errors(
    root: Path,
    geometry: dict[str, Any],
    physical_root: ET.Element,
    assumptions: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    generated = root / "model" / "generated"
    try:
        urdf = ET.parse(generated / "reference_mobile_manipulator.urdf").getroot()
        if urdf.tag != "robot" or urdf.get("name") != geometry["robot_name"]:
            errors.append("URDF robot name drift")
        links = {item.get("name"): item for item in urdf.findall("link")}
        joints = {item.get("name"): item for item in urdf.findall("joint")}
        expected_links = {
            geometry["base"]["link"], geometry["tool"]["link"],
            geometry["sensors"][0]["frame"],
            *(item["link"] for item in geometry["wheels"]),
            *(item["link"] for item in geometry["arm_links"]),
        }
        expected_joints = {
            geometry["tool"]["joint"], "imu_fixed",
            *(item["joint"] for item in geometry["wheels"]),
            *(item["joint"] for item in geometry["arm_joints"]),
        }
        if set(links) != expected_links:
            errors.append("URDF link inventory drift")
        if set(joints) != expected_joints:
            errors.append("URDF joint inventory drift")
        physical_links = {item.get("name"): item for item in physical_root.findall("link")}
        owned_links = [geometry["base"]["link"]] + [item["link"] for item in geometry["arm_links"]]
        for link_name in owned_links:
            generated_link = links.get(link_name)
            source_link = physical_links.get(link_name)
            if generated_link is None or source_link is None:
                errors.append(f"URDF physical ownership link missing: {link_name}")
                continue
            generated_mass = generated_link.find("inertial/mass")
            source_mass = source_link.find("inertial/mass")
            if generated_mass is None or source_mass is None or float(generated_mass.get("value", "nan")) != float(source_mass.get("value", "nan")):
                label = "base mass" if link_name == geometry["base"]["link"] else f"{link_name} mass"
                errors.append(f"URDF {label} drift from physical contract-owned source")
            generated_inertia = generated_link.find("inertial/inertia")
            source_inertia = source_link.find("inertial/inertia")
            if generated_inertia is None or source_inertia is None or any(
                float(generated_inertia.get(name, "nan")) != float(source_inertia.get(name, "nan"))
                for name in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")
            ):
                errors.append(f"URDF {link_name} inertia drift from physical contract-owned source")
        for expected in geometry["arm_joints"]:
            observed = joints.get(expected["joint"])
            if observed is None:
                errors.append(f"URDF missing joint {expected['joint']}")
                continue
            axis = observed.find("axis")
            if axis is None or _numbers(axis.get("xyz", "")) != tuple(expected["axis"]):
                errors.append(f"URDF joint {expected['joint']} axis drift")
            limit = observed.find("limit")
            if limit is None or float(limit.get("lower", "nan")) != expected["lower_rad"] or float(limit.get("upper", "nan")) != expected["upper_rad"]:
                errors.append(f"URDF joint {expected['joint']} limit drift")
            if not any(item.find("joint") is not None and item.find("joint").get("name") == expected["joint"] for item in urdf.findall("transmission")):
                errors.append(f"URDF missing transmission for {expected['joint']}")
        for link in links.values():
            collision = link.find("collision/geometry")
            if collision is not None and collision.find("mesh") is not None:
                errors.append("URDF primitive collision required; mesh-only collision is forbidden")
        control_joints = {item.get("name") for item in urdf.findall("ros2_control/joint")}
        expected_control = {item["joint"] for item in geometry["arm_joints"] + geometry["wheels"]}
        if control_joints != expected_control:
            errors.append("URDF ros2_control joint inventory drift")
        control_by_name = {item.get("name"): item for item in urdf.findall("ros2_control/joint")}
        for item in geometry["arm_joints"] + geometry["wheels"]:
            observed = control_by_name.get(item["joint"])
            if observed is None:
                continue
            group = "arm" if item in geometry["arm_joints"] else "wheel"
            commands = {node.get("name") for node in observed.findall("command_interface")}
            states = {node.get("name") for node in observed.findall("state_interface")}
            if commands != set(geometry["ros2_control"][f"{group}_command_interfaces"]):
                errors.append(f"URDF ros2_control command interface drift: {item['joint']}")
            if states != set(geometry["ros2_control"][f"{group}_state_interfaces"]):
                errors.append(f"URDF ros2_control state interface drift: {item['joint']}")
    except (ET.ParseError, OSError, TypeError, ValueError, KeyError) as exc:
        errors.append(f"cannot validate URDF semantics: {exc}")

    try:
        sdf = ET.parse(generated / "reference_mobile_manipulator.sdf").getroot()
        model = sdf.find("model")
        if sdf.get("version") != "1.12" or model is None or model.get("name") != geometry["robot_name"]:
            errors.append("SDF model identity/version drift")
        if model is None or model.find("plugin[@name='gz_ros2_control']") is None:
            errors.append("SDF missing gz_ros2_control plugin")
        if model is None or model.find("link/sensor[@name='base_imu']") is None:
            errors.append("SDF missing base_imu sensor")
        if model is not None:
            sdf_links = {item.get("name"): item for item in model.findall("link")}
            sdf_joints = {item.get("name"): item for item in model.findall("joint")}
            expected_links = {
                geometry["base"]["link"], geometry["tool"]["link"],
                *(item["link"] for item in geometry["wheels"]),
                *(item["link"] for item in geometry["arm_links"]),
            }
            expected_joints = {
                geometry["tool"]["joint"],
                *(item["joint"] for item in geometry["wheels"]),
                *(item["joint"] for item in geometry["arm_joints"]),
            }
            if set(sdf_links) != expected_links:
                errors.append("SDF link inventory drift")
            if set(sdf_joints) != expected_joints:
                errors.append("SDF joint inventory drift")
            physical_links = {item.get("name"): item for item in physical_root.findall("link")}
            assumed_links = assumptions["simulation_dynamics"]["links"]
            for link_name in expected_links - {geometry["tool"]["link"]}:
                observed = sdf_links.get(link_name)
                if observed is None:
                    continue
                if link_name in assumed_links:
                    expected_mass = assumed_links[link_name]["mass_kg"]
                    expected_inertia = assumed_links[link_name]["inertia_kg_m2"]
                else:
                    source = physical_links.get(link_name)
                    if source is None:
                        errors.append(f"SDF physical ownership link missing: {link_name}")
                        continue
                    expected_mass = float(source.find("inertial/mass").get("value"))
                    tensor = source.find("inertial/inertia")
                    expected_inertia = [float(tensor.get(name)) for name in ("ixx", "iyy", "izz")]
                mass = observed.find("inertial/mass")
                if mass is None or float(mass.text or "nan") != expected_mass:
                    errors.append(f"SDF {link_name} mass drift from owned source")
                tensor = observed.find("inertial/inertia")
                if tensor is None or any(
                    tensor.find(name) is None or float(tensor.find(name).text or "nan") != value
                    for name, value in zip(("ixx", "iyy", "izz"), expected_inertia, strict=True)
                ):
                    errors.append(f"SDF {link_name} inertia drift from owned source")
            for item in geometry["arm_joints"] + geometry["wheels"]:
                observed = sdf_joints.get(item["joint"])
                if observed is None:
                    continue
                axis = observed.find("axis/xyz")
                if axis is None or _numbers(axis.text or "") != tuple(item["axis"]):
                    errors.append(f"SDF joint {item['joint']} axis drift")
                if item in geometry["arm_joints"]:
                    limit = observed.find("axis/limit")
                    if (
                        limit is None
                        or float(limit.findtext("lower", "nan")) != item["lower_rad"]
                        or float(limit.findtext("upper", "nan")) != item["upper_rad"]
                        or float(limit.findtext("effort", "nan")) != item["effort_nm"]
                        or float(limit.findtext("velocity", "nan")) != item["velocity_rad_s"]
                    ):
                        errors.append(f"SDF joint {item['joint']} limit drift")
    except (ET.ParseError, OSError, TypeError, ValueError, KeyError, AttributeError) as exc:
        errors.append(f"cannot validate SDF semantics: {exc}")

    try:
        srdf = ET.parse(generated / "reference_mobile_manipulator.srdf").getroot()
        group = srdf.find(f"group[@name='{geometry['moveit']['group']}']/chain")
        if group is None or group.get("base_link") != geometry["moveit"]["base_link"] or group.get("tip_link") != geometry["moveit"]["tip_link"]:
            errors.append("SRDF MoveIt group/TCP drift")
        expected_pairs = {
            frozenset((item["parent"], item["child"])) for item in geometry["arm_joints"]
        }
        observed_pairs: set[frozenset[str | None]] = set()
        for item in srdf.findall("disable_collisions"):
            pair = frozenset((item.get("link1"), item.get("link2")))
            observed_pairs.add(pair)
            if pair not in expected_pairs or item.get("reason") != "Adjacent":
                errors.append("SRDF broad or unsupported disabled collision pair")
        if observed_pairs != expected_pairs:
            errors.append("SRDF disabled collision inventory drift")
    except (ET.ParseError, OSError, KeyError) as exc:
        errors.append(f"cannot validate SRDF semantics: {exc}")

    try:
        bridge = (generated / "bridge.yaml").read_text(encoding="utf-8")
        if "ros_topic_name: /clock" not in bridge or "gz_topic_name: /clock" not in bridge:
            errors.append("bridge configuration must include exact /clock mapping")
        controllers = (generated / "controllers.yaml").read_text(encoding="utf-8")
        for item in geometry["arm_joints"] + geometry["wheels"]:
            if item["joint"] not in controllers:
                errors.append(f"controller configuration missing {item['joint']}")
    except OSError as exc:
        errors.append(f"cannot validate ROS configuration: {exc}")
    return errors


def validate_artifact_manifest(
    root: str | Path,
    *,
    manifest_sha256: str | None = None,
) -> list[str]:
    """Validate exact files, hashes, symlink policy, and cross-artifact semantics."""

    base = Path(root)
    manifest_path = base / "simulation" / "artifact-manifest.json"
    try:
        if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
            return ["artifact manifest exceeds maximum size of 5 MiB"]
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        return [f"cannot load artifact manifest: {exc}"]
    errors: list[str] = []
    try:
        validate_sha256(manifest_sha256, "manifest_sha256")
        if manifest_sha256 != hashlib.sha256(manifest_bytes).hexdigest():
            errors.append("artifact manifest does not match its external receipt SHA-256")
    except ValueError as exc:
        errors.append(f"external receipt is required: {exc}")
    if not isinstance(manifest, dict):
        return ["artifact manifest root must be an object"]
    if set(manifest) != _ROOT_FIELDS:
        errors.append("artifact manifest root fields are not closed")
    try:
        if manifest_bytes != canonical_bytes(manifest):
            errors.append("artifact manifest must use canonical JSON bytes")
    except (OverflowError, TypeError, ValueError, UnicodeError) as exc:
        errors.append(f"artifact manifest is not canonical JSON: {exc}")
    if manifest.get("schema_version") != 1 or type(manifest.get("schema_version")) is not int:
        errors.append("artifact manifest schema_version must be integer 1")
    if manifest.get("generator") != _GENERATOR:
        errors.append("artifact manifest generator identity must be fixed")
    source = manifest.get("geometry_source")
    physical_source = manifest.get("physical_source")
    contract_source = manifest.get("contract_source")
    assumptions_source = manifest.get("assumptions_source")
    outputs = manifest.get("outputs")
    if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
        errors.append("geometry_source fields are not closed")
        return sorted(set(errors))
    source_path = _safe_path(source.get("path"))
    if source_path != "model/geometry.json":
        errors.append("geometry_source.path must be model/geometry.json")
        return sorted(set(errors))
    geometry_path = base / source_path
    if geometry_path.is_symlink():
        errors.append("geometry source must not be a symlink")
    try:
        observed_source_sha = _sha256(geometry_path)
        validate_sha256(source.get("sha256"), "geometry_source.sha256")
        if source.get("sha256") != observed_source_sha:
            errors.append("geometry source SHA-256 mismatch")
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"cannot validate geometry source: {exc}")
        return sorted(set(errors))
    geometry_errors = _geometry_schema_errors(geometry)
    errors.extend(geometry_errors)
    if geometry_errors:
        return sorted(set(errors))

    if not isinstance(physical_source, dict) or set(physical_source) != _SOURCE_FIELDS:
        errors.append("physical_source fields are not closed")
        return sorted(set(errors))
    physical_relative = _safe_path(physical_source.get("path"))
    if physical_relative != "robot.urdf":
        errors.append("physical_source.path must be robot.urdf")
        return sorted(set(errors))
    physical_path = base / physical_relative
    if physical_path.is_symlink():
        errors.append("physical source must not be a symlink")
    try:
        observed_physical_sha = _sha256(physical_path)
        validate_sha256(physical_source.get("sha256"), "physical_source.sha256")
        if physical_source.get("sha256") != observed_physical_sha:
            errors.append("physical source SHA-256 mismatch")
        physical_root = ET.parse(physical_path).getroot()
    except (ET.ParseError, OSError, TypeError, ValueError) as exc:
        errors.append(f"cannot validate physical source: {exc}")
        return sorted(set(errors))

    if not isinstance(contract_source, dict) or set(contract_source) != _SOURCE_FIELDS:
        errors.append("contract_source fields are not closed")
        return sorted(set(errors))
    contract_relative = _safe_path(contract_source.get("path"))
    if contract_relative != "design-contract.json":
        errors.append("contract_source.path must be design-contract.json")
        return sorted(set(errors))
    contract_path = base / contract_relative
    if contract_path.is_symlink():
        errors.append("contract source must not be a symlink")
    try:
        observed_contract_sha = _sha256(contract_path)
        validate_sha256(contract_source.get("sha256"), "contract_source.sha256")
        if contract_source.get("sha256") != observed_contract_sha:
            errors.append("contract source SHA-256 mismatch")
        contract = json.loads(contract_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        robot_artifacts = [
            item for item in contract.get("artifacts", [])
            if isinstance(item, dict) and item.get("id") == "robot-model"
        ]
        if len(robot_artifacts) != 1 or robot_artifacts[0].get("path") != "robot.urdf" or robot_artifacts[0].get("sha256") != observed_physical_sha:
            errors.append("contract source does not hash-bind physical robot.urdf")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"cannot validate contract source: {exc}")
        return sorted(set(errors))

    if not isinstance(assumptions_source, dict) or set(assumptions_source) != _SOURCE_FIELDS:
        errors.append("assumptions_source fields are not closed")
        return sorted(set(errors))
    assumptions_relative = _safe_path(assumptions_source.get("path"))
    if assumptions_relative != "assumptions.json":
        errors.append("assumptions_source.path must be assumptions.json")
        return sorted(set(errors))
    assumptions_path = base / assumptions_relative
    if assumptions_path.is_symlink():
        errors.append("assumptions source must not be a symlink")
    try:
        observed_assumptions_sha = _sha256(assumptions_path)
        validate_sha256(assumptions_source.get("sha256"), "assumptions_source.sha256")
        if assumptions_source.get("sha256") != observed_assumptions_sha:
            errors.append("assumptions source SHA-256 mismatch")
        assumptions = json.loads(assumptions_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        dynamics = assumptions.get("simulation_dynamics", {})
        links = dynamics.get("links", {}) if isinstance(dynamics, dict) else {}
        valid_dynamics = (
            isinstance(dynamics, dict)
            and set(dynamics) == {"evidence_level", "claim_boundary", "links"}
            and dynamics.get("evidence_level") == "assumed"
            and isinstance(dynamics.get("claim_boundary"), str)
            and bool(dynamics.get("claim_boundary"))
            and isinstance(links, dict)
            and set(links) == {"left_wheel_link", "right_wheel_link"}
        )
        if valid_dynamics:
            for record in links.values():
                if (
                    not isinstance(record, dict)
                    or set(record) != {"mass_kg", "inertia_kg_m2"}
                    or not _positive_number(record.get("mass_kg"))
                    or not isinstance(record.get("inertia_kg_m2"), list)
                    or len(record["inertia_kg_m2"]) != 3
                    or not all(_positive_number(value) for value in record["inertia_kg_m2"])
                ):
                    valid_dynamics = False
                    break
        if not valid_dynamics:
            errors.append("assumptions source must declare both wheel dynamics at assumed evidence")
        assumption_artifacts = [
            item for item in contract.get("artifacts", [])
            if isinstance(item, dict) and item.get("id") == "assumption-registry"
        ]
        if (
            len(assumption_artifacts) != 1
            or assumption_artifacts[0].get("path") != "assumptions.json"
            or assumption_artifacts[0].get("sha256") != observed_assumptions_sha
        ):
            errors.append("contract source does not hash-bind assumptions registry")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"cannot validate assumptions source: {exc}")
        return sorted(set(errors))

    if not isinstance(outputs, list):
        errors.append("outputs must be a list")
        return sorted(set(errors))
    declared: set[str] = set()
    for index, output in enumerate(outputs):
        if not isinstance(output, dict) or set(output) != _OUTPUT_FIELDS:
            errors.append(f"outputs[{index}] fields are not closed")
            continue
        relative = _safe_path(output.get("path"))
        if relative is None:
            errors.append(f"outputs[{index}].path is unsafe")
            continue
        if relative in declared:
            errors.append(f"duplicate output path: {relative}")
        declared.add(relative)
        path = base / relative
        if path.is_symlink():
            errors.append(f"output must not be a symlink: {relative}")
            continue
        if not path.is_file():
            errors.append(f"missing output file: {relative}")
            continue
        try:
            validate_sha256(output.get("sha256"), f"outputs[{index}].sha256")
            validate_sha256(output.get("source_sha256"), f"outputs[{index}].source_sha256")
        except ValueError as exc:
            errors.append(str(exc))
        if output.get("sha256") != _sha256(path):
            errors.append(f"output SHA-256 mismatch: {relative}")
        if output.get("source_sha256") != observed_source_sha:
            errors.append(f"output source SHA-256 mismatch: {relative}")
        if output.get("physical_source_sha256") != observed_physical_sha:
            errors.append(f"output physical source SHA-256 mismatch: {relative}")
        if output.get("contract_source_sha256") != observed_contract_sha:
            errors.append(f"output contract source SHA-256 mismatch: {relative}")
        if output.get("assumptions_source_sha256") != observed_assumptions_sha:
            errors.append(f"output assumptions source SHA-256 mismatch: {relative}")
        if path.suffix != ".step":
            payload = path.read_bytes()
            if b"\r" in payload or not payload.endswith(b"\n"):
                errors.append(f"text output must use LF and one trailing newline: {relative}")
    if declared != _EXPECTED_OUTPUTS:
        errors.append("output manifest file set does not match the required generated set")
    generated = base / "model" / "generated"
    actual = {
        path.relative_to(base).as_posix()
        for path in generated.rglob("*") if path.is_file() or path.is_symlink()
    }
    for extra in sorted(actual - declared):
        errors.append(f"extra file not declared by artifact manifest: {extra}")
    errors.extend(_semantic_errors(base, geometry, physical_root, assumptions))
    return sorted(set(errors))
