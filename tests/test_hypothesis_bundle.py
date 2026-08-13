import tempfile
import unittest
from pathlib import Path
import sys
import json
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.bundle import (
    BundleError,
    validate_bundle,
    write_bundle,
    write_bundle_with_receipt,
)


class BundleTests(unittest.TestCase):
    def test_write_and_validate_canonical_bundle(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            write_bundle(output, {"index.json": {"schema_version": 1}, "pareto.json": {"fronts": []}})
            self.assertEqual([], validate_bundle(output))

    def test_extra_and_tampered_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            write_bundle(output, {"index.json": {"schema_version": 1}})
            (output / "extra.txt").write_text("x", encoding="utf-8")
            self.assertTrue(validate_bundle(output))

    def test_index_is_hash_bound_by_external_manifest(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            receipt = write_bundle_with_receipt(
                output,
                {"index.json": {"schema_version": 1, "accepted_count": 1}},
            )
            self.assertEqual([], validate_bundle(output, manifest_sha256=receipt.manifest_sha256))
            index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            index["accepted_count"] = 999
            from assurance.hypothesis.canonical import canonical_bytes

            (output / "index.json").write_bytes(canonical_bytes(index))
            self.assertTrue(
                any("stale hash: index.json" in item for item in validate_bundle(output))
            )

    def test_external_manifest_receipt_detects_joint_manifest_and_index_rewrite(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            receipt = write_bundle_with_receipt(
                output,
                {"index.json": {"schema_version": 1, "accepted_count": 1}},
            )
            from assurance.hypothesis.canonical import canonical_bytes
            import hashlib

            index = {"schema_version": 1, "accepted_count": 999, "files": []}
            index_bytes = canonical_bytes(index)
            (output / "index.json").write_bytes(index_bytes)
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            for item in manifest["files"]:
                if item["path"] == "index.json":
                    item["sha256"] = hashlib.sha256(index_bytes).hexdigest()
            (output / "manifest.json").write_bytes(canonical_bytes(manifest))
            self.assertEqual([], validate_bundle(output))
            self.assertTrue(
                any(
                    "manifest SHA-256 mismatch" in item
                    for item in validate_bundle(
                        output, manifest_sha256=receipt.manifest_sha256
                    )
                )
            )

    def test_public_write_bundle_retains_path_return_compatibility(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            result = write_bundle(output, {"index.json": {"schema_version": 1}})
            self.assertIsInstance(result, Path)
            self.assertTrue(result.exists())

    def test_path_escape_noncanonical_and_missing_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            with self.assertRaisesRegex(BundleError, "paths"):
                write_bundle(output, {"index.json": {"schema_version": 1}, "../bad.json": {}})
            write_bundle(output, {"index.json": {"schema_version": 1}})
            (output / "index.json").write_text('{"files": [], "schema_version": 1}\n', encoding="utf-8")
            self.assertTrue(validate_bundle(output))

    def test_windows_drive_relative_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            with self.assertRaisesRegex(BundleError, "paths"):
                write_bundle(
                    output,
                    {"index.json": {"schema_version": 1}, "C:escape.json": {}},
                )

    def test_file_count_and_total_byte_budgets_are_enforced(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            with mock.patch(
                "assurance.hypothesis.bundle._MAX_FILES", 2
            ), self.assertRaisesRegex(BundleError, "file count"):
                write_bundle(
                    output,
                    {
                        "index.json": {"schema_version": 1},
                        "one.json": {},
                        "two.json": {},
                    },
                )
            with mock.patch(
                "assurance.hypothesis.bundle._MAX_BYTES", 32
            ), self.assertRaisesRegex(BundleError, "total size"):
                write_bundle(
                    output,
                    {
                        "index.json": {"schema_version": 1},
                        "large.json": {"value": "x" * 64},
                    },
                )

    def test_deep_json_returns_validation_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            write_bundle(output, {"index.json": {"schema_version": 1}})
            (output / "index.json").write_text(
                "[" * 1100 + "0" + "]" * 1100,
                encoding="utf-8",
            )
            errors = validate_bundle(output)
            self.assertTrue(errors)
            self.assertTrue(any("JSON" in item or "depth" in item for item in errors))

    def test_nonempty_output_requires_force(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"; output.mkdir(); (output / "old.txt").write_text("old")
            with self.assertRaisesRegex(BundleError, "already exists"):
                write_bundle(output, {"index.json": {"schema_version": 1}})

    def test_empty_existing_output_is_also_a_collision(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            output.mkdir()
            with self.assertRaisesRegex(BundleError, "already exists"):
                write_bundle(output, {"index.json": {"schema_version": 1}})

    def test_nonforce_publication_race_preserves_third_party_output(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            from assurance.hypothesis import bundle
            original_rename = bundle._rename_absent

            def inject_race(source, destination):
                if source.name.startswith(".hypothesis-txn-"):
                    output.mkdir()
                    (output / "third-party.txt").write_text("owned elsewhere")
                return original_rename(source, destination)

            with mock.patch(
                "assurance.hypothesis.bundle._rename_absent", inject_race
            ), self.assertRaisesRegex(BundleError, "race|already exists"):
                write_bundle(output, {"index.json": {"schema_version": 1}})
            self.assertEqual(
                "owned elsewhere", (output / "third-party.txt").read_text()
            )

    def test_force_restore_old_output_when_publication_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"; output.mkdir(); (output / "old.txt").write_text("old")
            original = Path.replace
            def fail_transaction(source, destination):
                if source.name.startswith(".hypothesis-txn-"):
                    raise OSError("injected publish failure")
                return original(source, destination)
            with mock.patch("assurance.hypothesis.bundle._rename_absent", side_effect=OSError("injected publish failure")), self.assertRaisesRegex(BundleError, "publish"):
                write_bundle(output, {"index.json": {"schema_version": 1}}, force=True)
            self.assertEqual("old", (output / "old.txt").read_text())

    def test_force_publication_race_never_deletes_third_party_output(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            output.mkdir()
            (output / "old.txt").write_text("old")

            def inject_race(source, destination):
                output.mkdir()
                (output / "third-party.txt").write_text("third")
                raise FileExistsError("injected force race")

            with mock.patch(
                "assurance.hypothesis.bundle._rename_absent", inject_race
            ), self.assertRaisesRegex(BundleError, "backup|recovery"):
                write_bundle(
                    output,
                    {"index.json": {"schema_version": 1}},
                    force=True,
                )
            self.assertEqual("third", (output / "third-party.txt").read_text())
            backups = list(output.parent.glob(".hypothesis-backup-*"))
            self.assertEqual(1, len(backups))
            self.assertEqual("old", (backups[0] / "old.txt").read_text())


if __name__ == "__main__":
    unittest.main()
