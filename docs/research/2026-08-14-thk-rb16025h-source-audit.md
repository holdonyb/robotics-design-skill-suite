# THK RB16025H source audit

Date observed: 2026-08-14

This is a source-bound supplier-catalog extraction for one reference-arm
bearing candidate. It is not an order, an approved manufacturing drawing, a
fit check, a life calculation, or an authorization to operate hardware.

## Source

- Manufacturer: THK
- Candidate part number: `RB16025H`
- Official catalog: <https://tech.thk.com/upload/catalog_claim/pdf/l83e_rbhrehruh.pdf>
- Parsed, closed snapshot:
  `reference/mobile-manipulator/supplier-catalogs/thk-rb16025h-2026-08-14.json`
- Snapshot SHA-256:
  `23badab0dbed010598e7ba84186576eeeac9e368c4cb16dad3f3d6c7a480c961`

The catalog row records a basic dynamic radial load rating of 89.4 kN and a
basic static radial load rating of 152 kN, plus a 188.6 mm roller pitch
diameter, for the candidate. The snapshot stores each value in explicit units
and the reference design contract binds each one to its component-owned
quantity.

## Use and limits

THK's catalog describes a static equivalent radial load that includes radial
load, axial load, and a moment term, as well as a static safety-factor method.
The reference model now has a separate, hash-bound `bearing-load-j2.json`
static-screen input for one J2 horizontal-reach case. Its gravity reaction,
zero axial load, and overturning moment are still explicit assumptions pending
bearing-stack geometry. It does not supply mounting, preload, stiffness,
duty-cycle, lubrication, life, shock, or thermal inputs needed to assess a real
assembly. Therefore this candidate only replaces an untraceable bearing rating
with parsed catalog evidence and supports a bounded static screen; it does not
make the arm, J2, or the robot physically promotable.

The contract deliberately remains blocked by the other engineering-placeholder
components. Vendor publication plus a hash-bound parsed snapshot is traceable
evidence, not independent supplier authentication or certified performance.
