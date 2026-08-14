# J2 motor--driver candidate interface precheck

Date observed: 2026-08-14

This is a catalog-level compatibility precheck for a possible J2 motor and
drive pair. It is not a source-bound actuator assembly, procurement decision,
functional-safety validation, or hardware authorization.

## Candidate records

| Role | Candidate | Source-bound record |
| --- | --- | --- |
| Motor | Kollmorgen `AKM54H-ANCNAB00` | `supplier-catalogs/kollmorgen-akm54h-ancnab00-candidate-2026-08-14.json` |
| Driver | Kollmorgen `AKD-P00607-NDCC` | `supplier-catalogs/kollmorgen-akd-p00607-ndcc-candidate-2026-08-14.json` |

The exact driver listing is
<https://shop.oxni.ch/en/store/drives/AKD-P00607-NDCC>. Its manufacturer-family
installation manual is
<https://www.kollmorgen.cn/sites/default/files/public_downloads/AKD%20Installation%20Manual%20EN%20%28REV%20AC%29.pdf>.

The driver snapshot SHA-256 is `319b72257469bcf74c3086eeccf02507301b9a97bfd8b5ca43f3ce9546ed3be2`.

## Bounded catalog comparison

| Property | Motor candidate | Driver candidate | Result |
| --- | ---: | ---: | --- |
| AC voltage class | 400 V AC | 3-phase 400 V AC | Same catalog voltage class only |
| Continuous current | 5.5 A RMS | 6 A RMS | 0.5 A RMS catalog margin |
| Peak current | 16.5 A RMS | 18 A RMS | 1.5 A RMS catalog margin |
| Feedback | BiSS-B | BiSS listed | Protocol-family overlap only |
| Motor thermal sensor | PTC | PTC supported | Sensor-family overlap only |
| Safety | no motor safety function claimed | STO listed | Drive feature only; no system safety claim |

The step.parts API was reachable on the observation date. Exact and alias
queries (`AKD-P00607-NDCC`, `Kollmorgen AKD-P00607`, and `AKD-P00607`) each
returned zero items. No STEP asset or inferred CAD envelope is used.

## Conflict found by the precheck

The reference contract's existing J2 thermal input is an **assumed** 10 A
thermal-on current. It is higher than the candidate driver's 6 A RMS continuous
rating and the motor's 5.5 A RMS continuous rating. No duration, RMS conversion,
peak-current duty allowance, temperature derating, or commanded current profile
has been source-bound for the exact parts. Therefore the 10 A model input cannot
be treated as a continuously supported driver operating point, and this precheck
does not reduce the J2 thermal blocker.

## Deliberate non-promotion and remaining interface work

`CMP-ARM-MOTOR-J2` and `CMP-ARM-DRIVER-J2` remain
`engineering_placeholder`; the reference robot remains non-promotable. Before
declaring any motor--driver interface compatible, bind exact revision-controlled
manufacturer documentation and validate all of the following:

1. motor winding/feedback suffix, connector pinouts, shield/grounding, phase
   order, sensor polarity, and parameterization;
2. motor torque-speed and current derating at the actual DC bus, ambient,
   mounting plate, cable length, switching frequency, and regenerative duty;
3. continuous and transient current waveforms against both components' rated
   and peak time limits, including the existing 10 A thermal-model assumption;
4. STO architecture, safe-torque-off response, brake-control interlocks,
   fault detection, power-loss behavior, and recovery procedure; and
5. the motor--reducer coupling/adapter, separate brake, bearing stack, and
   full CAD clearance checks.

The candidate pair narrows a sourcing hypothesis. It does not demonstrate that
the CSG-40-100-2UH reducer, a brake, or any reference robot hardware can be
assembled, energized, or operated.
