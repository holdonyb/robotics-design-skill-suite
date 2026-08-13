import dataclasses
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis import canonical_bytes  # noqa: E402
from assurance.simulation import (  # noqa: E402
    ArtifactRecord,
    EnvironmentLock,
    MetricResult,
    ScenarioSpec,
    SimulationAdmission,
    SimulationResult,
    TraceSample,
    TrajectoryRecord,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
CANDIDATE = "candidate-" + "1" * 24


class SimulationModelTests(unittest.TestCase):
    def make_environment(self, **overrides):
        values = {
            "environment_id": "environment-jazzy-harmonic",
            "image_digest": SHA_A,
            "ros_distro": "jazzy",
            "gazebo_version": "harmonic-8.9.0",
            "physics_engine": "dartsim",
            "parameters": {"max_step_size_s": 0.001, "solver_iterations": 50},
            "package_versions": {"gz-sim": "8.9.0", "ros2-control": "4.0.0"},
        }
        values.update(overrides)
        return EnvironmentLock(**values)

    def make_artifact(self, **overrides):
        values = {
            "artifact_id": "artifact-robot-urdf",
            "kind": "urdf",
            "path": "ros2_ws/src/description/robot.urdf.xacro",
            "sha256": SHA_A,
            "source_sha256": SHA_B,
            "consumer": "robot-state-publisher",
            "observations": {"robot_name": "reference_mobile_manipulator"},
        }
        values.update(overrides)
        return ArtifactRecord(**values)

    def make_admission(self, **overrides):
        values = {
            "candidate_id": CANDIDATE,
            "resolved_contract_sha256": SHA_A,
            "status": "simulation_admitted",
            "evidence_level": "simulation_admitted",
            "hardware_promotable": False,
            "remaining_blockers": ("BOM.PLACEHOLDER_BLOCKS_CLAIM",),
        }
        values.update(overrides)
        return SimulationAdmission(**values)

    def make_scenario(self, **overrides):
        values = {
            "scenario_id": "scenario-nominal-arm",
            "version": "v1",
            "model_sha256": SHA_A,
            "trajectory_sha256": SHA_B,
            "environment_sha256": SHA_C,
            "seed": 17,
            "duration_ns": 2_000_000_000,
            "joint_order": ("joint_1", "joint_2"),
            "parameters": {"payload_kg": 5.0},
            "faults": ({"fault_id": "fault-none", "at_ns": 0},),
        }
        values.update(overrides)
        return ScenarioSpec(**values)

    def make_trajectory(self, **overrides):
        values = {
            "trajectory_id": "trajectory-arm-home",
            "model_sha256": SHA_A,
            "joint_order": ("joint_1", "joint_2"),
            "sample_period_ns": 10_000_000,
            "positions": ((0.0, 0.0), (0.1, -0.1)),
        }
        values.update(overrides)
        return TrajectoryRecord(**values)

    def make_metric(self, **overrides):
        values = {
            "name": "final_joint_error",
            "unit": "rad",
            "status": "passed",
            "value": 0.001,
            "limit": 0.01,
            "details": {"direction": "max"},
        }
        values.update(overrides)
        return MetricResult(**values)

    def test_records_are_frozen_and_canonical(self):
        records = (
            self.make_environment(),
            self.make_artifact(),
            self.make_admission(),
            self.make_scenario(),
            self.make_trajectory(),
            TraceSample(0, (0.0, 0.0), {"mode": "active"}),
            self.make_metric(),
        )
        for record in records:
            with self.subTest(record=type(record).__name__):
                canonical_bytes(record.to_dict())
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    record.extra = True

        environment = records[0]
        with self.assertRaises(TypeError):
            environment.parameters["max_step_size_s"] = 0.1

    def test_nested_inputs_are_copied_before_freezing(self):
        parameters = {"nested": [1, {"mode": "deterministic"}]}
        environment = self.make_environment(parameters=parameters)
        parameters["nested"][1]["mode"] = "changed"

        self.assertEqual(environment.to_dict()["parameters"]["nested"][1]["mode"], "deterministic")

    def test_identifiers_hashes_paths_and_strings_are_closed(self):
        for factory, overrides in (
            (self.make_environment, {"environment_id": "bad id"}),
            (self.make_environment, {"image_digest": "A" * 64}),
            (self.make_artifact, {"path": "../robot.urdf"}),
            (self.make_artifact, {"path": "C" + ":/private/robot.urdf"}),
            (self.make_artifact, {"consumer": "bad consumer"}),
            (self.make_scenario, {"scenario_id": ""}),
            (self.make_trajectory, {"trajectory_id": False}),
        ):
            with self.subTest(factory=factory.__name__, overrides=overrides):
                with self.assertRaises(ValueError):
                    factory(**overrides)

        with self.assertRaisesRegex(ValueError, "surrogate"):
            self.make_artifact(observations={"bad": "\ud800"})

    def test_finite_scalars_and_integer_nanoseconds_reject_bool_and_overflow(self):
        for invalid in (True, -1, 1.5, 2**63):
            with self.subTest(duration_ns=invalid):
                with self.assertRaisesRegex(ValueError, "duration_ns"):
                    self.make_scenario(duration_ns=invalid)
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(value=invalid):
                with self.assertRaisesRegex(ValueError, "finite"):
                    self.make_metric(value=invalid)
        with self.assertRaisesRegex(ValueError, "timestamp_ns"):
            TraceSample(True, (0.0,), {})

    def test_joint_collections_are_unique_and_position_width_matches(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.make_scenario(joint_order=("joint_1", "joint_1"))
        with self.assertRaisesRegex(ValueError, "width"):
            self.make_trajectory(positions=((0.0,),))
        with self.assertRaisesRegex(ValueError, "positions"):
            self.make_trajectory(positions=((0.0, math.nan),))
        with self.assertRaisesRegex(ValueError, "positions"):
            TraceSample(0, (0.0, math.inf), {})

    def test_admission_status_and_hardware_firewall_are_consistent(self):
        with self.assertRaisesRegex(ValueError, "hardware_promotable"):
            self.make_admission(hardware_promotable=True)
        with self.assertRaisesRegex(ValueError, "evidence_level"):
            self.make_admission(evidence_level="simulated")
        with self.assertRaisesRegex(ValueError, "remaining_blockers"):
            self.make_admission(remaining_blockers=("A.CODE", "A.CODE"))
        rejected = self.make_admission(
            status="rejected",
            evidence_level="calculated",
            remaining_blockers=("PHY.DRIVE.PEAK_TORQUE",),
        )
        self.assertFalse(rejected.hardware_promotable)

    def test_result_rejects_illegal_evidence_jumps_and_mismatched_samples(self):
        sample = TraceSample(0, (0.0, 0.0), {})
        result = SimulationResult(
            scenario_id="scenario-nominal-arm",
            status="passed",
            evidence_level="simulated",
            model_sha256=SHA_A,
            trajectory_sha256=SHA_B,
            environment_sha256=SHA_C,
            trace_sha256=SHA_A,
            joint_order=("joint_1", "joint_2"),
            samples=(sample,),
            metrics=(self.make_metric(),),
            diagnostics=(),
        )
        canonical_bytes(result.to_dict())
        for invalid_level in (
            "generated",
            "calculated",
            "bench_tested",
            "integrated_hardware_tested",
            "task_validated",
            "certified",
        ):
            with self.subTest(level=invalid_level):
                with self.assertRaisesRegex(ValueError, "evidence_level"):
                    dataclasses.replace(result, evidence_level=invalid_level)
        with self.assertRaisesRegex(ValueError, "sample.*width"):
            dataclasses.replace(result, samples=(TraceSample(0, (0.0,), {}),))
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            dataclasses.replace(result, samples=(sample, sample))

    def test_result_accepts_10000_samples_and_rejects_10001(self):
        def make(count):
            return SimulationResult(
                scenario_id="scenario-scale",
                status="passed",
                evidence_level="simulated",
                model_sha256=SHA_A,
                trajectory_sha256=SHA_B,
                environment_sha256=SHA_C,
                trace_sha256=SHA_A,
                joint_order=("joint_1",),
                samples=tuple(TraceSample(index, (0.0,), {}) for index in range(count)),
                metrics=(),
                diagnostics=(),
            )

        self.assertEqual(len(make(10_000).samples), 10_000)
        with self.assertRaisesRegex(ValueError, "at most 10000"):
            make(10_001)

    def test_simulated_result_requires_at_least_one_trace_sample(self):
        with self.assertRaisesRegex(ValueError, "samples must not be empty"):
            SimulationResult(
                scenario_id="scenario-empty-trace",
                status="passed",
                evidence_level="simulated",
                model_sha256=SHA_A,
                trajectory_sha256=SHA_B,
                environment_sha256=SHA_C,
                trace_sha256=SHA_A,
                joint_order=("joint_1",),
                samples=(),
                metrics=(),
                diagnostics=(),
            )

    def test_recursive_nested_json_is_actionable(self):
        recursive = []
        recursive.append(recursive)
        with self.assertRaisesRegex(ValueError, r"parameters\[recursive\].*cycle"):
            self.make_environment(parameters={"recursive": recursive})


if __name__ == "__main__":
    unittest.main()
