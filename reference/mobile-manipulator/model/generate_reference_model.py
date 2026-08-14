"""Generate the reference robot's CAD, robot descriptions, and ROS configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from build123d import Align, Box, Compound, Cylinder, Location, Rot, export_step


SOURCE_DIR = Path(__file__).resolve().parent
REFERENCE_DIR = SOURCE_DIR.parent
PHYSICAL_SOURCE = REFERENCE_DIR / "robot.urdf"
CONTRACT_SOURCE = REFERENCE_DIR / "design-contract.json"
ASSUMPTIONS_SOURCE = REFERENCE_DIR / "assumptions.json"
SCRIPTS = REFERENCE_DIR.parents[1] / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".12g")


def _vec(values: list[float]) -> str:
    return " ".join(_fmt(item) for item in values)


def _indent(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def _inertial(link: ET.Element, mass: float, inertia: list[float], origin: list[float] | None = None) -> None:
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", {"xyz": _vec(origin or [0.0, 0.0, 0.0]), "rpy": "0 0 0"})
    ET.SubElement(inertial, "mass", {"value": _fmt(mass)})
    ET.SubElement(inertial, "inertia", {
        "ixx": _fmt(inertia[0]), "ixy": "0", "ixz": "0",
        "iyy": _fmt(inertia[1]), "iyz": "0", "izz": _fmt(inertia[2]),
    })


def _physical_properties() -> dict[str, dict[str, object]]:
    root = ET.parse(PHYSICAL_SOURCE).getroot()
    result: dict[str, dict[str, object]] = {}
    for link in root.findall("link"):
        inertial = link.find("inertial")
        if inertial is None:
            continue
        mass = inertial.find("mass")
        inertia = inertial.find("inertia")
        if mass is None or inertia is None:
            raise ValueError(f"physical source link {link.get('name')} has incomplete inertial")
        origin = inertial.find("origin")
        result[str(link.get("name"))] = {
            "mass_kg": float(mass.get("value")),
            "inertia_kg_m2": [float(inertia.get(name)) for name in ("ixx", "iyy", "izz")],
            "origin_xyz_m": [0.0, 0.0, 0.0] if origin is None else [float(item) for item in origin.get("xyz", "0 0 0").split()],
        }
    return result


def _assumed_simulation_dynamics() -> dict[str, dict[str, object]]:
    data = json.loads(ASSUMPTIONS_SOURCE.read_text(encoding="utf-8"))
    dynamics = data.get("simulation_dynamics", {})
    if dynamics.get("evidence_level") != "assumed" or not isinstance(dynamics.get("links"), dict):
        raise ValueError("simulation_dynamics must be an explicitly assumed link mapping")
    return dynamics["links"]


def _primitive(link: ET.Element, size: list[float], origin: list[float]) -> None:
    for tag in ("visual", "collision"):
        owner = ET.SubElement(link, tag)
        ET.SubElement(owner, "origin", {"xyz": _vec(origin), "rpy": "0 0 0"})
        geometry = ET.SubElement(owner, "geometry")
        ET.SubElement(geometry, "box", {"size": _vec(size)})


def _cylinder(link: ET.Element, radius: float, length: float, origin: list[float], rpy: str = "0 0 0") -> None:
    for tag in ("visual", "collision"):
        owner = ET.SubElement(link, tag)
        ET.SubElement(owner, "origin", {"xyz": _vec(origin), "rpy": rpy})
        geometry = ET.SubElement(owner, "geometry")
        ET.SubElement(geometry, "cylinder", {"radius": _fmt(radius), "length": _fmt(length)})


def _urdf(geometry: dict) -> bytes:
    robot = ET.Element("robot", {"name": geometry["robot_name"]})
    physical = _physical_properties()
    base = geometry["base"]
    base_link = ET.SubElement(robot, "link", {"name": base["link"]})
    base_physical = physical[base["link"]]
    _inertial(base_link, base_physical["mass_kg"], base_physical["inertia_kg_m2"], base_physical["origin_xyz_m"])
    _primitive(base_link, base["size_m"], base["origin_xyz_m"])
    mount = base["arm_mount"]
    _cylinder(base_link, mount["radius_m"], mount["height_m"], mount["origin_xyz_m"])

    for wheel in geometry["wheels"]:
        link = ET.SubElement(robot, "link", {"name": wheel["link"]})
        _cylinder(link, wheel["radius_m"], wheel["width_m"], [0, 0, 0], "1.57079632679 0 0")
        joint = ET.SubElement(robot, "joint", {"name": wheel["joint"], "type": "continuous"})
        ET.SubElement(joint, "parent", {"link": base["link"]})
        ET.SubElement(joint, "child", {"link": wheel["link"]})
        ET.SubElement(joint, "origin", {"xyz": _vec(wheel["origin_xyz_m"]), "rpy": "0 0 0"})
        ET.SubElement(joint, "axis", {"xyz": _vec(wheel["axis"])})
        ET.SubElement(joint, "limit", {"effort": "120", "velocity": "12"})

    arm_vectors = [item["origin_xyz_m"] for item in geometry["arm_joints"][1:]] + [geometry["tool"]["origin_xyz_m"]]
    for item, vector in zip(geometry["arm_links"], arm_vectors, strict=True):
        link = ET.SubElement(robot, "link", {"name": item["link"]})
        along_z = abs(vector[2]) > 0
        center = [0, 0, item["length_m"] / 2] if along_z else [item["length_m"] / 2, 0, 0]
        rpy = "0 0 0" if along_z else "0 1.57079632679 0"
        owned = physical[item["link"]]
        _inertial(link, owned["mass_kg"], owned["inertia_kg_m2"], owned["origin_xyz_m"])
        _cylinder(link, item["radius_m"], item["length_m"], center, rpy)
    for item in geometry["arm_joints"]:
        joint = ET.SubElement(robot, "joint", {"name": item["joint"], "type": "revolute"})
        ET.SubElement(joint, "parent", {"link": item["parent"]})
        ET.SubElement(joint, "child", {"link": item["child"]})
        ET.SubElement(joint, "origin", {"xyz": _vec(item["origin_xyz_m"]), "rpy": "0 0 0"})
        ET.SubElement(joint, "axis", {"xyz": _vec(item["axis"])})
        ET.SubElement(joint, "limit", {
            "lower": _fmt(item["lower_rad"]), "upper": _fmt(item["upper_rad"]),
            "effort": _fmt(item["effort_nm"]), "velocity": _fmt(item["velocity_rad_s"]),
        })

    tool = geometry["tool"]
    ET.SubElement(robot, "link", {"name": tool["link"]})
    joint = ET.SubElement(robot, "joint", {"name": tool["joint"], "type": "fixed"})
    ET.SubElement(joint, "parent", {"link": tool["parent"]})
    ET.SubElement(joint, "child", {"link": tool["link"]})
    ET.SubElement(joint, "origin", {"xyz": _vec(tool["origin_xyz_m"]), "rpy": "0 0 0"})

    imu = geometry["sensors"][0]
    ET.SubElement(robot, "link", {"name": imu["frame"]})
    joint = ET.SubElement(robot, "joint", {"name": "imu_fixed", "type": "fixed"})
    ET.SubElement(joint, "parent", {"link": imu["parent"]})
    ET.SubElement(joint, "child", {"link": imu["frame"]})

    control = ET.SubElement(robot, "ros2_control", {"name": "reference_system", "type": "system"})
    hardware = ET.SubElement(control, "hardware")
    ET.SubElement(hardware, "plugin").text = geometry["ros2_control"]["plugin"]
    for item in geometry["arm_joints"]:
        joint = ET.SubElement(control, "joint", {"name": item["joint"]})
        for interface in geometry["ros2_control"]["arm_command_interfaces"]:
            ET.SubElement(joint, "command_interface", {"name": interface})
        for interface in geometry["ros2_control"]["arm_state_interfaces"]:
            ET.SubElement(joint, "state_interface", {"name": interface})
    for item in geometry["wheels"]:
        joint = ET.SubElement(control, "joint", {"name": item["joint"]})
        for interface in geometry["ros2_control"]["wheel_command_interfaces"]:
            ET.SubElement(joint, "command_interface", {"name": interface})
        for interface in geometry["ros2_control"]["wheel_state_interfaces"]:
            ET.SubElement(joint, "state_interface", {"name": interface})

    for item in geometry["arm_joints"]:
        transmission = ET.SubElement(robot, "transmission", {"name": item["joint"] + "_transmission"})
        ET.SubElement(transmission, "type").text = "transmission_interface/SimpleTransmission"
        ET.SubElement(transmission, "joint", {"name": item["joint"]})
        ET.SubElement(transmission, "actuator", {"name": item["joint"] + "_motor"})
    return _indent(robot)


def _sdf(geometry: dict) -> bytes:
    sdf = ET.Element("sdf", {"version": "1.12"})
    model = ET.SubElement(sdf, "model", {"name": geometry["robot_name"]})
    physical = _physical_properties()
    assumed_dynamics = _assumed_simulation_dynamics()
    ET.SubElement(model, "static").text = "false"
    def text(parent: ET.Element, tag: str, value: object, attributes: dict[str, str] | None = None) -> ET.Element:
        child = ET.SubElement(parent, tag, attributes or {})
        child.text = str(value)
        return child

    def inertial(link: ET.Element, mass: float, inertia: list[float]) -> None:
        owner = ET.SubElement(link, "inertial")
        text(owner, "mass", _fmt(mass))
        tensor = ET.SubElement(owner, "inertia")
        for name, value in zip(("ixx", "iyy", "izz"), inertia, strict=True):
            text(tensor, name, _fmt(value))
        for name in ("ixy", "ixz", "iyz"):
            text(tensor, name, "0")

    def box(link: ET.Element, size: list[float], pose: list[float]) -> None:
        for tag in ("visual", "collision"):
            owner = ET.SubElement(link, tag, {"name": f"{link.get('name')}_{tag}"})
            text(owner, "pose", _vec(pose + [0, 0, 0]), {"relative_to": link.get("name")})
            shape = ET.SubElement(ET.SubElement(owner, "geometry"), "box")
            text(shape, "size", _vec(size))

    def cylinder(
        link: ET.Element,
        radius: float,
        length: float,
        pose: list[float],
        name_suffix: str = "",
    ) -> None:
        for tag in ("visual", "collision"):
            owner = ET.SubElement(link, tag, {"name": f"{link.get('name')}{name_suffix}_{tag}"})
            text(owner, "pose", _vec(pose), {"relative_to": link.get("name")})
            shape = ET.SubElement(ET.SubElement(owner, "geometry"), "cylinder")
            text(shape, "radius", _fmt(radius))
            text(shape, "length", _fmt(length))

    base_data = geometry["base"]
    base = ET.SubElement(model, "link", {"name": base_data["link"]})
    inertial(base, physical[base_data["link"]]["mass_kg"], physical[base_data["link"]]["inertia_kg_m2"])
    box(base, base_data["size_m"], base_data["origin_xyz_m"])
    mount = base_data["arm_mount"]
    cylinder(
        base,
        mount["radius_m"],
        mount["height_m"],
        mount["origin_xyz_m"] + [0, 0, 0],
        "_arm_mount",
    )
    sensor = ET.SubElement(base, "sensor", {"name": "base_imu", "type": "imu"})
    ET.SubElement(sensor, "update_rate").text = _fmt(geometry["sensors"][0]["update_rate_hz"])
    ET.SubElement(sensor, "topic").text = "/imu/data"
    for wheel in geometry["wheels"]:
        link = ET.SubElement(model, "link", {"name": wheel["link"]})
        wheel_dynamics = assumed_dynamics[wheel["link"]]
        inertial(link, wheel_dynamics["mass_kg"], wheel_dynamics["inertia_kg_m2"])
        text(link, "pose", _vec(wheel["origin_xyz_m"] + [0, 0, 0]), {"relative_to": base_data["link"]})
        cylinder(link, wheel["radius_m"], wheel["width_m"], [0, 0, 0, math.pi / 2, 0, 0])
        joint = ET.SubElement(model, "joint", {"name": wheel["joint"], "type": "continuous"})
        text(joint, "parent", base_data["link"])
        text(joint, "child", wheel["link"])
        axis = ET.SubElement(joint, "axis")
        text(axis, "xyz", _vec(wheel["axis"]))

    arm_vectors = [item["origin_xyz_m"] for item in geometry["arm_joints"][1:]] + [geometry["tool"]["origin_xyz_m"]]
    joint_by_child = {item["child"]: item for item in geometry["arm_joints"]}
    for item, vector in zip(geometry["arm_links"], arm_vectors, strict=True):
        link = ET.SubElement(model, "link", {"name": item["link"]})
        owning_joint = joint_by_child[item["link"]]
        text(link, "pose", _vec(owning_joint["origin_xyz_m"] + [0, 0, 0]), {"relative_to": owning_joint["parent"]})
        inertial(link, physical[item["link"]]["mass_kg"], physical[item["link"]]["inertia_kg_m2"])
        along_z = abs(vector[2]) > 0
        pose = [0, 0, item["length_m"] / 2, 0, 0, 0] if along_z else [item["length_m"] / 2, 0, 0, 0, math.pi / 2, 0]
        cylinder(link, item["radius_m"], item["length_m"], pose)
    for item in geometry["arm_joints"]:
        joint = ET.SubElement(model, "joint", {"name": item["joint"], "type": "revolute"})
        text(joint, "parent", item["parent"])
        text(joint, "child", item["child"])
        text(joint, "pose", _vec(item["origin_xyz_m"] + [0, 0, 0]), {"relative_to": item["parent"]})
        axis = ET.SubElement(joint, "axis")
        text(axis, "xyz", _vec(item["axis"]))
        limit = ET.SubElement(axis, "limit")
        text(limit, "lower", _fmt(item["lower_rad"]))
        text(limit, "upper", _fmt(item["upper_rad"]))
        text(limit, "effort", _fmt(item["effort_nm"]))
        text(limit, "velocity", _fmt(item["velocity_rad_s"]))
    tool = geometry["tool"]
    tool_link = ET.SubElement(model, "link", {"name": tool["link"]})
    text(tool_link, "pose", _vec(tool["origin_xyz_m"] + [0, 0, 0]), {"relative_to": tool["parent"]})
    joint = ET.SubElement(model, "joint", {"name": tool["joint"], "type": "fixed"})
    text(joint, "parent", tool["parent"])
    text(joint, "child", tool["link"])
    text(joint, "pose", _vec(tool["origin_xyz_m"] + [0, 0, 0]), {"relative_to": tool["parent"]})
    plugin = ET.SubElement(model, "plugin", {"name": "gz_ros2_control", "filename": "libgz_ros2_control-system.so"})
    ET.SubElement(plugin, "parameters").text = "controllers.yaml"
    return _indent(sdf)


def _srdf(geometry: dict) -> bytes:
    root = ET.Element("robot", {"name": geometry["robot_name"]})
    moveit = geometry["moveit"]
    group = ET.SubElement(root, "group", {"name": moveit["group"]})
    ET.SubElement(group, "chain", {"base_link": moveit["base_link"], "tip_link": moveit["tip_link"]})
    home = ET.SubElement(root, "group_state", {"name": "home", "group": moveit["group"]})
    for joint, value in zip(geometry["arm_joints"], moveit["home_rad"], strict=True):
        ET.SubElement(home, "joint", {"name": joint["joint"], "value": _fmt(value)})
    for joint in geometry["arm_joints"]:
        ET.SubElement(root, "disable_collisions", {"link1": joint["parent"], "link2": joint["child"], "reason": "Adjacent"})
    return _indent(root)


def _cad(geometry: dict) -> Compound:
    base_size = [item * 1000 for item in geometry["base"]["size_m"]]
    parts = []
    base = Box(*base_size, align=(Align.CENTER, Align.CENTER, Align.MIN))
    base.label = "base_link"
    parts.append(base)
    mount = geometry["base"]["arm_mount"]
    mount_shape = Cylinder(
        mount["radius_m"] * 1000,
        mount["height_m"] * 1000,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    )
    mount_shape = Location(tuple(item * 1000 for item in mount["origin_xyz_m"])) * mount_shape
    mount_shape.label = "arm_mount"
    parts.append(mount_shape)
    for wheel in geometry["wheels"]:
        radius = wheel["radius_m"] * 1000
        width = wheel["width_m"] * 1000
        shape = Cylinder(radius, width, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        shape = Rot(X=90) * shape
        shape = Location(tuple(item * 1000 for item in wheel["origin_xyz_m"])) * shape
        shape.label = wheel["link"]
        parts.append(shape)
    origin = [item * 1000 for item in geometry["arm_joints"][0]["origin_xyz_m"]]
    arm_vectors = [item["origin_xyz_m"] for item in geometry["arm_joints"][1:]] + [geometry["tool"]["origin_xyz_m"]]
    for link, vector in zip(geometry["arm_links"], arm_vectors, strict=True):
        length = link["length_m"] * 1000
        shape = Cylinder(link["radius_m"] * 1000, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if abs(vector[2]) == 0:
            shape = Rot(Y=90) * shape
        shape = Location(tuple(origin)) * shape
        shape.label = link["link"]
        parts.append(shape)
        origin = [origin[item] + vector[item] * 1000 for item in range(3)]
    return Compound(children=parts, label=geometry["robot_name"])


def _load_geometry() -> dict:
    return json.loads((SOURCE_DIR / "geometry.json").read_text(encoding="utf-8"))


def gen_step():
    """CAD-skill entry point; millimeter BREP with source-owned occurrence labels."""
    return _cad(_load_geometry())


def gen_urdf():
    """URDF-skill entry point."""
    return ET.fromstring(_urdf(_load_geometry()))


def gen_sdf():
    """SDF-skill entry point for Gazebo Harmonic / SDFormat 1.12."""
    return ET.fromstring(_sdf(_load_geometry()))


def gen_srdf():
    """SRDF-skill entry point linked to the generated URDF."""
    return {
        "xml": ET.fromstring(_srdf(_load_geometry())),
        "urdf": "generated/reference_mobile_manipulator.urdf",
    }


def _text_outputs(geometry: dict) -> dict[str, bytes]:
    arm = [item["joint"] for item in geometry["arm_joints"]]
    wheels = [item["joint"] for item in geometry["wheels"]]
    controllers = (
        "controller_manager:\n  ros__parameters:\n    update_rate: 100\n"
        "    joint_state_broadcaster:\n      type: joint_state_broadcaster/JointStateBroadcaster\n"
        "    arm_controller:\n      type: joint_trajectory_controller/JointTrajectoryController\n"
        "    diff_drive_controller:\n      type: diff_drive_controller/DiffDriveController\n"
        f"arm_controller:\n  ros__parameters:\n    joints: [{', '.join(arm)}]\n"
        "    command_interfaces: [position]\n    state_interfaces: [position, velocity]\n"
        f"diff_drive_controller:\n  ros__parameters:\n    left_wheel_names: [{wheels[0]}]\n"
        f"    right_wheel_names: [{wheels[1]}]\n"
    ).encode()
    bridge = (
        "- ros_topic_name: /clock\n  gz_topic_name: /clock\n  ros_type_name: rosgraph_msgs/msg/Clock\n"
        "  gz_type_name: gz.msgs.Clock\n  direction: GZ_TO_ROS\n"
        "- ros_topic_name: /imu/data\n  gz_topic_name: /imu/data\n  ros_type_name: sensor_msgs/msg/Imu\n"
        "  gz_type_name: gz.msgs.IMU\n  direction: GZ_TO_ROS\n"
    ).encode()
    rviz = b"Panels:\n  - Class: rviz_common/Displays\nVisualization Manager:\n  Global Options:\n    Fixed Frame: base_link\n"
    package = (
        '<?xml version="1.0"?>\n<package format="3"><name>jx_mobile_manipulator_description</name>'
        '<version>0.5.0</version><description>Generated reference robot descriptions.</description>'
        '<maintainer email="maintainers@example.invalid">Jingxin Digital Intelligence</maintainer>'
        '<license>Apache-2.0</license><buildtool_depend>ament_cmake</buildtool_depend></package>\n'
    ).encode()
    cmake = b"cmake_minimum_required(VERSION 3.16)\nproject(jx_mobile_manipulator_description)\nfind_package(ament_cmake REQUIRED)\nament_package()\n"
    return {
        "reference_mobile_manipulator.urdf": _urdf(geometry),
        "reference_mobile_manipulator.sdf": _sdf(geometry),
        "reference_mobile_manipulator.srdf": _srdf(geometry),
        "controllers.yaml": controllers,
        "bridge.yaml": bridge,
        "view.rviz": rviz,
        "package.xml": package,
        "CMakeLists.txt": cmake,
    }


def generate(output_root: Path) -> None:
    geometry = json.loads((SOURCE_DIR / "geometry.json").read_text(encoding="utf-8"))
    model = output_root / "model"
    generated = model / "generated"
    simulation = output_root / "simulation"
    if generated.exists():
        shutil.rmtree(generated)
    generated.mkdir(parents=True, exist_ok=True)
    simulation.mkdir(parents=True, exist_ok=True)
    geometry_path = model / "geometry.json"
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    source_geometry = SOURCE_DIR / "geometry.json"
    if geometry_path.resolve() != source_geometry.resolve():
        geometry_path.write_bytes(source_geometry.read_bytes())
    output_physical = output_root / "robot.urdf"
    output_contract = output_root / "design-contract.json"
    output_assumptions = output_root / "assumptions.json"
    if output_physical.resolve() != PHYSICAL_SOURCE.resolve():
        output_physical.write_bytes(PHYSICAL_SOURCE.read_bytes())
    if output_contract.resolve() != CONTRACT_SOURCE.resolve():
        output_contract.write_bytes(CONTRACT_SOURCE.read_bytes())
    if output_assumptions.resolve() != ASSUMPTIONS_SOURCE.resolve():
        output_assumptions.write_bytes(ASSUMPTIONS_SOURCE.read_bytes())

    step_path = generated / "reference_mobile_manipulator.step"
    export_step(_cad(geometry), step_path, timestamp="2000-01-01T00:00:00")
    for name, payload in _text_outputs(geometry).items():
        (generated / name).write_bytes(payload if payload.endswith(b"\n") else payload + b"\n")

    geometry_sha = _sha256(geometry_path)
    physical_sha = _sha256(output_physical)
    contract_sha = _sha256(output_contract)
    assumptions_sha = _sha256(output_assumptions)
    outputs = []
    for path in sorted(generated.iterdir(), key=lambda item: item.name):
        relative = path.relative_to(output_root).as_posix()
        outputs.append({
            "path": relative,
            "sha256": _sha256(path),
            "source_sha256": geometry_sha,
            "physical_source_sha256": physical_sha,
            "contract_source_sha256": contract_sha,
            "assumptions_source_sha256": assumptions_sha,
        })
    manifest = {
        "schema_version": 1,
        "generator": {"name": "reference-model-generator", "version": "0.5.0"},
        "geometry_source": {"path": "model/geometry.json", "sha256": geometry_sha},
        "physical_source": {"path": "robot.urdf", "sha256": physical_sha},
        "contract_source": {"path": "design-contract.json", "sha256": contract_sha},
        "assumptions_source": {"path": "assumptions.json", "sha256": assumptions_sha},
        "outputs": outputs,
    }
    (simulation / "artifact-manifest.json").write_bytes(canonical_bytes(manifest))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=REFERENCE_DIR)
    args = parser.parse_args()
    generate(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
