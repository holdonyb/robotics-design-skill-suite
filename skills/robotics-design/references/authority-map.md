# Robotics Authority Map

Use these as method references, not substitutes for project evidence. Verify current official documentation for version-sensitive APIs and standards.

- [Drake](https://drake.mit.edu/) — model-based design, multibody dynamics, optimization, planning, and control.
- [MIT Robotic Manipulation](https://manipulation.csail.mit.edu/) — perception, planning, dynamics, control, and manipulation system design.
- [Google DeepMind MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) — curated robot model examples and model-quality conventions.
- [Gemini Robotics SDK](https://github.com/google-deepmind/gemini-robotics-sdk) — current DeepMind robotics SDK integration patterns; verify supported hardware and APIs.
- [NVIDIA Agent Skills](https://github.com/NVIDIA/skills) — staged physical-AI skill packaging and validation structure.
- [NVIDIA ASPIRE](https://research.nvidia.com/labs/gear/aspire/) — trace-diagnose-repair-rerun-promote feedback pattern.
- Official patent offices and registers — authoritative publications, claims, families, prosecution records, and legal status for patent-aware architecture work; aggregators are discovery aids only.
- Exact manufacturer datasheets, application notes, drawings, motor/drive curves, battery limits, and certificates for the selected part revision — component identity and rating evidence; distributor snippets and family-level pages are discovery aids only.
- Project-controlled measurements with calibrated instrumentation, raw logs, configuration, uncertainty, specimen identity, and environmental conditions — authority for bench and integrated-hardware evidence.

Prefer project measurements and exact vendor data, then exact-version official documentation and official patent records, then institution-maintained methods/models, then installed community workflow guidance, and model memory only as a labeled hypothesis.

Analytical equations in `physical-plausibility-contract.md` are conservative
screening methods. Use higher-fidelity official or peer-reviewed models when
their domain applies, but retain the same quantity ownership, evidence edges,
validity assumptions, signed margins, and failure-preserving promotion rules.

NVIDIA `omniverse-cad-to-simready` is deliberately not a default dependency. Re-evaluate its current official benchmark, runtime requirements, and live-agent evidence before adding it.
