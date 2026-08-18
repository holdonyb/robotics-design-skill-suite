import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.simulation.policy_trace import (  # noqa: E402
    PolicyTraceError,
    replay_policy_trace_bundle,
    run_reference_policy_trace,
)
from assurance.simulation.scenario import compile_scenarios  # noqa: E402
from assurance.simulation.trusted_registry import load_trusted_scenario_registry  # noqa: E402
from tests.test_simulation_scenario import registry  # noqa: E402


class PolicyTraceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        path = Path(self.temporary.name) / "scenarios.json"
        path.write_bytes(canonical_bytes(registry()))
        self.registry = load_trusted_scenario_registry(
            path, hashlib.sha256(path.read_bytes()).hexdigest()
        )
        self.scenario = self.registry.scenarios[0]

    @staticmethod
    def actions(linear, angular):
        return [
            {"timestamp_ns": 0, "linear_m_s": linear, "angular_rad_s": angular},
            {"timestamp_ns": 500_000_000, "linear_m_s": linear, "angular_rad_s": angular},
            {"timestamp_ns": 1_000_000_000, "linear_m_s": linear, "angular_rad_s": angular},
        ]

    def test_runner_generates_different_receipted_outcomes_for_different_actions(self):
        stopped = run_reference_policy_trace(
            self.registry, self.scenario.scenario_id, "a" * 64,
            self.actions(0.0, 0.0),
            Path(self.temporary.name) / "stopped", wheel_radius_m=0.15, wheel_separation_m=0.68,
        )
        moving = run_reference_policy_trace(
            self.registry, self.scenario.scenario_id, "b" * 64,
            self.actions(0.2, 0.0),
            Path(self.temporary.name) / "moving", wheel_radius_m=0.15, wheel_separation_m=0.68,
        )
        stopped_replay = replay_policy_trace_bundle(
            stopped.bundle_root, stopped.manifest_sha256, self.registry, "a" * 64
        )
        moving_replay = replay_policy_trace_bundle(
            moving.bundle_root, moving.manifest_sha256, self.registry, "b" * 64
        )
        self.assertNotEqual(stopped_replay.trace_sha256, moving_replay.trace_sha256)
        self.assertLess(stopped_replay.features.wheel_progress_rad, moving_replay.features.wheel_progress_rad)

    def test_replay_rejects_unmatched_policy_or_action_identity(self):
        assignment = run_reference_policy_trace(
            self.registry, self.scenario.scenario_id, "a" * 64,
            self.actions(0.2, 0.1),
            Path(self.temporary.name) / "trace", wheel_radius_m=0.15, wheel_separation_m=0.68,
        )
        with self.assertRaisesRegex(PolicyTraceError, "policy"):
            replay_policy_trace_bundle(
                assignment.bundle_root, assignment.manifest_sha256, self.registry, "b" * 64
            )
        with self.assertRaisesRegex(PolicyTraceError, "actions"):
            replay_policy_trace_bundle(
                assignment.bundle_root, assignment.manifest_sha256, self.registry, "a" * 64,
                expected_actions=self.actions(0.0, 0.0),
            )

    def test_fault_stop_changes_runner_state_and_replayed_progress(self):
        normal = run_reference_policy_trace(
            self.registry, "scenario-03", "a" * 64,
            self.actions(0.2, 0.0),
            Path(self.temporary.name) / "normal", wheel_radius_m=0.15, wheel_separation_m=0.68,
        )
        stopped = run_reference_policy_trace(
            self.registry, "scenario-10", "b" * 64,
            self.actions(0.2, 0.0),
            Path(self.temporary.name) / "stopped", wheel_radius_m=0.15, wheel_separation_m=0.68,
        )
        normal_replay = replay_policy_trace_bundle(normal.bundle_root, normal.manifest_sha256, self.registry, "a" * 64)
        stopped_replay = replay_policy_trace_bundle(stopped.bundle_root, stopped.manifest_sha256, self.registry, "b" * 64)
        self.assertGreater(normal_replay.features.wheel_progress_rad, stopped_replay.features.wheel_progress_rad)
        self.assertEqual(0.0, stopped_replay.features.left_wheel_rad_s[-1])


if __name__ == "__main__":
    unittest.main()
