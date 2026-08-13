import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.bundle import BundleError, validate_bundle, write_bundle


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
            with self.assertRaisesRegex(BundleError, "non-empty"):
                write_bundle(output, {"index.json": {"schema_version": 1}})

    def test_force_restore_old_output_when_publication_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"; output.mkdir(); (output / "old.txt").write_text("old")
            original = Path.replace
            def fail_transaction(source, destination):
                if source.name.startswith(".hypothesis-txn-"):
                    raise OSError("injected publish failure")
                return original(source, destination)
            with mock.patch.object(Path, "replace", fail_transaction), self.assertRaisesRegex(BundleError, "publish"):
                write_bundle(output, {"index.json": {"schema_version": 1}}, force=True)
            self.assertEqual("old", (output / "old.txt").read_text())


if __name__ == "__main__":
    unittest.main()
