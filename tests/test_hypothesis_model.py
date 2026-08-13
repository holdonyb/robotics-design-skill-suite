import dataclasses
import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis import (  # noqa: E402
    CandidateDecision,
    CandidateLineage,
    HypothesisResult,
    StageResult,
    StageSpec,
    candidate_id,
    canonical_bytes,
    seeded_order,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
CANDIDATE_A = "candidate-" + "1" * 24
CANDIDATE_B = "candidate-" + "2" * 24
CANDIDATE_C = "candidate-" + "3" * 24


class CanonicalIdentityTests(unittest.TestCase):
    def test_candidate_id_ignores_assignment_mapping_order(self):
        forward = candidate_id(
            SHA_A,
            {"axis-b": "choice-2", "axis-a": "choice-1"},
            17,
        )
        reverse = candidate_id(
            SHA_A,
            {"axis-a": "choice-1", "axis-b": "choice-2"},
            17,
        )

        self.assertEqual(forward, reverse)
        self.assertRegex(forward, r"^candidate-[0-9a-f]{24}$")
        self.assertEqual(len(forward), 34)

    def test_candidate_id_changes_with_seed_and_lineage(self):
        base = candidate_id(SHA_A, {"axis-a": "choice-1"}, 17)
        changed_seed = candidate_id(SHA_A, {"axis-a": "choice-1"}, 18)
        repaired = candidate_id(
            SHA_A,
            {"axis-a": "choice-1"},
            17,
            parent_id=CANDIDATE_A,
            repair_rule_id="repair-1",
        )

        self.assertNotEqual(base, changed_seed)
        self.assertNotEqual(base, repaired)

    def test_candidate_id_rejects_bool_seed_and_noncanonical_hash(self):
        with self.assertRaisesRegex(ValueError, "seed must be an integer"):
            candidate_id(SHA_A, {"axis": "choice"}, True)
        for invalid in ("A" * 64, "a" * 63, "g" * 64, 7):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "base_sha256"):
                    candidate_id(invalid, {"axis": "choice"}, 1)

    def test_candidate_id_rejects_open_or_nested_assignments(self):
        invalid_assignments = (
            [],
            {"": "choice"},
            {"axis": ""},
            {"axis": ["choice"]},
            {"axis": True},
            {"axis with space": "choice"},
        )
        for invalid in invalid_assignments:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "assignments"):
                    candidate_id(SHA_A, invalid, 1)
        with self.assertRaisesRegex(ValueError, "parent_id"):
            candidate_id(SHA_A, {"axis": "choice"}, 1, parent_id=" ")
        with self.assertRaisesRegex(ValueError, "parent_id"):
            candidate_id(SHA_A, {"axis": "choice"}, 1, parent_id="parent-1")
        with self.assertRaisesRegex(ValueError, "repair_rule_id"):
            candidate_id(
                SHA_A,
                {"axis": "choice"},
                1,
                repair_rule_id=False,
            )


class CanonicalBytesTests(unittest.TestCase):
    def test_canonical_bytes_is_sorted_compact_utf8_with_one_lf(self):
        encoded = canonical_bytes({"z": [2, 1], "a": "机器人"})

        self.assertIsInstance(encoded, bytes)
        self.assertEqual(encoded, '{"a":"机器人","z":[2,1]}\n'.encode("utf-8"))
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertFalse(encoded.endswith(b"\n\n"))

    def test_canonical_bytes_rejects_nonfinite_nested_values(self):
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, r"value\[nested\]\[0\].*finite"):
                    canonical_bytes({"nested": [invalid]})

    def test_canonical_bytes_rejects_non_json_and_overflow_values(self):
        with self.assertRaisesRegex(ValueError, r"value\[bad\].*JSON"):
            canonical_bytes({"bad": object()})
        with self.assertRaisesRegex(ValueError, "canonical JSON"):
            canonical_bytes(10**10000)

    def test_canonical_bytes_rejects_cycles_with_the_failing_path(self):
        recursive_list = []
        recursive_list.append(recursive_list)
        with self.assertRaisesRegex(ValueError, r"value\[0\].*cycle"):
            canonical_bytes(recursive_list)

        recursive_mapping = {}
        recursive_mapping["self"] = recursive_mapping
        with self.assertRaisesRegex(ValueError, r"value\[self\].*cycle"):
            canonical_bytes(recursive_mapping)

    def test_canonical_bytes_rejects_excessive_nesting_explicitly(self):
        root = []
        nested = root
        for _ in range(70):
            child = []
            nested.append(child)
            nested = child

        with self.assertRaisesRegex(ValueError, "maximum canonical JSON depth"):
            canonical_bytes(root)


