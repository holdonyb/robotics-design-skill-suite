import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.objectives import extract_vector, pareto_fronts  # noqa: E402


def contract():
    return {
        "quantities": [{"id": "Q-MASS", "dimension": "mass", "value": {"value": 12, "unit": "kg"}, "evidence_level": "calculated"}],
        "evidence": [],
    }


def report(*, promotable=True, diagnostics=()):
    return {
        "promotable": promotable,
        "diagnostics": list(diagnostics),
        "analyses": [{"analysis_id": "AN-RUNTIME", "outputs": {"runtime": {"seconds": 120.0}}}],
        "metadata": {"minimum_evidence_level": "calculated"},
    }


OBJECTIVES = [
    {"id": "mass", "source": "quantity:Q-MASS", "direction": "min"},
    {"id": "runtime", "source": "analysis:AN-RUNTIME.outputs.runtime.seconds", "direction": "max"},
    {"id": "evidence", "source": "evidence:minimum-level", "direction": "max"},
    {"id": "blockers", "source": "diagnostics:blocking-count", "direction": "min"},
]


class ObjectiveVectorTests(unittest.TestCase):
    def test_extracts_all_four_sources_in_si_with_explicit_evidence_ordinal(self):
        vector = extract_vector("candidate-" + "a" * 24, contract(), report(), OBJECTIVES)
        self.assertTrue(vector.eligible)
        self.assertEqual({"mass": 12.0, "runtime": 120.0, "evidence": 3.0, "blockers": 0.0}, dict(vector.values))
        self.assertEqual({}, dict(vector.reasons))

    def test_blocked_or_malformed_candidates_are_ineligible_with_actionable_reasons(self):
        blocked = extract_vector("candidate-" + "a" * 24, contract(), report(promotable=False), OBJECTIVES)
        malformed = extract_vector("candidate-" + "b" * 24, contract(), report(), [{"id": "bad", "source": "analysis:AN-RUNTIME.outputs.missing", "direction": "min"}])
        self.assertFalse(blocked.eligible)
        self.assertIn("report.promotable", blocked.reasons["candidate"])
        self.assertFalse(malformed.eligible)
        self.assertIn("missing", malformed.reasons["bad"])

    def test_rejects_boolean_nonfinite_duplicate_and_unknown_objectives_fail_closed(self):
        for objectives in (
            [{"id": "x", "source": "quantity:Q-MASS", "direction": "sideways"}],
            [{"id": "x", "source": "quantity:Q-MASS", "direction": "min"}, {"id": "x", "source": "quantity:Q-MASS", "direction": "min"}],
            [{"id": "x", "source": "quantity:Q-MASS", "direction": "min"}],
        ):
            bad_contract = contract()
            if len(objectives) == 1 and objectives[0]["id"] == "x":
                bad_contract["quantities"][0]["value"]["value"] = math.nan
            vector = extract_vector("candidate-" + "a" * 24, bad_contract, report(), objectives)
            self.assertFalse(vector.eligible)

    def test_pareto_fronts_are_deterministic_directional_and_unweighted(self):
        vectors = {
            "long": {"mass": 12.0, "runtime": 140.0},
            "light": {"mass": 10.0, "runtime": 100.0},
            "dominated": {"mass": 13.0, "runtime": 90.0},
            "equal": {"mass": 10.0, "runtime": 100.0},
        }
        result = pareto_fronts(vectors, {"mass": "min", "runtime": "max"})
        self.assertEqual((("equal", "light", "long"), ("dominated",)), result.fronts)
        self.assertEqual((("equal", "dominated"), ("light", "dominated"), ("long", "dominated")), result.dominance_edges)
        self.assertNotIn("score", json.dumps(result.to_dict(), sort_keys=True))

    def test_ineligible_and_malformed_vectors_never_enter_fronts(self):
        good = extract_vector("candidate-" + "a" * 24, contract(), report(), OBJECTIVES)
        bad = extract_vector("candidate-" + "b" * 24, contract(), report(promotable=False), OBJECTIVES)
        result = pareto_fronts({good.candidate_id: good, bad.candidate_id: bad}, {item["id"]: item["direction"] for item in OBJECTIVES})
        self.assertEqual(((good.candidate_id,),), result.fronts)
        self.assertEqual((bad.candidate_id,), result.ineligible)

    def test_identity_and_report_consistency_are_fail_closed(self):
        candidate = "candidate-" + "a" * 24
        inconsistent = report(); inconsistent["candidate_id"] = "candidate-" + "b" * 24
        vector = extract_vector(candidate, contract(), inconsistent, OBJECTIVES)
        self.assertFalse(vector.eligible)
        self.assertIn("match", vector.reasons["candidate"])
        with self.assertRaisesRegex(ValueError, "match mapping key"):
            pareto_fronts({"candidate-" + "b" * 24: extract_vector(candidate, contract(), report(), OBJECTIVES)}, {item["id"]: item["direction"] for item in OBJECTIVES})
        mismatched_contract = contract(); mismatched_contract["candidate_id"] = "candidate-" + "b" * 24
        vector = extract_vector(candidate, mismatched_contract, report(), OBJECTIVES)
        self.assertFalse(vector.eligible)
        self.assertIn("contract.candidate_id", vector.reasons["candidate"])

    def test_metadata_mixed_keys_and_huge_integers_fail_closed(self):
        bad_report = report(); bad_report["metadata"] = []
        vector = extract_vector(
            "candidate-" + "a" * 24,
            contract(),
            bad_report,
            [{"id": "evidence", "source": "evidence:minimum-level", "direction": "max"}],
        )
        self.assertFalse(vector.eligible)
        self.assertIn("metadata", vector.reasons["evidence"])
        with self.assertRaisesRegex(ValueError, "candidate identifiers"):
            pareto_fronts({"a": {"x": 1}, 1: {"x": 1}}, {"x": "min"})
        result = pareto_fronts({"huge": {"x": 10**1000}, "valid": {"x": 1}}, {"x": "min"})
        self.assertEqual((("valid",),), result.fronts)
        self.assertEqual(("huge",), result.ineligible)

    def test_malformed_report_diagnostics_are_ineligible_not_tracebacks(self):
        for diagnostics in (None, "wrong"):
            source = report(); source["diagnostics"] = diagnostics
            vector = extract_vector("candidate-" + "a" * 24, contract(), source, OBJECTIVES)
            self.assertFalse(vector.eligible)
            self.assertIn("diagnostics", vector.reasons["candidate"])


if __name__ == "__main__":
    unittest.main()
