import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.uncertainty import (  # noqa: E402
    UncertaintyError,
    apply_case,
    evaluate_sensitivity,
    ordered_cases,
    search_counterexample,
)

CANDIDATE_ID = "candidate-" + "a" * 24


def contract():
    return {
        "candidate_id": CANDIDATE_ID,
        "quantities": [
            {"id": "Q-SLOPE", "dimension": "angle", "value": {"value": 5, "unit": "deg"}},
            {"id": "Q-MASS", "dimension": "mass", "value": {"value": 10, "unit": "kg"}},
        ],
    }


def uncertainties():
    return [
        {"id": "slope", "target": "quantity:Q-SLOPE.value", "values": [
            {"value": 8, "unit": "deg"}, {"value": 6, "unit": "deg"}], "hard": True},
        {"id": "mass", "target": "quantity:Q-MASS.value", "values": [
            {"value": 11, "unit": "kg"}, {"value": 12, "unit": "kg"}], "hard": False},
    ]


class OrderedCaseTests(unittest.TestCase):
    def test_nominal_first_same_seed_exact_and_different_seed_same_set(self):
        a = ordered_cases(CANDIDATE_ID, contract(), uncertainties(), seed=5, max_evaluations=5)
        b = ordered_cases(CANDIDATE_ID, contract(), uncertainties(), seed=5, max_evaluations=5)
        c = ordered_cases(CANDIDATE_ID, contract(), uncertainties(), seed=6, max_evaluations=5)
        self.assertEqual(a, b)
        self.assertTrue(a[0].nominal and c[0].nominal)
        self.assertEqual({case.case_id for case in a}, {case.case_id for case in c})
        self.assertEqual({}, a[0].to_dict()["values"])

    def test_cartesian_cases_are_unique_content_addressed_and_immutable(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties(), seed=5, max_evaluations=5)
        self.assertEqual(5, len(cases))
        self.assertEqual(5, len({case.case_id for case in cases}))
        with self.assertRaises(TypeError):
            cases[1].values["x"] = 1
        self.assertEqual(cases[1].to_dict(), copy.deepcopy(cases[1].to_dict()))

    def test_budget_is_rejected_before_cartesian_materialization(self):
        source = contract()
        huge = []
        for index in range(20):
            source["quantities"].append({"id": f"Q-U{index}", "dimension": "angle", "value": {"value": 0, "unit": "deg"}})
            huge.append({"id": f"u{index}", "target": f"quantity:Q-U{index}.value", "values": [
                {"value": value, "unit": "deg"} for value in range(20)
            ], "hard": True})
        with self.assertRaisesRegex(UncertaintyError, "max_evaluations"):
            ordered_cases(CANDIDATE_ID, source, huge, seed=1, max_evaluations=1_000_000)

    def test_bad_identity_seed_types_nonfinite_and_duplicate_values_are_rejected(self):
        with self.assertRaisesRegex(UncertaintyError, "candidate_id"):
            ordered_cases("bad", contract(), uncertainties(), seed=1, max_evaluations=5)
        with self.assertRaisesRegex(UncertaintyError, "seed"):
            ordered_cases(CANDIDATE_ID, contract(), uncertainties(), seed=True, max_evaluations=5)
        bad = uncertainties(); bad[0]["values"][0]["value"] = math.nan
        with self.assertRaisesRegex(UncertaintyError, "finite"):
            ordered_cases(CANDIDATE_ID, contract(), bad, seed=1, max_evaluations=5)
        duplicate = uncertainties(); duplicate[0]["values"][1] = dict(duplicate[0]["values"][0])
        with self.assertRaisesRegex(UncertaintyError, "duplicate"):
            ordered_cases(CANDIDATE_ID, contract(), duplicate, seed=1, max_evaluations=5)

    def test_targets_must_be_unique_existing_quantity_values_with_same_unit_dimension(self):
        bad = uncertainties(); bad[0]["target"] = "quantity:MISSING.value"
        with self.assertRaisesRegex(UncertaintyError, "does not exist"):
            ordered_cases(CANDIDATE_ID, contract(), bad, seed=1, max_evaluations=5)
        bad = uncertainties(); bad[0]["values"][0] = {"value": 1, "unit": "kg"}
        with self.assertRaisesRegex(UncertaintyError, "expected angle"):
            ordered_cases(CANDIDATE_ID, contract(), bad, seed=1, max_evaluations=5)
        bad = uncertainties(); bad[1]["target"] = bad[0]["target"]
        with self.assertRaisesRegex(UncertaintyError, "duplicate target"):
            ordered_cases(CANDIDATE_ID, contract(), bad, seed=1, max_evaluations=5)

    def test_zero_range_distance_is_finite_and_apply_case_preserves_inputs(self):
        source = contract()
        zero = [{"id": "zero", "target": "quantity:Q-SLOPE.value", "values": [{"value": 5, "unit": "deg"}], "hard": True}]
        cases = ordered_cases(CANDIDATE_ID, source, zero, seed=1, max_evaluations=2)
        self.assertTrue(math.isfinite(cases[1].distance))
        changed = apply_case(source, cases[1])
        self.assertEqual({"value": 5, "unit": "deg"}, changed["quantities"][0]["value"])
        self.assertEqual(contract(), source)


