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
from assurance.engine import _analysis_rating_owner_diagnostics  # noqa: E402
from assurance.plugin_contracts import validate_plugin_inputs  # noqa: E402


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


def load_envelope_quantities():
    dimensions = {
        "Q-LENGTH": "length",
        "Q-ANGLE": "angle",
        "Q-AXIS": "dimensionless",
        "Q-MASS": "mass",
        "Q-GRAVITY": "acceleration",
        "Q-TORQUE": "torque",
        "Q-FACTOR": "dimensionless",
    }
    return {name: {"id": name, "dimension": dimension} for name, dimension in dimensions.items()}


def valid_load_envelope_inputs():
    return {
        "joint_order": ["joint_1"],
        "joints": [
            {
                "id": "joint_1",
                "parent": "base_link",
                "child": "arm_link_1",
                "origin_xyz_m": ["quantity:Q-LENGTH"] * 3,
                "origin_rpy_rad": ["quantity:Q-ANGLE"] * 3,
                "axis_xyz": ["quantity:Q-AXIS", "quantity:Q-AXIS", "quantity:Q-AXIS"],
            }
        ],
        "links": [
            {
                "id": "arm_link_1",
                "mass_kg": "quantity:Q-MASS",
                "com_xyz_m": ["quantity:Q-LENGTH"] * 3,
            }
        ],
        "payload": {
            "mass_kg": "quantity:Q-MASS",
            "parent": "arm_link_1",
            "origin_xyz_m": ["quantity:Q-LENGTH"] * 3,
        },
        "load_cases": [
            {
                "id": "LC-HORIZONTAL",
                "joint_positions_rad": ["quantity:Q-ANGLE"],
                "gravity_xyz_m_s2": ["quantity:Q-GRAVITY"] * 3,
            }
        ],
        "continuous_safety_factor": "quantity:Q-FACTOR",
        "brake_safety_factor": "quantity:Q-FACTOR",
        "rated_continuous_torque_nm": [
            {"id": "joint_1", "value": "quantity:Q-TORQUE"}
        ],
        "brake_holding_torque_nm": [
            {"id": "joint_1", "value": "quantity:Q-TORQUE"}
        ],
        "motor_continuous_torque_nm": [
            {"id": "joint_1", "value": "quantity:Q-TORQUE"}
        ],
        "reducer_gear_ratio": [
            {"id": "joint_1", "value": "quantity:Q-FACTOR"}
        ],
        "reducer_efficiency": [
            {"id": "joint_1", "value": "quantity:Q-FACTOR"}
        ],
    }


