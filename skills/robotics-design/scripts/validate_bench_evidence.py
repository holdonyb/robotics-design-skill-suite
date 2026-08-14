#!/usr/bin/env python3
"""Validate local raw bench-evidence intake without hardware control authority."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from pathlib import PurePosixPath

from assurance.contract import load_contract
from assurance.engineering_freeze.schema import load_canonical_json
from assurance.hypothesis.canonical import canonical_bytes, validate_sha256
from assurance.bench_evidence import validate_bench_package


_INTAKE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


def _safe_bound_file(root: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} must be a nonempty forward-slash local path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field} must remain under the intake directory")
    target = root
    for part in parsed.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError(f"{field} must not traverse a symbolic link")
    if not target.is_file():
        raise ValueError(f"{field} must name a local regular file")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = load_canonical_json(args.index)
        allowed_empty = {"schema_version", "intake_id", "packages"}
        allowed_populated = allowed_empty | {"design_contract"}
        if not isinstance(index, dict) or set(index) not in (allowed_empty, allowed_populated) or index.get("schema_version") != 1 or not isinstance(index.get("packages"), list):
            raise ValueError("intake index must be a closed schema-v1 object")
        if not isinstance(index.get("intake_id"), str) or not _INTAKE_ID.fullmatch(index["intake_id"]):
            raise ValueError("intake_id must be a stable identifier")
        if not index["packages"]:
            if set(index) != allowed_empty:
                raise ValueError("empty intake must not carry a design contract or evidence claim")
            output = {
                "status": "awaiting_authorization", "intake_id": index.get("intake_id"), "accepted_packages": 0,
                "procurement_authorized": False, "motion_authorized": False,
                "findings": [{"code": "BENCH.NO_RAW_EVIDENCE", "path": "packages", "message": "no raw bench package has been provided under authorized test conditions"}],
            }
            sys.stdout.buffer.write(canonical_bytes(output))
            return 1
        contract_record = index.get("design_contract")
        if not isinstance(contract_record, dict) or set(contract_record) != {"path", "sha256"}:
            raise ValueError("nonempty intake requires a hash-bound design_contract")
        contract_path = _safe_bound_file(args.index.parent, contract_record["path"], "design_contract.path")
        if hashlib.sha256(contract_path.read_bytes()).hexdigest() != validate_sha256(contract_record["sha256"], "design_contract.sha256"):
            raise ValueError("design contract hash does not match intake index")
        contract, contract_errors = load_contract(contract_path)
        if contract_errors or not isinstance(contract, dict):
            raise ValueError("design contract is invalid: " + "; ".join(contract_errors))
        components = contract["components"]
        requirements = contract["requirements"]
        component_ids = {item.get("id") for item in components if isinstance(item, dict) and isinstance(item.get("id"), str)}
        requirement_ids = {item.get("id") for item in requirements if isinstance(item, dict) and isinstance(item.get("id"), str)}
        results = []
        package_ids: set[str] = set()
        package_hashes: set[str] = set()
        raw_hashes: set[str] = set()
        for index_number, record in enumerate(index["packages"]):
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise ValueError(f"packages[{index_number}] must have path and sha256")
            package_path = _safe_bound_file(args.index.parent, record["path"], f"packages[{index_number}].path")
            package_sha256 = validate_sha256(record["sha256"], f"packages[{index_number}].sha256")
            if package_sha256 in package_hashes:
                raise ValueError(f"packages[{index_number}] duplicates an earlier package hash")
            package_hashes.add(package_sha256)
            if hashlib.sha256(package_path.read_bytes()).hexdigest() != package_sha256:
                raise ValueError(f"packages[{index_number}] hash does not match")
            package = load_canonical_json(package_path)
            package_id = package.get("package_id")
            if not isinstance(package_id, str) or package_id in package_ids:
                raise ValueError(f"packages[{index_number}] must have a unique package_id")
            package_ids.add(package_id)
            raw_data = package.get("raw_data")
            raw_sha256 = raw_data.get("sha256") if isinstance(raw_data, dict) else None
            if not isinstance(raw_sha256, str) or raw_sha256 in raw_hashes:
                raise ValueError(f"packages[{index_number}] must bind a unique raw_data.sha256")
            raw_hashes.add(raw_sha256)
            results.append(validate_bench_package(args.index.parent, package, component_ids, requirement_ids).to_dict())
        accepted = sum(item["status"] == "accepted" and item["evidence_level"] == "bench-tested" for item in results)
        fixture_only = any(item["fixture_only"] for item in results)
        status = "accepted" if accepted == len(results) else "awaiting_authorization" if fixture_only and all(item["status"] == "accepted" for item in results) else "rejected"
        output = {"status": status, "intake_id": index.get("intake_id"), "accepted_packages": accepted, "evidence_level": "bench-tested" if status == "accepted" else None, "procurement_authorized": False, "motion_authorized": False, "packages": results}
        sys.stdout.buffer.write(canonical_bytes(output))
        return 0 if status == "accepted" else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: bench evidence validation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
