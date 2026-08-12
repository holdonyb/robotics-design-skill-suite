#!/usr/bin/env python3
"""Validate a robotics visual-fidelity manifest using the standard library."""

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
ALLOWED_CHANGES = {
    "background",
    "color",
    "environment",
    "lighting",
    "materials",
    "surface_finish",
}
REQUIRED_FORBIDDEN_CHANGES = {
    "interfaces",
    "joint_axes",
    "joint_count",
    "link_proportions",
    "pose",
    "topology",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(data: dict[str, Any], field: str, errors: list[str]) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or any(not _nonempty_string(item) for item in value):
        errors.append(f"{field} must be a list of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{field} must not contain duplicates")
    return value


def _file_record(
    record: Any,
    field: str,
    manifest_dir: Path,
    errors: list[str],
) -> None:
    if not isinstance(record, dict):
        errors.append(f"{field} must contain path and sha256")
        return

    raw_path = record.get("path")
    expected_hash = record.get("sha256")
    if not _nonempty_string(raw_path):
        errors.append(f"{field}.path must be a non-empty relative path")
        return
    if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash):
        errors.append(f"{field}.sha256 must be a lowercase SHA-256 digest")
        return

    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        errors.append(f"{field}.path must be relative to the manifest")
        return

    root = manifest_dir.resolve()
    candidate = (manifest_dir / relative_path).resolve()
    if not candidate.is_relative_to(root):
        errors.append(f"{field}.path escapes the manifest directory: {raw_path}")
        return
    if not candidate.is_file():
        errors.append(f"{field}.path does not exist: {raw_path}")
        return

    actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        errors.append(f"{field} SHA-256 mismatch: {raw_path}")


def validate_manifest(data: Any, manifest_dir: Path) -> list[str]:
    """Return actionable validation errors; an empty list means valid."""

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
    if not _nonempty_string(data.get("shot_id")):
        errors.append("shot_id must be a non-empty string")

    status = data.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        errors.append("status must be one of: draft, rejected, promoted")

    _file_record(data.get("source_model"), "source_model", manifest_dir, errors)
    _file_record(data.get("source_pose"), "source_pose", manifest_dir, errors)

    references = data.get("reference_images")
    if not isinstance(references, list) or not references:
        errors.append("reference_images must contain at least one deterministic render")
    else:
        for index, record in enumerate(references):
            _file_record(record, f"reference_images[{index}]", manifest_dir, errors)

    _file_record(data.get("rendered_image"), "rendered_image", manifest_dir, errors)

    required_landmarks = _string_list(data, "required_landmarks", errors)
    observed_landmarks = _string_list(data, "observed_landmarks", errors)
    allowed_changes = _string_list(data, "allowed_changes", errors)
    forbidden_changes = _string_list(data, "forbidden_changes", errors)

    unauthorized = sorted(set(allowed_changes) - ALLOWED_CHANGES)
    if unauthorized:
        errors.append("allowed_changes contains unauthorized values: " + ", ".join(unauthorized))

    missing_forbidden = sorted(REQUIRED_FORBIDDEN_CHANGES - set(forbidden_changes))
    if missing_forbidden:
        errors.append(
            "forbidden_changes must include structural invariants: "
            + ", ".join(missing_forbidden)
        )

    contradictory = sorted(set(allowed_changes) & set(forbidden_changes))
    if contradictory:
        errors.append("changes cannot be both allowed and forbidden: " + ", ".join(contradictory))

    if status == "promoted":
        if not required_landmarks:
            errors.append("required_landmarks must contain at least one joint or interface for promoted assets")
        missing = sorted(set(required_landmarks) - set(observed_landmarks))
        extra = sorted(set(observed_landmarks) - set(required_landmarks))
        if missing or extra:
            detail: list[str] = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if extra:
                detail.append("extra=" + ",".join(extra))
            errors.append("promoted landmark mismatch: " + "; ".join(detail))

        review = data.get("review")
        if not isinstance(review, dict):
            errors.append("review must be an object for promoted assets")
        else:
            for field in ("reviewer", "method", "notes"):
                if not _nonempty_string(review.get(field)):
                    errors.append(f"review.{field} must be a non-empty string for promoted assets")

    return errors


def load_and_validate(manifest_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"manifest does not exist: {manifest_path}"]
    except json.JSONDecodeError as exc:
        return None, [f"manifest is not valid JSON: {exc}"]
    except OSError as exc:
        return None, [f"cannot read manifest: {exc}"]

    return data, validate_manifest(data, manifest_path.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to a visual manifest JSON file")
    args = parser.parse_args(argv)

    data, errors = load_and_validate(args.manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    assert data is not None
    print(f"Visual manifest valid: {data['shot_id']} ({data['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
