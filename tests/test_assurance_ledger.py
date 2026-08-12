import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.ledger import required_roles, validate_ledger  # noqa: E402
from tests.test_assurance_contract import valid_contract  # noqa: E402


def component(component_id, role, state="engineering_placeholder", **extra):
    record = {
        "id": component_id,
        "role": role,
        "state": state,
        "interfaces": [f"IF-{component_id}"],
        "bindings": [],
    }
    record.update(extra)
    return record


class AssuranceLedgerTests(unittest.TestCase):
    def test_architecture_features_infer_mandatory_roles(self):
        roles = required_roles(
            {
                "features": ["differential_drive", "battery_powered"],
                "actuators": [],
                "moving_cables": [],
                "claimed_safety_functions": ["holding_brake"],
            }
        )
        self.assertIn("reducer", roles["feature:differential_drive"])
        self.assertIn("bms", roles["feature:battery_powered"])
        self.assertEqual(roles["safety_function:holding_brake"], {"brake"})

    def test_missing_reducer_bms_and_strain_relief_are_errors(self):
        data = valid_contract()
        data["architecture"]["moving_cables"] = ["arm-harness"]
        data["components"] = [
            component("MOTOR-L", "traction_motor"),
            component("WHEEL-L", "wheel"),
            component("BEARING-L", "bearing"),
            component("DRIVER-L", "motor_driver"),
            component("BATTERY", "battery"),
            component("PROTECTION", "main_protection"),
            component("CONTACTOR", "contactor"),
            component("CONVERTER", "dc_converter"),
            component("CABLE", "cable"),
            component("CONNECTOR", "connector"),
            component("CABLE-MGMT", "cable_management"),
        ]
        diagnostics = validate_ledger(data)
        missing = {item.message for item in diagnostics if item.code == "BOM.MISSING_ROLE"}
        self.assertTrue(any("reducer" in message for message in missing))
        self.assertTrue(any("bms" in message for message in missing))
        self.assertTrue(any("strain_relief" in message for message in missing))

    def test_verified_part_requires_exact_source_identity(self):
        data = valid_contract()
        data["architecture"]["features"] = []
        data["components"] = [component("MOTOR", "motor", "verified_part")]
        diagnostics = validate_ledger(data)
        self.assertTrue(
            any(item.code == "BOM.UNVERIFIED_PART" for item in diagnostics)
        )

    def test_complete_verified_part_has_no_identity_error(self):
        data = valid_contract()
        data["architecture"]["features"] = []
        data["components"] = [
            component(
                "MOTOR",
                "motor",
                "verified_part",
                manufacturer="Example Robotics",
                part_number="M-100",
                source_url="https://example.invalid/M-100",
                source_date="2026-08-13",
                limits={"continuous_torque": {"value": 1, "unit": "N*m"}},
            )
        ]
        diagnostics = validate_ledger(data)
        self.assertFalse(
            any(item.code == "BOM.UNVERIFIED_PART" for item in diagnostics)
        )

    def test_placeholder_cannot_support_promoted_claim(self):
        data = valid_contract()
        data["architecture"]["features"] = []
        data["components"][0]["supports_claims"] = ["REQ-PAYLOAD"]
        diagnostics = validate_ledger(data)
        self.assertTrue(
            any(
                item.code == "BOM.PLACEHOLDER_BLOCKS_CLAIM"
                for item in diagnostics
            )
        )

    def test_duplicate_component_id_and_interface_are_reported(self):
        data = valid_contract()
        data["architecture"]["features"] = []
        duplicate = copy.deepcopy(data["components"][0])
        data["components"].append(duplicate)
        diagnostics = validate_ledger(data)
        codes = {item.code for item in diagnostics}
        self.assertIn("BOM.DUPLICATE_ID", codes)
        self.assertIn("BOM.UNBOUND_INTERFACE", codes)

    def test_each_actuator_requires_its_own_motor_transmission_and_bearing(self):
        data = valid_contract()
        data["architecture"]["features"] = []
        data["architecture"]["actuators"] = ["joint_1", "joint_2"]
        data["components"] = [
            component(
                "MOTOR",
                "motor",
                bindings=["actuator:joint_1", "actuator:joint_2"],
            ),
            component("REDUCER", "reducer", bindings=["actuator:joint_1"]),
            component("BEARING", "bearing", bindings=["actuator:joint_1"]),
            component(
                "DRIVER",
                "motor_driver",
                bindings=["actuator:joint_1", "actuator:joint_2"],
            ),
        ]
        diagnostics = validate_ledger(data)
        messages = {item.message for item in diagnostics}
        self.assertTrue(any("actuator:joint_2" in item and "reducer" in item for item in messages))
        self.assertTrue(any("actuator:joint_2" in item and "bearing" in item for item in messages))
        self.assertTrue(
            any(item.code == "BOM.MULTI_ACTUATOR_COMPONENT" for item in diagnostics)
        )


if __name__ == "__main__":
    unittest.main()
