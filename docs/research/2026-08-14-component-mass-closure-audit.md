# Component mass-closure audit

Date: 2026-08-14

## Decision

The physical gate now has a closed `component_mass_closure_v1` analysis. For
each declared link it checks exact equality between the URDF-observed link mass
and the sum of a separately observed structural residual plus explicit
component masses. Every quantity is typed as mass and ownership is checked
against the named link or component.

## Reference result

The mobile-manipulator reference starts with six arm-link structural budgets
(8, 7, 5, 4, 3, and 2 kg) and no selected component contributions. This is a
deliberate unpromoted baseline, not a claim that any candidate part has zero
mass. The BFK458-20 brake candidate remains an unbound supplier snapshot and
is absent from the link budgets until an exact selected configuration, its
placement, and an updated physical model are supplied.

## Rejection cases

The gate rejects non-finite or unbalanced records, a component quantity owned
by another component, a verified/qualified component whose contribution does
not equal its catalog `mass` limit, and a verified/qualified component that
declares a mass limit but appears in no closure record.

## Boundary

Mass closure is an accounting screen. It does not infer mass properties,
mounting, CAD fit, braking capacity, structural strength, thermal behavior,
procurement suitability, energized operation, or hardware authority.
