import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
CLI = SCRIPTS / "validate_design_contract.py"
sys.path.insert(0, str(SCRIPTS))

from assurance.engine import evaluate_contract, serialize_report  # noqa: E402
from tests.test_assurance_contract import valid_contract  # noqa: E402


URDF = """<robot name="engine-fixture">
  <link name="base"><inertial><mass value="2"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>
</robot>
"""


def write_fixture(root, plugin=None):
    robot = root / "robot.urdf"
    robot.write_text(URDF, encoding="utf-8")
    digest = hashlib.sha256(robot.read_bytes()).hexdigest()
    data = valid_contract()
    data["architecture"]["features"] = []
    data["components"] = []
    data["artifacts"][0]["sha256"] = digest
    data["evidence"][0]["source"]["sha256"] = digest
    data["quantities"][0].update(
        {
            "value": {"value": 2, "unit": "kg"},
            "evidence_level": "parsed",
            "observation": "artifact:robot-model#links.base.mass_kg",
        }
    )
    data["analyses"] = []
    if plugin:
        data["analyses"] = [{"id": "AN-X", "plugin": plugin, "inputs": {}}]
    contract = root / "design-contract.json"
    contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return contract, robot


class AssuranceEngineTests(unittest.TestCase):
    def test_valid_evaluation_is_promotable_and_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, _ = write_fixture(Path(temp_dir))
            first, errors = evaluate_contract(contract)
            second, second_errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertEqual(second_errors, [])
        self.assertTrue(first.promotable)
        self.assertEqual(serialize_report(first), serialize_report(second))
        report = json.loads(serialize_report(first))
        self.assertEqual(report["metadata"]["schema_version"], 1)
        self.assertRegex(report["metadata"]["contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["metadata"]["evidence_coverage"], "1/1")
        self.assertEqual(report["metadata"]["minimum_evidence_level"], "parsed")
        self.assertEqual(
            report["metadata"]["evidence_level_counts"], {"parsed": 1}
        )

    def test_changed_artifact_invalidates_hash_bound_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, robot = write_fixture(Path(temp_dir))
            robot.write_text(URDF.replace('value="2"', 'value="3"'), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        codes = {item.code for item in report.diagnostics}
        self.assertIn("EVIDENCE.STALE_ARTIFACT", codes)

    def test_unknown_analysis_plugin_is_indeterminate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, _ = write_fixture(Path(temp_dir), "imaginary_solver")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        self.assertTrue(any(item.code == "PHY.PLUGIN.UNKNOWN" for item in report.diagnostics))

    def test_nested_arm_inputs_resolve_owned_quantities(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract, _ = write_fixture(root)
            data = json.loads(contract.read_text(encoding="utf-8"))
            for quantity_id, dimension, value, unit in (
                ("Q-LEVER", "length", 0.5, "m"),
                ("Q-RATING", "torque", 100.0, "N*m"),
                ("Q-BRAKE", "torque", 100.0, "N*m"),
                ("Q-SF", "dimensionless", 1.5, "1"),
            ):
                data["quantities"].append(
                    {
                        "id": quantity_id,
                        "dimension": dimension,
                        "value": {"value": value, "unit": unit},
                        "owner": "artifact:robot-model",
                        "source": "evidence:EV-URDF",
                        "evidence_level": "assumed",
                    }
                )
                data["evidence"][0]["supports"].append(f"quantity:{quantity_id}")
            data["analyses"] = [
                {
                    "id": "AN-ARM",
                    "plugin": "arm_gravity_v1",
                    "inputs": {
                        "joints": [
                            {
                                "id": "joint_2",
                                "loads": [
                                    {
                                        "mass_kg": "quantity:Q-PAYLOAD",
                                        "horizontal_lever_m": "quantity:Q-LEVER",
                                    }
                                ],
                                "rated_continuous_torque_nm": "quantity:Q-RATING",
                                "brake_holding_torque_nm": "quantity:Q-BRAKE",
                                "safety_factor": "quantity:Q-SF",
                            }
                        ]
                    },
                }
            ]
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertTrue(report.promotable)
        self.assertGreater(
            report.analyses[0]["outputs"]["joints"][0]["gravity_torque_nm"],
            0.0,
        )

    def test_schema_errors_do_not_create_a_physical_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract = Path(temp_dir) / "bad.json"
            contract.write_text("[]", encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertIsNone(report)
        self.assertEqual(errors, ["contract root must be a JSON object"])

    def test_cli_exit_codes_and_report_collision_are_actionable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract, _ = write_fixture(root)
            report_path = root / "evidence.json"
            success = subprocess.run(
                [sys.executable, str(CLI), str(contract), "--report", str(report_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertTrue(report_path.is_file())

            collision = subprocess.run(
                [sys.executable, str(CLI), str(contract), "--report", str(report_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(collision.returncode, 2)
            self.assertIn("report already exists", collision.stderr)
            self.assertNotIn("Traceback", collision.stderr)

            bad = root / "bad.json"
            bad.write_text("{", encoding="utf-8")
            malformed = subprocess.run(
                [sys.executable, str(CLI), str(bad)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("ERROR:", malformed.stderr)
            self.assertNotIn("Traceback", malformed.stderr)


if __name__ == "__main__":
    unittest.main()
