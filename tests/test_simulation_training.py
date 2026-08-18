import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.replay_features import (  # noqa: E402
    ReplayFeatureError,
    extract_replay_features,
)
from assurance.simulation.model import MetricResult, ScenarioSpec, SimulationResult, TraceSample  # noqa: E402
from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.simulation.scenario import CompiledScenario  # noqa: E402
from assurance.simulation.trace import publish_trace_bundle  # noqa: E402
from assurance.simulation.training import (  # noqa: E402
    REFERENCE_TRAINING_CONTRACT_RECEIPT,
    TrainingError,
    evaluate_policy,
    evaluate_policy_artifact,
    validate_training_contract,
)
from assurance.simulation.policy_trace import TrustedPolicyTraceContext  # noqa: E402
from assurance.simulation.trusted_registry import (  # noqa: E402
    load_reference_trusted_scenario_registry,
    load_trusted_scenario_registry,
)
from assurance.simulation import policy_trace  # noqa: E402
from assurance.simulation.policy_backend import execute_policy  # noqa: E402


SHA_A = "a" * 64


def contract():
    return {
        "schema_version": 1, "contract_id": "training-reference-v1", "artifact_sha256": SHA_A,
        "artifact_path": "simulation/policies/baseline-affine.json",
        "artifact_policy_id": "policy-reference-baseline",
        "artifact_observation_order": [
            "joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6",
            "left_wheel_rad_s", "right_wheel_rad_s",
        ],
        "observation": {"frame": "base_link", "unit": "si", "rate_hz": 20, "fields": ["joint_rad", "left_wheel_rad_s", "right_wheel_rad_s"]},
        "action": {"frame": "base_link", "unit": "si", "rate_hz": 20, "fields": ["linear_m_s", "angular_rad_s"]},
        "reward_weights": {"wheel_progress": 1.0, "wheel_effort": -0.1}, "baseline_mean_reward": 0.0,
        "hard_constraints": {"max_linear_m_s": 0.4, "max_angular_rad_s": 0.8, "max_joint_error_rad": 0.02},
        "budgets": {"episodes": 10, "steps": 1000, "wall_time_s": 60, "memory_mb": 256},
        "train_seeds": [1, 2], "evaluation_seeds": [3, 4],
        "randomization": {"owner": "uncertainty_v1", "friction": {"lower": 0.4, "upper": 0.8}},
        "held_out_faults": ["fault-stop"],
        "physical_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"],
    }


def physical_receipt():
    return {
        "remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"],
        "hardware_promotable": False,
    }


def scenario(*, scenario_id="scenario-01", seed=1, fault_id=None):
    faults = () if fault_id is None else ({"fault_id": fault_id, "at_ns": 500_000_000},)
    spec = ScenarioSpec(
        scenario_id, "v1", "a" * 64, "b" * 64, "c" * 64, seed,
        1_000_000_000, ("joint-1", "joint-2"), {}, faults,
    )
    metrics = (
        MappingProxyType({"name": "elapsed_time", "unit": "s", "direction": "max", "limit": 1.0}),
        MappingProxyType({"name": "final_joint_error", "unit": "rad", "direction": "max", "limit": 0.01}),
    )
    stop = MappingProxyType({"reason": "duration_elapsed", "at_ns": 1_000_000_000})
    normal = {**spec.to_dict(), "metrics": sorted((dict(item) for item in metrics), key=lambda item: item["name"]), "stop": dict(stop)}
    return CompiledScenario(spec, metrics, stop, hashlib.sha256(canonical_bytes(normal)).hexdigest())


