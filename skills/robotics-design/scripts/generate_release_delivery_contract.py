#!/usr/bin/env python3
"""Generate one canonical public-delivery contract from a closed release profile."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from assurance.hypothesis.canonical import canonical_bytes
from assurance.release.evaluator import REQUIRED_PATHS_BY_RELEASE, required_paths_for


def _under_root(root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError("output must remain under root") from None
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("output must not traverse a symbolic link")
    return relative


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--release-id", choices=sorted(REQUIRED_PATHS_BY_RELEASE), default="v1.0.0")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if not root.is_dir() or root.is_symlink():
            raise ValueError("root must be a local non-symlink directory")
        output = args.out.resolve()
        _under_root(root, output)
        if output.exists() or output.is_symlink():
            raise ValueError("output must be a new regular file")
        bindings = []
        for relative in sorted(required_paths_for(args.release_id)):
            source = root / relative
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"required source is not a regular file: {relative}")
            bindings.append({"path": relative, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            canonical_bytes(
                {
                    "schema_version": 1,
                    "release_id": args.release_id,
                    "artifact_bindings": bindings,
                    "hardware_claims": False,
                }
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: release delivery contract generation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
