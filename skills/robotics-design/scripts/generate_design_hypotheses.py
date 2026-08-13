#!/usr/bin/env python3
"""Generate bounded robot design hypotheses and publish an evidence bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assurance.hypothesis.engine import EngineError, run_space


def _seed(value: str) -> int:
    if value.lower() in {"true", "false"}:
        raise argparse.ArgumentTypeError("seed must be an integer")
    try:
        return int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("seed must be an integer") from None


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("space", type=Path, help="Path to hypothesis-space JSON")
    parser.add_argument("--out", type=Path, required=True, help="Absent output bundle path")
    parser.add_argument("--seed", type=_seed, required=True, help="Deterministic integer seed")
    parser.add_argument("--force", action="store_true", help="Transactionally replace output")
    args = parser.parse_args(argv)

    if _inside(args.out, args.space.parent):
        print(
            "ERROR: output must be outside the hypothesis-space source directory",
            file=sys.stderr,
        )
        return 2
    try:
        result = run_space(args.space, args.out, seed=args.seed, force=args.force)
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # Last-resort fail-closed CLI boundary.
        print(
            f"ERROR: hypothesis evaluation failed safely: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    candidate_count = result["candidate_count"]
    accepted_count = result["accepted_count"]
    receipt = result["bundle_manifest_sha256"]
    print(
        f"bundle={args.out.resolve()} candidates={candidate_count} "
        f"accepted={accepted_count} manifest_sha256={receipt}"
    )
    if accepted_count == 0:
        rejected = next(
            (
                item
                for item in result["candidates"]
                if item["status"] not in {"accepted", "alias"}
            ),
            None,
        )
        if rejected is not None:
            print(
                f"BLOCKED: candidate={rejected['candidate_id']} status={rejected['status']}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
