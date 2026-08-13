import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
REFERENCE = ROOT / "reference" / "mobile-manipulator"
sys.path.insert(0, str(SCRIPTS))

from assurance.engine import evaluate_contract  # noqa: E402


def apply_mutation(data, mutation):
    operation = mutation["op"]
    if operation == "set_component_missing":
        role = mutation["role"]
        for item in data["components"]:
            if item["role"] == role:
                item["state"] = "missing"
    elif operation == "set_quantity_value":
        quantity = next(
            item for item in data["quantities"] if item["id"] == mutation["id"]
        )
        quantity["value"] = mutation["value"]
    elif operation == "set_artifact_hash":
        artifact = next(
            item for item in data["artifacts"] if item["id"] == mutation["id"]
        )
        artifact["sha256"] = mutation["sha256"]
    else:
        raise AssertionError(f"unknown mutation operation: {operation}")


class ReferenceRobotTests(unittest.TestCase):
    def test_reference_baseline_is_structurally_sound_but_unpromoted(self):
        report, errors = evaluate_contract(REFERENCE / "design-contract.json")
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        codes = {item.code for item in report.diagnostics}
        self.assertTrue(codes)
        self.assertEqual(codes, {"BOM.PLACEHOLDER_BLOCKS_CLAIM"})
        self.assertEqual(
            {item["name"] for item in report.analyses},
            {
                "drivetrain_v1",
                "battery_v1",
                "stability_v1",
                "arm_gravity_v1",
                "thermal_duty_v1",
            },
        )
        self.assertTrue(all(item["passed"] for item in report.analyses))

    def test_all_critical_faults_are_rejected_by_expected_gate(self):
        baseline = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        fault_paths = sorted((REFERENCE / "faults").glob("*.json"))
        self.assertGreaterEqual(len(fault_paths), 25)
        seen = set()
        for fault_path in fault_paths:
            fault = json.loads(fault_path.read_text(encoding="utf-8"))
            self.assertTrue(fault["critical"], fault_path.name)
            self.assertNotIn(fault["id"], seen)
            seen.add(fault["id"])
            mutated = copy.deepcopy(baseline)
            apply_mutation(mutated, fault["mutation"])
            with self.subTest(fault=fault["id"]), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                for source_name in ("robot.urdf", "assumptions.json"):
                    (temp / source_name).write_bytes((REFERENCE / source_name).read_bytes())
                contract = temp / "design-contract.json"
                contract.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
                report, errors = evaluate_contract(contract)
                self.assertEqual(errors, [])
                self.assertIsNotNone(report)
                codes = {item.code for item in report.diagnostics}
                self.assertIn(fault["expected_diagnostic"], codes)
                self.assertFalse(report.promotable)


if __name__ == "__main__":
    unittest.main()
