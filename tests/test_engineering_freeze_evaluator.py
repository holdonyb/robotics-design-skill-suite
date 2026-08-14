import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.engineering_freeze.evaluator import evaluate_engineering_freeze


def write_json(path, value):
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def complete_package(root):
    drawing_hash = write_json(root / "drawings/base.json", {"kind": "controlled_drawing"})
    supplier_hash = write_json(root / "supplier-manifest.json", {"schema_version": 1, "snapshots": [], "supplier_manifest_id": "supplier-reference"})
    contract_hash = write_json(root / "design-contract.json", {"components": []})
    return {
        "schema_version": 1, "freeze_id": "freeze-reference", "design_contract": {"path": "design-contract.json", "sha256": contract_hash}, "supplier_manifest": {"path": "supplier-manifest.json", "sha256": supplier_hash},
        "artifacts": [{"id": "ART-DRAWING", "kind": "drawing", "path": "drawings/base.json", "sha256": drawing_hash}],
        "hazards": [{"id": "HZ-ENERGY", "phase": "power_up", "pre_risk": 5, "post_risk": 2, "controls": ["CTRL-ESTOP"], "verification_ids": ["VER-ESTOP"], "safety_function_id": "SF-ESTOP", "residual_disposition": "review_required"}],
        "safety_functions": [{"id": "SF-ESTOP", "initiating_event": "emergency", "safe_state": "power_removed", "independent_path": "wired", "test_card_id": "TC-POWER"}],
        "verifications": [{"id": "VER-ESTOP", "artifact_id": "ART-DRAWING", "method": "review"}],
        "inspection_items": [{"id": "INSP-WIRING", "artifact_id": "ART-DRAWING", "acceptance": "approved drawing review"}],
        "test_cards": [{"id": "TC-POWER", "status": "planned", "site_authorization": "required", "reachable_estop": "required", "operators": ["operator", "observer"], "energy_limit": "defined before execution", "abort_criteria": ["unexpected motion"]}],
    }


class EngineeringFreezeEvaluatorTests(unittest.TestCase):
    def test_complete_package_is_freeze_ready_but_never_authorized(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = complete_package(root)
            path = root / "freeze-package.json"
            write_json(path, package)
            report = evaluate_engineering_freeze(root, path, placeholder_components=set())
            self.assertTrue(report.freeze_ready)
            self.assertFalse(report.procurement_authorized)
            self.assertFalse(report.motion_authorized)

    def test_open_critical_hazard_and_missing_card_preconditions_block_freeze(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = complete_package(root)
            package["hazards"][0]["residual_disposition"] = "open"
            package["test_cards"][0].pop("reachable_estop")
            path = root / "freeze-package.json"
            write_json(path, package)
            report = evaluate_engineering_freeze(root, path, placeholder_components={"CMP-MOTOR"})
            codes = {item.code for item in report.findings}
            self.assertFalse(report.freeze_ready)
            self.assertTrue({"FREEZE.CRITICAL_HAZARD_OPEN", "FREEZE.TEST_CARD_PRECONDITION", "FREEZE.PLACEHOLDER_COMPONENT"} <= codes)

    def test_hash_drift_and_invalid_risk_or_graph_reference_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = complete_package(root)
            package["artifacts"][0]["sha256"] = "0" * 64
            package["hazards"][0]["post_risk"] = 6
            package["hazards"][0]["verification_ids"] = ["VER-NOPE"]
            path = root / "freeze-package.json"
            write_json(path, package)
            report = evaluate_engineering_freeze(root, path, placeholder_components=set())
            codes = {item.code for item in report.findings}
            self.assertTrue({"FREEZE.ARTIFACT_HASH_MISMATCH", "FREEZE.HAZARD_RISK_INVALID", "FREEZE.HAZARD_VERIFICATION_UNKNOWN"} <= codes)


if __name__ == "__main__":
    unittest.main()
