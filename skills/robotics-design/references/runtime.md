# Runtime Setup

## Optional generated host overlay

The public skill contains portable runtime guidance only. Installers may create
`references/host-runtime.md` when invoked with `--host-runtime-python`. That
generated file records the resolved executable and destination for one host; it
is installation state, not repository provenance, and must not be committed.

Skill installation and tool runtime are separate concerns.

## Codex skills

Install to `${CODEX_HOME}/skills`, `~/.codex/skills`, or an explicit `--dest`. Start a new Codex task after installation so skill discovery refreshes.

## CAD and robot-format generators

Use Python 3.12+ in an isolated environment. Install the declared local runtime package from the installed CAD skill and `ezdxf` when DXF generation is needed. Do not modify a user's global Python environment automatically.

Example after installation:

```bash
python3.12 -m venv .venv-robotics-design
.venv-robotics-design/bin/python -m pip install -e ~/.codex/skills/cad/scripts/packages/cadpy ezdxf
```

On Windows use the environment's `Scripts/python.exe`. Some generator CLIs require POSIX `/` separators even on Windows. Run CAD inspection from the target project/part directory with relative paths to avoid broad catalog scans.

## Visual manifest validator

`scripts/validate_visual_manifest.py` uses only the Python standard library and runs on Python 3.11+. Invoke it with a visual manifest JSON path after the landmark review and before promoting a generated robot render.

## ROS 2 simulation

`ros2-sim` targets ROS 2 Jazzy and Gazebo Harmonic on Linux. Run its `scripts/env_check.sh` before promising build or simulation results. A missing `/opt/ros/jazzy/setup.bash` is an environment gate, not a design pass or failure.
