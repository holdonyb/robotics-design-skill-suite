"""Immutable authority for benchmark-owned simulation scenarios."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..hypothesis.canonical import validate_sha256
from .scenario import CompiledScenario, ScenarioError, _load_registry_bytes, compile_scenarios


# This is retained by the benchmark code, rather than accepted from the policy
# callback or trace-assignment caller.  Updating reference scenarios is an
# explicit review/release operation that must update this receipt and its
# release-contract binding together.
REFERENCE_SCENARIO_REGISTRY_RECEIPT = "1d142ab3945e7c27ba90f0a0b15695eb47654cb659bfd9840ee87ca665f5341c"


class TrustedRegistryError(ValueError):
    """A scenario registry is not the benchmark-authorized registry."""


@dataclass(frozen=True)
class TrustedScenarioRegistry:
    """The exact, compiled scenario set authorized by a benchmark owner."""

    registry_sha256: str
    scenarios: tuple[CompiledScenario, ...]

    def scenario_by_id(self, scenario_id: str) -> CompiledScenario:
        if not isinstance(scenario_id, str):
            raise TrustedRegistryError("scenario_id must be a string")
        for scenario in self.scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        raise TrustedRegistryError(f"unknown scenario: {scenario_id}")


def load_trusted_scenario_registry(path: str | Path, external_receipt_sha256: str) -> TrustedScenarioRegistry:
    """Load a registry only when its exact source bytes match an external receipt."""

    try:
        expected = validate_sha256(external_receipt_sha256, "external registry receipt")
        payload = Path(path).read_bytes()
    except (OSError, TypeError, ValueError) as exc:
        raise TrustedRegistryError(f"cannot load trusted scenario registry: {exc}") from None
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise TrustedRegistryError("scenario registry SHA-256 does not match its external receipt")
    try:
        scenarios = compile_scenarios(_load_registry_bytes(payload))
    except ScenarioError as exc:
        raise TrustedRegistryError(f"cannot compile trusted scenario registry: {exc}") from None
    return TrustedScenarioRegistry(actual, scenarios)


def load_reference_trusted_scenario_registry(reference_root: str | Path) -> TrustedScenarioRegistry:
    """Load the public reference scenarios from the benchmark-owned receipt."""

    root = Path(reference_root)
    if root.is_symlink() or not root.is_dir():
        raise TrustedRegistryError("reference root is missing, not a directory, or a symlink")
    try:
        return load_trusted_scenario_registry(
            root / "simulation" / "scenarios.json", REFERENCE_SCENARIO_REGISTRY_RECEIPT
        )
    except TrustedRegistryError as exc:
        raise TrustedRegistryError("reference scenario registry does not match its external receipt: " + str(exc)) from None
