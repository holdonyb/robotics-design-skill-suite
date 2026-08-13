import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.model import TraceSample  # noqa: E402
from assurance.simulation.scenario import compile_scenarios  # noqa: E402
from assurance.simulation.trace import TraceError, publish_trace_bundle, replay_trace_bundle  # noqa: E402
from tests.test_simulation_scenario import registry  # noqa: E402


class SimulationTraceTests(unittest.TestCase):
    def scenario(self):
        return compile_scenarios(registry())[0]

    def samples(self):
        return (
            TraceSample(0, (0.0,) * 6, {"mode": "start"}),
            TraceSample(1_000_000_000, (0.001,) * 6, {"mode": "duration_elapsed"}),
        )

    def test_transactional_bundle_replays_metrics_without_trusting_stored_verdicts(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "trace"
            receipt = publish_trace_bundle(target, self.scenario(), self.samples())
            replay = replay_trace_bundle(target, receipt.manifest_sha256)
            self.assertEqual("passed", replay.status)
            self.assertEqual("simulated", replay.evidence_level)
            self.assertEqual(("elapsed_time", "final_joint_error"), tuple(metric.name for metric in replay.metrics))
            self.assertEqual(0.001, next(metric.value for metric in replay.metrics if metric.name == "final_joint_error"))

    def test_rejects_time_joint_stop_and_resource_violations_before_publication(self):
        cases = (
            ((TraceSample(1, (0.0,) * 6, {}),), "first timestamp"),
            ((TraceSample(0, (0.0,) * 6, {}), TraceSample(0, (0.0,) * 6, {})), "strictly increasing"),
            ((TraceSample(0, (0.0,), {}), TraceSample(1_000_000_000, (0.0,), {})), "width"),
            ((TraceSample(0, (0.0,) * 6, {}), TraceSample(1, (0.0,) * 6, {}), TraceSample(1_000_000_000, (0.0,) * 6, {})), "sample period"),
            ((TraceSample(0, (0.0,) * 6, {}), TraceSample(2_000_000_000, (0.0,) * 6, {})), "stop timestamp"),
        )
        with tempfile.TemporaryDirectory() as raw:
            for samples, expected in cases:
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(TraceError, expected):
                        publish_trace_bundle(Path(raw) / expected.replace(" ", "-"), self.scenario(), samples)

    def test_tamper_and_self_rehashed_trace_cannot_bypass_external_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "trace"
            receipt = publish_trace_bundle(target, self.scenario(), self.samples())
            trace = (target / "trace.json").read_text(encoding="utf-8")
            (target / "trace.json").write_text(trace.replace('"mode":"start"', '"mode":"forged"'), encoding="utf-8")
            with self.assertRaisesRegex(TraceError, "stale hash|receipt"):
                replay_trace_bundle(target, receipt.manifest_sha256)

    def test_replay_does_not_trust_stored_status(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "trace"
            receipt = publish_trace_bundle(target, self.scenario(), self.samples())
            # The stored data has no result status.  A failed metric is derived from trace data.
            bad = list(self.samples())
            bad[-1] = TraceSample(1_000_000_000, (0.1,) * 6, {"mode": "duration_elapsed"})
            target2 = Path(raw) / "bad"
            receipt2 = publish_trace_bundle(target2, self.scenario(), tuple(bad))
            self.assertEqual("failed", replay_trace_bundle(target2, receipt2.manifest_sha256).status)

    def test_replay_rejects_self_consistent_malformed_scenario_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "trace"
            receipt = publish_trace_bundle(target, self.scenario(), self.samples())
            scenario = json.loads((target / "scenario.json").read_text(encoding="utf-8"))
            scenario["metrics"][0]["unit"] = "kg"
            from assurance.hypothesis.canonical import canonical_bytes
            from assurance.hypothesis.bundle import write_bundle_with_receipt
            trace = json.loads((target / "trace.json").read_text(encoding="utf-8"))
            trace["scenario_sha256"] = __import__("hashlib").sha256(canonical_bytes(scenario)).hexdigest()
            poisoned = Path(raw) / "poisoned"
            receipt = write_bundle_with_receipt(poisoned, {"index.json": {"schema_version": 1, "kind": "simulation_trace"}, "scenario.json": scenario, "trace.json": trace})
            with self.assertRaisesRegex(TraceError, "unit is invalid"):
                replay_trace_bundle(poisoned, receipt.manifest_sha256)


if __name__ == "__main__":
    unittest.main()
