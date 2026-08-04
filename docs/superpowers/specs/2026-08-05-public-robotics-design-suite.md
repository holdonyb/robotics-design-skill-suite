# Public Robotics Design Skill Suite

## Goal

Publish a standalone, public GitHub repository that installs a curated robotics design suite for Codex without copying third-party skill trees into this repository.

## Repository identity

- Local path: `<workspace>/robotics-design-skill-suite`
- GitHub repository: `holdonyb/robotics-design-skill-suite`
- Visibility: public
- Original-content license: MIT

## Packaging decision

Use a thin distribution repository.

The repository owns:

- the `robotics-design` routing skill and its original references;
- a machine-readable manifest pinning audited upstream commits;
- a standard-library Python installer and validator;
- public hygiene, manifest, and dry-run tests;
- bilingual documentation, third-party notices, contribution guidance, security policy, and CI.

The repository does not vendor the full upstream skill trees. The installer downloads pinned GitHub archives and copies only the declared skill paths. This keeps provenance, licenses, updates, and review boundaries explicit.

## Installation architecture

`manifest.json` is the single source of truth. Each source declares repository, commit, license, and skill path-to-install-name mappings. `scripts/install.py` resolves a destination, refuses to overwrite existing skills, downloads archives, validates safe ZIP extraction, copies declared skills, attaches upstream licenses, normalizes the known Claude-only ROS 2 frontmatter, and installs the local router last.

The default destination is `${CODEX_HOME}/skills` when `CODEX_HOME` is set and `~/.codex/skills` otherwise. `--dest` overrides it. `--dry-run` performs no writes or network calls and prints the exact installation plan.

Heavy CAD Python dependencies are deliberately not installed automatically. README documents an optional isolated Python 3.12+ runtime because mutating a user's global Python environment is outside a skill installer's authority.

## Public safety and hygiene

- No private workspace content, credentials, tokens, user names, drive-letter paths, or local project names.
- No automatic real-robot motion, deployment, publishing, or external messaging.
- No claim that installing a skill proves robot safety, simulation correctness, certification, payload, stability, or endurance.
- Existing destination directories cause an error; the installer never overwrites or deletes them.
- Network downloads are pinned to full commit hashes and use HTTPS.
- Third-party licenses and exact source commits remain visible after installation.

## Validation

CI and local validation must prove:

1. manifest schema, commit hashes, source uniqueness, and declared local paths are valid;
2. all public text passes sensitive-path and secret-pattern scans;
3. the local router has valid Agent Skill frontmatter and required references;
4. installer dry-run is deterministic and complete;
5. a local fixture archive can be installed without network access;
6. existing destination collisions fail without modifying the destination;
7. Python files compile and the complete unit test suite passes.

Live ROS 2 Jazzy/Gazebo Harmonic and physical robot validation are explicitly outside repository CI.

## Release boundary

The first release is source-first: tagged repository, installation instructions, pinned sources, tests, and CI. It does not include a package registry, auto-update daemon, telemetry, hosted service, or vendored offline bundle.
