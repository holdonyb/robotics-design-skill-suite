import copy
import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.hypothesis.overlay import (  # noqa: E402
    OverlayError,
    apply_operation,
    generate_candidates,
)
from tests.test_assurance_contract import valid_contract  # noqa: E402


def design_space() -> dict:
    return {
        "schema_version": 1,
        "space_id": "overlay-test",
        "base_contract": {"path": "design-contract.json", "sha256": "a" * 64},
        "max_candidates": 4,
        "axes": [
            {
                "id": "wheel",
                "choices": [
                    {"id": "small", "operations": [{"target": "quantity:Q-PAYLOAD.value", "value": {"value": 4, "unit": "kg"}}]},
                    {"id": "large", "operations": [{"target": "quantity:Q-PAYLOAD.value", "value": {"value": 5, "unit": "kg"}}]},
                ],
            },
            {
                "id": "motor",
                "choices": [
                    {"id": "b", "operations": [{"target": "architecture.features", "value": ["mobile_base"]}]},
                    {"id": "a", "operations": [{"target": "architecture.features", "value": ["mobile_base"]}]},
                ],
            },
        ],
        "uncertainties": [],
        "objectives": [],
        "repair_rules": [],
        "evaluation": {"max_stage_evaluations": 32, "stages": ["contract_v1", "physical_v030"]},
    }


class OverlayOperationTests(unittest.TestCase):
    def test_quantity_operation_is_immutable_and_resolves_by_id(self):
        base = valid_contract()
        before = copy.deepcopy(base)
        result = apply_operation(base, {"target": "quantity:Q-PAYLOAD.value", "value": {"value": 7, "unit": "kg"}})
        self.assertEqual(base, before)
        self.assertEqual(result["quantities"][0]["value"], {"value": 7, "unit": "kg"})

    def test_whole_component_evidence_and_architecture_replacements(self):
        base = valid_contract()
        component = copy.deepcopy(base["components"][0])
        evidence = copy.deepcopy(base["evidence"][0])
        result = apply_operation(base, {"target": f"component:{component['id']}", "value": component})
        result = apply_operation(result, {"target": f"evidence:{evidence['id']}", "value": evidence})
        result = apply_operation(result, {"target": "architecture.features", "value": ["mobile_base"]})
        self.assertEqual(result["architecture"]["features"], ["mobile_base"])

    def test_missing_duplicate_or_identity_mismatched_targets_fail(self):
        base = valid_contract()
        with self.assertRaisesRegex(OverlayError, "does not exist"):
            apply_operation(base, {"target": "quantity:Q-NOPE.value", "value": {"value": 1, "unit": "kg"}})
        duplicate = copy.deepcopy(base)
        duplicate["quantities"].append(copy.deepcopy(duplicate["quantities"][0]))
        with self.assertRaisesRegex(OverlayError, "not unique"):
            apply_operation(duplicate, {"target": "quantity:Q-PAYLOAD.value", "value": {"value": 1, "unit": "kg"}})
        with self.assertRaisesRegex(OverlayError, "same id"):
            apply_operation(base, {"target": f"component:{base['components'][0]['id']}", "value": {"id": "OTHER"}})

    def test_forbidden_partial_or_obligation_mutations_are_impossible(self):
        base = valid_contract()
        for target in (
            "requirement:REQ-X.statement",
            "analysis:AN-X.inputs",
            "artifact:robot.sha256",
            "component:C.role",
            "candidate_id",
        ):
            with self.subTest(target=target), self.assertRaisesRegex(OverlayError, "unsupported semantic target"):
                apply_operation(base, {"target": target, "value": None})


class CandidateGenerationTests(unittest.TestCase):
    def test_axes_resolve_in_canonical_order_and_inputs_are_unchanged(self):
        base = valid_contract()
        space = design_space()
        before_base, before_space = copy.deepcopy(base), copy.deepcopy(space)
        candidates = generate_candidates(space, base, seed=11)
        self.assertEqual([dict(item.decision.assignments) for item in candidates], [
            {"motor": "a", "wheel": "large"},
            {"motor": "a", "wheel": "small"},
            {"motor": "b", "wheel": "large"},
            {"motor": "b", "wheel": "small"},
        ])
        self.assertEqual(base, before_base)
        self.assertEqual(space, before_space)
        for item in candidates:
            self.assertEqual(item.resolved_contract["candidate_id"], item.candidate_id)

    def test_content_hash_omits_only_candidate_id_and_duplicates_are_aliases(self):
        base = valid_contract()
        space = design_space()
        # Motor choices intentionally resolve to the same content.
        candidates = generate_candidates(space, base, seed=11)
        self.assertIsNone(candidates[0].alias_of)
        self.assertEqual(candidates[2].alias_of, candidates[0].candidate_id)
        contract = candidates[0].resolved_contract
        without_id = {key: value for key, value in contract.items() if key != "candidate_id"}
        self.assertEqual(candidates[0].resolved_contract_sha256, hashlib.sha256(canonical_bytes(without_id)).hexdigest())

    def test_seed_changes_candidate_identity_but_not_resolved_content_hash(self):
        first = generate_candidates(design_space(), valid_contract(), seed=1)
        second = generate_candidates(design_space(), valid_contract(), seed=2)
        self.assertNotEqual(first[0].candidate_id, second[0].candidate_id)
        self.assertEqual(first[0].resolved_contract_sha256, second[0].resolved_contract_sha256)

    def test_invalid_space_and_budget_fail_before_generation(self):
        space = design_space()
        space["max_candidates"] = 3
        with self.assertRaisesRegex(OverlayError, "Cartesian product"):
            generate_candidates(space, valid_contract(), seed=1)

    def test_contract_errors_are_retained_without_claiming_validity(self):
        base = valid_contract()
        base["status"] = "invented"
        candidates = generate_candidates(design_space(), base, seed=1)
        self.assertTrue(candidates[0].contract_errors)
        self.assertTrue(any("status must be one of" in error for error in candidates[0].contract_errors))


if __name__ == "__main__":
    unittest.main()
