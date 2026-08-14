# Kendrion INTORQ BFK458-20 J2 brake candidate audit

Date observed: 2026-08-14

This is an output-side holding-brake candidate screen. It is not a selected
part, an assembly design, a safety-function validation, procurement approval,
or permission to energize or move a robot.

## Candidate and source

- Manufacturer: Kendrion INTORQ
- Catalog model: `BFK458-20` (a modular size, not a fully configured order
  code)
- Manufacturer product page:
  <https://www.kendrion.com/en/productfinder/group/product/brakes/bfk458-20>
- Manufacturer operating instructions:
  <https://www.kendrion.com/fileadmin/user_upload/Downloads/Datasheets_Operating_instructions/Industrial_Brakes_INTORQ/operating-instructions-spring-applied-brake-BFK458.pdf>
- Candidate snapshot:
  `reference/mobile-manipulator/supplier-catalogs/kendrion-intorq-bfk458-20-j2-brake-candidate-2026-08-14.json`
- Snapshot SHA-256: `63567f8ba5667e3d9d2c26ac63fa5b677624fd9f1a9ed2a90b913d791f822e1f`

The manufacturer page describes the size-20 model as a holding brake with
400 N*m torque, 100 W nominal coil power, 80,000 J maximum switching energy per
emergency stop, 3,600 rpm maximum rotation speed (conditional on switching
work), 19.3 kg mass, 252.6 mm outer diameter, 114.6 mm length, 230 mm front and
flange pitch circles, and 35/40/45/50 mm hub choices.

## Output-side screen and resulting risk

The reference J2 arm-load calculation currently reports 393.3447315 N*m output
holding-torque demand, including its declared brake safety factor. A nominal
400 N*m catalog rating would leave only 6.6552685 N*m (about 1.7%) calculated
margin. This is a screening comparison only. It does not establish the torque
at the configured air gap, temperature, speed, wear state, friction surface,
or emergency-stop energy.

The current J2 brake input is explicitly an **output-side** torque requirement;
it must not be divided by the 100:1 reducer ratio and compared to a motor-side
brake without a proven torque path. Conversely, the BFK458-20's 19.3 kg mass
and 252.6 mm envelope are absent from the current arm load model and CAD. Adding
that mass at an actual datum can change the gravity, bearing, collision and
thermal results that led to the 393.3447315 N*m requirement. The candidate
cannot be considered adequate until the design is iterated with its real
placement and geometry.

The step.parts API was reachable on the observation date. Exact and alias
queries (`INTORQ BFK458 20`, `BFK458-20`, and `Kendrion BFK458`) each returned
zero items. No CAD surrogate is introduced.

## Deliberate non-promotion

`CMP-BRAKE-J2` remains `engineering_placeholder`. `BFK458-20` is a modular
catalog size, not a configured order code: voltage, hub, flange/counter-friction
part, IP level, lining, hand release, monitoring, lead wiring and control must
be selected from manufacturer-controlled configuration data. The required
output interface to the CSG-40-100-2UH, brake reaction path, fastener preload,
support structure, released-state drag, command interlock and power-loss state
are all unresolved.

Before a J2 brake or holding-safety claim, bind the exact configured part and
drawings, update CAD/URDF/SDF mass/inertia and clearance observations, model the
actual torque path and reaction structure, prove the complete static and
emergency-stop duty, and validate the driver/brake power and safe-state
interlocks. The reference robot remains non-promotable throughout.