class CounterexampleTests(unittest.TestCase):
    def test_smallest_hard_counterexample_blocks_by_distance_then_case_id(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties()[:1], seed=5, max_evaluations=3)
        def evaluate(case):
            value = case.to_dict()["values"].get("quantity:Q-SLOPE.value", {}).get("value", 5)
            return {"promotable": value < 8, "diagnostic_codes": ["PHY.STABILITY.MARGIN"] if value >= 8 else [], "objectives": {"margin": 8 - value}}
        result = search_counterexample(cases, evaluate)
        self.assertTrue(result.blocking)
        self.assertEqual({"quantity:Q-SLOPE.value": {"value": 8, "unit": "deg"}}, result.case.to_dict()["values"])
        self.assertEqual(["PHY.STABILITY.MARGIN"], result.to_dict()["diagnostic_codes"])

    def test_soft_failure_is_explicit_risk_but_not_blocking(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties()[1:], seed=2, max_evaluations=3)
        result = search_counterexample(cases, lambda case: {
            "promotable": case.nominal, "diagnostic_codes": [] if case.nominal else ["PHY.SOFT"], "objectives": {"mass": 10},
        })
        self.assertFalse(result.blocking)
        self.assertIsNone(result.case)
        self.assertEqual(2, len(result.soft_risks))

    def test_callback_exception_and_malformed_result_are_actionable(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties()[:1], seed=1, max_evaluations=3)
        with self.assertRaisesRegex(UncertaintyError, "evaluation callback failed"):
            search_counterexample(cases, lambda case: 1 / 0)
        with self.assertRaisesRegex(UncertaintyError, "evaluation result"):
            search_counterexample(cases, lambda case: {"promotable": "yes"})

    def test_sensitivity_has_finite_objective_deltas_and_new_diagnostics(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties()[:1], seed=1, max_evaluations=3)
        def evaluate(case):
            value = case.to_dict()["values"].get("quantity:Q-SLOPE.value", {}).get("value", 5)
            return {"promotable": value < 8, "diagnostic_codes": ["PHY.BLOCK"] if value >= 8 else ["BASE"], "objectives": {"margin": float(10 - value)}}
        records = evaluate_sensitivity(cases, evaluate)
        eight = next(record for record in records if record.objective_deltas["margin"] == -3.0)
        self.assertEqual(("PHY.BLOCK",), eight.newly_blocking_diagnostic_codes)
        with self.assertRaisesRegex(UncertaintyError, "finite"):
            evaluate_sensitivity(cases, lambda case: {"promotable": True, "diagnostic_codes": [], "objectives": {"x": math.inf}})

    def test_cartesian_cases_reconstruct_four_unique_oat_sensitivity_probes(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties(), seed=1, max_evaluations=5)
        seen = []
        def evaluate(case):
            values = case.to_dict()["values"]
            seen.append(values)
            return {"promotable": True, "diagnostic_codes": [], "objectives": {"count": float(len(values))}}
        records = evaluate_sensitivity(cases, evaluate)
        self.assertEqual(4, len(records))
        self.assertEqual(4, len({record.case_id for record in records}))
        self.assertEqual([0, 1, 1, 1, 1], [len(values) for values in seen])

    def test_counterexample_callback_order_is_nominal_then_distance_and_case_id(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties()[:1], seed=9, max_evaluations=3)
        observed = []
        search_counterexample(cases, lambda case: (
            observed.append(case.case_id)
            or {"promotable": True, "diagnostic_codes": [], "objectives": {}}
        ))
        expected = [cases[0].case_id] + [case.case_id for case in sorted(cases[1:], key=lambda item: (item.distance, item.case_id))]
        self.assertEqual(expected, observed)

    def test_nominally_blocked_candidate_cannot_report_perturbation_counterexample(self):
        cases = ordered_cases(CANDIDATE_ID, contract(), uncertainties()[:1], seed=1, max_evaluations=3)
        with self.assertRaisesRegex(UncertaintyError, "already blocked at nominal case"):
            search_counterexample(cases, lambda case: {
                "promotable": False, "diagnostic_codes": ["BASE.BLOCK"], "objectives": {},
            })


if __name__ == "__main__":
    unittest.main()
