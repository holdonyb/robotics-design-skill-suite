import copy
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes
from assurance.hypothesis.model import CandidateDecision
from assurance.hypothesis.overlay import ResolvedCandidate
from assurance.hypothesis.repair import RepairError, repair, select_repair

CANDIDATE = "candidate-" + "a" * 24

def parent():
    contract = {"schema_version": 1, "candidate_id": CANDIDATE, "quantities": [{"id": "Q-MOTOR", "owner": "component:CMP-MOTOR", "value": {"value": 1, "unit": "N*m"}}], "components": [{"id": "CMP-MOTOR", "source_evidence": "evidence:EV-MOTOR"}], "evidence": [{"id": "EV-MOTOR"}]}
    decision = CandidateDecision("a" * 64, {"axis": "choice"}, 1)
    contract["candidate_id"] = decision.candidate_id
    digest = hashlib.sha256(canonical_bytes({key: value for key, value in contract.items() if key != "candidate_id"})).hexdigest()
    return ResolvedCandidate(decision, contract, digest, ())

def rule(target="quantity:Q-MOTOR.value"):
    return {"id": "motor-fix", "diagnostic_code": "PHY.MOTOR", "owner_prefix": "component:CMP-MOTOR", "operations": [{"target": target, "value": {"value": 2, "unit": "N*m"}}], "max_applications": 1}

class RepairTests(unittest.TestCase):
    def test_owned_quantity_repair_creates_immutable_child_and_trace(self):
        source = parent(); before = copy.deepcopy(source.resolved_contract)
        child, trace = repair(source, {"code": "PHY.MOTOR", "path": "quantity:Q-MOTOR.value", "message": "low"}, rule(), seen_hashes=set(), failed_stage="physical_v030")
        self.assertEqual(source.candidate_id, child.decision.parent_id)
        self.assertNotEqual(source.candidate_id, child.candidate_id)
        self.assertEqual("component:CMP-MOTOR", trace.owner)
        self.assertNotEqual(trace.before_hash, trace.after_hash)
        self.assertEqual(before, source.resolved_contract)
        self.assertEqual(("physical_v030", "uncertainty_v1", "counterexample_v1", "objectives_v1"), trace.rerun_stages)

    def test_unowned_or_forbidden_operation_is_rejected(self):
        diagnostic = {"code": "PHY.MOTOR", "path": "quantity:Q-MOTOR.value", "message": "low"}
        with self.assertRaisesRegex(RepairError, "outside diagnostic owner"):
            repair(parent(), diagnostic, rule("quantity:Q-OTHER.value"), seen_hashes=set(), failed_stage="physical_v030")
        with self.assertRaisesRegex(RepairError, "forbidden"):
            repair(parent(), diagnostic, rule("requirements[0].statement"), seen_hashes=set(), failed_stage="physical_v030")

    def test_malformed_owner_rule_stage_counts_and_cycles_fail_closed(self):
        diagnostic = {"code": "PHY.MOTOR", "path": "unknown", "message": "low", "owner": "component:CMP-MOTOR"}
        with self.assertRaisesRegex(RepairError, "owner"):
            repair(parent(), diagnostic, rule(), seen_hashes=set(), failed_stage="physical_v030")
        with self.assertRaisesRegex(RepairError, "unknown stage"):
            repair(parent(), {"code": "PHY.MOTOR", "path": "quantity:Q-MOTOR.value", "message": "low"}, rule(), seen_hashes=set(), failed_stage="unknown")
        with self.assertRaisesRegex(RepairError, "max_applications"):
            repair(parent(), {"code": "PHY.MOTOR", "path": "quantity:Q-MOTOR.value", "message": "low"}, rule(), seen_hashes=set(), failed_stage="physical_v030", rule_applications={"motor-fix": 1})

    def test_seen_hash_unchanged_and_global_depth_are_rejected(self):
        diagnostic = {"code": "PHY.MOTOR", "path": "quantity:Q-MOTOR.value", "message": "low"}
        child, _ = repair(parent(), diagnostic, rule(), seen_hashes=set(), failed_stage="physical_v030")
        with self.assertRaisesRegex(RepairError, "seen resolution hash"):
            repair(parent(), diagnostic, rule(), seen_hashes={child.resolved_contract_sha256}, failed_stage="physical_v030")
        unchanged = rule(); unchanged["operations"][0]["value"] = {"value": 1, "unit": "N*m"}
        with self.assertRaisesRegex(RepairError, "does not change"):
            repair(parent(), diagnostic, unchanged, seen_hashes=set(), failed_stage="physical_v030")
        with self.assertRaisesRegex(RepairError, "global repair depth"):
            repair(parent(), diagnostic, rule(), seen_hashes=set(), failed_stage="physical_v030", depth=2, max_depth=2)

    def test_selects_earliest_blocker_then_lowest_rule_id_deterministically(self):
        diagnostics = [
            {"stage": "physical_v030", "severity": "error", "code": "Z", "path": "quantity:Q-MOTOR.value", "message": "z"},
            {"stage": "contract_v1", "severity": "error", "code": "A", "path": "quantity:Q-MOTOR.value", "message": "a"},
        ]
        second = rule(); second["id"] = "z-rule"; second["diagnostic_code"] = "A"
        first = copy.deepcopy(second); first["id"] = "a-rule"
        selected, selected_rule = select_repair(list(reversed(diagnostics)), [second, first])
        self.assertEqual("A", selected["code"])
        self.assertEqual("a-rule", selected_rule["id"])
        with self.assertRaisesRegex(RepairError, "no repair rule"):
            select_repair(diagnostics, [])


if __name__ == "__main__":
    unittest.main()
