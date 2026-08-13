import copy
import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.simulation import evaluate_simulation_admission  # noqa: E402
from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402


CANDIDATE = "candidate-" + "1" * 24
RESOLVED_CONTRACT = {
    "candidate_id": CANDIDATE,
    "schema_version": 1,
    "quantities": [{"id": "robot_mass", "value": {"value": 100.0, "unit": "kg"}}],
}
SHA_A = hashlib.sha256(
    canonical_bytes({key: value for key, value in RESOLVED_CONTRACT.items() if key != "candidate_id"})
).hexdigest()
SHA_FULL = hashlib.sha256(canonical_bytes(RESOLVED_CONTRACT)).hexdigest()


def physical_report():
    return {
        "candidate_id": CANDIDATE,
        "promotable": False,
        "diagnostics": [
            {
                "code": "BOM.PLACEHOLDER_BLOCKS_CLAIM",
                "severity": "indeterminate",
                "path": "components[0]",
                "message": "engineering placeholder",
                "evidence_ids": [],
            }
        ],
        "analyses": [
            {"name": "drivetrain", "version": "v1", "passed": True, "outputs": {}},
            {"name": "stability", "version": "v1", "passed": True, "outputs": {}},
        ],
        "metadata": {"contract_sha256": SHA_FULL},
    }


def hypothesis_report():
    return {
        "candidate_id": CANDIDATE,
        "resolved_contract_sha256": SHA_A,
        "contract_passed": True,
        "physical_passed": False,
        "hard_counterexample": False,
        "complete": True,
        "blocking_diagnostics": ["BOM.PLACEHOLDER_BLOCKS_CLAIM"],
    }


