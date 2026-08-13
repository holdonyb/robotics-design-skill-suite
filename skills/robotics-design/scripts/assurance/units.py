"""Explicit conversion of supported physical quantities to SI units."""

from __future__ import annotations

import math
from typing import Any


class QuantityError(ValueError):
    """Raised when a physical quantity is missing, ambiguous, or non-finite."""


# unit -> (dimension, multiplicative factor, additive offset after scaling)
UNITS: dict[str, tuple[str, float, float]] = {
    "1": ("dimensionless", 1.0, 0.0),
    "%": ("dimensionless", 0.01, 0.0),
    "m": ("length", 1.0, 0.0),
    "mm": ("length", 1e-3, 0.0),
    "cm": ("length", 1e-2, 0.0),
    "kg": ("mass", 1.0, 0.0),
    "g": ("mass", 1e-3, 0.0),
    "s": ("time", 1.0, 0.0),
    "min": ("time", 60.0, 0.0),
    "h": ("time", 3600.0, 0.0),
    "rad": ("angle", 1.0, 0.0),
    "deg": ("angle", math.pi / 180.0, 0.0),
    "rad/s": ("angular_velocity", 1.0, 0.0),
    "rpm": ("angular_velocity", 2.0 * math.pi / 60.0, 0.0),
    "N": ("force", 1.0, 0.0),
    "N*m": ("torque", 1.0, 0.0),
    "W": ("power", 1.0, 0.0),
    "kW": ("power", 1000.0, 0.0),
    "J": ("energy", 1.0, 0.0),
    "Wh": ("energy", 3600.0, 0.0),
    "kWh": ("energy", 3_600_000.0, 0.0),
    "V": ("voltage", 1.0, 0.0),
    "A": ("current", 1.0, 0.0),
    "ohm": ("resistance", 1.0, 0.0),
    "K/W": ("thermal_resistance", 1.0, 0.0),
    "K": ("temperature", 1.0, 0.0),
    "degC": ("temperature", 1.0, 273.15),
    "kg*m^2": ("inertia", 1.0, 0.0),
    "m/s": ("speed", 1.0, 0.0),
    "m/s^2": ("acceleration", 1.0, 0.0),
}

DIMENSIONS = frozenset(dimension for dimension, _, _ in UNITS.values())


def to_si(record: Any, expected_dimension: str, path: str = "quantity") -> float:
    """Return a finite SI value from an explicit ``value``/``unit`` object."""

    if expected_dimension not in DIMENSIONS:
        raise QuantityError(f"{path}: unsupported dimension: {expected_dimension}")
    if not isinstance(record, dict):
        raise QuantityError(f"{path}: quantity must be an object with value and unit")

    value = record.get("value")
    unit = record.get("unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QuantityError(f"{path}.value must be a finite number")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise QuantityError(f"{path}.value must be a finite number") from exc
    if not math.isfinite(numeric):
        raise QuantityError(f"{path}.value must be a finite number")
    if not isinstance(unit, str) or not unit:
        raise QuantityError(f"{path}.unit must be a non-empty string")
    if unit not in UNITS:
        raise QuantityError(f"{path}: unsupported unit: {unit}")

    dimension, factor, offset = UNITS[unit]
    if dimension != expected_dimension:
        raise QuantityError(
            f"{path}: expected {expected_dimension}, got {dimension} from {unit}"
        )
    try:
        result = numeric * factor + offset
    except OverflowError as exc:
        raise QuantityError(f"{path}: converted value is not finite") from exc
    if not math.isfinite(result):
        raise QuantityError(f"{path}: converted value is not finite")
    return result
