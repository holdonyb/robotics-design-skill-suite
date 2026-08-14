# Harmonic Drive CSG-40-100-2UH source audit

Date observed: 2026-08-14

This is a source-bound extraction for the J2 reducer candidate. It is not a
purchase decision, a motor-selection result, an assembly drawing, or a
hardware authorization.

## Source and selection

- Manufacturer: Harmonic Drive
- Candidate part number: `CSG-40-100-2UH`
- Official product page:
  <https://www.harmonicdrive.net/products/gear-units/gear-units/csg-2uh/csg-40-100-2uh>
- Official drawings download index:
  <https://www.harmonicdrive.net/downloads/pdf-drawings/csg-gear-units>
- Parsed, closed snapshot:
  `reference/mobile-manipulator/supplier-catalogs/harmonic-drive-csg-40-100-2uh-2026-08-14.json`
- Snapshot SHA-256:
  `454209eef068805b94d524c37bd6785f810471799ba6c00deed66bf4e8248a42`

The official product page identifies the unit as CSG size 40, ratio 100, type
2UH, with a rated L10 output torque of 345 N*m. The reference contract binds
only that continuous output-side rating and the 100:1 ratio to the exact J2
reducer record. A step.parts exact-model search completed with no catalog
candidate, so no third-party CAD proxy is used.

## Use and limits

The bound 345 N*m rating is sufficient for the current declared J2 static
gravity envelope (its required continuous output torque is approximately
295.01 N*m), but that result is only a calculated screening margin. It does
not prove that the selected motor, adapter, coupling, brake, output bearing
stack, bolt pattern, lubrication, backdrive behavior, peak duty, life,
stiffness, thermal duty, collision loads, or CAD fit is suitable. Those remain
explicitly unresolved until their own parts, geometry and evidence are bound.

The reference robot remains blocked from physical promotion by the remaining
engineering placeholders. This snapshot adds reproducible vendor provenance;
it is not supplier authentication, qualification, procurement, fabrication,
energization, or motion authority.