class SimulationAdmissionTests(unittest.TestCase):
    def test_placeholder_only_analytically_clean_candidate_is_admitted(self):
        decision = evaluate_simulation_admission(
            physical_report(), hypothesis_report(), RESOLVED_CONTRACT
        )
        self.assertEqual(decision.status, "simulation_admitted")
        self.assertEqual(decision.evidence_level, "simulation_admitted")
        self.assertFalse(decision.hardware_promotable)
        self.assertEqual(
            decision.remaining_blockers, ("BOM.PLACEHOLDER_BLOCKS_CLAIM",)
        )

    def test_nonplaceholder_physical_blockers_reject_admission(self):
        for code in (
            "PHY.DRIVE.PEAK_TORQUE",
            "COMPONENT.REQUIRED_ROLE",
            "PHY.DRIVE.CARDINALITY_MISMATCH",
            "EVIDENCE.STALE_ARTIFACT",
            "REQ.UNKNOWN_SAFETY",
        ):
            with self.subTest(code=code):
                report = physical_report()
                report["diagnostics"].append(
                    {"code": code, "severity": "error", "path": "x", "message": "blocked", "evidence_ids": []}
                )
                decision = evaluate_simulation_admission(report, hypothesis_report(), RESOLVED_CONTRACT)
                self.assertEqual(decision.status, "rejected")
                self.assertIn(code, decision.remaining_blockers)

    def test_empty_failed_or_indeterminate_analyses_reject(self):
        cases = ([], [{"name": "drive", "passed": False}], [{"name": "drive", "passed": None}])
        for analyses in cases:
            with self.subTest(analyses=analyses):
                report = physical_report()
                report["analyses"] = analyses
                decision = evaluate_simulation_admission(report, hypothesis_report(), RESOLVED_CONTRACT)
                self.assertEqual(decision.status, "rejected")
                self.assertIn("SIM.ADMISSION.ANALYSIS", decision.remaining_blockers)

    def test_hard_counterexample_incomplete_or_failed_contract_rejects(self):
        for field, value, code in (
            ("hard_counterexample", True, "SIM.ADMISSION.HARD_COUNTEREXAMPLE"),
            ("complete", False, "SIM.ADMISSION.INCOMPLETE"),
            ("contract_passed", False, "SIM.ADMISSION.CONTRACT"),
        ):
            report = hypothesis_report()
            report[field] = value
            decision = evaluate_simulation_admission(physical_report(), report, RESOLVED_CONTRACT)
            self.assertEqual(decision.status, "rejected")
            self.assertIn(code, decision.remaining_blockers)

    def test_identity_hash_and_blocker_inventory_must_match(self):
        attacks = []
        report = hypothesis_report()
        report["candidate_id"] = "candidate-" + "2" * 24
        attacks.append(report)
        report = hypothesis_report()
        report["resolved_contract_sha256"] = "b" * 64
        attacks.append(report)
        report = hypothesis_report()
        report["blocking_diagnostics"] = []
        attacks.append(report)
        for attack in attacks:
            with self.subTest(attack=attack):
                decision = evaluate_simulation_admission(physical_report(), attack, RESOLVED_CONTRACT)
                self.assertEqual(decision.status, "rejected")
                self.assertTrue(any(code.startswith("SIM.ADMISSION") for code in decision.remaining_blockers))

    def test_malformed_nested_collections_fail_closed_without_traceback(self):
        malformed = (
            ("diagnostics", []),
            ("analyses", "bad"),
            ("metadata", []),
        )
        for field, value in malformed:
            report = physical_report()
            report[field] = value
            with self.subTest(field=field):
                decision = evaluate_simulation_admission(report, hypothesis_report(), RESOLVED_CONTRACT)
                self.assertIn(decision.status, {"rejected", "indeterminate"})

    def test_inputs_are_not_mutated_and_caller_cannot_request_hardware_promotion(self):
        physical = physical_report()
        hypothesis = hypothesis_report()
        before = copy.deepcopy((physical, hypothesis))
        hypothesis["hardware_promotable"] = True
        decision = evaluate_simulation_admission(physical, hypothesis, RESOLVED_CONTRACT)
        self.assertEqual(decision.status, "rejected")
        self.assertFalse(decision.hardware_promotable)
        del hypothesis["hardware_promotable"]
        evaluate_simulation_admission(physical, hypothesis, RESOLVED_CONTRACT)
        self.assertEqual((physical, hypothesis), before)

    def test_physical_report_and_nested_records_are_closed(self):
        attacks = []
        report = physical_report()
        report["hardware_promotable"] = True
        attacks.append(report)
        report = physical_report()
        report["diagnostics"][0]["accepted"] = True
        attacks.append(report)
        report = physical_report()
        report["analyses"][0]["hardware_passed"] = True
        attacks.append(report)
        report = physical_report()
        report["analyses"].append(dict(report["analyses"][0]))
        attacks.append(report)
        report = physical_report()
        report["diagnostics"][0]["path"] = []
        attacks.append(report)
        report = physical_report()
        report["analyses"][0]["outputs"] = []
        attacks.append(report)
        report = physical_report()
        report["analyses"][0]["analysis_id"] = False
        attacks.append(report)
        report = physical_report()
        report["analyses"][0]["evidence_level"] = "certified"
        attacks.append(report)
        for attack in attacks:
            with self.subTest(attack=attack):
                decision = evaluate_simulation_admission(attack, hypothesis_report(), RESOLVED_CONTRACT)
                self.assertEqual(decision.status, "rejected")
                self.assertIn("SIM.ADMISSION.MALFORMED", decision.remaining_blockers)

        report = physical_report()
        report["metadata"]["contract_sha256"] = "b" * 64
        decision = evaluate_simulation_admission(report, hypothesis_report(), RESOLVED_CONTRACT)
        self.assertEqual(decision.status, "rejected")
        self.assertIn("SIM.ADMISSION.HASH", decision.remaining_blockers)

    def test_resolved_contract_content_and_candidate_are_recomputed(self):
        mutated = copy.deepcopy(RESOLVED_CONTRACT)
        mutated["quantities"][0]["value"]["value"] = 101.0
        decision = evaluate_simulation_admission(physical_report(), hypothesis_report(), mutated)
        self.assertEqual(decision.status, "rejected")
        self.assertIn("SIM.ADMISSION.HASH", decision.remaining_blockers)

        wrong_candidate = copy.deepcopy(RESOLVED_CONTRACT)
        wrong_candidate["candidate_id"] = "candidate-" + "2" * 24
        decision = evaluate_simulation_admission(physical_report(), hypothesis_report(), wrong_candidate)
        self.assertEqual(decision.status, "rejected")
        self.assertIn("SIM.ADMISSION.IDENTITY", decision.remaining_blockers)


if __name__ == "__main__":
    unittest.main()
