import copy
import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.simulation.scenario import (  # noqa: E402
    ScenarioError,
    compile_scenarios,
    load_scenario_registry,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
JOINTS = [f"joint_{index}" for index in range(1, 7)]


def registry():
    return {
        "schema_version": 1,
        "registry_id": "reference-scenarios-v1",
        "model_sha256": SHA_A,
        "trajectory_sha256": SHA_B,
        "environment_sha256": SHA_C,
        "joint_order": JOINTS,
        "scenarios": [
            {
                "scenario_id": f"scenario-{index:02d}",
                "version": "v1",
                "seed": index,
                "duration_ns": 1_000_000_000,
                "parameters": {"payload_kg": 5.0, "surface": "level"},
                "faults": [] if index != 10 else [{"fault_id": "fault-stop", "at_ns": 500_000_000}],
                "metrics": [
                    {"name": "final_joint_error", "unit": "rad", "direction": "max", "limit": 0.01},
                    {"name": "elapsed_time", "unit": "s", "direction": "max", "limit": 1.0},
                ],
                "stop": {"reason": "duration_elapsed", "at_ns": 1_000_000_000},
            }
            for index in range(1, 11)
        ],
    }


class ScenarioCompilationTests(unittest.TestCase):
    def test_compiles_exactly_ten_canonical_seed_ordered_specs(self):
        source = registry()
        specs = compile_scenarios(source)
        self.assertEqual(10, len(specs))
        self.assertEqual(list(range(1, 11)), [spec.seed for spec in specs])
        self.assertEqual([f"scenario-{index:02d}" for index in range(1, 11)], [spec.scenario_id for spec in specs])
        self.assertEqual(tuple(JOINTS), specs[0].joint_order)
        self.assertEqual("fault-stop", specs[-1].faults[0]["fault_id"])
        self.assertEqual(specs, compile_scenarios(copy.deepcopy(source)))
        self.assertEqual(
            hashlib.sha256(canonical_bytes(specs[0].to_dict())).hexdigest(),
            specs[0].scenario_sha256,
        )

    def test_rejects_invalid_registry_fault_metric_and_stop_contracts(self):
        attacks = (
            (lambda value: value.__setitem__("schema_version", True), "schema_version"),
            (lambda value: value["scenarios"].pop(), "exactly 10"),
            (lambda value: value["scenarios"][1].__setitem__("seed", 1), "duplicate seed"),
            (lambda value: value["scenarios"][0]["faults"].extend([{ "fault_id": "f", "at_ns": 1}, {"fault_id": "f", "at_ns": 2}]), "duplicate fault_id"),
            (lambda value: value["scenarios"][0]["metrics"][0].__setitem__("unit", "kg"), "unit"),
            (lambda value: value["scenarios"][0]["stop"].__setitem__("at_ns", 2_000_000_000), "stop.at_ns"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected):
                bad = registry()
                mutate(bad)
                with self.assertRaisesRegex(ScenarioError, expected):
                    compile_scenarios(bad)

    def test_loader_rejects_duplicate_keys_and_reference_registry_is_compilable(self):
        path = ROOT / "reference" / "mobile-manipulator" / "simulation" / "scenarios.json"
        loaded = load_scenario_registry(path)
        self.assertEqual(10, len(compile_scenarios(loaded)))
        with self.assertRaisesRegex(ScenarioError, "duplicate JSON key"):
            load_scenario_registry_bytes(b'{"schema_version":1,"schema_version":1}')


def load_scenario_registry_bytes(payload):
    from assurance.simulation.scenario import _load_registry_bytes

    return _load_registry_bytes(payload)


if __name__ == "__main__":
    unittest.main()
