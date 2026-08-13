"""Regenerate the closed, hash-bound receipt manifest for the ROS workspace."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


REFERENCE = Path(__file__).resolve().parents[1]
SCRIPTS = REFERENCE.parents[1] / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402


SOURCES = ("model/geometry.json", "robot.urdf", "design-contract.json", "assumptions.json")
OUTPUT = REFERENCE / "simulation" / "ros-workspace-manifest.json"


def _record(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(REFERENCE).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> None:
    workspace = REFERENCE / "ros2_ws" / "src"
    if not workspace.is_dir():
        raise SystemExit("ROS workspace source directory is missing")
    files = sorted(path for path in workspace.rglob("*") if path.is_file() and not path.is_symlink())
    if not files:
        raise SystemExit("ROS workspace source directory is empty")
    if any(path.is_symlink() for path in workspace.rglob("*")):
        raise SystemExit("ROS workspace cannot contain symlinks")
    manifest = {
        "schema_version": 1,
        "sources": [_record(REFERENCE / value) for value in SOURCES],
        "outputs": [_record(path) for path in files],
    }
    OUTPUT.write_bytes(canonical_bytes(manifest))
    print(hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
