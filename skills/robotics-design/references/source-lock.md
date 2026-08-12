# Source Lock

`manifest.json` in the distribution repository is the machine-readable source of truth.

| Skills | Upstream | Commit | License |
|---|---|---|---|
| `cad`, `cad-viewer`, `step-parts`, `dxf`, `urdf`, `sdf`, `srdf` | `earthtojake/text-to-cad` | `4fd71ea75fbb8a80b0d7c76862e0fd73c52a8989` | MIT |
| `ros2-engineering-skills` | `dbwls99706/ros2-engineering-skills` | `118d505c4b540912668ad2d4874022f34060112c` | Apache-2.0 |
| `ros2-sim` | `BaraaLazkani/ros2-sim-skill` | `97cd3cec17b89b28c577a001285bcace35ec2374` | MIT |

The installer removes Claude-only frontmatter fields from `ros2-engineering-skills` while retaining its scripts for manual Codex validation. Version 0.2.0 adds local, portable visual-fidelity, mission-animation, and patent-aware contracts without changing these upstream locks. Host runtime paths belong only in generated `host-runtime.md` overlays.

Update commits only after source audit, structural validation, real artifact smoke tests, ROS script tests, routing regression tests, and the affected visual, mission-animation, patent-aware, and host-overlay RED/GREEN suites.
