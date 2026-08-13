import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.canonical import canonical_bytes
from tests.test_assurance_contract import valid_contract
from tests.test_assurance_engine import write_fixture


CLI = SCRIPTS / "generate_design_hypotheses.py"


def _write_space(root: Path, *, invalid=False) -> Path:
    base = valid_contract()
    (root / "base.json").write_bytes(canonical_bytes(base))
    space = {
        "schema_version": 1,
        "space_id": "cli-test",
        "base_contract": {
            "path": "base.json",
            "sha256": hashlib.sha256(canonical_bytes(base)).hexdigest(),
        },
        "max_candidates": 1,
        "axes": [
            {
                "id": "payload",
                "choices": [
                    {
                        "id": "nominal",
                        "operations": [
                            {
                                "target": "quantity:Q-PAYLOAD.value",
                                "value": {"value": 2.0, "unit": "kg"},
                            }
                        ],
                    }
                ],
            }
        ],
        "uncertainties": [],
        "objectives": [],
        "repair_rules": [],
        "evaluation": {
            "max_stage_evaluations": 4,
            "stages": ["contract_v1", "physical_v030"],
        },
    }
    if invalid:
        space["schema_version"] = True
    path = root / ("invalid.json" if invalid else "space.json")
    path.write_bytes(canonical_bytes(space))
    return path


def _write_promotable_space(root: Path) -> Path:
    contract_path, _ = write_fixture(root)
    import json

    base = json.loads(contract_path.read_text(encoding="utf-8"))
    (root / "base.json").write_bytes(canonical_bytes(base))
    quantity = next(item for item in base["quantities"] if item["id"] == "Q-RUNTIME")
    space = {
        "schema_version": 1,
        "space_id": "cli-promotable",
        "base_contract": {
            "path": "base.json",
            "sha256": hashlib.sha256(canonical_bytes(base)).hexdigest(),
        },
        "max_candidates": 1,
        "axes": [
            {
                "id": "runtime",
                "choices": [
                    {
                        "id": "nominal",
                        "operations": [
                            {
                                "target": "quantity:Q-RUNTIME.value",
                                "value": quantity["value"],
                            }
                        ],
                    }
                ],
            }
        ],
        "uncertainties": [],
        "objectives": [],
        "repair_rules": [],
        "evaluation": {
            "max_stage_evaluations": 4,
            "stages": ["contract_v1", "physical_v030"],
        },
    }
    path = root / "promotable-space.json"
    path.write_bytes(canonical_bytes(space))
    return path


def _run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *(str(item) for item in args)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
    )


class HypothesisCliTests(unittest.TestCase):
    def test_exit_zero_for_accepted_candidate(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            space = _write_promotable_space(root)
            output = root.parent / (root.name + "-accepted")
            result = _run(space, "--out", output, "--seed", 1)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("accepted=1", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_exit_one_for_no_accepted_candidate_and_prints_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            space = _write_space(root)
            result = _run(space, "--out", root.parent / (root.name + "-out"), "--seed", 1)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("accepted=0", result.stdout)
            self.assertRegex(result.stdout, r"manifest_sha256=[0-9a-f]{64}")
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_invalid_input_and_output_collision_exit_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            invalid = _write_space(root, invalid=True)
            result = _run(invalid, "--out", root.parent / (root.name + "-bad"), "--seed", 1)
            self.assertEqual(2, result.returncode)
            self.assertIn("ERROR:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

            valid = _write_space(root)
            collision = root.parent / (root.name + "-collision")
            collision.mkdir()
            result = _run(valid, "--out", collision, "--seed", 1)
            self.assertEqual(2, result.returncode)
            self.assertIn("already exists", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_boolean_invalid_seed_and_output_inside_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            space = _write_space(root)
            for seed in ("true", "1.0"):
                with self.subTest(seed=seed):
                    result = _run(space, "--out", root.parent / f"{root.name}-out-{seed}", "--seed", seed)
                    self.assertEqual(2, result.returncode)
                    self.assertNotIn("Traceback", result.stderr)
            result = _run(space, "--out", root / "nested-out", "--seed", 1)
            self.assertEqual(2, result.returncode)
            self.assertIn("source directory", result.stderr)

    def test_force_replaces_owned_output(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            space = _write_space(root)
            output = root.parent / (root.name + "-out")
            first = _run(space, "--out", output, "--seed", 1)
            second = _run(space, "--out", output, "--seed", 1, "--force")
            self.assertEqual(1, first.returncode, first.stderr)
            self.assertEqual(1, second.returncode, second.stderr)


if __name__ == "__main__":
    unittest.main()
