"""Conservative, bounded physical-analysis plug-ins for schema v1 contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from .model import Diagnostic, EvidenceLevel


GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class AnalysisResult:
    name: str
    version: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    diagnostics: tuple[Diagnostic, ...]
    validity_assumptions: tuple[str, ...]
    evidence_level: EvidenceLevel = EvidenceLevel.CALCULATED

    @property
    def passed(self) -> bool:
        return not any(
            item.severity in {"error", "indeterminate"} for item in self.diagnostics
        )


@dataclass(frozen=True)
class AnalysisPlugin:
    name: str
    version: str
    required_inputs: tuple[str, ...]
    run: Callable[[dict[str, Any]], AnalysisResult]


def _diagnostic(code: str, severity: str, path: str, message: str) -> Diagnostic:
    return Diagnostic(code, severity, path, message)


def _finite_inputs(
    name: str, inputs: dict[str, Any], required: tuple[str, ...]
) -> tuple[dict[str, float], list[Diagnostic]]:
    values: dict[str, float] = {}
    diagnostics: list[Diagnostic] = []
    for field in required:
        value = inputs.get(field)
        if value is None:
            diagnostics.append(
                _diagnostic(
                    "PHY.INPUT.MISSING",
                    "indeterminate",
                    f"analyses.{name}.inputs.{field}",
                    f"required analysis input is missing: {field}",
                )
            )
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            diagnostics.append(
                _diagnostic(
                    "PHY.INPUT.TYPE",
                    "error",
                    f"analyses.{name}.inputs.{field}",
                    f"analysis input must be a finite number: {field}",
                )
            )
        elif not math.isfinite(float(value)):
            diagnostics.append(
                _diagnostic(
                    "PHY.INPUT.TYPE",
                    "error",
                    f"analyses.{name}.inputs.{field}",
                    f"analysis input must be finite: {field}",
                )
            )
        else:
            values[field] = float(value)
    return values, diagnostics


DRIVETRAIN_INPUTS = (
    "base_mass_kg",
    "payload_mass_kg",
    "rolling_resistance",
    "slope_rad",
    "acceleration_m_s2",
    "wheel_radius_m",
    "driven_wheels",
    "gear_ratio",
    "efficiency",
    "target_speed_m_s",
    "motor_continuous_torque_nm",
    "motor_peak_torque_nm",
    "motor_max_speed_rad_s",
    "duty_cycle",
)


def _drivetrain(inputs: dict[str, Any]) -> AnalysisResult:
    values, diagnostics = _finite_inputs("drivetrain_v1", inputs, DRIVETRAIN_INPUTS)
    outputs: dict[str, Any] = {}
    assumptions = (
        "straight-line motion with equal load sharing across driven wheels",
        "rolling resistance is constant over the checked operating point",
        "gear ratio and efficiency are positive scalar approximations",
    )
    if diagnostics:
        return AnalysisResult(
            "drivetrain_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions
        )

    positive = (
        "wheel_radius_m",
        "driven_wheels",
        "gear_ratio",
        "motor_continuous_torque_nm",
        "motor_peak_torque_nm",
        "motor_max_speed_rad_s",
    )
    invalid = [field for field in positive if values[field] <= 0.0]
    if values["base_mass_kg"] < 0 or values["payload_mass_kg"] < 0:
        invalid.extend(["base_mass_kg/payload_mass_kg"])
    if values["base_mass_kg"] + values["payload_mass_kg"] <= 0:
        invalid.append("total_mass")
    if values["rolling_resistance"] < 0:
        invalid.append("rolling_resistance")
    if not 0.0 < values["efficiency"] <= 1.0:
        invalid.append("efficiency")
    if not 0.0 <= values["duty_cycle"] <= 1.0:
        invalid.append("duty_cycle")
    if values["target_speed_m_s"] < 0 or values["acceleration_m_s2"] < 0:
        invalid.append("target_speed_m_s/acceleration_m_s2")
    if abs(values["slope_rad"]) >= math.pi / 2.0:
        invalid.append("slope_rad")
    if invalid:
        diagnostics.append(
            _diagnostic(
                "PHY.INPUT.DOMAIN",
                "error",
                "analyses.drivetrain_v1.inputs",
                "inputs outside drivetrain validity domain: " + ", ".join(sorted(set(invalid))),
            )
        )
        return AnalysisResult(
            "drivetrain_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions
        )

    mass = values["base_mass_kg"] + values["payload_mass_kg"]
    slope = values["slope_rad"]
    force = mass * (
        values["acceleration_m_s2"]
        + GRAVITY_M_S2
        * (
            values["rolling_resistance"] * math.cos(slope)
            + math.sin(slope)
        )
    )
    if force < 0.0:
        outputs["tractive_force_n"] = force
        diagnostics.append(
            _diagnostic(
                "PHY.DRIVE.BRAKING_REGIME",
                "indeterminate",
                "analyses.drivetrain_v1",
                "negative net tractive force requires an explicit downhill braking or regenerative model",
            )
        )
        return AnalysisResult(
            "drivetrain_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions
        )
    wheel_torque = force * values["wheel_radius_m"] / values["driven_wheels"]
    motor_torque = wheel_torque / values["gear_ratio"] / values["efficiency"]
    motor_speed = (
        values["target_speed_m_s"]
        / values["wheel_radius_m"]
        * values["gear_ratio"]
    )
    continuous_demand = motor_torque * values["duty_cycle"]
    outputs.update(
        {
            "total_mass_kg": mass,
            "tractive_force_n": force,
            "wheel_torque_per_driven_wheel_nm": wheel_torque,
            "motor_torque_nm": motor_torque,
            "continuous_equivalent_motor_torque_nm": continuous_demand,
            "motor_speed_rad_s": motor_speed,
            "continuous_torque_margin_nm": values["motor_continuous_torque_nm"]
            - continuous_demand,
            "peak_torque_margin_nm": values["motor_peak_torque_nm"] - motor_torque,
            "speed_margin_rad_s": values["motor_max_speed_rad_s"] - motor_speed,
        }
    )
    if continuous_demand > values["motor_continuous_torque_nm"]:
        diagnostics.append(
            _diagnostic(
                "PHY.DRIVE.CONTINUOUS_TORQUE",
                "error",
                "analyses.drivetrain_v1",
                "continuous-equivalent motor torque exceeds declared rating",
            )
        )
    if motor_torque > values["motor_peak_torque_nm"]:
        diagnostics.append(
            _diagnostic(
                "PHY.DRIVE.PEAK_TORQUE",
                "error",
                "analyses.drivetrain_v1",
                "motor torque exceeds declared peak rating",
            )
        )
    if motor_speed > values["motor_max_speed_rad_s"]:
        diagnostics.append(
            _diagnostic(
                "PHY.DRIVE.OVERSPEED",
                "error",
                "analyses.drivetrain_v1",
                "motor speed exceeds declared maximum",
            )
        )
    return AnalysisResult(
        "drivetrain_v1", "1", dict(values), outputs, tuple(diagnostics), assumptions
    )


BATTERY_INPUTS = (
    "voltage_v",
    "peak_power_w",
    "continuous_power_w",
    "max_continuous_current_a",
    "max_peak_current_a",
    "usable_energy_j",
    "required_runtime_s",
)


def _battery(inputs: dict[str, Any]) -> AnalysisResult:
    values, diagnostics = _finite_inputs("battery_v1", inputs, BATTERY_INPUTS)
    outputs: dict[str, Any] = {}
    assumptions = (
        "declared usable energy already includes state-of-charge and temperature derating",
        "continuous power is the mission-average electrical load for runtime screening",
        "voltage is constant for the checked current calculation",
    )
    if diagnostics:
        return AnalysisResult("battery_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions)
    positive = [field for field in BATTERY_INPUTS if field != "required_runtime_s"]
    invalid = [field for field in positive if values[field] <= 0.0]
    if values["required_runtime_s"] < 0.0:
        invalid.append("required_runtime_s")
    if invalid:
        diagnostics.append(
            _diagnostic(
                "PHY.INPUT.DOMAIN",
                "error",
                "analyses.battery_v1.inputs",
                "inputs outside battery validity domain: " + ", ".join(sorted(invalid)),
            )
        )
        return AnalysisResult("battery_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions)

    peak_current = values["peak_power_w"] / values["voltage_v"]
    continuous_current = values["continuous_power_w"] / values["voltage_v"]
    runtime = values["usable_energy_j"] / values["continuous_power_w"]
    outputs.update(
        {
            "peak_current_a": peak_current,
            "continuous_current_a": continuous_current,
            "estimated_runtime_s": runtime,
            "peak_current_margin_a": values["max_peak_current_a"] - peak_current,
            "continuous_current_margin_a": values["max_continuous_current_a"]
            - continuous_current,
            "runtime_margin_s": runtime - values["required_runtime_s"],
        }
    )
    for code, demand, limit, message in (
        (
            "PHY.POWER.PEAK_CURRENT",
            peak_current,
            values["max_peak_current_a"],
            "peak current exceeds declared battery limit",
        ),
        (
            "PHY.POWER.CONTINUOUS_CURRENT",
            continuous_current,
            values["max_continuous_current_a"],
            "continuous current exceeds declared battery limit",
        ),
    ):
        if demand > limit:
            diagnostics.append(_diagnostic(code, "error", "analyses.battery_v1", message))
    if runtime < values["required_runtime_s"]:
        diagnostics.append(
            _diagnostic(
                "PHY.POWER.ENERGY",
                "error",
                "analyses.battery_v1",
                "usable energy does not meet required runtime",
            )
        )
    return AnalysisResult("battery_v1", "1", dict(values), outputs, tuple(diagnostics), assumptions)


STABILITY_INPUTS = (
    "support_min_x_m",
    "support_max_x_m",
    "support_min_y_m",
    "support_max_y_m",
    "com_x_m",
    "com_y_m",
    "com_height_m",
    "slope_x_rad",
    "slope_y_rad",
)


def _stability(inputs: dict[str, Any]) -> AnalysisResult:
    values, diagnostics = _finite_inputs("stability_v1", inputs, STABILITY_INPUTS)
    outputs: dict[str, Any] = {}
    assumptions = (
        "support polygon is represented by the declared axis-aligned conservative rectangle",
        "center of mass is statically projected along gravity onto the declared support plane",
        "slope axes use the base-frame x and y directions with rigid support contact",
        "dynamic and contact disturbances require separate checks",
    )
    if diagnostics:
        return AnalysisResult("stability_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions)
    if (
        values["support_min_x_m"] >= values["support_max_x_m"]
        or values["support_min_y_m"] >= values["support_max_y_m"]
        or values["com_height_m"] < 0.0
        or abs(values["slope_x_rad"]) >= math.pi / 2.0
        or abs(values["slope_y_rad"]) >= math.pi / 2.0
    ):
        diagnostics.append(
            _diagnostic(
                "PHY.INPUT.DOMAIN",
                "error",
                "analyses.stability_v1.inputs",
                "support bounds, COM height, or slope lie outside the stability validity domain",
            )
        )
        return AnalysisResult("stability_v1", "1", dict(values), outputs, tuple(diagnostics), assumptions)
    shift_x = values["com_height_m"] * math.tan(abs(values["slope_x_rad"]))
    shift_y = values["com_height_m"] * math.tan(abs(values["slope_y_rad"]))
    x_candidates = (values["com_x_m"] + shift_x, values["com_x_m"] - shift_x)
    y_candidates = (values["com_y_m"] + shift_y, values["com_y_m"] - shift_y)

    def axis_margin(value: float, lower: float, upper: float) -> float:
        return min(value - lower, upper - value)

    projected_x = min(
        x_candidates,
        key=lambda value: axis_margin(
            value, values["support_min_x_m"], values["support_max_x_m"]
        ),
    )
    projected_y = min(
        y_candidates,
        key=lambda value: axis_margin(
            value, values["support_min_y_m"], values["support_max_y_m"]
        ),
    )
    margins = (
        projected_x - values["support_min_x_m"],
        values["support_max_x_m"] - projected_x,
        projected_y - values["support_min_y_m"],
        values["support_max_y_m"] - projected_y,
    )
    margin = min(margins)
    outputs.update(
        {
            "projected_com_x_m": projected_x,
            "projected_com_y_m": projected_y,
            "projected_com_x_range_m": [min(x_candidates), max(x_candidates)],
            "projected_com_y_range_m": [min(y_candidates), max(y_candidates)],
            "static_margin_m": margin,
        }
    )
    if margin < 0.0:
        diagnostics.append(
            _diagnostic(
                "PHY.STABILITY.OUTSIDE_SUPPORT",
                "error",
                "analyses.stability_v1",
                "projected center of mass lies outside the support bounds",
            )
        )
    return AnalysisResult("stability_v1", "1", dict(values), outputs, tuple(diagnostics), assumptions)


def _arm_gravity(inputs: dict[str, Any]) -> AnalysisResult:
    diagnostics: list[Diagnostic] = []
    outputs: dict[str, Any] = {"joints": []}
    assumptions = (
        "horizontal lever arms are conservative magnitudes for the checked pose",
        "gravity is standard gravity and dynamic loads require separate analysis",
        "rated and brake torques are valid at the declared temperature and duty",
    )
    joints = inputs.get("joints")
    if not isinstance(joints, list) or not joints:
        diagnostics.append(
            _diagnostic(
                "PHY.INPUT.MISSING",
                "indeterminate",
                "analyses.arm_gravity_v1.inputs.joints",
                "at least one joint load record is required",
            )
        )
        return AnalysisResult("arm_gravity_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions)

    for index, joint in enumerate(joints):
        path = f"analyses.arm_gravity_v1.inputs.joints[{index}]"
        if not isinstance(joint, dict) or not isinstance(joint.get("loads"), list):
            diagnostics.append(
                _diagnostic("PHY.INPUT.TYPE", "error", path, "joint and loads must be objects/lists")
            )
            continue
        joint_id = joint.get("id")
        numeric_fields = (
            "rated_continuous_torque_nm",
            "brake_holding_torque_nm",
            "safety_factor",
        )
        numeric, input_errors = _finite_inputs(
            "arm_gravity_v1", joint, numeric_fields
        )
        diagnostics.extend(input_errors)
        torque = 0.0
        valid_loads = True
        for load_index, load in enumerate(joint["loads"]):
            if not isinstance(load, dict):
                valid_loads = False
                break
            mass = load.get("mass_kg")
            lever = load.get("horizontal_lever_m")
            if (
                not isinstance(mass, (int, float))
                or isinstance(mass, bool)
                or not math.isfinite(float(mass))
                or float(mass) < 0.0
                or not isinstance(lever, (int, float))
                or isinstance(lever, bool)
                or not math.isfinite(float(lever))
                or float(lever) < 0.0
            ):
                diagnostics.append(
                    _diagnostic(
                        "PHY.INPUT.DOMAIN",
                        "error",
                        f"{path}.loads[{load_index}]",
                        "mass and horizontal lever must be finite and non-negative",
                    )
                )
                valid_loads = False
                continue
            torque += float(mass) * GRAVITY_M_S2 * float(lever)
        if input_errors or not valid_loads:
            continue
        if any(numeric[field] <= 0.0 for field in numeric_fields):
            diagnostics.append(
                _diagnostic(
                    "PHY.INPUT.DOMAIN",
                    "error",
                    path,
                    "torque ratings and safety factor must be positive",
                )
            )
            continue
        required = torque * numeric["safety_factor"]
        outputs["joints"].append(
            {
                "id": joint_id,
                "gravity_torque_nm": torque,
                "required_with_safety_factor_nm": required,
                "continuous_margin_nm": numeric["rated_continuous_torque_nm"] - required,
                "brake_margin_nm": numeric["brake_holding_torque_nm"] - required,
            }
        )
        if required > numeric["rated_continuous_torque_nm"]:
            diagnostics.append(
                _diagnostic(
                    "PHY.ARM.CONTINUOUS_TORQUE",
                    "error",
                    path,
                    f"joint {joint_id} gravity torque with safety factor exceeds continuous rating",
                )
            )
        if required > numeric["brake_holding_torque_nm"]:
            diagnostics.append(
                _diagnostic(
                    "PHY.ARM.BRAKE_HOLDING",
                    "error",
                    path,
                    f"joint {joint_id} gravity torque with safety factor exceeds brake holding rating",
                )
            )
    return AnalysisResult("arm_gravity_v1", "1", dict(inputs), outputs, tuple(diagnostics), assumptions)


THERMAL_DUTY_INPUTS = (
    "ambient_temperature_k",
    "winding_resistance_ohm",
    "on_current_a",
    "duty_cycle",
    "thermal_resistance_k_per_w",
    "max_winding_temperature_k",
)


def _thermal_duty(inputs: dict[str, Any]) -> AnalysisResult:
    values, diagnostics = _finite_inputs(
        "thermal_duty_v1", inputs, THERMAL_DUTY_INPUTS
    )
    outputs: dict[str, Any] = {}
    assumptions = (
        "winding resistance is evaluated at the declared conservative operating point",
        "duty is periodic and average copper loss is on-current squared times resistance times duty",
        "scalar thermal resistance represents the complete winding-to-ambient path at steady state",
        "transient hot spots and controller or gearbox heating require higher-fidelity analysis",
    )
    if diagnostics:
        return AnalysisResult(
            "thermal_duty_v1",
            "1",
            dict(inputs),
            outputs,
            tuple(diagnostics),
            assumptions,
        )

    invalid: list[str] = []
    for field in ("ambient_temperature_k", "winding_resistance_ohm", "thermal_resistance_k_per_w", "max_winding_temperature_k"):
        if values[field] <= 0.0:
            invalid.append(field)
    if values["on_current_a"] < 0.0:
        invalid.append("on_current_a")
    if not 0.0 <= values["duty_cycle"] <= 1.0:
        invalid.append("duty_cycle")
    if values["max_winding_temperature_k"] <= values["ambient_temperature_k"]:
        invalid.append("max_winding_temperature_k")
    if invalid:
        diagnostics.append(
            _diagnostic(
                "PHY.INPUT.DOMAIN",
                "error",
                "analyses.thermal_duty_v1.inputs",
                "inputs outside thermal-duty validity domain: "
                + ", ".join(sorted(set(invalid))),
            )
        )
        return AnalysisResult(
            "thermal_duty_v1",
            "1",
            dict(inputs),
            outputs,
            tuple(diagnostics),
            assumptions,
        )

    copper_loss = (
        values["on_current_a"] ** 2
        * values["winding_resistance_ohm"]
        * values["duty_cycle"]
    )
    estimated_temperature = (
        values["ambient_temperature_k"]
        + copper_loss * values["thermal_resistance_k_per_w"]
    )
    margin = values["max_winding_temperature_k"] - estimated_temperature
    outputs.update(
        {
            "copper_loss_w": copper_loss,
            "estimated_steady_state_temperature_k": estimated_temperature,
            "temperature_margin_k": margin,
        }
    )
    if margin < 0.0:
        diagnostics.append(
            _diagnostic(
                "PHY.THERMAL.WINDING_OVER_TEMPERATURE",
                "error",
                "analyses.thermal_duty_v1",
                "estimated steady-state winding temperature exceeds declared maximum",
            )
        )
    return AnalysisResult(
        "thermal_duty_v1",
        "1",
        dict(values),
        outputs,
        tuple(diagnostics),
        assumptions,
    )


PLUGINS: dict[str, AnalysisPlugin] = {
    "drivetrain_v1": AnalysisPlugin("drivetrain_v1", "1", DRIVETRAIN_INPUTS, _drivetrain),
    "battery_v1": AnalysisPlugin("battery_v1", "1", BATTERY_INPUTS, _battery),
    "stability_v1": AnalysisPlugin("stability_v1", "1", STABILITY_INPUTS, _stability),
    "arm_gravity_v1": AnalysisPlugin("arm_gravity_v1", "1", ("joints",), _arm_gravity),
    "thermal_duty_v1": AnalysisPlugin(
        "thermal_duty_v1", "1", THERMAL_DUTY_INPUTS, _thermal_duty
    ),
}


def run_plugin(name: str, inputs: dict[str, Any]) -> AnalysisResult:
    """Run a known plug-in or return a fail-closed indeterminate result."""

    plugin = PLUGINS.get(name)
    if plugin is None:
        return AnalysisResult(
            name=str(name),
            version="unknown",
            inputs=dict(inputs) if isinstance(inputs, dict) else {},
            outputs={},
            diagnostics=(
                _diagnostic(
                    "PHY.PLUGIN.UNKNOWN",
                    "indeterminate",
                    "analyses.plugin",
                    f"unknown physical analysis plug-in: {name}",
                ),
            ),
            validity_assumptions=(),
        )
    if not isinstance(inputs, dict):
        return AnalysisResult(
            name=plugin.name,
            version=plugin.version,
            inputs={},
            outputs={},
            diagnostics=(
                _diagnostic(
                    "PHY.INPUT.TYPE",
                    "error",
                    f"analyses.{name}.inputs",
                    "analysis inputs must be an object",
                ),
            ),
            validity_assumptions=(),
        )
    try:
        result = plugin.run(inputs)
    except ArithmeticError:
        return AnalysisResult(
            name=plugin.name,
            version=plugin.version,
            inputs=dict(inputs),
            outputs={},
            diagnostics=(
                _diagnostic(
                    "PHY.NUMERIC.OVERFLOW",
                    "error",
                    f"analyses.{name}",
                    "finite inputs overflowed the plug-in's numerical validity domain",
                ),
            ),
            validity_assumptions=(),
        )

    def contains_nonfinite(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return not math.isfinite(float(value))
        if isinstance(value, dict):
            return any(contains_nonfinite(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(contains_nonfinite(item) for item in value)
        return False

    if contains_nonfinite(result.outputs):
        return AnalysisResult(
            name=result.name,
            version=result.version,
            inputs=result.inputs,
            outputs={},
            diagnostics=(
                *result.diagnostics,
                _diagnostic(
                    "PHY.NUMERIC.OVERFLOW",
                    "error",
                    f"analyses.{name}",
                    "plug-in produced a non-finite derived value",
                ),
            ),
            validity_assumptions=result.validity_assumptions,
        )
    return result