def replay(*, scenario_value=None, trace_sha256="d" * 64, status="passed", final_error=0.001, metric_error=None):
    scenario_value = scenario_value or scenario()
    metric_error = final_error if metric_error is None else metric_error
    return SimulationResult(
        scenario_value.scenario_id, status, "simulated", "a" * 64, "b" * 64, "c" * 64,
        trace_sha256, ("joint-1", "joint-2"),
        (
            TraceSample(0, (0.0, 0.0), {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
            TraceSample(500_000_000, (0.0005, 0.0005), {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
            TraceSample(1_000_000_000, (final_error, final_error), {"left_wheel_rad_s": 1.0, "right_wheel_rad_s": 1.0}),
        ),
        (
            MetricResult("elapsed_time", "s", "passed", 1.0, 1.0, {}),
            MetricResult("final_joint_error", "rad", "passed", metric_error, 0.01, {}),
        ), (),
    )


def assignments(*, final_error=0.001):
    cases = [
        ("train", 1, None), ("train", 2, None), ("evaluation", 3, None),
        ("evaluation", 4, None), ("held_out", 3, "fault-stop"), ("held_out", 4, "fault-stop"),
    ]
    return [
        {
            "phase": phase, "seed": seed, "fault_id": fault_id,
            "scenario": scenario(scenario_id=f"scenario-{index:02d}", seed=seed, fault_id=fault_id),
            "replay": replay(
                scenario_value=scenario(scenario_id=f"scenario-{index:02d}", seed=seed, fault_id=fault_id),
                trace_sha256=f"{index:064x}", final_error=final_error,
            ),
        }
        for index, (phase, seed, fault_id) in enumerate(cases, start=1)
    ]


def receipt_assignments(output, *, final_error=0.001):
    cases = [
        ("train", 1, None), ("train", 2, None), ("evaluation", 3, None),
        ("evaluation", 4, None), ("held_out", 3, "fault-stop"), ("held_out", 4, "fault-stop"),
    ]
    values = []
    bundle_base = Path(tempfile.mkdtemp(dir=output))
    for index, (phase, seed, fault_id) in enumerate(cases, start=1):
        compiled = scenario(scenario_id=f"scenario-{index:02d}", seed=seed, fault_id=fault_id)
        bundle = bundle_base / compiled.scenario_id
        receipt = publish_trace_bundle(bundle, compiled, replay(scenario_value=compiled, final_error=final_error).samples)
        values.append({
            "phase": phase,
            "seed": seed,
            "fault_id": fault_id,
            "scenario": compiled,
            "bundle_root": str(bundle),
            "manifest_sha256": receipt.manifest_sha256,
        })
    return values


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def receipt_assignments(self, *, final_error=0.001):
        return TrustedPolicyTraceContext(
            ROOT / "reference" / "mobile-manipulator",
            Path(tempfile.mkdtemp(dir=self.temporary.name)),
        )

    def test_rejects_forged_simulation_result_instead_of_a_revalidated_bundle(self):
        with self.assertRaisesRegex(TrainingError, "context"):
            evaluate_policy(
                contract(), lambda _: {"linear_m_s": 0.0, "angular_rad_s": 0.0},
                physical_receipt(), {"replay": replace(replay(), trace_sha256="f" * 64)},
            )

    def test_accepts_each_assignment_only_after_bundle_receipt_revalidation(self):
        result = evaluate_policy(
            contract(), lambda _: {"linear_m_s": 0.0, "angular_rad_s": 0.0},
            physical_receipt(), self.receipt_assignments(),
        )
        self.assertEqual(6, result.evaluation_count)
        self.assertEqual(6, len(result.trace_sha256s))

    def test_extracts_features_only_from_validated_result_and_recomputes_joint_error(self):
        features = extract_replay_features(replay())
        self.assertEqual("d" * 64, features.trace_sha256)
        self.assertEqual(("joint-1", "joint-2"), features.joint_order)
        self.assertEqual(1.0, features.elapsed_time_s)
        self.assertEqual(1.0, features.left_wheel_travel_rad)
        self.assertEqual(1.0, features.right_wheel_travel_rad)
        self.assertEqual(1.0, features.wheel_effort_rad2_s)
        self.assertEqual(0.001, features.final_joint_error_rad)
        self.assertEqual([0.001, 0.001], features.observation["joint_rad"])
        with self.assertRaisesRegex(ReplayFeatureError, "SimulationResult"):
            extract_replay_features({"samples": []})
        with self.assertRaisesRegex(ReplayFeatureError, "final_joint_error"):
            extract_replay_features(replay(final_error=0.1, metric_error=0.001))

    def test_replay_feature_extractor_rejects_invalid_trace_outcomes(self):
        with self.assertRaisesRegex(ReplayFeatureError, "passed"):
            extract_replay_features(replay(status="failed"))

    def test_contract_is_closed_and_policy_stays_simulated_with_firewall(self):
        self.assertEqual([], validate_training_contract(contract()))
        physical = physical_receipt()
        def policy(observation):
            observation["joint_rad"][0] = 999
            return {"linear_m_s": 0.2, "angular_rad_s": 0.1}
        result = evaluate_policy(contract(), policy, physical, self.receipt_assignments())
        self.assertEqual("simulated", result.evidence_level)
        self.assertEqual("not_justified", result.status)
        self.assertEqual(("BOM.PLACEHOLDER_BLOCKS_CLAIM",), result.physical_blockers)
        self.assertEqual(6, result.evaluation_count)
        self.assertEqual(2, result.held_out_evaluation_count)
        self.assertNotIn("hardware_promotable", result.to_dict())
        self.assertEqual(physical_receipt(), physical)

    def test_rejects_schema_budget_seed_randomization_and_callback_attacks(self):
        attacks = (
            (lambda x: x.__setitem__("extra", True), "unknown"),
            (lambda x: x["budgets"].__setitem__("episodes", 0), "budgets"),
            (lambda x: x.__setitem__("evaluation_seeds", [1]), "distinct"),
            (lambda x: x["randomization"].__setitem__("owner", "policy"), "owner"),
            (lambda x: x["randomization"]["friction"].__setitem__("upper", 2.0), "randomization"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected):
                value = contract(); mutate(value)
                self.assertTrue(any(expected in item for item in validate_training_contract(value)))
        for callback, expected in (
            (lambda x: {"linear_m_s": float("nan"), "angular_rad_s": 0.0}, "finite"),
            (lambda x: {"linear_m_s": 9.0, "angular_rad_s": 0.0}, "constraint"),
            (lambda x: {"linear_m_s": 0.0}, "fields"),
            (lambda x: (_ for _ in ()).throw(RuntimeError("bad")), "callback"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(TrainingError, expected):
                    evaluate_policy(contract(), callback, physical_receipt(), self.receipt_assignments())

    def test_physical_blocker_receipt_is_required_and_can_never_authorize_hardware(self):
        callback = lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}
        for physical, expected in (
            ({"remaining_blockers": [], "hardware_promotable": False}, "blockers"),
            ({"remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"], "hardware_promotable": True}, "hardware"),
            ({"remaining_blockers": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"], "hardware_promotable": False, "extra": 1}, "fields"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(TrainingError, expected):
                    evaluate_policy(contract(), callback, physical, self.receipt_assignments())

    def test_rejects_unbounded_or_ambiguous_contract_collections(self):
        attacks = (
            (lambda x: x["reward_weights"].__setitem__("progress", True), "reward_weights"),
            (lambda x: x["hard_constraints"].__setitem__("extra", 1.0), "hard_constraints"),
            (lambda x: x.__setitem__("held_out_faults", ["fault-stop", "fault-stop"]), "held_out_faults"),
            (lambda x: x.__setitem__("physical_blockers", []), "physical_blockers"),
            (lambda x: x["observation"].__setitem__("fields", ["scan_m", "scan_m"]), "observation"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected):
                value = contract()
                mutate(value)
                self.assertTrue(any(expected in item for item in validate_training_contract(value)))

    def test_policy_identity_and_blocker_order_are_stable(self):
        callback = lambda x: {"linear_m_s": 0.2, "angular_rad_s": -0.1}
        first = evaluate_policy(contract(), callback, physical_receipt(), self.receipt_assignments())
        second = evaluate_policy(contract(), callback, physical_receipt(), self.receipt_assignments())
        self.assertEqual(first.policy_id, second.policy_id)
        self.assertEqual(("BOM.PLACEHOLDER_BLOCKS_CLAIM",), first.physical_blockers)

    def test_two_in_range_policies_cannot_reuse_a_score_or_trace(self):
        stopped = evaluate_policy(
            contract(), lambda _: {"linear_m_s": 0.0, "angular_rad_s": 0.0},
            physical_receipt(), self.receipt_assignments(),
        )
        moving = evaluate_policy(
            contract(), lambda _: {"linear_m_s": 0.2, "angular_rad_s": 0.0},
            physical_receipt(), self.receipt_assignments(),
        )
        self.assertLess(stopped.mean_reward, moving.mean_reward)
        self.assertTrue(set(stopped.trace_sha256s).isdisjoint(moving.trace_sha256s))

    def test_callback_cannot_mutate_the_evaluation_geometry_profile(self):
        baseline = evaluate_policy(
            contract(), lambda _: {"linear_m_s": 0.2, "angular_rad_s": 0.0},
            physical_receipt(), self.receipt_assignments(),
        )
        original = getattr(policy_trace, "REFERENCE_RUNNER_PROFILE", None)
        try:
            def callback(_):
                policy_trace.REFERENCE_RUNNER_PROFILE = {"wheel_radius_m": 0.04, "wheel_separation_m": 0.68}
                return {"linear_m_s": 0.2, "angular_rad_s": 0.0}
            attacked = evaluate_policy(contract(), callback, physical_receipt(), self.receipt_assignments())
        finally:
            if original is None:
                delattr(policy_trace, "REFERENCE_RUNNER_PROFILE")
            else:
                policy_trace.REFERENCE_RUNNER_PROFILE = original
        self.assertEqual(baseline.mean_reward, attacked.mean_reward)

    def test_executes_each_evaluation_seed_with_held_out_fault_and_baseline_comparison(self):
        seen = []

        def callback(observation):
            seen.append((observation["phase"], observation["seed"], observation["fault_id"]))
            return {"linear_m_s": 0.2, "angular_rad_s": 0.0}

        result = evaluate_policy(contract(), callback, physical_receipt(), self.receipt_assignments())
        self.assertEqual(18, len(seen))
        self.assertEqual([("train", 1, None)] * 3, seen[:3])
        self.assertEqual(6, result.evaluation_count)
        self.assertEqual(2, result.held_out_evaluation_count)

    def test_rejects_baseline_regression_and_budget_excess(self):
        baseline = contract()
        baseline["baseline_mean_reward"] = 1.0
        with self.assertRaisesRegex(TrainingError, "baseline"):
            evaluate_policy(baseline, lambda x: {"linear_m_s": -0.1, "angular_rad_s": 0.0}, physical_receipt(), self.receipt_assignments())
        with self.assertRaisesRegex(TrainingError, "fields"):
            evaluate_policy(contract(), lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0, "mean_reward": 9999}, physical_receipt(), self.receipt_assignments())
        value = contract()
        value["budgets"]["episodes"] = 5
        with self.assertRaisesRegex(TrainingError, "episodes"):
            evaluate_policy(value, lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}, physical_receipt(), self.receipt_assignments())

        with self.assertRaisesRegex(TrainingError, "constraint"):
            evaluate_policy(contract(), lambda x: {"linear_m_s": 1.0, "angular_rad_s": 0.0}, physical_receipt(), self.receipt_assignments())

    def test_trace_context_is_a_hard_gate(self):
        callback = lambda x: {"linear_m_s": 0.0, "angular_rad_s": 0.0}
        with self.assertRaisesRegex(TrainingError, "context"):
            evaluate_policy(contract(), callback, physical_receipt(), [])

    def test_rejects_a_context_signed_by_an_unapproved_registry(self):
        source = ROOT / "reference" / "mobile-manipulator" / "simulation" / "scenarios.json"
        forged = json.loads(source.read_text(encoding="utf-8"))
        forged["registry_id"] = "attacker-registry"
        path = Path(self.temporary.name) / "scenarios.json"
        path.write_bytes(canonical_bytes(forged))
        forged_root = Path(self.temporary.name) / "reference"
        (forged_root / "simulation").mkdir(parents=True)
        (forged_root / "simulation" / "scenarios.json").write_bytes(path.read_bytes())
        context = TrustedPolicyTraceContext(forged_root, Path(self.temporary.name) / "forged")
        with self.assertRaisesRegex(TrainingError, "benchmark owner receipt"):
            evaluate_policy(
                contract(), lambda _: {"linear_m_s": 0.2, "angular_rad_s": 0.0},
                physical_receipt(), context,
            )

    def test_context_generated_traces_are_unique_per_required_case(self):
        result = evaluate_policy(
            contract(), lambda x: {"linear_m_s": 0.2, "angular_rad_s": 0.0},
            physical_receipt(), self.receipt_assignments(),
        )
        self.assertEqual(6, len(result.trace_sha256s))
        self.assertEqual(6, len(set(result.trace_sha256s)))

    def test_artifact_evaluator_runs_bound_reference_artifact_without_callback(self):
        reference_root = ROOT / "reference" / "mobile-manipulator"
        contract_value = json.loads(
            (reference_root / "simulation" / "training-contract.json").read_text(encoding="utf-8")
        )
        trace_output = Path(self.temporary.name) / "artifact-traces"
        result = evaluate_policy_artifact(
            contract_value,
            contract_value["artifact_path"],
            {
                "remaining_blockers": list(contract_value["physical_blockers"]),
                "hardware_promotable": False,
            },
            TrustedPolicyTraceContext(reference_root, trace_output),
        )
        self.assertEqual("policy-reference-baseline", result.policy_id)
        self.assertEqual("simulated", result.evidence_level)
        self.assertEqual("not_justified", result.status)
        traces = sorted(trace_output.glob("*/trace.json"))
        self.assertEqual(result.evaluation_count, len(traces))
        self.assertTrue(all(
            json.loads(path.read_text(encoding="utf-8"))["training_contract_sha256"]
            == REFERENCE_TRAINING_CONTRACT_RECEIPT
            for path in traces
        ))

    def test_artifact_evaluator_rejects_digest_path_id_and_order_before_worker(self):
        reference_root = ROOT / "reference" / "mobile-manipulator"
        source_contract = json.loads(
            (reference_root / "simulation" / "training-contract.json").read_text(encoding="utf-8")
        )
        artifact_path = source_contract["artifact_path"]
        physical = {
            "remaining_blockers": list(source_contract["physical_blockers"]),
            "hardware_promotable": False,
        }
        for mutate, expected in (
            (lambda value: value.__setitem__("artifact_sha256", "a" * 64), "artifact|training contract"),
            (lambda value: value.__setitem__("artifact_path", "../outside.json"), "artifact_path"),
            (lambda value: value.__setitem__("artifact_path", "C:/outside.json"), "artifact_path"),
            (lambda value: value.__setitem__("artifact_policy_id", "policy-other"), "artifact|training contract"),
            (lambda value: value.__setitem__("artifact_observation_order", ["joint_1"]), "artifact|training contract"),
        ):
            with self.subTest(expected=expected):
                contract_value = copy.deepcopy(source_contract)
                mutate(contract_value)
                with self.assertRaisesRegex(TrainingError, expected):
                    evaluate_policy_artifact(
                        contract_value,
                        artifact_path,
                        physical,
                        TrustedPolicyTraceContext(reference_root, Path(self.temporary.name) / expected),
                    )

    def test_artifact_binding_failures_reject_before_worker_and_success_uses_worker(self):
        source = ROOT / "reference" / "mobile-manipulator"
        with tempfile.TemporaryDirectory(dir=self.temporary.name) as raw:
            reference_root = Path(raw) / "reference"
            shutil.copytree(source, reference_root)
            contract_value = json.loads(
                (reference_root / "simulation" / "training-contract.json").read_text(encoding="utf-8")
            )
            artifact_path = reference_root / contract_value["artifact_path"]
            artifact_argument = contract_value["artifact_path"]
            physical = {
                "remaining_blockers": list(contract_value["physical_blockers"]),
                "hardware_promotable": False,
            }
            for mutation, expected in (
                (lambda: artifact_path.write_bytes(artifact_path.read_bytes() + b" "), "artifact"),
                (lambda: artifact_path.unlink() or os.symlink(source / "simulation" / "policies" / "baseline-affine.json", artifact_path), "symlink"),
            ):
                with self.subTest(expected=expected):
                    if artifact_path.exists() or artifact_path.is_symlink():
                        artifact_path.unlink()
                    shutil.copyfile(source / "simulation" / "policies" / "baseline-affine.json", artifact_path)
                    try:
                        mutation()
                    except (NotImplementedError, OSError) as exc:
                        self.skipTest(f"symlink mutation is unavailable: {exc}")
                    with mock.patch("assurance.simulation.training.execute_policy", wraps=execute_policy) as worker:
                        with self.assertRaisesRegex(TrainingError, expected):
                            evaluate_policy_artifact(
                                contract_value, artifact_argument, physical,
                                TrustedPolicyTraceContext(reference_root, Path(raw) / expected),
                            )
                        worker.assert_not_called()

            if artifact_path.exists() or artifact_path.is_symlink():
                artifact_path.unlink()
            shutil.copyfile(source / "simulation" / "policies" / "baseline-affine.json", artifact_path)
            with mock.patch("assurance.simulation.training.execute_policy", wraps=execute_policy) as worker:
                result = evaluate_policy_artifact(
                    contract_value, artifact_argument, physical,
                    TrustedPolicyTraceContext(reference_root, Path(raw) / "success"),
                )
            self.assertEqual(18, worker.call_count)
            self.assertEqual(contract_value["artifact_sha256"], result.artifact_sha256)

    def test_artifact_argument_must_be_the_exact_contract_relative_path_before_worker(self):
        reference_root = ROOT / "reference" / "mobile-manipulator"
        contract_value = json.loads(
            (reference_root / "simulation" / "training-contract.json").read_text(encoding="utf-8")
        )
        physical = {
            "remaining_blockers": list(contract_value["physical_blockers"]),
            "hardware_promotable": False,
        }
        for artifact_path in (
            reference_root / contract_value["artifact_path"],
            "simulation/policies/../policies/baseline-affine.json",
            "simulation//policies/baseline-affine.json",
        ):
            with self.subTest(artifact_path=artifact_path):
                with mock.patch("assurance.simulation.training.execute_policy", wraps=execute_policy) as worker:
                    with self.assertRaisesRegex(TrainingError, "artifact_path"):
                        evaluate_policy_artifact(
                            contract_value,
                            artifact_path,
                            physical,
                            TrustedPolicyTraceContext(reference_root, Path(self.temporary.name) / "aliased-path"),
                        )
                    worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
