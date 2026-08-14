"""Local, fail-closed intake for raw component bench-evidence packages."""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from .hypothesis.canonical import validate_sha256
from .engineering_freeze.schema import FreezeSchemaError, load_canonical_json


_ROOT = frozenset({"schema_version", "package_id", "fixture_only", "component_id", "supports_claims", "observed_date", "site_id", "operator_id", "test_card", "instrument", "raw_data"})
_TEST_CARD = frozenset({"id", "status", "authority", "reachable_estop", "energy_limit", "abort_criteria"})
_INSTRUMENT = frozenset({"id", "calibration_path", "calibration_sha256"})
_RAW = frozenset({"path", "sha256", "columns", "sample_count", "start_timestamp_ns", "end_timestamp_ns"})


@dataclass(frozen=True)
class BenchEvidenceResult:
    status: str
    evidence_level: str | None
    fixture_only: bool
    findings: tuple[dict[str, str], ...]
    procurement_authorized: bool = False
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "rejected", "awaiting_authorization"}:
            raise ValueError("invalid bench evidence status")
        if self.procurement_authorized or self.motion_authorized:
            raise ValueError("bench evidence cannot authorize procurement or motion")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "evidence_level": self.evidence_level, "fixture_only": self.fixture_only, "procurement_authorized": False, "motion_authorized": False, "findings": list(self.findings)}


def _finding(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _safe_file(root: Path, value: object, prefix: str | None = None) -> Path | None:
    if not isinstance(value, str) or "\\" in value:
        return None
    parsed = PurePosixPath(value)
    if not value or parsed.is_absolute() or ".." in parsed.parts or (prefix and (not parsed.parts or parsed.parts[0] != prefix)):
        return None
    target = root / Path(*parsed.parts)
    return target if target.is_file() and not target.is_symlink() else None


def _sha(target: Path, expected: object) -> bool:
    try:
        return hashlib.sha256(target.read_bytes()).hexdigest() == validate_sha256(expected, "sha256")
    except ValueError:
        return False


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def validate_bench_package(root: Path, data: object, component_ids: set[str], requirement_ids: set[str]) -> BenchEvidenceResult:
    findings: list[dict[str, str]] = []
    if not isinstance(data, dict) or set(data) != _ROOT or data.get("schema_version") != 1:
        return BenchEvidenceResult("rejected", None, False, (_finding("BENCH.PACKAGE_INVALID", "package", "fields are closed and schema_version must be 1"),))
    fixture_only = data.get("fixture_only")
    if type(fixture_only) is not bool:
        findings.append(_finding("BENCH.FIXTURE_FLAG_INVALID", "fixture_only", "fixture_only must be a boolean"))
    if data.get("component_id") not in component_ids:
        findings.append(_finding("BENCH.COMPONENT_UNKNOWN", "component_id", "component must exist in the design ledger"))
    claims = data.get("supports_claims")
    if not isinstance(claims, list) or not claims or any(item not in requirement_ids for item in claims):
        findings.append(_finding("BENCH.CLAIM_UNKNOWN", "supports_claims", "claims must be known non-empty requirement IDs"))
    observed = _date(data.get("observed_date"))
    if observed is None or not all(isinstance(data.get(name), str) and data[name] for name in ("package_id", "site_id", "operator_id")):
        findings.append(_finding("BENCH.PROVENANCE_INVALID", "package", "identity, site, operator, and observed ISO date are required"))
    card = data.get("test_card")
    if not isinstance(card, dict) or set(card) != _TEST_CARD or card.get("status") != "approved_for_recording" or not all(isinstance(card.get(name), str) and card[name] for name in ("id", "authority", "reachable_estop", "energy_limit")) or not isinstance(card.get("abort_criteria"), list) or not card["abort_criteria"]:
        findings.append(_finding("BENCH.TEST_CARD_INVALID", "test_card", "approved recording card requires authority, E-stop, energy and abort records"))
    instrument = data.get("instrument")
    if not isinstance(instrument, dict) or set(instrument) != _INSTRUMENT:
        findings.append(_finding("BENCH.INSTRUMENT_INVALID", "instrument", "instrument fields are closed"))
    else:
        calibration_path = _safe_file(root, instrument.get("calibration_path"))
        if calibration_path is None:
            findings.append(_finding("BENCH.CALIBRATION_MISSING", "instrument.calibration_path", "calibration must be a local regular file"))
        elif not _sha(calibration_path, instrument.get("calibration_sha256")):
            findings.append(_finding("BENCH.CALIBRATION_HASH_MISMATCH", "instrument.calibration_sha256", "calibration hash does not match"))
        else:
            try:
                calibration = load_canonical_json(calibration_path)
                valid_from, valid_to = _date(calibration.get("valid_from")), _date(calibration.get("valid_to"))
                if set(calibration) != {"certificate_id", "instrument_id", "valid_from", "valid_to", "measured_columns"} or calibration.get("instrument_id") != instrument.get("id") or observed is None or valid_from is None or valid_to is None or not valid_from <= observed <= valid_to:
                    findings.append(_finding("BENCH.CALIBRATION_EXPIRED", "instrument", "calibration identity/window does not cover observation"))
            except FreezeSchemaError as exc:
                findings.append(_finding("BENCH.CALIBRATION_INVALID", "instrument.calibration_path", str(exc)))
    raw = data.get("raw_data")
    if not isinstance(raw, dict) or set(raw) != _RAW:
        findings.append(_finding("BENCH.RAW_INVALID", "raw_data", "raw data fields are closed"))
    else:
        target = _safe_file(root, raw.get("path"), "raw")
        if target is None:
            findings.append(_finding("BENCH.RAW_PATH_INVALID", "raw_data.path", "raw CSV must be a local regular file under raw/"))
        elif not _sha(target, raw.get("sha256")):
            findings.append(_finding("BENCH.RAW_HASH_MISMATCH", "raw_data.sha256", "raw CSV hash does not match"))
        else:
            try:
                with target.open("r", encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                columns = raw.get("columns")
                if not isinstance(columns, dict) or columns != {"timestamp_ns": "ns", "command_m_s": "m/s", "observed_m_s": "m/s"} or not rows or any(set(row) != set(columns) for row in rows):
                    findings.append(_finding("BENCH.RAW_COLUMNS", "raw_data", "raw CSV must use exact declared columns and units"))
                else:
                    timestamps = []
                    for row in rows:
                        stamp = int(row["timestamp_ns"])
                        if stamp < 0 or any(not math.isfinite(float(row[name])) for name in ("command_m_s", "observed_m_s")):
                            raise ValueError("non-finite or negative sample")
                        timestamps.append(stamp)
                    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
                        findings.append(_finding("BENCH.RAW_TIMESTAMPS", "raw_data", "timestamps must be strictly increasing"))
                    if raw.get("sample_count") != len(rows) or raw.get("start_timestamp_ns") != timestamps[0] or raw.get("end_timestamp_ns") != timestamps[-1]:
                        findings.append(_finding("BENCH.RAW_SUMMARY_MISMATCH", "raw_data", "raw summary does not match CSV"))
            except (OSError, UnicodeDecodeError, ValueError, csv.Error) as exc:
                findings.append(_finding("BENCH.RAW_INVALID", "raw_data", f"cannot parse bounded CSV: {exc}"))
    findings.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return BenchEvidenceResult("accepted" if not findings else "rejected", "bench-tested" if not findings else None, bool(fixture_only), tuple(findings))
