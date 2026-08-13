"""Closed, bounded schema for deterministic robot-design hypothesis spaces."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import canonical_bytes, canonical_value, validate_identifier, validate_sha256
from ..units import QuantityError, UNITS, to_si


_MAX_FILE_BYTES = 5 * 1024 * 1024
_ROOT_FIELDS = {
    "schema_version",
    "space_id",
    "base_contract",
    "max_candidates",
    "axes",
    "uncertainties",
    "objectives",
    "repair_rules",
    "evaluation",
}
_ARCHITECTURE_FIELDS = {
    "features",
    "drive_units",
    "actuators",
    "moving_cables",
    "claimed_safety_functions",
}
_STAGE_ORDER = (
    "contract_v1",
    "physical_v030",
    "uncertainty_v1",
    "counterexample_v1",
    "objectives_v1",
)
_SEMANTIC_ID = r"[A-Za-z0-9][A-Za-z0-9_:/+@-]*"
_QUANTITY_TARGET = re.compile(rf"^quantity:({_SEMANTIC_ID})\.(value|tolerance)$")
_REPLACEMENT_TARGET = re.compile(rf"^(component|evidence):({_SEMANTIC_ID})$")
_QUANTITY_SOURCE = re.compile(rf"^quantity:{_SEMANTIC_ID}$")
_ANALYSIS_SOURCE = re.compile(
    r"^analysis:[A-Za-z0-9][A-Za-z0-9._:/+@-]*\.outputs"
    r"(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+$"
)


def _closed(record: dict[str, Any], required: set[str], path: str, errors: list[str]) -> None:
    missing = sorted(required - set(record))
    unknown = sorted(set(record) - required)
    if missing:
        errors.append(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")


def _identifier(value: object, path: str, errors: list[str]) -> str | None:
    try:
        return validate_identifier(value, path)
    except ValueError as exc:
        errors.append(str(exc))
        return None


def _unique_ids(records: list[object], path: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if isinstance(identifier, str) and identifier in seen:
            errors.append(f"{path} has duplicate id {identifier}")
        elif isinstance(identifier, str):
            seen.add(identifier)


def _bounded_integer(value: object, low: int, high: int, path: str, errors: list[str]) -> bool:
    if type(value) is not int or not low <= value <= high:
        errors.append(f"{path} must be an integer from {low} through {high}")
        return False
    return True


def _quantity_value(value: object, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object with exactly value and unit")
        return
    _closed(value, {"value", "unit"}, path, errors)
    number = value.get("value")
    if type(number) not in (int, float) or not math.isfinite(number):
        errors.append(f"{path}.value must be a finite JSON number (booleans are not allowed)")
    unit = value.get("unit")
    if not isinstance(unit, str) or not unit:
        errors.append(f"{path}.unit must be a non-empty string")
    elif unit not in UNITS:
        errors.append(f"{path}: unsupported unit: {unit}")
    elif set(value) == {"value", "unit"}:
        try:
            to_si(value, UNITS[unit][0], path)
        except QuantityError as exc:
            errors.append(str(exc))


def _operation(operation: object, path: str, errors: list[str]) -> str | None:
    if not isinstance(operation, dict):
        errors.append(f"{path} must be an object")
        return None
    _closed(operation, {"target", "value"}, path, errors)
    target = operation.get("target")
    if not isinstance(target, str):
        errors.append(f"{path}.target is an unsupported semantic target")
        return None

    quantity = _QUANTITY_TARGET.fullmatch(target)
    replacement = _REPLACEMENT_TARGET.fullmatch(target)
    if quantity:
        _quantity_value(operation.get("value"), f"{path}.value", errors)
    elif replacement:
        value = operation.get("value")
        if not isinstance(value, dict) or value.get("id") != replacement.group(2):
            errors.append(f"{path}.value must be a whole replacement object with the same id as {target}")
        else:
            try:
                canonical_value(value, f"{path}.value")
            except ValueError as exc:
                errors.append(str(exc))
    elif target.startswith("architecture.") and target.removeprefix("architecture.") in _ARCHITECTURE_FIELDS:
        value = operation.get("value")
        if not isinstance(value, list) or not value:
            errors.append(f"{path}.value must be a non-empty list of unique identifiers")
        else:
            checked: list[str] = []
            for index, item in enumerate(value):
                identifier = _identifier(item, f"{path}.value[{index}]", errors)
                if identifier is not None:
                    checked.append(identifier)
            if len(set(checked)) != len(checked):
                errors.append(f"{path}.value must not contain duplicates")
    else:
        errors.append(f"{path}.target is an unsupported semantic target: {target}")
    return target


def _operations(value: object, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path} must be a non-empty list")
        return
    targets: set[str] = set()
    for index, operation in enumerate(value):
        target = _operation(operation, f"{path}[{index}]", errors)
        if target is not None:
            if target in targets:
                errors.append(f"{path} has duplicate target {target}")
            targets.add(target)


def _records_list(value: object, path: str, errors: list[str]) -> list[object] | None:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return None
    return value


def validate_space(data: object) -> list[str]:
    """Return deterministic actionable errors; never mutate or raise for JSON-like input."""

    if not isinstance(data, dict):
        return ["hypothesis-space root must be a JSON object"]
    canonical_error: str | None = None
    try:
        canonical_value(data, "hypothesis-space")
    except (OverflowError, RecursionError, TypeError, ValueError, UnicodeError) as exc:
        canonical_error = f"hypothesis-space is outside the canonical JSON domain: {exc}"
        # Finite/range failures are also reported at their semantic field below.
        # Other failures (cycles, invalid keys/types, excessive depth) are unsafe
        # to traverse further and therefore stop at this actionable boundary.
        if "must be finite" not in str(exc) and "supported 64-bit integer range" not in str(exc):
            return [canonical_error]

    errors: list[str] = [canonical_error] if canonical_error is not None else []
    _closed(data, _ROOT_FIELDS, "root", errors)
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        errors.append("schema_version must be integer 1")
    _identifier(data.get("space_id"), "space_id", errors)
    budget_ok = _bounded_integer(data.get("max_candidates"), 1, 10_000, "max_candidates", errors)

    base = data.get("base_contract")
    if not isinstance(base, dict):
        errors.append("base_contract must be an object")
    else:
        _closed(base, {"path", "sha256"}, "base_contract", errors)
        path = base.get("path")
        valid_path = isinstance(path, str) and bool(path) and "\\" not in path
        if valid_path:
            pure = PurePosixPath(path)
            valid_path = (
                not pure.is_absolute()
                and pure.as_posix() == path
                and path != "."
                and not re.match(r"^[A-Za-z]:/", path)
                and all(part not in ("", ".", "..") for part in path.split("/"))
            )
        if not valid_path:
            errors.append("base_contract.path must be a normalized non-escaping relative POSIX path")
        try:
            validate_sha256(base.get("sha256"), "base_contract.sha256")
        except ValueError as exc:
            errors.append(str(exc))

    axes = data.get("axes")
    product = 1
    if not isinstance(axes, list) or not axes:
        errors.append("axes must be a non-empty list")
    else:
        _unique_ids(axes, "axes", errors)
        for axis_index, axis in enumerate(axes):
            axis_path = f"axes[{axis_index}]"
            if not isinstance(axis, dict):
                errors.append(f"{axis_path} must be an object")
                continue
            _closed(axis, {"id", "choices"}, axis_path, errors)
            _identifier(axis.get("id"), f"{axis_path}.id", errors)
            choices = axis.get("choices")
            if not isinstance(choices, list) or not choices:
                errors.append(f"{axis_path}.choices must be a non-empty list")
                continue
            product *= len(choices)
            _unique_ids(choices, f"{axis_path}.choices", errors)
            for choice_index, choice in enumerate(choices):
                choice_path = f"{axis_path}.choices[{choice_index}]"
                if not isinstance(choice, dict):
                    errors.append(f"{choice_path} must be an object")
                    continue
                _closed(choice, {"id", "operations"}, choice_path, errors)
                _identifier(choice.get("id"), f"{choice_path}.id", errors)
                _operations(choice.get("operations"), f"{choice_path}.operations", errors)
        if budget_ok and product > data["max_candidates"]:
            errors.append(
                f"axes Cartesian product {product} exceeds max_candidates {data['max_candidates']}; "
                "reduce choices or raise max_candidates"
            )

    uncertainties = _records_list(data.get("uncertainties"), "uncertainties", errors)
    if uncertainties is not None:
        _unique_ids(uncertainties, "uncertainties", errors)
        for index, record in enumerate(uncertainties):
            path = f"uncertainties[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{path} must be an object")
                continue
            _closed(record, {"id", "target", "values", "hard"}, path, errors)
            _identifier(record.get("id"), f"{path}.id", errors)
            target = record.get("target")
            if not isinstance(target, str) or not _QUANTITY_TARGET.fullmatch(target) or not target.endswith(".value"):
                errors.append(f"{path}.target must be a quantity:<id>.value target")
            values = record.get("values")
            if not isinstance(values, list) or not values:
                errors.append(f"{path}.values must be a non-empty list")
            else:
                seen_values: set[bytes] = set()
                for value_index, item in enumerate(values):
                    _quantity_value(item, f"{path}.values[{value_index}]", errors)
                    try:
                        encoded = canonical_bytes(item)
                    except ValueError:
                        continue
                    if encoded in seen_values:
                        errors.append(f"{path}.values has duplicate canonical value at index {value_index}")
                    seen_values.add(encoded)
            if type(record.get("hard")) is not bool:
                errors.append(f"{path}.hard must be a boolean")

    objectives = _records_list(data.get("objectives"), "objectives", errors)
    if objectives is not None:
        _unique_ids(objectives, "objectives", errors)
        for index, record in enumerate(objectives):
            path = f"objectives[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{path} must be an object")
                continue
            _closed(record, {"id", "source", "direction"}, path, errors)
            _identifier(record.get("id"), f"{path}.id", errors)
            source = record.get("source")
            if not (
                isinstance(source, str)
                and (
                    _QUANTITY_SOURCE.fullmatch(source)
                    or _ANALYSIS_SOURCE.fullmatch(source)
                    or source == "evidence:minimum-level"
                    or source == "diagnostics:blocking-count"
                )
            ):
                errors.append(f"{path}.source is unsupported")
            if record.get("direction") not in ("min", "max"):
                errors.append(f"{path}.direction must be min or max")

    repairs = _records_list(data.get("repair_rules"), "repair_rules", errors)
    if repairs is not None:
        _unique_ids(repairs, "repair_rules", errors)
        for index, record in enumerate(repairs):
            path = f"repair_rules[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{path} must be an object")
                continue
            _closed(record, {"id", "diagnostic_code", "owner_prefix", "operations", "max_applications"}, path, errors)
            _identifier(record.get("id"), f"{path}.id", errors)
            for field in ("diagnostic_code", "owner_prefix"):
                value = record.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{path}.{field} must be a non-empty string")
            _operations(record.get("operations"), f"{path}.operations", errors)
            _bounded_integer(record.get("max_applications"), 1, 100, f"{path}.max_applications", errors)

    evaluation = data.get("evaluation")
    if not isinstance(evaluation, dict):
        errors.append("evaluation must be an object")
    else:
        _closed(evaluation, {"max_stage_evaluations", "stages"}, "evaluation", errors)
        _bounded_integer(evaluation.get("max_stage_evaluations"), 1, 1_000_000, "evaluation.max_stage_evaluations", errors)
        stages = evaluation.get("stages")
        if not isinstance(stages, list) or not stages:
            errors.append("evaluation.stages must be a non-empty list")
        else:
            if any(not isinstance(stage, str) or stage not in _STAGE_ORDER for stage in stages):
                errors.append("evaluation.stages contains an unknown stage")
            if len(set(stage for stage in stages if isinstance(stage, str))) != len(stages):
                errors.append("evaluation.stages must not contain duplicates")
            positions = [_STAGE_ORDER.index(stage) for stage in stages if stage in _STAGE_ORDER]
            if positions != sorted(positions):
                errors.append("evaluation.stages must follow dependency order")
            if len(stages) < 2 or stages[:2] != ["contract_v1", "physical_v030"]:
                errors.append("evaluation.stages must begin with contract_v1 then physical_v030")
            if "counterexample_v1" in stages and "uncertainty_v1" not in stages:
                errors.append("evaluation.stages counterexample_v1 requires uncertainty_v1")

    return sorted(set(errors))


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {token}")


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number is not allowed: {token}")
    return value


def _parse_int(token: str) -> int:
    digits = token.removeprefix("-")
    if len(digits) > 308:
        raise ValueError("JSON integers may contain at most 308 digits")
    return int(token)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_space(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load UTF-8 JSON within hard resource bounds, then validate the closed schema."""

    source = Path(path)
    try:
        if not source.exists():
            return None, [f"hypothesis space does not exist: {source}"]
        size = source.stat().st_size
        if size > _MAX_FILE_BYTES:
            return None, ["hypothesis space exceeds maximum size of 5 MiB"]
        payload = source.read_bytes()
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None, ["hypothesis space is not valid UTF-8"]
        data = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
        try:
            canonical_value(data, "hypothesis space")
        except ValueError as exc:
            message = str(exc)
            if "maximum canonical JSON depth of 64" in message:
                message = message.replace("maximum canonical JSON depth", "maximum JSON depth")
            return None, [message]
        errors = validate_space(data)
        return (data if not errors else data), errors
    except (OSError, json.JSONDecodeError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        return None, [f"cannot load hypothesis space: {exc}"]