class SeededOrderTests(unittest.TestCase):
    def test_seeded_order_is_stable_and_preserves_items(self):
        items = ["candidate-c", "candidate-a", "candidate-b"]

        first = seeded_order(items, "seed/material")
        second = seeded_order(reversed(items), "seed/material")

        self.assertEqual(first, second)
        self.assertCountEqual(first, items)
        self.assertIsInstance(first, tuple)

    def test_seeded_order_changes_with_seed_material(self):
        items = [f"item-{index}" for index in range(12)]

        self.assertNotEqual(
            seeded_order(items, "seed-a"),
            seeded_order(items, "seed-b"),
        )

    def test_seeded_order_rejects_duplicates_and_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "items contains duplicate"):
            seeded_order(["item-a", "item-a"], "seed")
        for items in ("item-a", ["item-a", ""], ["item-a", 1], [True]):
            with self.subTest(items=items):
                with self.assertRaisesRegex(ValueError, "items"):
                    seeded_order(items, "seed")
        with self.assertRaisesRegex(ValueError, "seed_material"):
            seeded_order(["item-a"], False)


class RecordTests(unittest.TestCase):
    def make_lineage(
        self,
        candidate=CANDIDATE_A,
        status="accepted",
        alias_of=None,
        parent_id=None,
        resolved_contract_sha256=SHA_B,
        evaluation_key="evaluation-1",
    ):
        return CandidateLineage(
            candidate_id=candidate,
            parent_id=parent_id,
            assignments={"axis-b": "choice-2", "axis-a": "choice-1"},
            repair_rule_id=None,
            resolved_contract_sha256=resolved_contract_sha256,
            evaluation_key=evaluation_key,
            status=status,
            alias_of=alias_of,
        )

    def make_stage(self, name="physical", status="passed"):
        return StageResult(
            name=name,
            version="v1",
            status=status,
            cache_key=SHA_A,
            input_hash=SHA_B,
            output={"z": 2, "a": [1, None]},
            diagnostics=(
                {"code": "Z.CODE", "message": "later"},
                {"code": "A.CODE", "message": "first"},
            ),
        )

    def make_result(self, candidates=(), stages=()):
        return HypothesisResult("space-1", SHA_A, 1, candidates, stages, {})

    def make_deep_parent_chain(self, count, cycle=False):
        candidate_ids = tuple(f"candidate-{index:024x}" for index in range(count))
        return tuple(
            CandidateLineage(
                candidate_id=candidate_id_value,
                parent_id=(
                    candidate_ids[index + 1]
                    if index + 1 < count
                    else candidate_ids[0] if cycle else None
                ),
                assignments={},
                repair_rule_id=None,
                resolved_contract_sha256=SHA_B,
                evaluation_key="evaluation-1",
                status="accepted",
            )
            for index, candidate_id_value in enumerate(candidate_ids)
        )

    def test_candidate_decision_is_frozen_and_derives_identity(self):
        decision = CandidateDecision(
            base_sha256=SHA_A,
            assignments={"axis-b": "choice-2", "axis-a": "choice-1"},
            seed=17,
            parent_id=CANDIDATE_A,
            repair_rule_id="repair-1",
        )

        self.assertEqual(
            decision.candidate_id,
            candidate_id(
                SHA_A,
                {"axis-a": "choice-1", "axis-b": "choice-2"},
                17,
                CANDIDATE_A,
                "repair-1",
            ),
        )
        self.assertEqual(
            decision.to_dict(),
            {
                "base_sha256": SHA_A,
                "assignments": {"axis-a": "choice-1", "axis-b": "choice-2"},
                "seed": 17,
                "parent_id": CANDIDATE_A,
                "repair_rule_id": "repair-1",
            },
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.seed = 18
        with self.assertRaises(TypeError):
            decision.assignments["axis-a"] = "changed"

    def test_candidate_lineage_serializes_deterministically(self):
        lineage = self.make_lineage()

        self.assertEqual(list(lineage.to_dict()["assignments"]), ["axis-a", "axis-b"])
        self.assertEqual(lineage.to_dict()["candidate_id"], CANDIDATE_A)
        canonical_bytes(lineage.to_dict())

    def test_candidate_lineage_rejects_malformed_candidate_references(self):
        invalid_records = (
            {"candidate": "candidate-" + "A" * 24},
            {"parent_id": "parent-1"},
            {"alias_of": "candidate-short"},
        )
        for invalid in invalid_records:
            field = next(iter(invalid))
            expected_name = "candidate_id" if field == "candidate" else field
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, expected_name):
                    self.make_lineage(**invalid)

    def test_stage_spec_validates_dependencies_and_budget(self):
        spec = StageSpec(
            name="objectives",
            version="v1",
            dependencies=("physical", "contract"),
            max_evaluations=12,
        )

        self.assertEqual(spec.to_dict()["dependencies"], ["contract", "physical"])
        with self.assertRaisesRegex(ValueError, "dependencies contains duplicate"):
            StageSpec("objectives", "v1", ("contract", "contract"), 1)
        for invalid in (True, 0, -1, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "max_evaluations"):
                    StageSpec("contract", "v1", (), invalid)

    def test_stage_result_returns_only_canonical_json_values(self):
        stage = self.make_stage()
        serialized = stage.to_dict()

        self.assertEqual(list(serialized["output"]), ["a", "z"])
        self.assertEqual(
            [item["code"] for item in serialized["diagnostics"]],
            ["A.CODE", "Z.CODE"],
        )
        self.assertIsInstance(serialized["diagnostics"], list)
        canonical_bytes(serialized)

    def test_stage_result_rejects_nested_cycles_with_the_failing_path(self):
        recursive_output = {"nested": []}
        recursive_output["nested"].append(recursive_output)

        with self.assertRaisesRegex(ValueError, r"output\[nested\]\[0\].*cycle"):
            StageResult("physical", "v1", "passed", SHA_A, SHA_B, recursive_output)

    def test_hypothesis_result_sorts_records_and_copies_metadata(self):
        metadata = {"z": 2, "a": {"nested": [1, True]}}
        result = HypothesisResult(
            space_id="space-1",
            space_sha256=SHA_C,
            seed=5,
            candidates=(
                self.make_lineage(CANDIDATE_B, status="rejected"),
                self.make_lineage(CANDIDATE_A),
            ),
            stages=(self.make_stage("physical"), self.make_stage("contract")),
            metadata=metadata,
        )
        metadata["z"] = 99
        serialized = result.to_dict()

        self.assertEqual(
            [item["candidate_id"] for item in serialized["candidates"]],
            [CANDIDATE_A, CANDIDATE_B],
        )
        self.assertEqual(
            [item["name"] for item in serialized["stages"]],
            ["contract", "physical"],
        )
        self.assertEqual(serialized["metadata"]["z"], 2)
        self.assertEqual(list(serialized["metadata"]), ["a", "z"])
        canonical_bytes(serialized)

    def test_hypothesis_result_rejects_duplicate_record_identities_in_any_order(self):
        candidate = self.make_lineage(CANDIDATE_A)
        duplicate_candidate = self.make_lineage(CANDIDATE_A, status="rejected")
        for records in (
            (candidate, duplicate_candidate),
            (duplicate_candidate, candidate),
        ):
            with self.subTest(kind="candidate", reversed=records[0] is duplicate_candidate):
                with self.assertRaisesRegex(ValueError, "duplicate candidate_id"):
                    self.make_result(candidates=records)

        stage = self.make_stage("physical", status="passed")
        duplicate_stage = self.make_stage("physical", status="failed")
        for records in ((stage, duplicate_stage), (duplicate_stage, stage)):
            with self.subTest(kind="stage", reversed=records[0] is duplicate_stage):
                with self.assertRaisesRegex(ValueError, "duplicate stage identity"):
                    self.make_result(stages=records)

    def test_hypothesis_result_requires_alias_status_exactly_with_alias_target(self):
        target = self.make_lineage(CANDIDATE_B)
        contradictions = (
            self.make_lineage(CANDIDATE_A, status="alias"),
            self.make_lineage(CANDIDATE_A, status="accepted", alias_of=CANDIDATE_B),
        )
        for candidate in contradictions:
            with self.subTest(status=candidate.status, alias_of=candidate.alias_of):
                with self.assertRaisesRegex(ValueError, r"status.*alias_of"):
                    self.make_result(candidates=(candidate, target))

    def test_hypothesis_result_rejects_self_and_missing_lineage_targets(self):
        invalid_candidates = (
            self.make_lineage(CANDIDATE_A, parent_id=CANDIDATE_A),
            self.make_lineage(
                CANDIDATE_A,
                status="alias",
                alias_of=CANDIDATE_A,
            ),
            self.make_lineage(CANDIDATE_A, parent_id=CANDIDATE_B),
            self.make_lineage(
                CANDIDATE_A,
                status="alias",
                alias_of=CANDIDATE_B,
            ),
        )
        for candidate in invalid_candidates:
            reference = "parent_id" if candidate.parent_id else "alias_of"
            expected = "differ from self" if (
                candidate.parent_id == candidate.candidate_id
                or candidate.alias_of == candidate.candidate_id
            ) else "target must exist"
            with self.subTest(reference=reference, expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    self.make_result(candidates=(candidate,))

    def test_hypothesis_result_rejects_parent_alias_and_cross_reference_cycles(self):
        cycles = (
            (
                self.make_lineage(CANDIDATE_A, parent_id=CANDIDATE_B),
                self.make_lineage(CANDIDATE_B, parent_id=CANDIDATE_A),
            ),
            (
                self.make_lineage(CANDIDATE_A, parent_id=CANDIDATE_B),
                self.make_lineage(CANDIDATE_B, status="alias", alias_of=CANDIDATE_A),
            ),
        )
        for index, candidates in enumerate(cycles):
            with self.subTest(cycle=index):
                with self.assertRaisesRegex(ValueError, "lineage cycle"):
                    self.make_result(candidates=candidates)

    def test_hypothesis_result_handles_a_valid_10000_node_parent_chain(self):
        result = self.make_result(candidates=self.make_deep_parent_chain(10_000))

        self.assertEqual(len(result.candidates), 10_000)

    def test_hypothesis_result_rejects_a_deep_cycle_without_recursion_error(self):
        with self.assertRaisesRegex(ValueError, "lineage cycle"):
            self.make_result(candidates=self.make_deep_parent_chain(10_000, cycle=True))

    def test_hypothesis_result_accepts_alias_matching_a_canonical_target(self):
        target = self.make_lineage(CANDIDATE_B)
        valid_alias = self.make_lineage(
            CANDIDATE_A,
            status="alias",
            alias_of=CANDIDATE_B,
        )
        self.assertEqual(
            len(self.make_result(candidates=(valid_alias, target)).candidates),
            2,
        )

    def test_hypothesis_result_rejects_alias_to_alias(self):
        valid_alias = self.make_lineage(
            CANDIDATE_A,
            status="alias",
            alias_of=CANDIDATE_B,
        )
        alias_target = self.make_lineage(
            CANDIDATE_B,
            status="alias",
            alias_of=CANDIDATE_C,
        )
        canonical_target = self.make_lineage(CANDIDATE_C)
        with self.assertRaisesRegex(ValueError, "canonical non-alias"):
            self.make_result(
                candidates=(valid_alias, alias_target, canonical_target)
            )

    def test_hypothesis_result_rejects_alias_hash_mismatch(self):
        target = self.make_lineage(CANDIDATE_B)
        hash_mismatch = self.make_lineage(
            CANDIDATE_A,
            status="alias",
            alias_of=CANDIDATE_B,
            resolved_contract_sha256=SHA_C,
        )
        with self.assertRaisesRegex(ValueError, "resolved_contract_sha256.*match"):
            self.make_result(candidates=(hash_mismatch, target))

    def test_hypothesis_result_rejects_alias_evaluation_key_mismatch(self):
        target = self.make_lineage(CANDIDATE_B)
        evaluation_mismatch = self.make_lineage(
            CANDIDATE_A,
            status="alias",
            alias_of=CANDIDATE_B,
            evaluation_key="evaluation-2",
        )
        with self.assertRaisesRegex(ValueError, "evaluation_key.*match"):
            self.make_result(candidates=(evaluation_mismatch, target))

    def test_records_reject_bad_hash_status_and_nested_types(self):
        with self.assertRaisesRegex(ValueError, "resolved_contract_sha256"):
            CandidateLineage(
                CANDIDATE_A,
                None,
                {"axis": "choice"},
                None,
                "B" * 64,
                "evaluation-1",
                "accepted",
            )
        with self.assertRaisesRegex(ValueError, "status"):
            self.make_lineage(status="maybe")
        with self.assertRaisesRegex(ValueError, "status"):
            self.make_stage(status=True)
        with self.assertRaisesRegex(ValueError, r"output\[nested\]\[0\]"):
            StageResult(
                "physical",
                "v1",
                "passed",
                SHA_A,
                SHA_B,
                {"nested": [math.nan]},
            )
        with self.assertRaisesRegex(ValueError, r"candidates\[0\]"):
            HypothesisResult("space-1", SHA_A, 1, (True,), (), {})
        with self.assertRaisesRegex(ValueError, r"stages\[0\]"):
            HypothesisResult("space-1", SHA_A, 1, (), ({"name": "stage"},), {})
        with self.assertRaisesRegex(ValueError, r"metadata\[bad\]"):
            HypothesisResult("space-1", SHA_A, 1, (), (), {"bad": object()})

    def test_record_collection_inputs_reject_strings_and_booleans(self):
        with self.assertRaisesRegex(ValueError, "dependencies"):
            StageSpec("contract", "v1", "physical", 1)
        with self.assertRaisesRegex(ValueError, "diagnostics"):
            StageResult("physical", "v1", "passed", SHA_A, SHA_B, {}, True)
        with self.assertRaisesRegex(ValueError, "candidates"):
            HypothesisResult("space-1", SHA_A, 1, True, (), {})


if __name__ == "__main__":
    unittest.main()
