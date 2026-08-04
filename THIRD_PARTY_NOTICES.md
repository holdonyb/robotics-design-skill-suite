# Third-Party Notices

This distribution installs third-party skills from pinned upstream commits. Those components are not relicensed under this repository's MIT license.

| Upstream | Commit | Installed skills | License |
|---|---|---|---|
| [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) | `4fd71ea75fbb8a80b0d7c76862e0fd73c52a8989` | `cad`, `cad-viewer`, `step-parts`, `dxf`, `urdf`, `sdf`, `srdf` | MIT |
| [dbwls99706/ros2-engineering-skills](https://github.com/dbwls99706/ros2-engineering-skills) | `118d505c4b540912668ad2d4874022f34060112c` | `ros2-engineering-skills` | Apache-2.0 |
| [BaraaLazkani/ros2-sim-skill](https://github.com/BaraaLazkani/ros2-sim-skill) | `97cd3cec17b89b28c577a001285bcace35ec2374` | `ros2-sim` | MIT |

The installer retrieves each upstream `LICENSE` file and writes it as `UPSTREAM_LICENSE` inside every installed third-party skill. Consult the upstream repositories for copyright notices, dependency licenses, and source-specific terms.

The `ros2-engineering-skills` installation receives one compatibility transformation: Claude-only top-level frontmatter is removed so Codex accepts the skill. Its documentation and executable validation scripts otherwise remain upstream material under Apache-2.0.
