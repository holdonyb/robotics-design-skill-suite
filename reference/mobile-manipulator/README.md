# Reference Mobile Manipulator

This differential-drive base plus six-axis arm is a deterministic regression
fixture for the physical-plausibility kernel. Its dimensions, masses, component
ratings, duty, payload and environment values are engineering assumptions. They
are not measurements, a finished design, a purchasing recommendation, or proof
of payload, stability, endurance, braking, thermal, safety or task performance.

The baseline intentionally uses `engineering_placeholder` component records.
It must remain unpromoted until exact parts, manufacturer evidence and measured
or qualified operating limits replace every claim-driving placeholder. A clean
analysis result means only that the declared regression inputs satisfy the
implemented conservative equations.

Run the gate from the repository root:

```powershell
python skills/robotics-design/scripts/validate_design_contract.py reference/mobile-manipulator/design-contract.json --report reference-evidence.json
```

Expected baseline result: exit `1` with
`BOM.PLACEHOLDER_BLOCKS_CLAIM`; structural, reference, hash, drift and physical
analysis diagnostics remain clear. Files under `faults/` mutate one critical
condition at a time and must add their declared diagnostic without allowing
promotion.
