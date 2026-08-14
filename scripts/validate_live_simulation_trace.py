#!/usr/bin/env python3
"""Decode one bounded Jazzy rosbag2 MCAP capture into retained simulation evidence."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes
from assurance.simulation.live_trace import (
    LiveTraceError,
    _TOPIC_TYPES,
    _raw_inventory,
    normalize_records,
    publish_live_trace_bundle,
    require_live_dynamics_crosscheck,
    validate_live_capture,
    validate_retained_live_trace_bundle,
)
from validate_simulation_bundle import BenchmarkError, _load_backend_profile


def _message_mapping(topic: str, message: object) -> dict:
    def stamp(header):
        return {"sec": int(header.stamp.sec), "nanosec": int(header.stamp.nanosec)}

    if topic == "/clock":
        return {"clock": {"sec": int(message.clock.sec), "nanosec": int(message.clock.nanosec)}}
    if topic == "/joint_states":
        return {"header": {"stamp": stamp(message.header)}, "name": list(message.name), "position": list(message.position)}
    if topic == "/diff_drive_controller/odom":
        pose = message.pose.pose
        return {
            "header": {"stamp": stamp(message.header)},
            "pose": {"pose": {"position": {"x": pose.position.x, "y": pose.position.y}, "orientation": {"z": pose.orientation.z, "w": pose.orientation.w}}},
        }
    twist = message.twist
    return {"header": {"stamp": stamp(message.header)}, "twist": {"linear": {"x": twist.linear.x}, "angular": {"z": twist.angular.z}}}


def _decode_mcap(bag: Path) -> list[dict]:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id="mcap"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    declared = {item.name: item.type for item in reader.get_all_topics_and_types()}
    if declared != _TOPIC_TYPES:
        raise LiveTraceError("rosbag topic/type inventory is not closed")
    records = []
    while reader.has_next():
        topic, payload, timestamp_ns = reader.read_next()
        message_type = declared.get(topic)
        if message_type is None:
            raise LiveTraceError("rosbag emitted an unknown topic")
        message = deserialize_message(payload, get_message(message_type))
        records.append({"topic": topic, "type": message_type, "timestamp_ns": int(timestamp_ns), "message": _message_mapping(topic, message)})
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--bag", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _raw_inventory(args.bag)
        capture = normalize_records(_decode_mcap(args.bag))
        profile = _load_backend_profile(args.reference_root)
        validation = validate_live_capture(capture, profile)
        dynamics_crosscheck = require_live_dynamics_crosscheck(capture, profile)
        validation["dynamics_crosscheck"] = dynamics_crosscheck
        receipt = publish_live_trace_bundle(args.out, capture, profile, args.bag)
        errors = validate_retained_live_trace_bundle(args.out, receipt.manifest_sha256, args.bag)
        if errors:
            raise LiveTraceError("retained bundle validation failed: " + "; ".join(errors))
        print(canonical_bytes({"manifest_sha256": receipt.manifest_sha256, "validation": validation}).decode("utf-8"), end="")
        return 0
    except (BenchmarkError, LiveTraceError, OSError, OverflowError, TypeError, ValueError) as exc:
        print(f"ERROR: live simulation trace validation failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
