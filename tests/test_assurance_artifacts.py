import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.artifacts import compare_observations, observe_declared_json, observe_urdf  # noqa: E402
from tests.test_assurance_contract import valid_contract  # noqa: E402


VALID_URDF = """<?xml version="1.0"?>
<robot name="reference">
  <link name="base">
    <inertial>
      <origin xyz="0 0 0.1" rpy="0 0 0"/>
      <mass value="100"/>
      <inertia ixx="10" ixy="0" ixz="0" iyy="11" iyz="0" izz="12"/>
    </inertial>
  </link>
  <link name="arm_link"/>
  <joint name="joint_1" type="revolute">
    <parent link="base"/>
    <child link="arm_link"/>
    <origin xyz="0 0 0.4" rpy="0 0 0"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1.5" upper="1.5" effort="100" velocity="2"/>
  </joint>
  <transmission name="joint_1_transmission">
    <type>transmission_interface/SimpleTransmission</type>
    <joint name="joint_1"/>
    <actuator name="joint_1_motor"/>
  </transmission>
</robot>
"""


class AssuranceArtifactTests(unittest.TestCase):
    def _write(self, root, text=VALID_URDF):
        path = root / "robot.urdf"
        path.write_text(text, encoding="utf-8")
        return path

    def test_urdf_observation_extracts_owned_physical_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            observation, diagnostics = observe_urdf(
                self._write(Path(temp_dir))
            )
        self.assertEqual(diagnostics, [])
        self.assertEqual(observation["robot_name"], "reference")
        self.assertEqual(observation["links"]["base"]["mass_kg"], 100.0)
        self.assertEqual(
            observation["links"]["base"]["inertia_kg_m2"]["izz"], 12.0
        )
        self.assertEqual(observation["joints"]["joint_1"]["axis"], [0.0, 0.0, 1.0])
        self.assertEqual(observation["joints"]["joint_1"]["limit"]["upper"], 1.5)
        self.assertEqual(observation["transmission_joints"], ["joint_1"])

    def test_urdf_rejects_dtd_entity_and_malformed_numbers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unsafe = '<!DOCTYPE robot [<!ENTITY x "bad">]><robot name="x"/>'
            observation, diagnostics = observe_urdf(self._write(root, unsafe))
            self.assertIsNone(observation)
            self.assertEqual(diagnostics[0].code, "ARTIFACT.XML_UNSAFE")

            malformed = VALID_URDF.replace('value="100"', 'value="nan"')
            observation, diagnostics = observe_urdf(self._write(root, malformed))
            self.assertIsNone(observation)
            self.assertTrue(any(item.code == "ARTIFACT.NUMBER" for item in diagnostics))

    def test_owned_quantity_detects_mass_drift_and_honors_tolerance(self):
        data = valid_contract()
        quantity = data["quantities"][0]
        quantity.update(
            {
                "value": {"value": 99.0, "unit": "kg"},
                "observation": "artifact:robot-model#links.base.mass_kg",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            observation, diagnostics = observe_urdf(self._write(Path(temp_dir)))
        self.assertEqual(diagnostics, [])
        findings = compare_observations(data, {"robot-model": observation})
        self.assertTrue(any(item.code == "DRIFT.VALUE" for item in findings))

        quantity["tolerance"] = {"value": 1.1, "unit": "kg"}
        findings = compare_observations(data, {"robot-model": observation})
        self.assertFalse(any(item.code == "DRIFT.VALUE" for item in findings))

    def test_declared_json_adapter_supports_bounded_cross_artifact_observations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bom-observations.json"
            path.write_text(
                json.dumps({"components": {"motor": {"continuous_torque_nm": 2.0}}}),
                encoding="utf-8",
            )
            observation, diagnostics = observe_declared_json(path)
            self.assertEqual(diagnostics, [])
            self.assertEqual(
                observation["components"]["motor"]["continuous_torque_nm"], 2.0
            )

            path.write_text('{"x": NaN}', encoding="utf-8")
            observation, diagnostics = observe_declared_json(path)
            self.assertIsNone(observation)
            self.assertTrue(any(item.code == "ARTIFACT.JSON" for item in diagnostics))

    def test_joint_limit_drift_and_missing_observation_are_reported(self):
        data = valid_contract()
        data["quantities"] = [
            {
                "id": "Q-J1-UPPER",
                "dimension": "angle",
                "value": {"value": 1.0, "unit": "rad"},
                "owner": "artifact:robot-model",
                "source": "evidence:EV-URDF",
                "evidence_level": "parsed",
                "observation": "artifact:robot-model#joints.joint_1.limit.upper",
            },
            {
                "id": "Q-MISSING",
                "dimension": "mass",
                "value": {"value": 1.0, "unit": "kg"},
                "owner": "artifact:robot-model",
                "source": "evidence:EV-URDF",
                "evidence_level": "parsed",
                "observation": "artifact:robot-model#links.missing.mass_kg",
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            observation, _ = observe_urdf(self._write(Path(temp_dir)))
        findings = compare_observations(data, {"robot-model": observation})
        codes = {item.code for item in findings}
        self.assertIn("DRIFT.VALUE", codes)
        self.assertIn("DRIFT.MISSING", codes)

    def test_actuated_joint_requires_urdf_transmission(self):
        data = valid_contract()
        data["architecture"]["actuators"] = ["joint_1"]
        with tempfile.TemporaryDirectory() as temp_dir:
            observation, _ = observe_urdf(self._write(Path(temp_dir)))
        missing = copy.deepcopy(observation)
        missing["transmission_joints"] = []
        findings = compare_observations(data, {"robot-model": missing})
        self.assertTrue(
            any(item.code == "DRIFT.MISSING_TRANSMISSION" for item in findings)
        )


if __name__ == "__main__":
    unittest.main()
