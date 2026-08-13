# Physical Plausibility Contract

Read this contract before selecting components or claiming physical
feasibility. It defines the minimum analytical gate between a design narrative
and simulation, optimization, training, rendering, procurement, or hardware
commissioning.

## Machine-readable gate

Create a schema-v1 JSON design contract using
`scripts/assurance/schema.md`, then run:

```bash
python skills/robotics-design/scripts/validate_design_contract.py path/to/design-contract.json --report evidence.json
```

Exit `0` means the declared contract is promotable at its recorded evidence
levels. Exit `1` means physical failure or indeterminate evidence. Exit `2`
means the contract or invocation is invalid. Preserve every failure report;
never replace a failed report with a prose disclaimer.

## Required records

The contract must contain:

- numbered requirements and assumptions, including confidence, owner,
  validation method, deadline, and change trigger;
- every physical quantity as an explicit value/unit record with one owner, one
  evidence source, an evidence level, and optional drift tolerance;
- a component ledger with exact architecture bindings, interfaces, lifecycle
  state, limits, provenance, and supported claims;
- hash-bound CAD/URDF/SDF/SRDF/ROS/BOM inputs and normalized observations;
- named analysis plug-ins whose numeric inputs are quantity references;
- evidence edges that explicitly support each quantity or artifact they claim.

Bare physical numbers and inferred units are invalid. Supported evidence
levels are `assumed`, `generated`, `parsed`, `calculated`, `simulated`,
`bench-tested`, `integrated-hardware-tested`, `task-validated`, and
`certified`. These levels order evidence strength; they never automatically
upgrade a claim. A quantity cannot declare a stronger level than the evidence
record selected as its source. Reports include declared-level counts and the
minimum quantity evidence level so a clean calculation cannot hide an assumed
dependency.

## Component and load-path completeness

Architecture declarations create mandatory component responsibilities.

- Differential drive requires traction motor, reducer, wheel, bearing, and
  motor driver records.
- Battery power requires battery, BMS, main protection, contactor, and DC
  converter records.
- Every declared actuator requires a specifically bound motor, reducer, bearing, and motor driver. A motor, reducer, or bearing cannot be shared
  across multiple actuator bindings merely to satisfy a role count.
- Every moving cable responsibility requires cable, connector, strain relief,
  and cable-management records.
- A declared holding-brake safety function requires a bound brake.

`missing` is an explicit error. `engineering_placeholder` is useful during
exploration but cannot support a promoted claim. `verified_part` and
`qualified_substitute` require manufacturer, part number, source URL/date, and
non-empty limits. Catalog values require exact part provenance; a similar
product family or remembered rating is assumed evidence.

An incomplete drive example is a wheel and motor without its reducer, bearing,
driver, or electrical feed. An incomplete arm example is a URDF joint without
its own actuator load path, transmission, holding behavior, and cable route.
An incomplete power example is a battery without BMS, protection, contactor,
conversion, continuous/peak current checks, and usable-energy budget.

## Conservative analytical plug-ins

All plug-ins use normalized SI values and publish their validity assumptions,
outputs, signed margins, diagnostics, version, and `calculated` evidence level.

### `drivetrain_v1`

For total mass `m`, rolling coefficient `c_r`, slope `theta`, acceleration `a`,
wheel radius `r`, driven-wheel count `n`, ratio `G`, and efficiency `eta`:

```text
F = m * (a + g * (c_r * cos(theta) + sin(theta)))
T_wheel = F * r / n
T_motor = T_wheel / (G * eta)
omega_motor = v * G / r
```

It checks peak torque, duty-scaled continuous torque, and maximum motor speed.
The scalar efficiency and equal wheel-load assumptions bound an operating
point; they do not replace a motor curve, traction limit, transient model,
braking calculation, or gearbox life check.

### `battery_v1`

```text
I_peak = P_peak / V
I_continuous = P_continuous / V
runtime = usable_energy / P_continuous
```

It checks continuous/peak current and required runtime. It does not model cell
sag, temperature, aging, balancing, fault energy, cable drop, fuse clearing,
or regenerative charge acceptance.

### `stability_v1`

The current plug-in projects center of mass along gravity using declared COM
height and base-frame x/y support-plane slopes:

```text
x_projected = x_com + h_com * tan(slope_x)
y_projected = y_com + h_com * tan(slope_y)
margin = min(distance from projected COM to each rectangular support bound)
```

A negative margin fails. This is a rigid-contact static screen, not proof for
acceleration, slope transitions, compliance, suspension, tire deformation,
collision impulse, or manipulation dynamics.

### `arm_gravity_v1`

For each checked joint:

```text
T_gravity = sum(m_i * g * horizontal_lever_i)
T_required = T_gravity * declared_safety_factor
```

It checks continuous actuator torque and brake holding torque. It does not
replace full-chain inverse dynamics, reflected inertia, efficiency/backlash,
impact, fatigue, bearing life, or drive thermal limits.

### `thermal_duty_v1`

```text
P_copper = I_on^2 * R_winding * duty
T_estimated = T_ambient + P_copper * R_thermal
margin = T_max - T_estimated
```

This conservative steady-state winding screen requires explicit resistance,
duty, thermal resistance, ambient, and winding-temperature limit. It does not
replace temperature-dependent resistance, a transient thermal network, gearbox
and controller losses, hot-spot analysis, cooling degradation, or bench data.

Domain violations, non-finite values, missing inputs, unsupported units, and
unknown plug-ins fail closed with stable diagnostics instead of tracebacks.

## Artifact ownership and drift

Each quantity has one owner. Hash every source file used as evidence. Bind
owned URDF observations such as link mass and joint limit to normalized paths;
the validator rejects stale hashes, changed owned values, absent transmissions,
unsafe XML constructs, and missing observations. Repair the owning artifact,
regenerate dependents, and rerun the complete gate.

## Promotion order

Analytical gates run before simulation or training, and simulation cannot replace
missing physical components, broken ownership, unsupported continuous or
thermal capability, or stale evidence. The order is:

```text
contract/schema -> hashes/references -> component bindings -> artifact drift
-> analytical margins -> simulation -> bench -> integrated hardware -> task
```

Promotion requires zero `error` and zero `indeterminate` diagnostics. A report
also records the lowest evidence level on which its claims depend. Simulation
and training may explore only candidates that pass the applicable analytical
screen, unless the run is explicitly a fault-injection experiment whose failed
upstream gate remains visible.

Passing this contract proves only that the declared values, bindings, evidence
edges, artifacts, and implemented conservative equations agree. It does not
prove structural strength, collision safety, braking distance, controllability,
manufacturability, reliability, human safety, certification, or real-world task
performance. Those claims require their own analyses and physical evidence.
