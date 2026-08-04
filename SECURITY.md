# Security Policy

## Supported version

Security fixes target the latest release and the default branch.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for this repository. Do not open a public issue containing an exploitable archive, credential, private path, or unsafe installation sequence.

Include the affected commit, platform, command, observed behavior, expected behavior, and a minimal reproduction that does not expose secrets.

## Security boundary

The installer downloads pinned HTTPS archives, rejects ZIP path traversal, refuses existing destinations, and does not execute installed skill scripts. It is not a sandbox and does not make third-party skill code trustworthy. Review source changes before updating pinned commits.

Robot safety is a separate boundary. This repository does not authorize real hardware motion or certify control, perception, emergency-stop, or functional-safety systems.
