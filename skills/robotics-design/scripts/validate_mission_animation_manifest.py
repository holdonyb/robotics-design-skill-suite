#!/usr/bin/env python3
"""Validate traceability and safety invariants for robot mission animations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
STATUSES = {"draft", "rejected", "promoted"}
CONTACT_STATES = {"free", "coarse_capture", "guided_alignment", "hard_lock", "service_mate"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(data: dict[str, Any], field: str, errors: list[str]) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or any(not _nonempty(item) for item in value):
        errors.append(f"{field} must be a list of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{field} must not contain duplicates")
    return value


def _file(record: Any, field: str, root: Path, errors: list[str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"{field} must contain path and sha256")
        return
    raw_path = record.get("path")
    expected = record.get("sha256")
    if not _nonempty(raw_path) or not isinstance(expected, str) or not SHA256.fullmatch(expected):
        errors.append(f"{field} must contain a relative path and lowercase SHA-256")
        return
    relative = Path(raw_path)
    if relative.is_absolute():
        errors.append(f"{field}.path must be relative to the manifest")
        return
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        errors.append(f"{field}.path escapes the manifest directory: {raw_path}")
        return
    if not candidate.is_file():
        errors.append(f"{field}.path does not exist: {raw_path}")
        return
    actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual != expected:
        errors.append(f"{field} SHA-256 mismatch: {raw_path}")


def validate_manifest(data: Any, manifest_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be a JSON object"]
    schema_version = data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != SCHEMA_VERSION
    ):
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _nonempty(data.get("animation_id")):
        errors.append("animation_id must be a non-empty string")
    status = data.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        errors.append("status must be one of: draft, rejected, promoted")

    for field in ("source_model", "source_trajectory", "physics_trace", "rendered_animation"):
        _file(data.get(field), field, manifest_dir, errors)

    joint_order = _strings(data, "joint_order", errors)
    required = _strings(data, "required_moving_joints", errors)
    observed = _strings(data, "observed_moving_joints", errors)
    contact_interfaces = _strings(data, "contact_interfaces", errors)
    continuous_anchor_required = data.get("continuous_anchor_required")
    if not isinstance(continuous_anchor_required, bool):
        errors.append("continuous_anchor_required must be boolean")
    unknown = sorted((set(required) | set(observed)) - set(joint_order))
    if unknown:
        errors.append("moving joints absent from joint_order: " + ",".join(unknown))

    phases = data.get("task_phases")
    if not isinstance(phases, list) or not phases:
        errors.append("task_phases must contain at least one phase")
    else:
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                errors.append(f"task_phases[{index}] must be an object")
                continue
            if not _nonempty(phase.get("name")):
                errors.append(f"task_phases[{index}].name must be non-empty")
            if not _nonempty(phase.get("load_case_id")):
                errors.append(f"task_phases[{index}].load_case_id must be non-empty")
            contacts = phase.get("contact_state")
            if not isinstance(contacts, dict) or not contacts:
                errors.append(f"task_phases[{index}].contact_state must be a non-empty object")
                continue
            missing_interfaces = sorted(set(contact_interfaces) - set(contacts))
            if missing_interfaces:
                errors.append(
                    f"task_phases[{index}] missing declared contact interfaces: "
                    + ",".join(missing_interfaces)
                )
            invalid = sorted(
                repr(value)
                for value in contacts.values()
                if not isinstance(value, str) or value not in CONTACT_STATES
            )
            if invalid:
                errors.append(f"task_phases[{index}] has invalid contact states: " + ",".join(invalid))
            if (
                continuous_anchor_required is True
                and contact_interfaces
                and all(contacts.get(interface) == "free" for interface in contact_interfaces)
            ):
                errors.append(f"task_phases[{index}] leaves all declared interfaces free")

    checks = data.get("checks")
    required_zero = (
        "topology_drift",
        "joint_limit_violations",
        "collision_violations",
        "unconstrained_both_ends_frames",
    )
    if not isinstance(checks, dict):
        errors.append("checks must be an object")
    else:
        for field in required_zero:
            value = checks.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"checks.{field} must be a non-negative integer")
            elif status == "promoted" and value != 0:
                errors.append(f"checks.{field} must be zero for promoted animations")
        if not isinstance(checks.get("physics_trace_passed"), bool):
            errors.append("checks.physics_trace_passed must be boolean")
        elif status == "promoted" and not checks["physics_trace_passed"]:
            errors.append("checks.physics_trace_passed must be true for promoted animations")

    if status == "promoted":
        if not joint_order:
            errors.append("joint_order must contain at least one joint for promoted animations")
        if not required:
            errors.append(
                "required_moving_joints must contain at least one joint for promoted animations"
            )
        if not observed:
            errors.append(
                "observed_moving_joints must contain at least one joint for promoted animations"
            )
        if not contact_interfaces:
            errors.append(
                "contact_interfaces must contain at least one interface for promoted animations"
            )
        missing = sorted(set(required) - set(observed))
        extra = sorted(set(observed) - set(required))
        if missing or extra:
            parts = []
            if missing:
                parts.append("missing=" + ",".join(missing))
            if extra:
                parts.append("extra=" + ",".join(extra))
            errors.append("promoted moving joint mismatch: " + "; ".join(parts))
        review = data.get("review")
        if not isinstance(review, dict):
            errors.append("review must be an object for promoted animations")
        else:
            for field in ("reviewer", "method", "notes"):
                if not _nonempty(review.get(field)):
                    errors.append(f"review.{field} must be non-empty for promoted animations")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load manifest: {exc}", file=sys.stderr)
        return 1
    errors = validate_manifest(data, args.manifest.parent)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Mission animation manifest valid: {data['animation_id']} ({data['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
