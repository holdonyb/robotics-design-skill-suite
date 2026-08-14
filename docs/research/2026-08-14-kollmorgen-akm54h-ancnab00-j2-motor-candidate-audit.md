# Kollmorgen AKM54H-ANCNAB00 J2 motor candidate audit

Date observed: 2026-08-14

This record identifies a concrete J2 motor candidate for follow-up engineering.
It is not a part promotion, purchase decision, motor--reducer assembly
approval, CAD-fit conclusion, or hardware authorization.

## Candidate and sources

- Manufacturer: Kollmorgen
- Exact candidate part number: `AKM54H-ANCNAB00`
- Exact-variant listing (independent distributor):
  <https://shop.oxni.ch/de/shop/motoren/pmsm/akm/AKM54H-ANCNAB00>
- Manufacturer AKM selection guide (Rev F):
  <https://www.kollmorgen.com/sites/default/files/2025-04/AKM-KM_SG_000077_RevF_EN.pdf>
- Candidate snapshot:
  `reference/mobile-manipulator/supplier-catalogs/kollmorgen-akm54h-ancnab00-candidate-2026-08-14.json`
- Snapshot SHA-256: `b55a47906f461c2a91a1fd5bcb507cf0bf68109b59d879a5c4abdf1d729f146b`

The independent exact-variant listing identifies the selected suffix and reports
14.19 N*m continuous stall torque, 5.5 A RMS continuous stall current, 37.5
N*m peak torque, 6000 rpm maximum speed, a 24 mm shaft, and a 108 mm nominal
flange. The manufacturer guide independently reports the AKM54H winding's
continuous-stall performance family. The current J2 static transmission screen
requires about 4.2144 N*m at the motor shaft (100:1 ratio and 0.70 assumed
reducer efficiency), so the catalog continuous-torque value exceeds that
specific static screen by about 9.98 N*m.

The step.parts API was reachable on the observation date. Exact part, family
name, and short-model queries (`AKM54H-ANCNAB00`, `Kollmorgen AKM54H`, and
`AKM54H`) all returned zero items. There is therefore no STEP asset, no CAD
proxy, and no inferred geometry in this repository.

## Deliberate non-promotion

`CMP-ARM-MOTOR-J2` remains `engineering_placeholder`. The manufacturer source
currently establishes family-level performance, while the full exact-option
configuration and the thermal model inputs presently used by the contract
(winding resistance, thermal resistance, and maximum winding temperature) are
not source-bound for this exact serial configuration. Promoting only its torque
would make the static check look stronger while leaving the thermal claim
unfounded.

The candidate also has no holding brake, whereas the design still requires a
separate J2 brake path. It is not evidence that the brake, motor driver,
feedback connector, power voltage, shaft coupling, CSG-40-100-2UH input
interface, mounting adapter, bearing stack, or output-side alignment is
compatible.

## Required evidence before a J2 assembly claim

1. Obtain a manufacturer-controlled exact-variant datasheet or written
   configuration confirmation covering the selected suffix and the thermal
   parameters required by the contract; bind only values with their stated
   mounting and temperature conditions.
2. Bind the CSG-40-100-2UH input drawing and a motor-to-reducer coupling/
   adapter drawing; validate shaft, bolt pattern, axial/radial loading,
   concentricity, and assembly clearances from the actual CAD.
3. Select and source-bind a driver with matching voltage, continuous/peak
   current, feedback protocol, power connector, STO/fault behavior, and thermal
   envelope.
4. Select and source-bind the separate fail-safe brake, including its required
   torque, engagement behavior, release power, and mechanical interface.
5. Re-run static, thermal, dynamics, collision, and hardware safety gates using
   the source-bound assembly, then obtain the separately authorized real-world
   evidence needed for any physical claim.

This candidate narrows the research space without changing the reference
robot's non-promotable state.
