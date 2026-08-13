import json
import math
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.simulation.schema import load_simulation_contract, validate_simulation_contract  # noqa: E402


SHA_A = "a" * 64
SHA_B = "b" * 64
CANDIDATE = "candidate-" + "1" * 24


def valid_contract():
    return {
        "schema_version": 1,
        "contract_id": "simulation-reference-v1",
        "candidate_id": CANDIDATE,
        "resolved_contract_sha256": SHA_A,
        "environment": {
            "environment_id": "environment-jazzy-harmonic",
            "image_digest": SHA_B,
            "ros_distro": "jazzy",
            "gazebo_version": "harmonic-8.9.0",
            "physics_engine": "dartsim",
            "parameters": {"max_step_size_s": 0.001, "solver_iterations": 50},
            "package_versions": {"gz-sim": "8.9.0"},
        },
        "max_scenarios": 32,
        "max_trace_samples": 10000,
        "max_trace_bytes": 10_000_000,
        "artifacts": [
            {
                "artifact_id": "artifact-urdf",
                "kind": "urdf",
                "path": "ros2_ws/src/description/robot.urdf.xacro",
                "sha256": SHA_A,
                "source_sha256": SHA_B,
                "consumer": "robot-state-publisher",
                "observations": {"robot_name": "reference_mobile_manipulator"},
            }
        ],
        "scenarios": [
            {
                "scenario_id": "scenario-nominal",
                "version": "v1",
                "model_sha256": SHA_A,
                "trajectory_sha256": SHA_B,
                "environment_sha256": SHA_A,
                "seed": 17,
                "duration_ns": 1_000_000_000,
                "joint_order": ["joint_1"],
                "parameters": {"payload_kg": 5.0},
                "faults": [{"fault_id": "fault-none", "at_ns": 0}],
            }
        ],
    }


class SimulationSchemaTests(unittest.TestCase):
    def test_valid_contract_is_closed_and_bounded(self):
        data = valid_contract()
        self.assertEqual(validate_simulation_contract(data), [])
        data["extra"] = True
        self.assertIn("root has unknown fields: extra", validate_simulation_contract(data))

    def test_nested_records_require_exact_fields(self):
        for key, selector in (
            ("image_digest", lambda data: data["environment"]),
            ("sha256", lambda data: data["artifacts"][0]),
            ("duration_ns", lambda data: data["scenarios"][0]),
        ):
            data = valid_contract()
            record = selector(data)
            del record[key]
            record["extra"] = 1
            errors = validate_simulation_contract(data)
            self.assertTrue(any("is missing fields" in item for item in errors), errors)
            self.assertTrue(any("has unknown fields: extra" in item for item in errors), errors)

    def test_paths_hashes_identifiers_and_budgets_are_validated(self):
        cases = (
            lambda data: data["artifacts"][0].__setitem__("path", "../escape"),
            lambda data: data["artifacts"][0].__setitem__("path", "C" + ":/private"),
            lambda data: data["environment"].__setitem__("image_digest", "A" * 64),
            lambda data: data.__setitem__("candidate_id", "candidate-short"),
            lambda data: data.__setitem__("max_scenarios", True),
            lambda data: data.__setitem__("max_scenarios", 33),
            lambda data: data.__setitem__("max_trace_samples", 10001),
            lambda data: data.__setitem__("max_trace_bytes", 10_000_001),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                data = valid_contract()
                mutate(data)
                self.assertNotEqual(validate_simulation_contract(data), [])

    def test_duplicate_artifacts_scenarios_joints_and_faults_are_rejected(self):
        data = valid_contract()
        data["artifacts"].append(dict(data["artifacts"][0]))
        self.assertTrue(any("duplicate artifact_id" in item for item in validate_simulation_contract(data)))

        data = valid_contract()
        data["scenarios"].append(json.loads(json.dumps(data["scenarios"][0])))
        self.assertTrue(any("duplicate scenario_id" in item for item in validate_simulation_contract(data)))

        data = valid_contract()
        data["scenarios"][0]["joint_order"] = ["joint_1", "joint_1"]
        self.assertTrue(any("duplicate" in item for item in validate_simulation_contract(data)))

        data = valid_contract()
        data["scenarios"][0]["faults"].append({"fault_id": "fault-none", "at_ns": 1})
        self.assertTrue(any("duplicate fault_id" in item for item in validate_simulation_contract(data)))

    def test_nonfinite_recursive_and_surrogate_values_are_actionable(self):
        data = valid_contract()
        data["environment"]["parameters"]["bad"] = math.nan
        self.assertTrue(any("finite" in item for item in validate_simulation_contract(data)))

        data = valid_contract()
        recursive = []
        recursive.append(recursive)
        data["environment"]["parameters"]["bad"] = recursive
        self.assertTrue(any("cycle" in item for item in validate_simulation_contract(data)))

        data = valid_contract()
        data["artifacts"][0]["observations"]["bad"] = "\ud800"
        self.assertTrue(any("surrogate" in item for item in validate_simulation_contract(data)))

    def _load(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "simulation.json"
            path.write_bytes(payload)
            return load_simulation_contract(path)

    def test_loader_rejects_duplicate_keys_invalid_utf8_depth_and_size(self):
        for payload, expected in (
            (b'{"schema_version":1,"schema_version":1}', "duplicate JSON key"),
            (b'{"bad":"\xff"}', "valid UTF-8"),
            (("[" * 65 + "0" + "]" * 65).encode(), "maximum JSON depth"),
            (b" " * (5 * 1024 * 1024 + 1), "maximum size"),
        ):
            with self.subTest(expected=expected):
                loaded, errors = self._load(payload)
                self.assertIsNone(loaded)
                self.assertTrue(any(expected in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
