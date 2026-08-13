import contextlib
import http.client
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def _fixture(self, base: Path):
        repo_root = base / "distribution"
        router = repo_root / "skills" / "robotics-design"
        router.mkdir(parents=True)
        (router / "SKILL.md").write_text(
            "---\nname: robotics-design\ndescription: Use when designing robots.\n---\n# Router\n",
            encoding="utf-8",
        )
        cache = router / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "generated.pyc").write_bytes(b"bytecode")

        archive = base / "source.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("source-aaaaaaaa/LICENSE", "Apache License 2.0\n")
            handle.writestr(
                "source-aaaaaaaa/SKILL.md",
                "---\n"
                "name: ros2-engineering-skills\n"
                "description: Use when writing ROS 2 software.\n"
                "context: fork\n"
                "hooks:\n  Stop: []\n"
                "---\n# ROS 2\n",
            )

        manifest = {
            "schema_version": 1,
            "suite": {"name": "fixture", "version": "0.0.0"},
            "sources": [
                {
                    "id": "ros2-engineering-skills",
                    "repo": "example/source",
                    "commit": "a" * 40,
                    "license": "Apache-2.0",
                    "license_path": "LICENSE",
                    "transforms": ["normalize_codex_frontmatter"],
                    "skills": [{"path": ".", "name": "ros2-engineering-skills"}],
                }
            ],
            "local_skills": [{"path": "skills/robotics-design", "name": "robotics-design"}],
        }
        manifest_path = repo_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return repo_root, manifest_path, archive

    def test_installs_archive_and_local_skill_without_network(self):
        from scripts.install import install_from_manifest

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo_root, manifest_path, archive = self._fixture(base)
            dest = base / "skills"
            install_from_manifest(
                manifest_path=manifest_path,
                destination=dest,
                repository_root=repo_root,
                archive_provider=lambda _source: archive,
            )

            installed = dest / "ros2-engineering-skills"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertEqual((installed / "UPSTREAM_LICENSE").read_text(), "Apache License 2.0\n")
            frontmatter = (installed / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
            self.assertNotIn("context:", frontmatter)
            self.assertNotIn("hooks:", frontmatter)
            self.assertIn("license: Apache-2.0", frontmatter)
            self.assertTrue((dest / "robotics-design" / "SKILL.md").is_file())
            self.assertFalse(
                (dest / "robotics-design" / "references" / "host-runtime.md").exists()
            )
            self.assertFalse((dest / "robotics-design" / "scripts" / "__pycache__").exists())

    def test_archive_download_retries_incomplete_response_without_partial_file(self):
        from scripts.install import download_archive

        source = {
            "id": "source",
            "repo": "example/source",
            "commit": "a" * 40,
        }
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw)
            valid = io.BytesIO()
            with zipfile.ZipFile(valid, "w") as handle:
                handle.writestr("source/LICENSE", "license")
            valid_bytes = valid.getvalue()
            responses = [
                http.client.IncompleteRead(b"partial", 7),
                io.BytesIO(valid_bytes),
            ]
            with mock.patch(
                "scripts.install.urllib.request.urlopen", side_effect=responses
            ) as opened:
                archive = download_archive(source, destination)

            self.assertEqual(2, opened.call_count)
            self.assertEqual(valid_bytes, archive.read_bytes())
            self.assertFalse((destination / "source.zip.part").exists())

    def test_archive_download_exhaustion_is_actionable_and_leaves_no_partial(self):
        from scripts.install import download_archive

        source = {
            "id": "source",
            "repo": "example/source",
            "commit": "a" * 40,
        }
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw)
            failure = http.client.IncompleteRead(b"partial", 7)
            with mock.patch(
                "scripts.install.urllib.request.urlopen", side_effect=[failure] * 3
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "cannot download pinned source source after 3 attempts"
                ):
                    download_archive(source, destination)

            self.assertFalse((destination / "source.zip").exists())
            self.assertFalse((destination / "source.zip.part").exists())

    def test_archive_download_retries_malformed_zip_before_returning(self):
        from scripts.install import download_archive

        source = {
            "id": "source",
            "repo": "example/source",
            "commit": "a" * 40,
        }
        valid = io.BytesIO()
        with zipfile.ZipFile(valid, "w") as handle:
            handle.writestr("source/LICENSE", "license")
        valid.seek(0)
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw)
            with mock.patch(
                "scripts.install.urllib.request.urlopen",
                side_effect=[io.BytesIO(b"not a zip"), valid],
            ) as opened:
                archive = download_archive(source, destination)

            self.assertEqual(2, opened.call_count)
            with zipfile.ZipFile(archive) as handle:
                self.assertEqual(None, handle.testzip())
            self.assertFalse((destination / "source.zip.part").exists())

    def test_cli_reports_exhausted_download_without_traceback(self):
        from scripts.install import main

        stderr = io.StringIO()
        with mock.patch(
            "scripts.install.install_from_manifest",
            side_effect=RuntimeError("cannot download pinned source source after 3 attempts"),
        ), mock.patch(
            "sys.argv", ["install.py", "--dest", "unused"]
        ), contextlib.redirect_stderr(stderr):
            returncode = main()

        self.assertEqual(1, returncode)
        self.assertIn("cannot download pinned source source after 3 attempts", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_generates_host_runtime_overlay_when_requested(self):
        from scripts.install import install_from_manifest

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo_root, manifest_path, archive = self._fixture(base)
            runtime = base / "runtime" / "python.exe"
            runtime.parent.mkdir()
            runtime.write_bytes(b"python")
            dest = base / "skills"

            install_from_manifest(
                manifest_path=manifest_path,
                destination=dest,
                repository_root=repo_root,
                archive_provider=lambda _source: archive,
                host_runtime_python=runtime,
            )

            overlay = dest / "robotics-design" / "references" / "host-runtime.md"
            self.assertTrue(overlay.is_file())
            text = overlay.read_text(encoding="utf-8")
            self.assertIn(str(runtime.resolve()), text)
            self.assertIn(str(dest.resolve()), text)
            self.assertIn("generated host state", text.lower())
            self.assertNotIn("Installation date", text)

    def test_missing_host_runtime_fails_before_archive_download(self):
        from scripts.install import install_from_manifest

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo_root, manifest_path, archive = self._fixture(base)
            dest = base / "skills"
            provider_called = False

            def provider(_source):
                nonlocal provider_called
                provider_called = True
                return archive

            with self.assertRaisesRegex(ValueError, "Host runtime Python does not exist"):
                install_from_manifest(
                    manifest_path=manifest_path,
                    destination=dest,
                    repository_root=repo_root,
                    archive_provider=provider,
                    host_runtime_python=base / "missing-python",
                )

            self.assertFalse(provider_called)
            self.assertFalse(dest.exists())

    def test_prepares_transaction_on_destination_filesystem(self):
        from scripts.install import prepare_destination_transaction

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            staged = base / "download-stage"
            (staged / "alpha").mkdir(parents=True)
            (staged / "alpha" / "SKILL.md").write_text("alpha", encoding="utf-8")
            destination = base / "publish-volume" / "skills"

            transaction = prepare_destination_transaction(staged, destination, ["alpha"])
            try:
                self.assertEqual(transaction.parent.resolve(), destination.parent.resolve())
                self.assertEqual((transaction / "alpha" / "SKILL.md").read_text(), "alpha")
            finally:
                import shutil

                shutil.rmtree(transaction)

    def test_refuses_existing_destination_without_changing_it(self):
        from scripts.install import install_from_manifest

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo_root, manifest_path, archive = self._fixture(base)
            dest = base / "skills"
            existing = dest / "ros2-engineering-skills"
            existing.mkdir(parents=True)
            sentinel = existing / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                install_from_manifest(
                    manifest_path=manifest_path,
                    destination=dest,
                    repository_root=repo_root,
                    archive_provider=lambda _source: archive,
                )

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
            self.assertFalse((dest / "robotics-design").exists())

    def test_rolls_back_installer_owned_targets_after_publish_race(self):
        from scripts.install import install_from_manifest

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo_root, manifest_path, archive = self._fixture(base)
            dest = base / "skills"

            def provider(_source):
                raced = dest / "robotics-design"
                raced.mkdir(parents=True)
                (raced / "keep.txt").write_text("other process", encoding="utf-8")
                return archive

            with self.assertRaises(FileExistsError):
                install_from_manifest(
                    manifest_path=manifest_path,
                    destination=dest,
                    repository_root=repo_root,
                    archive_provider=provider,
                )

            self.assertFalse((dest / "ros2-engineering-skills").exists())
            self.assertEqual((dest / "robotics-design" / "keep.txt").read_text(), "other process")
            self.assertEqual(list(dest.parent.glob(".robotics-design-txn-*")), [])

    def test_rejects_archive_path_traversal(self):
        from scripts.install import safe_extract_archive

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            archive = base / "bad.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                safe_extract_archive(archive, base / "extract")
            self.assertFalse((base / "escape.txt").exists())

    def test_dry_run_is_complete_and_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "skills"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "install.py"),
                "--dry-run",
                "--dest",
                str(destination),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("robotics-design", completed.stdout)
            self.assertIn("ros2-engineering-skills", completed.stdout)
            self.assertIn("source_commit=", completed.stdout)
            self.assertFalse(destination.exists())

    def test_dry_run_reports_requested_host_overlay_without_writes(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            destination = base / "skills"
            runtime = base / "runtime" / "python.exe"
            runtime.parent.mkdir()
            runtime.write_bytes(b"python")
            command = [
                sys.executable,
                str(ROOT / "scripts" / "install.py"),
                "--dry-run",
                "--dest",
                str(destination),
                "--host-runtime-python",
                str(runtime),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("host-runtime overlay", completed.stdout)
            self.assertIn(str(runtime.resolve()), completed.stdout)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
