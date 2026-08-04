# Contributing

## Development

Use Python 3.11+ and the standard library only for installer code.

```bash
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
```

## Pull requests

- Keep the distribution thin; do not vendor upstream skill trees.
- Add a failing test before changing installer or validator behavior.
- Preserve the single source of truth in `manifest.json`.
- Never add credentials, private workspace paths, customer data, or machine-specific configuration.
- Document safety and evidence boundaries for new robotics capabilities.

## Updating an upstream commit

Review the changed `SKILL.md`, scripts, dependencies, network/process behavior, and license. Then run structural validation, artifact smoke tests where applicable, ROS script tests, routing scenarios, and the complete repository test suite. Update `manifest.json`, `THIRD_PARTY_NOTICES.md`, and `source-lock.md` together.
