import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.trusted_registry import (  # noqa: E402
    TrustedRegistryError,
    load_reference_trusted_scenario_registry,
    load_trusted_scenario_registry,
)


class TrustedScenarioRegistryTests(unittest.TestCase):
    def test_loads_only_the_exact_receipted_registry_bytes(self):
        path = ROOT / "reference" / "mobile-manipulator" / "simulation" / "scenarios.json"
        receipt = hashlib.sha256(path.read_bytes()).hexdigest()
        registry = load_trusted_scenario_registry(path, receipt)
        self.assertEqual(receipt, registry.registry_sha256)
        self.assertEqual(10, len(registry.scenarios))
        self.assertEqual("scenario-01", registry.scenario_by_id("scenario-01").scenario_id)

    def test_rejects_registry_byte_drift_and_unknown_scenarios(self):
        source = ROOT / "reference" / "mobile-manipulator" / "simulation" / "scenarios.json"
        receipt = hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "scenarios.json"
            shutil.copyfile(source, copied)
            copied.write_bytes(copied.read_bytes() + b"\n")
            with self.assertRaisesRegex(TrustedRegistryError, "SHA-256"):
                load_trusted_scenario_registry(copied, receipt)
        registry = load_trusted_scenario_registry(source, receipt)
        with self.assertRaisesRegex(TrustedRegistryError, "unknown scenario"):
            registry.scenario_by_id("scenario-nope")

    def test_reference_authority_has_its_own_retained_receipt(self):
        reference = ROOT / "reference" / "mobile-manipulator"
        registry = load_reference_trusted_scenario_registry(reference)
        self.assertEqual("1d142ab3945e7c27ba90f0a0b15695eb47654cb659bfd9840ee87ca665f5341c", registry.registry_sha256)
        with tempfile.TemporaryDirectory() as raw:
            copied_root = Path(raw) / "reference"
            shutil.copytree(reference, copied_root)
            scenario_path = copied_root / "simulation" / "scenarios.json"
            scenario_path.write_bytes(scenario_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(TrustedRegistryError, "external receipt"):
                load_reference_trusted_scenario_registry(copied_root)


if __name__ == "__main__":
    unittest.main()
