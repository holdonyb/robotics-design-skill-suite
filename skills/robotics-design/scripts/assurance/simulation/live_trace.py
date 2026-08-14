"""Validate and retain receipt-bound evidence from a live simulator capture."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ..hypothesis.bundle import BundleError, BundleReceipt, validate_bundle, write_bundle_with_receipt
from ..hypothesis.canonical import canonical_value, validate_sha256


class LiveTraceError(ValueError):
    """A live simulation capture is malformed, stale, or outside its contract."""


_CAPTURE_FIELDS = {"clock_ns", "joint_samples", "odom_samples", "command_samples"}
_MAX_SAMPLES = 10_000
_MAX_RAW_BYTES = 64 * 1024 * 1024
_DRIVE_JOINTS = {"left_wheel_joint", "right_wheel_joint"}
_TOPIC_TYPES = {
    "/clock": "rosgraph_msgs/msg/Clock",
    "/joint_states": "sensor_msgs/msg/JointState",
    "/odom": "nav_msgs/msg/Odometry",
    "/diff_drive_controller/cmd_vel": "geometry_msgs/msg/TwistStamped",
}


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise LiveTraceError(f"{name} must be finite")
    return float(value)


def _timestamps(values: object, name: str, *, minimum: int) -> list[int]:
    if not isinstance(values, list) or not minimum <= len(values) <= _MAX_SAMPLES:
        raise LiveTraceError(f"{name} must contain between {minimum} and {_MAX_SAMPLES} samples")
    stamps: list[int] = []
    for index, value in enumerate(values):
        if type(value) is not int or value < 0:
            raise LiveTraceError(f"{name}[{index}] timestamp must be a nonnegative integer")
        if stamps and value <= stamps[-1]:
            raise LiveTraceError(f"{name} timestamps must be strictly increasing")
        stamps.append(value)
    return stamps


def _profile(profile: object) -> tuple[float, float, str, list[dict[str, str]]]:
    if not isinstance(profile, dict):
        raise LiveTraceError("profile must be an object")
    radius = _finite(profile.get("wheel_radius_m"), "profile wheel_radius_m")
    speed = _finite(profile.get("wheel_speed_limit_rad_s"), "profile wheel_speed_limit_rad_s")
    if radius <= 0 or speed <= 0:
        raise LiveTraceError("profile wheel geometry must be positive")
    workspace = profile.get("workspace_manifest_sha256")
    try:
        validate_sha256(workspace, "profile workspace_manifest_sha256")
    except ValueError as exc:
        raise LiveTraceError(str(exc)) from None
    sources = profile.get("sources")
    if not isinstance(sources, list) or not sources:
        raise LiveTraceError("profile sources must be a non-empty list")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(sources):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise LiveTraceError(f"profile sources[{index}] fields are invalid")
        path, digest = item["path"], item["sha256"]
        if not isinstance(path, str) or not path or path in seen:
            raise LiveTraceError("profile source paths must be unique non-empty strings")
        try:
            validate_sha256(digest, f"profile sources[{index}].sha256")
        except ValueError as exc:
            raise LiveTraceError(str(exc)) from None
        seen.add(path)
        normalized.append({"path": path, "sha256": digest})
    return radius, speed, workspace, sorted(normalized, key=lambda item: item["path"])


def _header(message: object, name: str) -> None:
    if not isinstance(message, dict) or not isinstance(message.get("header"), dict):
        raise LiveTraceError(f"{name} message must contain a header")
    stamp = message["header"].get("stamp")
    if not isinstance(stamp, dict) or type(stamp.get("sec")) is not int or type(stamp.get("nanosec")) is not int:
        raise LiveTraceError(f"{name} header stamp is invalid")


def normalize_records(records: object) -> dict[str, Any]:
    """Convert message-shaped records from the ROS-only adapter to closed primitives."""
    if not isinstance(records, list) or not records:
        raise LiveTraceError("decoded records must be a non-empty list")
    output: dict[str, list[Any]] = {
        "clock_ns": [], "joint_samples": [], "odom_samples": [], "command_samples": [],
    }
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {"topic", "type", "timestamp_ns", "message"}:
            raise LiveTraceError(f"decoded records[{index}] fields are not closed")
        topic, message_type, stamp, message = record["topic"], record["type"], record["timestamp_ns"], record["message"]
        if topic not in _TOPIC_TYPES:
            raise LiveTraceError(f"decoded records[{index}] has unknown topic")
        if message_type != _TOPIC_TYPES[topic]:
            raise LiveTraceError(f"decoded records[{index}] has unexpected ROS type")
        if type(stamp) is not int or stamp < 0 or not isinstance(message, dict):
            raise LiveTraceError(f"decoded records[{index}] timestamp or message is invalid")
        if topic == "/clock":
            clock = message.get("clock")
            if not isinstance(clock, dict) or type(clock.get("sec")) is not int or type(clock.get("nanosec")) is not int:
                raise LiveTraceError("clock message is invalid")
            output["clock_ns"].append(stamp)
        elif topic == "/joint_states":
            _header(message, "joint state")
            output["joint_samples"].append({"timestamp_ns": stamp, "names": message.get("name"), "positions": message.get("position")})
        elif topic == "/odom":
            _header(message, "odometry")
            try:
                pose = message["pose"]["pose"]
                position, orientation = pose["position"], pose["orientation"]
                z, w = _finite(orientation["z"], "odometry orientation.z"), _finite(orientation["w"], "odometry orientation.w")
                yaw = math.atan2(2.0 * z * w, 1.0 - 2.0 * z * z)
                output["odom_samples"].append({"timestamp_ns": stamp, "x_m": position["x"], "y_m": position["y"], "yaw_rad": yaw})
            except (KeyError, TypeError, LiveTraceError) as exc:
                raise LiveTraceError(f"odometry message is invalid: {exc}") from None
        else:
            _header(message, "command")
            try:
                twist = message["twist"]
                output["command_samples"].append({"timestamp_ns": stamp, "linear_x_m_s": twist["linear"]["x"], "angular_z_rad_s": twist["angular"]["z"]})
            except (KeyError, TypeError) as exc:
                raise LiveTraceError(f"command message is invalid: {exc}") from None
    return output


def validate_live_capture(capture: object, profile: object) -> dict[str, Any]:
    """Validate closed primitive records decoded from one bounded live rosbag."""
    radius, wheel_speed, _, _ = _profile(profile)
    if not isinstance(capture, dict) or set(capture) != _CAPTURE_FIELDS:
        raise LiveTraceError("capture fields are not closed")
    clock = _timestamps(capture["clock_ns"], "clock", minimum=3)

    joints = capture["joint_samples"]
    if not isinstance(joints, list) or not 2 <= len(joints) <= _MAX_SAMPLES:
        raise LiveTraceError("joint_samples must contain between 2 and 10000 samples")
    joint_stamps: list[int] = []
    for index, item in enumerate(joints):
        if not isinstance(item, dict) or set(item) != {"timestamp_ns", "names", "positions"}:
            raise LiveTraceError(f"joint_samples[{index}] fields are not closed")
        stamp = _timestamps([item["timestamp_ns"]], f"joint_samples[{index}]", minimum=1)[0]
        if joint_stamps and stamp <= joint_stamps[-1]:
            raise LiveTraceError("joint_samples timestamps must be strictly increasing")
        names, positions = item["names"], item["positions"]
        if not isinstance(names, list) or not isinstance(positions, list) or not names or len(names) != len(positions):
            raise LiveTraceError(f"joint_samples[{index}] names and positions are invalid")
        if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
            raise LiveTraceError(f"joint_samples[{index}] names are invalid")
        if not _DRIVE_JOINTS.issubset(names):
            raise LiveTraceError("joint_samples must include both drive joints")
        for position_index, value in enumerate(positions):
            _finite(value, f"joint_samples[{index}].positions[{position_index}]")
        joint_stamps.append(stamp)

    odom = capture["odom_samples"]
    if not isinstance(odom, list) or not 2 <= len(odom) <= _MAX_SAMPLES:
        raise LiveTraceError("odom_samples must contain between 2 and 10000 samples")
    odom_stamps: list[int] = []
    x_values: list[float] = []
    for index, item in enumerate(odom):
        if not isinstance(item, dict) or set(item) != {"timestamp_ns", "x_m", "y_m", "yaw_rad"}:
            raise LiveTraceError(f"odom_samples[{index}] fields are not closed")
        stamp = _timestamps([item["timestamp_ns"]], f"odom_samples[{index}]", minimum=1)[0]
        if odom_stamps and stamp <= odom_stamps[-1]:
            raise LiveTraceError("odom_samples timestamps must be strictly increasing")
        x_values.append(_finite(item["x_m"], f"odom_samples[{index}].x_m"))
        _finite(item["y_m"], f"odom_samples[{index}].y_m")
        _finite(item["yaw_rad"], f"odom_samples[{index}].yaw_rad")
        odom_stamps.append(stamp)

    commands = capture["command_samples"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= _MAX_SAMPLES:
        raise LiveTraceError("command_samples must contain between 1 and 10000 samples")
    command_stamps: list[int] = []
    max_linear = radius * wheel_speed
    positive_command = False
    for index, item in enumerate(commands):
        if not isinstance(item, dict) or set(item) != {"timestamp_ns", "linear_x_m_s", "angular_z_rad_s"}:
            raise LiveTraceError(f"command_samples[{index}] fields are not closed")
        stamp = _timestamps([item["timestamp_ns"]], f"command_samples[{index}]", minimum=1)[0]
        if command_stamps and stamp <= command_stamps[-1]:
            raise LiveTraceError("command_samples timestamps must be strictly increasing")
        linear = _finite(item["linear_x_m_s"], f"command_samples[{index}].linear_x_m_s")
        _finite(item["angular_z_rad_s"], f"command_samples[{index}].angular_z_rad_s")
        if abs(linear) > max_linear:
            raise LiveTraceError("linear command exceeds profile limit")
        positive_command = positive_command or linear > 0
        command_stamps.append(stamp)
    if not positive_command:
        raise LiveTraceError("capture requires a positive forward command")
    displacement = x_values[-1] - x_values[0]
    if displacement < 0.01:
        raise LiveTraceError("forward displacement must be at least 0.01 m")
    return {
        "kind": "live_simulation_trace",
        "evidence_level": "simulated",
        "status": "passed",
        "hardware_promotable": False,
        "forward_displacement_m": displacement,
        "counts": {
            "clock": len(clock),
            "joint_states": len(joints),
            "odom": len(odom),
            "commands": len(commands),
        },
    }


def _raw_inventory(raw_bag: str | Path) -> list[dict[str, Any]]:
    root = Path(raw_bag)
    if root.is_symlink() or not root.is_dir():
        raise LiveTraceError("raw bag directory is invalid")
    files: list[Path] = []
    try:
        for item in root.rglob("*"):
            if item.is_symlink() or item.is_dir() or not item.is_file():
                raise LiveTraceError("raw bag files are not closed")
            files.append(item)
    except OSError as exc:
        raise LiveTraceError(f"cannot inventory raw bag: {exc}") from None
    relative = {item.relative_to(root).as_posix(): item for item in files}
    mcap = [path for path in relative if path.endswith(".mcap")]
    if set(relative) != {"metadata.yaml", *mcap} or len(mcap) != 1:
        raise LiveTraceError("raw bag files are not closed")
    result = []
    for path in sorted(relative):
        try:
            payload = relative[path].read_bytes()
        except OSError as exc:
            raise LiveTraceError(f"cannot read raw bag file: {exc}") from None
        if not payload or len(payload) > _MAX_RAW_BYTES:
            raise LiveTraceError("raw bag file size is invalid")
        result.append({"path": path, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    return result


def publish_live_trace_bundle(output: str | Path, capture: object, profile: object, raw_bag: str | Path) -> BundleReceipt:
    """Publish canonical trace evidence and bind it to a retained raw MCAP bag."""
    result = validate_live_capture(capture, profile)
    _, _, workspace, sources = _profile(profile)
    inventory = _raw_inventory(raw_bag)
    files = {
        "index.json": {"schema_version": 1, "kind": "live_simulation_trace"},
        "provenance.json": {
            "schema_version": 1,
            "workspace_manifest_sha256": workspace,
            "profile_sources": sources,
            "raw_bag_files": inventory,
        },
        "trace.json": capture,
        "validation.json": result,
    }
    try:
        return write_bundle_with_receipt(output, files)
    except BundleError as exc:
        raise LiveTraceError(str(exc)) from None


def _load_object(path: Path) -> dict[str, Any]:
    pairs = lambda values: _unique_pairs(values)
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
        data = canonical_value(data, path.name)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LiveTraceError(f"cannot load retained {path.name}: {exc}") from None
    if not isinstance(data, dict):
        raise LiveTraceError(f"retained {path.name} must be an object")
    return data


def _unique_pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_retained_live_trace_bundle(bundle: str | Path, receipt: str, raw_bag: str | Path) -> list[str]:
    """Return deterministic integrity errors for a canonical bundle and its raw MCAP."""
    root = Path(bundle)
    errors = validate_bundle(root, manifest_sha256=receipt)
    if errors:
        return errors
    try:
        provenance = _load_object(root / "provenance.json")
        if set(provenance) != {"schema_version", "workspace_manifest_sha256", "profile_sources", "raw_bag_files"} or provenance["schema_version"] != 1:
            return ["retained provenance fields are not closed"]
        inventory = _raw_inventory(raw_bag)
        if provenance["raw_bag_files"] != inventory:
            return ["raw bag SHA-256 mismatch"]
    except LiveTraceError as exc:
        return [str(exc)]
    return []