class AssuranceContractTests(unittest.TestCase):
    def test_bearing_static_inputs_are_closed_and_dimensioned(self):
        quantities = {
            "Q-R": {"dimension": "force"}, "Q-A": {"dimension": "force"},
            "Q-M": {"dimension": "torque"}, "Q-D": {"dimension": "length"},
            "Q-C0": {"dimension": "force"}, "Q-SF": {"dimension": "dimensionless"},
        }
        valid = {"joints": [{"id": "joint_2", "radial_load_n": "quantity:Q-R", "axial_load_n": "quantity:Q-A", "moment_nm": "quantity:Q-M", "pitch_diameter_m": "quantity:Q-D", "static_load_rating_n": "quantity:Q-C0", "safety_factor": "quantity:Q-SF"}]}
        self.assertEqual([], validate_plugin_inputs("bearing_static_v1", valid, quantities, "inputs"))
        invalid = {"joints": [{**valid["joints"][0], "moment_nm": "quantity:Q-R"}]}
        self.assertTrue(validate_plugin_inputs("bearing_static_v1", invalid, quantities, "inputs"))

    def test_arm_load_envelope_output_ratings_bind_to_the_named_reducers(self):
        data = {
            "architecture": {"actuators": ["joint_1", "joint_2"], "drive_units": []},
            "quantities": [
                {"id": "Q-M1", "owner": "component:CMP-R1"},
                {"id": "Q-B1", "owner": "component:CMP-B1"},
                {"id": "Q-M2", "owner": "component:CMP-R2"},
                {"id": "Q-B2", "owner": "component:CMP-B2"},
                {"id": "Q-MOTOR1", "owner": "component:CMP-M1"},
                {"id": "Q-MOTOR2", "owner": "component:CMP-M2"},
                {"id": "Q-RATIO1", "owner": "component:CMP-R1"},
                {"id": "Q-RATIO2", "owner": "component:CMP-R2"},
                {"id": "Q-EFF1", "owner": "component:CMP-R1"},
                {"id": "Q-EFF2", "owner": "component:CMP-R2"},
            ],
            "components": [
                {"id": "CMP-R1", "role": "reducer", "state": "engineering_placeholder", "bindings": ["actuator:joint_1"]},
                {"id": "CMP-B1", "role": "brake", "state": "engineering_placeholder", "bindings": ["actuator:joint_1"]},
                {"id": "CMP-R2", "role": "reducer", "state": "engineering_placeholder", "bindings": ["actuator:joint_2"]},
                {"id": "CMP-B2", "role": "brake", "state": "engineering_placeholder", "bindings": ["actuator:joint_2"]},
                {"id": "CMP-M1", "role": "motor", "state": "engineering_placeholder", "bindings": ["actuator:joint_1"]},
                {"id": "CMP-M2", "role": "motor", "state": "engineering_placeholder", "bindings": ["actuator:joint_2"]},
            ],
            "analyses": [
                {
                    "plugin": "arm_load_envelope_v1",
                    "covers": ["actuator:joint_1", "actuator:joint_2"],
                    "inputs": {
                        "rated_continuous_torque_nm": [
                            {"id": "joint_1", "value": "quantity:Q-M1"},
                            {"id": "joint_2", "value": "quantity:Q-M2"},
                        ],
                        "brake_holding_torque_nm": [
                            {"id": "joint_1", "value": "quantity:Q-B1"},
                            {"id": "joint_2", "value": "quantity:Q-B2"},
                        ],
                        "motor_continuous_torque_nm": [
                            {"id": "joint_1", "value": "quantity:Q-MOTOR1"},
                            {"id": "joint_2", "value": "quantity:Q-MOTOR2"},
                        ],
                        "reducer_gear_ratio": [
                            {"id": "joint_1", "value": "quantity:Q-RATIO1"},
                            {"id": "joint_2", "value": "quantity:Q-RATIO2"},
                        ],
                        "reducer_efficiency": [
                            {"id": "joint_1", "value": "quantity:Q-EFF1"},
                            {"id": "joint_2", "value": "quantity:Q-EFF2"},
                        ],
                    },
                }
            ],
        }
        self.assertEqual(_analysis_rating_owner_diagnostics(data), [])
        data["analyses"][0]["inputs"]["rated_continuous_torque_nm"][1]["value"] = "quantity:Q-M1"
        self.assertIn(
            "PHY.ANALYSIS.RATING_OWNER",
            {item.code for item in _analysis_rating_owner_diagnostics(data)},
        )
        data["analyses"][0]["inputs"]["rated_continuous_torque_nm"][1]["value"] = "quantity:Q-M2"
        data["analyses"][0]["inputs"]["motor_continuous_torque_nm"][1]["value"] = "quantity:Q-MOTOR1"
        self.assertIn(
            "PHY.ANALYSIS.RATING_OWNER",
            {item.code for item in _analysis_rating_owner_diagnostics(data)},
        )

    def test_arm_load_envelope_has_closed_dimensioned_inputs(self):
        self.assertEqual(
            validate_plugin_inputs(
                "arm_load_envelope_v1",
                valid_load_envelope_inputs(),
                load_envelope_quantities(),
                "analyses[0].inputs",
            ),
            [],
        )

    def test_arm_load_envelope_requires_closed_motor_transmission_records(self):
        value = valid_load_envelope_inputs()
        value.update(
            {
                "motor_continuous_torque_nm": [
                    {"id": "joint_1", "value": "quantity:Q-TORQUE"}
                ],
                "reducer_gear_ratio": [
                    {"id": "joint_1", "value": "quantity:Q-FACTOR"}
                ],
                "reducer_efficiency": [
                    {"id": "joint_1", "value": "quantity:Q-FACTOR"}
                ],
            }
        )
        quantities = load_envelope_quantities()
        self.assertEqual(
            [],
            validate_plugin_inputs("arm_load_envelope_v1", value, quantities, "inputs"),
        )

        value["reducer_efficiency"] = []
        errors = validate_plugin_inputs("arm_load_envelope_v1", value, quantities, "inputs")
        self.assertTrue(any("reducer_efficiency" in error for error in errors))

        value["reducer_efficiency"] = [
            {"id": "joint_1", "value": "quantity:Q-MASS"}
        ]
        errors = validate_plugin_inputs("arm_load_envelope_v1", value, quantities, "inputs")
        self.assertTrue(any("expects dimension dimensionless" in error for error in errors))

    def test_arm_load_envelope_rejects_shape_identity_and_dimension_errors(self):
        quantities = load_envelope_quantities()
        cases = {
            "unknown": lambda value: value.update(extra=True),
            "wrong-dimension": lambda value: quantities["Q-MASS"].update(dimension="length"),
            "duplicate-joint": lambda value: value.update(joint_order=["joint_1", "joint_1"]),
            "missing-rating": lambda value: value.update(brake_holding_torque_nm=[]),
            "not-chain": lambda value: value["joints"][0].update(parent="arm_link_9"),
            "wrong-case-count": lambda value: value["load_cases"][0].update(joint_positions_rad=[]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                value = valid_load_envelope_inputs()
                mutate(value)
                errors = validate_plugin_inputs(
                    "arm_load_envelope_v1", value, quantities, "analyses[0].inputs"
                )
                self.assertTrue(errors)

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
                "supports_claims": ["REQ-PAYLOAD"],
            }
        )
        data["quantities"][2]["owner"] = f"component:{component['id']}"
        data["quantities"][2]["evidence_level"] = "parsed"
        data["evidence"][0]["kind"] = "component_catalog_v1"
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

    def test_verified_reducer_accepts_only_a_dimensioned_output_torque_limit(self):
        data = valid_contract()
        component = data["components"][0]
        component.update(
            {
                "role": "reducer",
                "state": "verified_part",
                "manufacturer": "Example Motion",
                "part_number": "R-100",
                "source_url": "https://example.com/R-100",
                "source_date": "2026-08-14",
                "source_evidence": "evidence:EV-URDF",
                "limits": {"continuous_output_torque": "quantity:Q-RATING"},
                "supports_claims": ["REQ-PAYLOAD"],
            }
        )
        rating = data["quantities"][2]
        rating["owner"] = f"component:{component['id']}"
        rating["evidence_level"] = "parsed"
        data["evidence"][0]["kind"] = "component_catalog_v1"
        data["evidence"][0]["locator"] = component["source_url"]
        data["evidence"][0]["observed_date"] = component["source_date"]
        data["evidence"][0]["supports"] = list(
            dict.fromkeys(
                [
                    *data["evidence"][0]["supports"],
                    f"quantity:{rating['id']}",
                    f"component:{component['id']}",
                ]
            )
        )
        self.assertEqual([], validate_contract(data))

        component["limits"] = {"continuous_output_torque": "quantity:Q-PAYLOAD"}
        self.assertTrue(
            any("expects dimension torque" in error for error in validate_contract(data))
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
        self.assertTrue(any("parsed or certified provenance" in error for error in errors))

        data["evidence"][0]["level"] = "parsed"
        data["evidence"][0]["locator"] = "https://example.com/another-part"
        errors = validate_contract(data)
        self.assertTrue(any("locator must match component source_url" in error for error in errors))

        data["evidence"][0]["locator"] = component["source_url"]
        data["evidence"][0]["observed_date"] = "2026-08-12"
        errors = validate_contract(data)
        self.assertTrue(any("observed_date must match component source_date" in error for error in errors))

    def test_verified_component_requires_claim_edge_and_catalog_provenance(self):
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
        errors = validate_contract(data)
        self.assertTrue(any("supports_claims must be a non-empty" in error for error in errors))
        self.assertTrue(any("source evidence kind must be component_catalog_v1" in error for error in errors))
        self.assertTrue(any("limit quantity evidence_level must be parsed or certified" in error for error in errors))

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
