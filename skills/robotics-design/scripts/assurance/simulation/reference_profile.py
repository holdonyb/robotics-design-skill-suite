"""Receipt-bound geometry used by the portable reference policy runner."""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .artifacts import validate_ros_workspace_manifest


ROS_WORKSPACE_RECEIPT = "fe325213ea6081a8bb35a5c7651b7183678bb62d8a2baf26cf267a896aba4db1"
_XACRO = "ros2_ws/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro"
_CONTROLLERS = "ros2_ws/src/jx_mobile_manipulator_sim/config/controllers.yaml"


class ReferenceProfileError(ValueError):
    """The reference runner geometry is missing, stale, or inconsistent."""


def _finite(value: object, name: str, *, positive: bool = True) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ReferenceProfileError(f"{name} must be numeric") from None
    if not math.isfinite(result) or (positive and result <= 0):
        raise ReferenceProfileError(f"{name} must be {'positive and ' if positive else ''}finite")
    return result


def _yaml(source: str, field: str) -> float:
    matches = re.findall(rf"(?m)^\s*{re.escape(field)}:\s*([^\s#]+)\s*$", source)
    if len(matches) != 1:
        raise ReferenceProfileError(f"controllers must declare exactly one {field}")
    return _finite(matches[0], f"controllers {field}")


@dataclass(frozen=True)
class ReferenceRunnerProfile:
    wheel_radius_m: float
    wheel_separation_m: float
    workspace_manifest_sha256: str = ROS_WORKSPACE_RECEIPT


def load_reference_runner_profile(reference_root: str | Path) -> ReferenceRunnerProfile:
    """Parse and cross-check reference wheel geometry after workspace receipt validation."""
    root = Path(reference_root)
    if root.is_symlink() or not root.is_dir():
        raise ReferenceProfileError("reference root is missing, not a directory, or a symlink")
    errors = validate_ros_workspace_manifest(root, root / "simulation" / "ros-workspace-manifest.json", ROS_WORKSPACE_RECEIPT)
    if errors:
        raise ReferenceProfileError("ROS workspace is not receipt-valid: " + "; ".join(errors))
    xacro_path, controllers_path = root / _XACRO, root / _CONTROLLERS
    try:
        if any(path.is_symlink() or not path.is_file() for path in (xacro_path, controllers_path)):
            raise ReferenceProfileError("reference profile sources are missing or symlinked")
        xacro = ET.fromstring(xacro_path.read_bytes())
        controllers = controllers_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ET.ParseError) as exc:
        raise ReferenceProfileError(f"cannot load reference profile source: {exc}") from None
    namespace = "{http://www.ros.org/wiki/xacro}"
    radii, wheel_y = {}, {}
    for node in xacro:
        if node.tag == namespace + "cylinder_link" and node.get("name") in {"left_wheel_link", "right_wheel_link"}:
            name = node.get("name")
            if name in radii:
                raise ReferenceProfileError(f"duplicate wheel link: {name}")
            radii[name] = _finite(node.get("radius"), f"xacro {name} radius")
        if node.tag == "joint" and node.get("name") in {"left_wheel_joint", "right_wheel_joint"}:
            name = node.get("name")
            origin = node.find("origin")
            if name in wheel_y or node.get("type") != "continuous" or origin is None or not origin.get("xyz"):
                raise ReferenceProfileError(f"xacro {name} wheel joint is invalid")
            parts = origin.get("xyz").split()
            if len(parts) != 3:
                raise ReferenceProfileError(f"xacro {name} origin is invalid")
            wheel_y[name] = _finite(parts[1], f"xacro {name} origin y", positive=False)
    if set(radii) != {"left_wheel_link", "right_wheel_link"} or len(set(radii.values())) != 1:
        raise ReferenceProfileError("xacro must declare matching left/right wheel radii")
    if set(wheel_y) != {"left_wheel_joint", "right_wheel_joint"}:
        raise ReferenceProfileError("xacro must declare left/right wheel joints")
    radius = radii["left_wheel_link"]
    separation = abs(wheel_y["left_wheel_joint"] - wheel_y["right_wheel_joint"])
    if separation <= 0:
        raise ReferenceProfileError("xacro wheel separation must be positive")
    if _yaml(controllers, "wheel_radius") != radius or _yaml(controllers, "wheel_separation") != separation:
        raise ReferenceProfileError("controllers and xacro wheel geometry disagree")
    return ReferenceRunnerProfile(radius, separation)
