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
    def test_wrong_dimension_blocks_each_known_plugin_before_evaluation(self):
        selected_fields = {
            "drivetrain_v1": ("wheel_radius_m",),
            "battery_v1": ("voltage_v",),
            "stability_v1": ("com_height_m",),
            "arm_load_envelope_v1": ("rated_continuous_torque_nm", 0, "value"),
            "thermal_duty_v1": ("ambient_temperature_k",),
        }
        baseline = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        for analysis in baseline["analyses"]:
            plugin = analysis["plugin"]
            if plugin not in selected_fields:
                continue
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory() as temp_dir:
                mutated = copy.deepcopy(baseline)
                target = next(item for item in mutated["analyses"] if item["plugin"] == plugin)
                reference = target["inputs"]
                for part in selected_fields[plugin]:
                    reference = reference[part]
                quantity_id = reference.removeprefix("quantity:")
                quantity = next(
                    item for item in mutated["quantities"] if item["id"] == quantity_id
                )
                quantity["dimension"] = "mass"
                quantity["value"] = {"value": 1.0, "unit": "kg"}
                contract = Path(temp_dir) / "design-contract.json"
                contract.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
                report, errors = evaluate_contract(contract)
                self.assertIsNone(report)
                self.assertTrue(
                    any(plugin in error and "expects dimension" in error for error in errors),
                    errors,
                )

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
                "arm_load_envelope_v1",
                "thermal_duty_v1",
            },
        )
        self.assertTrue(all(item["passed"] for item in report.analyses))

    def test_load_envelope_is_hash_bound_and_downstream_mass_is_monotone(self):
        data = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        artifact = next(item for item in data["artifacts"] if item["id"] == "load-envelope-model")
        self.assertEqual(artifact["kind"], "declared_json")
        analysis = next(item for item in data["analyses"] if item["id"] == "AN-ARM-LOAD-ENVELOPE")
        self.assertEqual(analysis["plugin"], "arm_load_envelope_v1")
        self.assertEqual(analysis["inputs"]["joint_order"], [f"joint_{index}" for index in range(1, 7)])

        baseline, errors = evaluate_contract(REFERENCE / "design-contract.json")
        self.assertEqual(errors, [])
        baseline_j2 = next(
            item for item in next(record for record in baseline.analyses if record["analysis_id"] == "AN-ARM-LOAD-ENVELOPE")["outputs"]["joints"]
            if item["id"] == "joint_2"
        )["maximum_gravity_torque_nm"]
        data["quantities"] = [
            {**item, "value": {"value": 8.0, "unit": "kg"}}
            if item["id"] == "Q-LE-L3-MASS" else item
            for item in data["quantities"]
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for source_name in ("robot.urdf", "assumptions.json"):
                (temp / source_name).write_bytes((REFERENCE / source_name).read_bytes())
            (temp / "model").mkdir()
            (temp / "model" / "load-envelope.json").write_bytes(
                (REFERENCE / "model" / "load-envelope.json").read_bytes()
            )
            contract = temp / "design-contract.json"
            contract.write_text(json.dumps(data), encoding="utf-8")
            heavier, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        heavier_j2 = next(
            item for item in next(record for record in heavier.analyses if record["analysis_id"] == "AN-ARM-LOAD-ENVELOPE")["outputs"]["joints"]
            if item["id"] == "joint_2"
        )["maximum_gravity_torque_nm"]
        self.assertGreater(heavier_j2, baseline_j2)

    def test_all_critical_faults_are_rejected_by_expected_gate(self):
        baseline = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        fault_paths = sorted((REFERENCE / "faults").glob("*.json"))
        expected_ids = {
            "missing-traction-motor", "missing-reducer", "missing-wheel",
            "missing-bearing", "missing-motor-driver", "missing-battery",
            "missing-bms", "missing-main-protection", "missing-contactor",
            "missing-dc-converter", "missing-arm-motor", "missing-brake",
            "missing-cable", "missing-connector", "missing-strain-relief",
            "missing-cable-management", "negative-base-mass", "zero-wheel-radius",
            "efficiency-over-one", "insufficient-continuous-torque",
            "motor-overspeed", "insufficient-continuous-current",
            "insufficient-peak-current", "insufficient-energy",
            "com-outside-support", "arm-torque-overload",
            "brake-holding-overload", "stale-artifact-hash", "base-mass-drift",
            "joint-limit-drift", "thermal-over-temperature", "slope-tip-over",
        }
        actual_ids = {
            json.loads(path.read_text(encoding="utf-8"))["id"] for path in fault_paths
        }
        self.assertEqual(len(fault_paths), 32)
        self.assertEqual(actual_ids, expected_ids)
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

    def test_driven_wheel_count_matches_explicit_left_right_responsibilities(self):
        data = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        quantity = next(
            item for item in data["quantities"] if item["id"] == "Q-DRIVEN-WHEELS"
        )
        quantity["value"] = {"value": 1, "unit": "1"}
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for source_name in ("robot.urdf", "assumptions.json"):
                (temp / source_name).write_bytes((REFERENCE / source_name).read_bytes())
            contract = temp / "design-contract.json"
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertTrue(
            any(item.code == "PHY.DRIVE.CARDINALITY_MISMATCH" for item in report.diagnostics)
        )

    def test_every_drive_and_arm_actuator_requires_thermal_coverage(self):
        data = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        data["analyses"] = [
            item for item in data["analyses"] if item["plugin"] != "thermal_duty_v1"
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for source_name in ("robot.urdf", "assumptions.json"):
                (temp / source_name).write_bytes((REFERENCE / source_name).read_bytes())
            contract = temp / "design-contract.json"
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        missing = {
            item.message
            for item in report.diagnostics
            if item.code == "PHY.ANALYSIS.MISSING_COVERAGE"
        }
        for responsibility in ("drive:left", "drive:right", *(f"actuator:joint_{i}" for i in range(1, 7))):
            self.assertIn(
                f"{responsibility} requires analysis thermal_duty_v1", missing
            )

    def test_drive_analysis_rating_must_be_owned_by_covered_motor(self):
        data = json.loads(
            (REFERENCE / "design-contract.json").read_text(encoding="utf-8")
        )
        drive = next(item for item in data["analyses"] if item["id"] == "AN-DRIVE-R")
        drive["inputs"]["motor_continuous_torque_nm"] = "quantity:Q-MOTOR-CONTINUOUS-TORQUE-L"
        drive["covers"].append("actuator:joint_1")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for source_name in ("robot.urdf", "assumptions.json"):
                (temp / source_name).write_bytes((REFERENCE / source_name).read_bytes())
            contract = temp / "design-contract.json"
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertTrue(
            any(item.code == "PHY.ANALYSIS.RATING_OWNER" for item in report.diagnostics)
        )


if __name__ == "__main__":
    unittest.main()
