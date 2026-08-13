import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.bundle import validate_bundle
from assurance.hypothesis.engine import run_space


REFERENCE = ROOT / "reference" / "mobile-manipulator"


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(item.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


class ReferenceHypothesisTests(unittest.TestCase):
    def _run(self, root: Path, name="out"):
        for filename in ("design-contract.json", "robot.urdf", "assumptions.json"):
            shutil.copy2(REFERENCE / filename, root / filename)
        shutil.copy2(REFERENCE / "hypothesis-space.json", root / "hypothesis-space.json")
        output = root / name
        result = run_space(root / "hypothesis-space.json", output, seed=20260813)
        return result, output

    def test_reference_tradeoff_is_screened_but_never_accepted(self):
        with tempfile.TemporaryDirectory() as raw:
            result, output = self._run(Path(raw))
            self.assertEqual(0, result["accepted_count"])
            self.assertEqual([], validate_bundle(output, manifest_sha256=result["bundle_manifest_sha256"]))
            candidates = result["candidates"]
            self.assertTrue(candidates)
            self.assertTrue(all(item["status"] in {"rejected", "alias"} for item in candidates))
            objective_files = list((output / "candidates").glob("*/objectives.json"))
            self.assertTrue(objective_files)
            runtime_values = []
            for path in objective_files:
                body = json.loads(path.read_text(encoding="utf-8"))
                if "runtime" in body["values"]:
                    runtime_values.append(body["values"]["runtime"])
            self.assertIn(22500.0, runtime_values)
            self.assertIn(27000.0, runtime_values)
            screening = json.loads(
                (output / "screening-pareto.json").read_text(encoding="utf-8")
            )
            screened = sum(screening["fronts"], [])
            self.assertTrue(screened)
            self.assertTrue(
                any(
                    json.loads(path.read_text(encoding="utf-8"))["values"].get("runtime")
                    == 27000.0
                    and path.parent.name in screened
                    for path in objective_files
                )
            )

    def test_wrong_right_rating_repairs_only_its_owner_and_stays_unpromoted(self):
        with tempfile.TemporaryDirectory() as raw:
            result, output = self._run(Path(raw))
            traces = list((output / "candidates").glob("*/repair-trace.json"))
            self.assertTrue(traces)
            bodies = [json.loads(path.read_text(encoding="utf-8")) for path in traces]
            trace = next(item for item in bodies if item["rule_id"] == "restore-right-rating")
            self.assertEqual("component:CMP-TRACTION-MOTOR-R", trace["owner"])
            self.assertEqual("PHY.DRIVE.PEAK_TORQUE", trace["trigger_code"])
            self.assertNotIn("controller", json.dumps(trace).lower())
            child = next(item for item in result["candidates"] if item["repair_rule_id"])
            self.assertEqual("rejected", child["status"])

    def test_reference_bundle_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first, one = self._run(root, "one")
            second, two = self._run(root, "two")
            self.assertEqual(first["bundle_manifest_sha256"], second["bundle_manifest_sha256"])
            self.assertEqual(_tree_hash(one), _tree_hash(two))

    def test_reference_matches_pinned_expected_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            result, output = self._run(Path(raw))
            expected = json.loads(
                (REFERENCE / "hypothesis-expected.json").read_text(encoding="utf-8")
            )
            screening = json.loads(
                (output / "screening-pareto.json").read_text(encoding="utf-8")
            )
            observed = {
                "accepted_count": result["accepted_count"],
                "bundle_manifest_sha256": result["bundle_manifest_sha256"],
                "candidate_count": result["candidate_count"],
                "screening_fronts": screening["fronts"],
                "seed": result["seed"],
                "space_sha256": result["space_sha256"],
                "stage_evaluations": result["metadata"]["stage_evaluations"],
            }
            self.assertEqual(expected, observed)


if __name__ == "__main__":
    unittest.main()
