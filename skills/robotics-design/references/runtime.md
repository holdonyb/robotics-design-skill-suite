# Runtime Setup

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

## ROS 2 simulation

`ros2-sim` targets ROS 2 Jazzy and Gazebo Harmonic on Linux. Run its `scripts/env_check.sh` before promising build or simulation results. A missing `/opt/ros/jazzy/setup.bash` is an environment gate, not a design pass or failure.
