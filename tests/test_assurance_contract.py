import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.contract import load_contract, validate_contract  # noqa: E402


def valid_contract():
    return {
        "schema_version": 1,
        "candidate_id": "reference-mm-v0",
        "status": "draft",
        "requirements": [
            {
                "id": "REQ-PAYLOAD",
                "statement": "Carry the declared payload",
                "verification": "AN-ARM-GRAVITY",
                "owner": "project:system",
            }
        ],
        "assumptions": [
            {
                "id": "ASM-PAYLOAD",
                "statement": "Initial payload regression value",
                "confidence": "low",
                "owner": "project:system",
                "validation": "Replace with approved mission requirement",
                "decision_deadline": "engineering-freeze",
            }
        ],
        "quantities": [
            {
                "id": "Q-PAYLOAD",
                "dimension": "mass",
                "value": {"value": 2.0, "unit": "kg"},
                "owner": "artifact:robot-model",
                "source": "evidence:EV-URDF",
                "evidence_level": "assumed",
            }
        ],
        "components": [
            {
                "id": "CMP-BASE-MOTOR-L",
                "role": "traction_motor",
                "state": "engineering_placeholder",
                "interfaces": ["IF-BASE-DRIVE-L"],
                "bindings": ["feature:differential_drive"],
            }
        ],
        "architecture": {
            "features": ["differential_drive", "battery_powered"],
            "actuators": [],
            "moving_cables": [],
            "claimed_safety_functions": [],
        },
        "artifacts": [
            {
                "id": "robot-model",
                "kind": "urdf",
                "path": "robot.urdf",
                "sha256": "0" * 64,
            }
        ],
        "analyses": [
            {
                "id": "AN-ARM-GRAVITY",
                "plugin": "arm_gravity_v1",
                "inputs": {"payload": "quantity:Q-PAYLOAD"},
            }
        ],
        "evidence": [
            {
                "id": "EV-URDF",
                "level": "parsed",
                "source": {
                    "path": "robot.urdf",
                    "sha256": "0" * 64,
                },
                "supports": ["quantity:Q-PAYLOAD"],
            }
        ],
    }


class AssuranceContractTests(unittest.TestCase):
    def test_minimal_contract_is_valid(self):
        self.assertEqual(validate_contract(valid_contract()), [])

    def test_boolean_schema_version_is_rejected(self):
        data = valid_contract()
        data["schema_version"] = True
        self.assertIn("schema_version must be integer 1", validate_contract(data))

    def test_duplicate_ids_are_rejected(self):
        data = valid_contract()
        data["requirements"].append(copy.deepcopy(data["requirements"][0]))
        self.assertTrue(
            any("requirements has duplicate id REQ-PAYLOAD" in error for error in validate_contract(data))
        )

    def test_unknown_owner_is_rejected(self):
        data = valid_contract()
        data["quantities"][0]["owner"] = "artifact:missing"
        self.assertIn(
            "quantities[0].owner references unknown owner: artifact:missing",
            validate_contract(data),
        )

    def test_bare_physical_number_is_rejected(self):
        data = valid_contract()
        data["quantities"][0]["value"] = 2.0
        self.assertTrue(
            any("quantities[0].value" in error and "object with value and unit" in error for error in validate_contract(data))
        )

    def test_vacuous_physical_contract_is_rejected(self):
        data = valid_contract()
        for collection in (
            "requirements",
            "quantities",
            "components",
            "artifacts",
            "analyses",
            "evidence",
        ):
            data[collection] = []
        self.assertIn(
            "physical contract must contain at least one engineering obligation",
            validate_contract(data),
        )

    def test_certified_evidence_requires_external_authority(self):
        data = valid_contract()
        data["evidence"][0]["level"] = "certified"
        errors = validate_contract(data)
        self.assertIn(
            "evidence[0].authority must be a non-empty string for certified evidence",
            errors,
        )
        self.assertIn(
            "evidence[0].certificate_id must be a non-empty string for certified evidence",
            errors,
        )

    def test_quantity_cannot_claim_stronger_level_than_its_source(self):
        data = valid_contract()
        data["quantities"][0]["evidence_level"] = "certified"
        data["evidence"][0]["level"] = "assumed"
        self.assertIn(
            "quantities[0].evidence_level certified exceeds source evidence level assumed",
            validate_contract(data),
        )

    def test_quantity_source_must_explicitly_support_that_quantity(self):
        data = valid_contract()
        data["evidence"][0]["supports"] = ["artifact:robot-model"]
        self.assertIn(
            "quantities[0].source evidence:EV-URDF does not support quantity:Q-PAYLOAD",
            validate_contract(data),
        )

    def test_component_binding_must_reference_declared_architecture(self):
        data = valid_contract()
        data["components"][0]["bindings"] = ["actuator:missing-axis"]
        self.assertIn(
            "components[0].bindings references unknown architecture responsibility: actuator:missing-axis",
            validate_contract(data),
        )

    def test_malformed_architecture_and_supports_are_actionable_not_tracebacks(self):
        data = valid_contract()
        data["architecture"]["actuators"] = None
        data["evidence"][0]["supports"] = [{}]
        errors = validate_contract(data)
        self.assertIn(
            "architecture.actuators must be a list of non-empty strings", errors
        )
        self.assertIn(
            "evidence[0].supports must be a list of non-empty strings", errors
        )

    def test_valid_json_wrong_types_never_raise_tracebacks(self):
        mutations = (
            ("status", lambda data: data.update(status=[])),
            ("requirement owner", lambda data: data["requirements"][0].update(owner=[])),
            ("assumption confidence", lambda data: data["assumptions"][0].update(confidence=[])),
            ("quantity source", lambda data: data["quantities"][0].update(source={})),
            ("component state", lambda data: data["components"][0].update(state=[])),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                data = valid_contract()
                mutate(data)
                errors = validate_contract(data)
                self.assertTrue(errors)

    def test_unknown_fields_are_rejected_in_schema_one(self):
        data = valid_contract()
        data["magic_completion"] = True
        self.assertIn("root has unknown fields: magic_completion", validate_contract(data))

    def test_quantity_may_bind_to_normalized_artifact_observation(self):
        data = valid_contract()
        data["quantities"][0]["observation"] = (
            "artifact:robot-model#links.base.mass_kg"
        )
        self.assertEqual(validate_contract(data), [])

    def test_analysis_inputs_may_nest_quantity_references(self):
        data = valid_contract()
        data["analyses"][0]["inputs"] = {
            "joints": [
                {
                    "id": "joint_2",
                    "loads": [
                        {
                            "mass_kg": "quantity:Q-PAYLOAD",
                            "horizontal_lever_m": "quantity:Q-PAYLOAD",
                        }
                    ],
                }
            ]
        }
        self.assertEqual(validate_contract(data), [])

    def test_load_errors_are_actionable_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text("[]", encoding="utf-8")
            loaded, errors = load_contract(path)
            self.assertEqual(loaded, [])
            self.assertEqual(errors, ["contract root must be a JSON object"])

            path.write_text("{", encoding="utf-8")
            loaded, errors = load_contract(path)
            self.assertIsNone(loaded)
            self.assertTrue(errors[0].startswith("contract is not valid JSON:"))


if __name__ == "__main__":
    unittest.main()
