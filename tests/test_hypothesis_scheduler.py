import hashlib
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.hypothesis.model import CandidateDecision, StageSpec  # noqa: E402
from assurance.hypothesis.overlay import ResolvedCandidate  # noqa: E402
from assurance.hypothesis.scheduler import (  # noqa: E402
    HypothesisScheduler,
    SchedulerError,
    default_registry,
)


def candidate(*, errors=(), alias_of=None, seed=3):
    contract = {"schema_version": 1, "candidate_id": "placeholder", "payload": 7}
    digest = hashlib.sha256(canonical_bytes({"schema_version": 1, "payload": 7})).hexdigest()
    decision = CandidateDecision("a" * 64, {"motor": "small"}, seed)
    contract["candidate_id"] = decision.candidate_id
    return ResolvedCandidate(decision, contract, digest, tuple(errors), alias_of)


class SchedulerTests(unittest.TestCase):
    def test_physical_stage_calls_v030_gate_and_cache_binds_tool_version(self):
        calls = []

        def gate(path):
            calls.append(path.read_bytes())
            return mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}), []

        with tempfile.TemporaryDirectory() as raw:
            scheduler = HypothesisScheduler(gate=gate, artifact_root=Path(raw))
            first = scheduler.evaluate(candidate(), Path(raw) / "cache", stages=("contract_v1", "physical_v030"))
            second = scheduler.evaluate(candidate(), Path(raw) / "cache", stages=("contract_v1", "physical_v030"))
            self.assertEqual(1, len(calls))
            self.assertTrue(calls[0].endswith(b"\n"))
            self.assertFalse(calls[0].endswith(b"\n\n"))
            self.assertEqual(first, second)
            scheduler.tool_versions["assurance_kernel"] = "0.3.1"
            scheduler.evaluate(candidate(), Path(raw) / "cache", stages=("contract_v1", "physical_v030"))
            self.assertEqual(2, len(calls))

    def test_contract_errors_block_physical_stage(self):
        gate = mock.Mock()
        with tempfile.TemporaryDirectory() as raw:
            scheduler = HypothesisScheduler(gate=gate, artifact_root=Path(raw))
            result = scheduler.evaluate(
                candidate(errors=("bad contract",)), Path(raw) / "cache"
            )
        self.assertEqual(("contract_v1",), tuple(stage.name for stage in result))
        self.assertEqual("blocked", result[0].status)
        self.assertEqual(1, scheduler.evaluation_count)
        self.assertEqual(0, scheduler.stage_evaluation_counts["physical_v030"])
        gate.assert_not_called()

    def test_registry_is_exact_and_topological_order_is_deterministic(self):
        registry = default_registry()
        self.assertEqual(
            {"contract_v1", "physical_v030", "uncertainty_v1", "counterexample_v1", "objectives_v1"},
            set(registry),
        )
        scheduler = HypothesisScheduler(registry=registry, gate=lambda path: (mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}), []))
        self.assertEqual(
            ("contract_v1", "physical_v030", "uncertainty_v1", "counterexample_v1", "objectives_v1"),
            scheduler.order(tuple(reversed(tuple(registry)))),
        )

    def test_unknown_stage_and_dependency_cycle_are_rejected(self):
        scheduler = HypothesisScheduler()
        with self.assertRaisesRegex(SchedulerError, "unknown stage"):
            scheduler.order(("made_up",))
        registry = default_registry()
        registry["contract_v1"] = StageSpec("contract_v1", "1", ("physical_v030",), 1_000_000)
        with self.assertRaisesRegex(SchedulerError, "cycle"):
            HypothesisScheduler(registry=registry)

    def test_missing_dependency_is_rejected(self):
        with self.assertRaisesRegex(SchedulerError, "requires dependency"):
            HypothesisScheduler().order(("physical_v030",))

    def test_global_budget_counts_alias_and_uncertainty_requests(self):
        with tempfile.TemporaryDirectory() as raw:
            scheduler = HypothesisScheduler(max_stage_evaluations=2, gate=lambda path: (mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}), []))
            scheduler.evaluate(candidate(), Path(raw), stages=("contract_v1",), uncertainty_case={"slope": 1})
            scheduler.evaluate(candidate(alias_of="candidate-" + "b" * 24), Path(raw), stages=("contract_v1",), uncertainty_case={"slope": 2})
            with self.assertRaisesRegex(SchedulerError, "max_stage_evaluations"):
                scheduler.evaluate(candidate(), Path(raw), stages=("contract_v1",))

    def test_corrupt_and_stale_cache_are_ignored(self):
        calls = []
        gate = lambda path: (calls.append(1) or mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}), [])
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw) / "cache"
            scheduler = HypothesisScheduler(gate=gate, artifact_root=Path(raw))
            result = scheduler.evaluate(candidate(), cache, stages=("contract_v1", "physical_v030"))
            physical = result[-1]
            entry = cache / f"{physical.cache_key}.json"
            entry.write_text("not json", encoding="utf-8")
            scheduler.evaluate(candidate(), cache, stages=("contract_v1", "physical_v030"))
            payload = json.loads(entry.read_text(encoding="utf-8"))
            payload["cache_key"] = "0" * 64
            entry.write_text(json.dumps(payload), encoding="utf-8")
            scheduler.evaluate(candidate(), cache, stages=("contract_v1", "physical_v030"))
            payload = json.loads(entry.read_text(encoding="utf-8"))
            payload["result"]["name"] = "objectives_v1"
            payload["result_sha256"] = hashlib.sha256(canonical_bytes(payload["result"])).hexdigest()
            body = dict(payload)
            body.pop("payload_sha256")
            payload["payload_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
            entry.write_bytes(canonical_bytes(payload) + b"\n")
            scheduler.evaluate(candidate(), cache, stages=("contract_v1", "physical_v030"))
            self.assertEqual(4, len(calls))

    def test_cache_entry_self_validates_payload_hash_and_schema(self):
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw) / "cache"
            result = HypothesisScheduler().evaluate(candidate(errors=("bad",)), cache, stages=("contract_v1",))
            payload = json.loads((cache / f"{result[0].cache_key}.json").read_text(encoding="utf-8"))
            self.assertEqual(1, payload["schema_version"])
            body = dict(payload)
            body.pop("auth_hmac_sha256")
            digest = body.pop("payload_sha256")
            self.assertEqual(digest, hashlib.sha256(canonical_bytes(body)).hexdigest())

    def test_fully_rehashed_cache_cannot_change_physical_promotion(self):
        calls = []
        gate = lambda path: (
            calls.append(1)
            or mock.Mock(to_dict=lambda: {"promotable": False, "diagnostics": []}),
            [],
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            scheduler = HypothesisScheduler(gate=gate, artifact_root=root)
            failed = scheduler.evaluate(
                candidate(), root / "cache", stages=("contract_v1", "physical_v030")
            )[-1]
            entry = root / "cache" / f"{failed.cache_key}.json"
            payload = json.loads(entry.read_text(encoding="utf-8"))
            payload["result"]["status"] = "passed"
            payload["result"]["output"]["report"]["promotable"] = True
            payload["result_sha256"] = hashlib.sha256(
                canonical_bytes(payload["result"])
            ).hexdigest()
            body = dict(payload)
            body.pop("auth_hmac_sha256")
            body.pop("payload_sha256")
            payload["payload_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
            # Attacker cannot recompute the process-secret HMAC.
            entry.write_bytes(canonical_bytes(payload))
            second = scheduler.evaluate(
                candidate(), root / "cache", stages=("contract_v1", "physical_v030")
            )[-1]
            self.assertEqual("failed", second.status)
            self.assertFalse(second.to_dict()["output"]["report"]["promotable"])
            self.assertEqual(2, len(calls))

    def test_cache_from_another_scheduler_is_untrusted_and_recomputed(self):
        calls = []
        gate = lambda path: (
            calls.append(1)
            or mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}),
            [],
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            HypothesisScheduler(gate=gate, artifact_root=root).evaluate(
                candidate(), root / "cache", stages=("contract_v1", "physical_v030")
            )
            HypothesisScheduler(gate=gate, artifact_root=root).evaluate(
                candidate(), root / "cache", stages=("contract_v1", "physical_v030")
            )
            self.assertEqual(2, len(calls))

    def test_cache_and_contract_writes_are_transactional_without_residue(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            HypothesisScheduler(gate=lambda path: (mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}), []), artifact_root=root).evaluate(
                candidate(), root / "chosen-cache", stages=("contract_v1", "physical_v030")
            )
            self.assertFalse(list(root.rglob("*.tmp")))
            self.assertEqual(2, len(list((root / "chosen-cache").glob("*.json"))))

    def test_cache_key_binds_dependency_hash_uncertainty_and_candidate_content(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            def gate(path):
                candidate_id = json.loads(path.read_text(encoding="utf-8"))["candidate_id"]
                return mock.Mock(to_dict=lambda: {"candidate_id": candidate_id, "promotable": True, "diagnostics": []}), []

            scheduler = HypothesisScheduler(gate=gate, artifact_root=root)
            one = scheduler.evaluate(candidate(), root / "cache", stages=("contract_v1", "physical_v030"), uncertainty_case={"x": 1})[-1]
            two = scheduler.evaluate(candidate(), root / "cache", stages=("contract_v1", "physical_v030"), uncertainty_case={"x": 2})[-1]
            self.assertNotEqual(one.cache_key, two.cache_key)
            alias = scheduler.evaluate(candidate(alias_of=candidate().candidate_id, seed=4), root / "cache", stages=("contract_v1", "physical_v030"), uncertainty_case={"x": 1})[-1]
            self.assertNotEqual(one.cache_key, alias.cache_key)
            self.assertEqual(candidate(seed=4).candidate_id, alias.to_dict()["output"]["report"]["candidate_id"])

    def test_candidate_declared_content_hash_must_match_actual_contract(self):
        forged = candidate()
        object.__setattr__(forged, "resolved_contract_sha256", "f" * 64)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(SchedulerError, "content SHA-256 mismatch"):
                HypothesisScheduler().evaluate(forged, Path(raw), stages=("contract_v1",))

    def test_each_stage_budget_is_enforced_even_when_cache_hits(self):
        registry = default_registry()
        registry["contract_v1"] = StageSpec("contract_v1", "1", (), 1)
        with tempfile.TemporaryDirectory() as raw:
            scheduler = HypothesisScheduler(registry=registry)
            scheduler.evaluate(candidate(), Path(raw), stages=("contract_v1",))
            with self.assertRaisesRegex(SchedulerError, "contract_v1 max_evaluations"):
                scheduler.evaluate(candidate(), Path(raw), stages=("contract_v1",))

    def test_deep_cache_json_is_ignored_without_recursion_traceback(self):
        calls = []
        gate = lambda path: (calls.append(1) or mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": []}), [])
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw) / "cache"
            scheduler = HypothesisScheduler(gate=gate, artifact_root=Path(raw))
            result = scheduler.evaluate(candidate(), cache, stages=("contract_v1", "physical_v030"))[-1]
            (cache / f"{result.cache_key}.json").write_text("[" * 1100 + "0" + "]" * 1100, encoding="utf-8")
            scheduler.evaluate(candidate(), cache, stages=("contract_v1", "physical_v030"))
            self.assertEqual(2, len(calls))

    def test_gate_failure_and_invalid_report_diagnostics_clean_temporary_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            def explode(path):
                raise RuntimeError("gate exploded")

            with self.assertRaisesRegex(SchedulerError, "gate failed"):
                HypothesisScheduler(gate=explode, artifact_root=root).evaluate(
                    candidate(), root / "cache", stages=("contract_v1", "physical_v030")
                )
            self.assertFalse(list(root.glob(".hypothesis-contract-*.tmp")))

            invalid = mock.Mock(to_dict=lambda: {"promotable": True, "diagnostics": "wrong"})
            with self.assertRaisesRegex(SchedulerError, "invalid diagnostics"):
                HypothesisScheduler(gate=lambda path: (invalid, []), artifact_root=root).evaluate(
                    candidate(), root / "cache2", stages=("contract_v1", "physical_v030")
                )
            self.assertFalse(list(root.glob(".hypothesis-contract-*.tmp")))


if __name__ == "__main__":
    unittest.main()
