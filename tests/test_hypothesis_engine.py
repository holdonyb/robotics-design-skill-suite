import unittest
import sys
from pathlib import Path
import hashlib
import json
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.engine import EngineError, run_space
from assurance.hypothesis.canonical import canonical_bytes
from tests.test_assurance_contract import valid_contract


class EngineTests(unittest.TestCase):
    def test_missing_space_is_actionable(self):
        with self.assertRaisesRegex(EngineError, "does not exist"):
            run_space("missing-space.json", "missing-output", seed=1)

    def test_run_space_emits_candidates_and_aliases_without_duplicate_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); base=valid_contract(); (root/"base.json").write_bytes(canonical_bytes(base))
            space={"schema_version":1,"space_id":"engine-test","base_contract":{"path":"base.json","sha256":hashlib.sha256(canonical_bytes(base)).hexdigest()},"max_candidates":2,"axes":[{"id":"a","choices":[{"id":"x","operations":[{"target":"architecture.features","value":["mobile_base"]}]},{"id":"y","operations":[{"target":"architecture.features","value":["mobile_base"]}]}]}],"uncertainties":[],"objectives":[],"repair_rules":[],"evaluation":{"max_stage_evaluations":8,"stages":["contract_v1","physical_v030"]}}
            (root/"space.json").write_bytes(canonical_bytes(space))
            result=run_space(root/"space.json",root/"out",seed=1)
            self.assertEqual(2,result["candidate_count"])
            self.assertEqual(1,len(list((root/"out"/"candidates").glob("*/stages.json"))))

    def test_same_seed_is_reproducible_and_base_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); base=valid_contract(); (root/"base.json").write_bytes(canonical_bytes(base))
            space={"schema_version":1,"space_id":"repro","base_contract":{"path":"base.json","sha256":hashlib.sha256(canonical_bytes(base)).hexdigest()},"max_candidates":1,"axes":[{"id":"a","choices":[{"id":"x","operations":[{"target":"architecture.features","value":["mobile_base"]}]}]}],"uncertainties":[],"objectives":[],"repair_rules":[],"evaluation":{"max_stage_evaluations":4,"stages":["contract_v1","physical_v030"]}}
            (root/"space.json").write_bytes(canonical_bytes(space)); run_space(root/"space.json",root/"one",seed=1); run_space(root/"space.json",root/"two",seed=1)
            self.assertEqual(sorted(p.relative_to(root/"one").as_posix() for p in (root/"one").rglob("*.json")),sorted(p.relative_to(root/"two").as_posix() for p in (root/"two").rglob("*.json")))
            space["base_contract"]["sha256"]="0"*64; (root/"bad.json").write_bytes(canonical_bytes(space))
            with self.assertRaisesRegex(EngineError,"SHA-256 mismatch"): run_space(root/"bad.json",root/"bad",seed=1)


if __name__ == "__main__":
    unittest.main()
