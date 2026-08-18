import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.simulation.policy_artifact import (  # noqa: E402
    PolicyArtifactError,
    load_policy_artifact,
)


class PolicyArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "baseline.json"

    @staticmethod
    def artifact(**overrides):
        value = {
            "schema_version": 1,
            "kind": "affine_tanh_v1",
            "policy_id": "policy-reference-baseline",
            "observation_order": ["joint-1", "joint-2", "left_wheel_rad_s"],
            "linear": {"bias": 0.2, "weights": [0.0, 0.0, 0.1]},
            "angular": {"bias": 0.0, "weights": [0.1, -0.1, 0.0]},
        }
        value.update(overrides)
        return value

    def write_canonical(self, value, path=None):
        target = path or self.path
        target.write_bytes(canonical_bytes(value))
        return target

    def test_loads_closed_canonical_artifact_with_actual_sha256(self):
        path = self.write_canonical(self.artifact())

        artifact = load_policy_artifact(path)

        self.assertEqual(
            "3009d9ffb881e665bfb8be01adf09b894c90e6f43e81388d99c7f6851ef6a47a",
            artifact.sha256,
        )
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact.sha256)
        self.assertEqual("policy-reference-baseline", artifact.policy_id)
        self.assertEqual(("joint-1", "joint-2", "left_wheel_rad_s"), artifact.observation_order)
        self.assertEqual(0.2, artifact.linear_bias)
        self.assertEqual((0.0, 0.0, 0.1), artifact.linear_weights)
        self.assertEqual(0.0, artifact.angular_bias)
        self.assertEqual((0.1, -0.1, 0.0), artifact.angular_weights)

    def test_rejects_noncanonical_json_and_duplicate_fields(self):
        self.path.write_text(json.dumps(self.artifact()), encoding="utf-8")
        with self.assertRaisesRegex(PolicyArtifactError, "canonical"):
            load_policy_artifact(self.path)

        self.path.write_bytes(
            b'{"schema_version":1,"schema_version":1,"kind":"affine_tanh_v1",'
            b'"policy_id":"policy-reference-baseline","observation_order":["joint-1"],'
            b'"linear":{"bias":0,"weights":[0]},"angular":{"bias":0,"weights":[0]}}\n'
        )
        with self.assertRaisesRegex(PolicyArtifactError, "duplicate"):
            load_policy_artifact(self.path)

    def test_normalizes_surrogate_key_and_value_encoding_failures(self):
        payloads = (
            b'{"angular":{"bias":0,"weights":[0]},"kind":"affine_tanh_v1",'
            b'"linear":{"bias":0,"weights":[0]},"observation_order":["joint-1"],'
            b'"policy_id":"\\ud800","schema_version":1}\n',
            b'{"angular":{"bias":0,"weights":[0]},"kind":"affine_tanh_v1",'
            b'"linear":{"bias":0,"weights":[0]},"observation_order":["joint-1"],'
            b'"policy_id":"policy-reference-baseline","schema_version":1,"\\ud800":0}\n',
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                with self.assertRaisesRegex(PolicyArtifactError, "canonical JSON"):
                    load_policy_artifact(self.path)

    def test_rejects_extra_root_and_nested_fields(self):
        root_extra = self.artifact(extra=True)
        self.write_canonical(root_extra)
        with self.assertRaisesRegex(PolicyArtifactError, "root.*unknown"):
            load_policy_artifact(self.path)

        nested_extra = self.artifact(linear={"bias": 0.0, "weights": [0.0, 0.0, 0.0], "extra": 1})
        self.write_canonical(nested_extra)
        with self.assertRaisesRegex(PolicyArtifactError, "linear.*unknown"):
            load_policy_artifact(self.path)

    def test_rejects_invalid_nonfinite_boolean_and_excessive_numbers(self):
        cases = (
            (self.artifact(schema_version=True), "schema_version"),
            (self.artifact(kind="callback_v1"), "kind"),
            (self.artifact(linear={"bias": True, "weights": [0.0, 0.0, 0.0]}), "linear.bias"),
            (self.artifact(angular={"bias": 0.0, "weights": [0.0, float("nan"), 0.0]}), "finite"),
            (self.artifact(angular={"bias": 0.0, "weights": [0.0, 1001.0, 0.0]}), "bounded"),
            (self.artifact(linear={"bias": "0", "weights": [0.0, 0.0, 0.0]}), "linear.bias"),
        )
        for value, expected in cases:
            with self.subTest(expected=expected):
                if "nan" in repr(value):
                    self.path.write_bytes(
                        b'{"angular":{"bias":0,"weights":[0,NaN,0]},"kind":"affine_tanh_v1",'
                        b'"linear":{"bias":0,"weights":[0,0,0]},"observation_order":["joint-1","joint-2","left_wheel_rad_s"],'
                        b'"policy_id":"policy-reference-baseline","schema_version":1}\n'
                    )
                else:
                    self.write_canonical(value)
                with self.assertRaisesRegex(PolicyArtifactError, expected):
                    load_policy_artifact(self.path)

    def test_rejects_duplicate_observation_ids_and_weight_length_mismatch(self):
        duplicate = self.artifact(observation_order=["joint-1", "joint-1", "left_wheel_rad_s"])
        self.write_canonical(duplicate)
        with self.assertRaisesRegex(PolicyArtifactError, "duplicate"):
            load_policy_artifact(self.path)

        length_mismatch = self.artifact(angular={"bias": 0.0, "weights": [0.0, 0.0]})
        self.write_canonical(length_mismatch)
        with self.assertRaisesRegex(PolicyArtifactError, "angular.weights"):
            load_policy_artifact(self.path)

    def test_rejects_symlinks_when_supported(self):
        source = self.write_canonical(self.artifact())
        link = Path(self.temporary.name) / "link.json"
        try:
            os.symlink(source, link)
        except (NotImplementedError, OSError):
            self.skipTest("symlink creation is unavailable")
        with self.assertRaisesRegex(PolicyArtifactError, "symlink"):
            load_policy_artifact(link)

    def test_returns_an_immutable_independent_snapshot(self):
        source = self.artifact()
        self.write_canonical(source)
        loaded = load_policy_artifact(self.path)
        source["linear"]["weights"][0] = 99.0
        self.path.write_bytes(canonical_bytes(source))

        self.assertEqual((0.0, 0.0, 0.1), loaded.linear_weights)
        with self.assertRaises(FrozenInstanceError):
            loaded.policy_id = "replacement"
        with self.assertRaises(TypeError):
            loaded.payload["policy_id"] = "replacement"
        with self.assertRaises(TypeError):
            loaded.payload["linear"]["weights"][0] = 1.0

    def test_sha256_tracks_the_real_canonical_bytes(self):
        self.write_canonical(self.artifact())
        first = load_policy_artifact(self.path)
        changed = self.artifact(linear={"bias": 0.3, "weights": [0.0, 0.0, 0.1]})
        self.write_canonical(changed)
        second = load_policy_artifact(self.path)

        self.assertNotEqual(first.sha256, second.sha256)
        self.assertEqual(hashlib.sha256(canonical_bytes(changed)).hexdigest(), second.sha256)


if __name__ == "__main__":
    unittest.main()
