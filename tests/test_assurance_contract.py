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
            },
            {
                "id": "Q-LEVER",
                "dimension": "length",
                "value": {"value": 0.5, "unit": "m"},
                "owner": "project:system",
                "source": "evidence:EV-URDF",
                "evidence_level": "assumed",
            },
            {
                "id": "Q-RATING",
                "dimension": "torque",
                "value": {"value": 100.0, "unit": "N*m"},
                "owner": "project:system",
                "source": "evidence:EV-URDF",
                "evidence_level": "assumed",
            },
            {
                "id": "Q-BRAKE",
                "dimension": "torque",
                "value": {"value": 100.0, "unit": "N*m"},
                "owner": "project:system",
                "source": "evidence:EV-URDF",
                "evidence_level": "assumed",
            },
            {
                "id": "Q-SAFETY",
                "dimension": "dimensionless",
                "value": {"value": 1.5, "unit": "1"},
                "owner": "project:system",
                "source": "evidence:EV-URDF",
                "evidence_level": "assumed",
            },
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
            "drive_units": ["left", "right"],
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
                "covers": ["requirement:REQ-PAYLOAD"],
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
                            "safety_factor": "quantity:Q-SAFETY",
                        }
                    ]
                },
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
                "locator": "https://example.com/M-100",
                "observed_date": "2026-08-13",
                "supports": [
                    "quantity:Q-PAYLOAD",
                    "quantity:Q-LEVER",
                    "quantity:Q-RATING",
                    "quantity:Q-BRAKE",
                    "quantity:Q-SAFETY",
                ],
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

    def test_component_claim_support_must_reference_declared_requirement(self):
        data = valid_contract()
        data["components"][0]["supports_claims"] = ["REQ-MISSING"]
        self.assertIn(
            "components[0].supports_claims references unknown requirement: REQ-MISSING",
            validate_contract(data),
        )

    def test_verified_component_limits_are_owned_quantity_references(self):
        data = valid_contract()
        component = data["components"][0]
        component.update(
            {
                "state": "verified_part",
                "manufacturer": "Example Robotics",
                "part_number": "M-100",
                "source_url": "https://example.com/M-100",
                "source_date": "2026-08-13",
                "source_evidence": "evidence:EV-URDF",
                "limits": {"continuous_torque": "quantity:Q-RATING"},
            }
        )
        data["quantities"][2]["owner"] = f"component:{component['id']}"
        data["evidence"][0]["supports"].append(f"component:{component['id']}")
        self.assertEqual(validate_contract(data), [])

        component["limits"] = {"continuous_torque": {"value": float("nan")}}
        self.assertTrue(
            any("limits.continuous_torque must reference a quantity" in error for error in validate_contract(data))
        )

        component["limits"] = {"magic_rating": "quantity:Q-RATING"}
        self.assertTrue(
            any("limits has unsupported fields for role traction_motor: magic_rating" in error for error in validate_contract(data))
        )

    def test_verified_component_source_url_and_date_are_closed(self):
        data = valid_contract()
        component = data["components"][0]
        component.update(
            {
                "state": "verified_part",
                "manufacturer": "Example Robotics",
                "part_number": "M-100",
                "source_url": "remembered catalog",
                "source_date": "soon",
                "source_evidence": "evidence:EV-URDF",
                "limits": {"continuous_torque": "quantity:Q-RATING"},
            }
        )
        data["quantities"][2]["owner"] = f"component:{component['id']}"
        errors = validate_contract(data)
        self.assertTrue(any("source_url must be an absolute HTTP(S) URL" in error for error in errors))
        self.assertTrue(any("source_date must be an ISO calendar date" in error for error in errors))

    def test_verified_component_requires_hash_bound_supporting_evidence(self):
        data = valid_contract()
        component = data["components"][0]
        component.update(
            {
                "state": "verified_part",
                "manufacturer": "Example Robotics",
                "part_number": "M-100",
                "source_url": "https://example.com/M-100",
                "source_date": "2026-08-13",
                "limits": {"continuous_torque": "quantity:Q-RATING"},
            }
        )
        data["quantities"][2]["owner"] = f"component:{component['id']}"
        errors = validate_contract(data)
        self.assertTrue(any("source_evidence must reference" in error for error in errors))

        component["source_evidence"] = "evidence:EV-URDF"
        errors = validate_contract(data)
        self.assertTrue(any("does not support component:" in error for error in errors))

        data["evidence"][0]["supports"].append(f"component:{component['id']}")
        data["evidence"][0]["level"] = "assumed"
        errors = validate_contract(data)
        self.assertTrue(any("must be parsed or stronger" in error for error in errors))

        data["evidence"][0]["level"] = "parsed"
        data["evidence"][0]["locator"] = "https://example.com/another-part"
        errors = validate_contract(data)
        self.assertTrue(any("locator must match component source_url" in error for error in errors))

        data["evidence"][0]["locator"] = component["source_url"]
        data["evidence"][0]["observed_date"] = "2026-08-12"
        errors = validate_contract(data)
        self.assertTrue(any("observed_date must match component source_date" in error for error in errors))

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
        self.assertEqual(validate_contract(data), [])

    def test_every_known_plugin_rejects_wrong_quantity_dimensions(self):
        reference = json.loads(
            (ROOT / "reference" / "mobile-manipulator" / "design-contract.json").read_text(
                encoding="utf-8"
            )
        )
        selected_fields = {
            "drivetrain_v1": ("wheel_radius_m",),
            "battery_v1": ("voltage_v",),
            "stability_v1": ("com_height_m",),
            "arm_gravity_v1": ("joints", 0, "rated_continuous_torque_nm"),
            "thermal_duty_v1": ("ambient_temperature_k",),
        }
        for analysis in reference["analyses"]:
            plugin = analysis["plugin"]
            if plugin not in selected_fields:
                continue
            with self.subTest(plugin=plugin):
                value = analysis["inputs"]
                for part in selected_fields[plugin]:
                    value = value[part]
                quantity_id = value.removeprefix("quantity:")
                quantity = next(
                    item for item in reference["quantities"] if item["id"] == quantity_id
                )
                original_dimension = quantity["dimension"]
                original_value = copy.deepcopy(quantity["value"])
                quantity["dimension"] = "mass"
                quantity["value"] = {"value": 1.0, "unit": "kg"}
                errors = validate_contract(reference)
                self.assertTrue(
                    any(
                        plugin in error
                        and f"expects dimension {original_dimension}" in error
                        for error in errors
                    ),
                    errors,
                )
                quantity["dimension"] = original_dimension
                quantity["value"] = original_value

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

            path.write_bytes(b"\xff\xfe")
            loaded, errors = load_contract(path)
            self.assertIsNone(loaded)
            self.assertTrue(errors[0].startswith("contract is not valid UTF-8:"))


if __name__ == "__main__":
    unittest.main()
