# v0.4 Hypothesis Benchmark

This finite benchmark exercises the v0.4 engine against the differential-drive
base plus six-axis-arm reference contract. It evaluates four root combinations:
5 or 6 kWh assumed usable energy, and the baseline or an intentionally
undersized right-motor peak-torque rating. Two hard uncertainty dimensions use
analytically passing 5/6 kg payload and 5/6 degree slope values. A 7 kg payload
probe is outside this screened set because it triggers current arm torque and
brake blockers.

The expected seed is `20260813`. It produces four root candidates and two
owner-correct repair children under 76 stage evaluations, including the full
hard-uncertainty and one-at-a-time sensitivity probes. The extended-energy,
rated-right-motor candidate improves calculated runtime from 22,500 to 27,000
seconds and is the first analytical-screening Pareto front. The deliberately
wrong right rating triggers `PHY.DRIVE.PEAK_TORQUE`; its repair changes only
`quantity:Q-MOTOR-PEAK-TORQUE-R.value`, owned by
`component:CMP-TRACTION-MOTOR-R`.

No candidate is accepted. All 49 claim-driving components remain
`engineering_placeholder`, so `BOM.PLACEHOLDER_BLOCKS_CLAIM` remains open.
`screening-pareto.json` is a comparison of candidates whose analyses pass and
whose only blocker is that placeholder code; it is not the promotion Pareto
front, not an optimization guarantee, and not simulation, training, bench, or
hardware evidence. `hypothesis-expected.json` pins the deterministic seed,
space hash, counts, screening fronts, stage budget, and out-of-band bundle
manifest receipt.

Run from the repository root:

```powershell
python skills/robotics-design/scripts/generate_design_hypotheses.py reference/mobile-manipulator/hypothesis-space.json --out .tmp-install/v040-reference --seed 20260813
```

Expected exit code: `1`, because no candidate is promotable.
