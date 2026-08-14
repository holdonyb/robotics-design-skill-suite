# Live Simulation Trace Evidence Design

## Decision

The Jazzy/Harmonic consumer gate will retain one bounded, commanded Gazebo
drive as a receipt-bound **simulated** trace.  It will preserve the raw rosbag2
MCAP files, decode only a closed set of ROS messages, and publish a canonical
normalized summary whose receipt binds the raw inputs, the ROS workspace
receipt, the portable physical profile, and the command envelope.

This closes the present gap between two valid but separate checks: the portable
benchmark's deterministic synthetic traces and CI's live consumer startup.
It does not make Gazebo an oracle for physical behavior, calibrate a model, or
authorize hardware.  Every resulting record derives
`hardware_promotable: false`.

## Scope and data flow

After the live gate verifies Gazebo and all three controllers are active, it
starts `ros2 bag record` with MCAP storage for exactly four topics:

- `/clock`;
- `/joint_states`;
- `/odom`;
- `/diff_drive_controller/cmd_vel`.

The gate emits a bounded positive `TwistStamped` command (0.10 m/s linear,
zero angular) at 10 Hz for two seconds, waits for settling, stops the recorder,
and retains its directory unchanged.  This affects only the Dockerized Gazebo
robot.  The command is below the receipt-bound Nav2 linear limit and is never
sent to a physical topic or device.

The live container has `--network=none`, `ROS_DOMAIN_ID=139`, and
`ROS_LOCALHOST_ONLY=1`; the gate verifies both ROS isolation variables before
starting any simulator process.  Thus DDS discovery cannot reach a host or
physical controller even if the workflow runner is reused outside GitHub.

A runtime adapter opens the MCAP with `rosbag2_py`, deserializes the four exact
ROS message types, and converts them to primitive records.  A pure-Python
validator then checks bounded topic closure, monotonic timestamps, required
counts, finite fields, reference joint identity, a nonzero forward odometry
response, and a command that remains inside the parsed ROS profile.  The
validator writes a canonical evidence bundle containing:

- a closed provenance record with the ROS workspace receipt and profile source
  hashes;
- the SHA-256 and exact relative filename of each raw bag file;
- normalized command, clock, joint-state, and odometry summaries;
- the validation disposition and the constant hardware firewall.

The canonical bundle manifest and its out-of-band receipt are retained beside
the original MCAP directory.  The raw bag is deliberately not interpreted as a
portable engineering truth: the normalized conclusion is only that this exact
receipt-bound simulator stack accepted and responded to the bounded command.

## Fail-closed rules

- Unknown topics, missing or duplicate required raw files, symlinks, non-MCAP
  data, empty recordings, malformed messages, nonfinite numbers, and timestamp
  regressions reject the capture.
- A source profile mismatch, unbound ROS workspace, missing controller command,
  missing wheel joints, no positive base displacement, or command over the
  parsed limit rejects the capture.
- The adapter never trusts a stored rosbag verdict.  It recomputes its
  normalized summary from deserialized records and hashes every raw file it
  names.
- A runtime dependency failure (`rosbag2_py`, deserializer, MCAP storage) fails
  the live CI job rather than publishing a substitute synthetic result.

## Verification and claims

Portable tests exercise the pure normalizer with valid records and attacks:
wrong topic/type, duplicate/unknown bag file, timestamp reversal, NaN,
unbounded command, missing wheel identity, and no motion.  Static CI tests
ensure the live gate records the exact topic set, transmits only the bounded
simulated command, invokes the runtime extraction script, and uploads both raw
and normalized receipts.  The Jazzy/Harmonic job is the integration proof.

No performance, safety, calibration, collision, task, vendor, procurement, or
hardware claim follows from this feature.
