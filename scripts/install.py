#!/usr/bin/env python3
"""Install the pinned robotics design skill suite without external packages."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "manifest.json"
ArchiveProvider = Callable[[dict], Path]


def load_manifest(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def default_destination() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "skills"


def build_plan(manifest: dict, destination: Path) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    for source in manifest["sources"]:
        for skill in source["skills"]:
            plan.append(
                {
                    "name": skill["name"],
                    "destination": str(Path(destination) / skill["name"]),
                    "source": source["repo"],
                    "source_commit": source["commit"],
                }
            )
    for skill in manifest["local_skills"]:
        plan.append(
            {
                "name": skill["name"],
                "destination": str(Path(destination) / skill["name"]),
                "source": "local-distribution",
                "source_commit": "local",
            }
        )
    return plan


def safe_extract_archive(archive: Path, destination: Path) -> Path:
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            normalized = member.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                raise ValueError(f"Unsafe archive member: {member.filename}")
            resolved = (destination / Path(*path.parts)).resolve()
            if resolved != destination and destination not in resolved.parents:
                raise ValueError(f"Archive member escapes destination: {member.filename}")
        handle.extractall(destination)
    return destination


def _archive_root(extracted: Path) -> Path:
    children = [path for path in extracted.iterdir() if path.is_dir()]
    if len(children) != 1:
        raise ValueError("Expected one top-level directory in GitHub archive")
    return children[0]


def download_archive(source: dict, destination: Path) -> Path:
    url = f"https://codeload.github.com/{source['repo']}/zip/{source['commit']}"
    output = Path(destination) / f"{source['id']}.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "robotics-design-skill-suite"})
    with urllib.request.urlopen(request, timeout=120) as response, output.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return output


def _split_frontmatter(text: str) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("SKILL.md frontmatter is not terminated")
    return text[4:end].splitlines(), text[end + 5 :]


def normalize_codex_frontmatter(skill_md: Path, source: dict) -> None:
    lines, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
    allowed = {"name", "description", "allowed-tools"}
    kept: list[str] = []
    keep_block = False
    for line in lines:
        top_level = re.match(r"^([A-Za-z0-9_-]+):", line)
        if top_level:
            keep_block = top_level.group(1) in allowed
        if keep_block and not line.lstrip().startswith("#"):
            kept.append(line)
    kept.extend(
        [
            f"license: {source['license']}",
            "metadata:",
            f"  source: https://github.com/{source['repo']}",
            f"  source_commit: {source['commit']}",
            "  codex_note: Claude-only frontmatter removed; validation scripts remain manual.",
        ]
    )
    skill_md.write_text("---\n" + "\n".join(kept) + "\n---\n" + body, encoding="utf-8")


def _copy_skill(source_path: Path, destination: Path) -> None:
    if not (source_path / "SKILL.md").is_file():
        raise ValueError(f"Skill path has no SKILL.md: {source_path}")
    shutil.copytree(
        source_path,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def resolve_host_runtime(path: Path | None) -> Path | None:
    """Resolve an optional host Python executable before installation side effects."""
    if path is None:
        return None
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Host runtime Python does not exist or is not a file: {resolved}")
    return resolved


def write_host_runtime_overlay(skill_root: Path, runtime: Path, destination: Path) -> Path:
    """Write generated host state into a staged robotics-design skill."""
    references = Path(skill_root) / "references"
    references.mkdir(parents=True, exist_ok=True)
    output = references / "host-runtime.md"
    output.write_text(
        "# Host Runtime Overlay\n\n"
        "This file is generated host state, not public source provenance.\n\n"
        f"- Python executable: `{Path(runtime).resolve()}`\n"
        f"- Skills destination: `{Path(destination).expanduser().resolve()}`\n\n"
        "Use this runtime only for the installed suite tools. Keep target-project "
        "dependencies in that project's own environment.\n",
        encoding="utf-8",
    )
    return output


def prepare_destination_transaction(staged: Path, destination: Path, names: list[str]) -> Path:
    """Copy a complete install set to a hidden directory on the destination filesystem."""
    destination_parent = Path(destination).expanduser().resolve().parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    transaction = Path(tempfile.mkdtemp(prefix=".robotics-design-txn-", dir=destination_parent))
    try:
        for name in names:
            shutil.copytree(Path(staged) / name, transaction / name)
    except Exception:
        shutil.rmtree(transaction, ignore_errors=True)
        raise
    return transaction


def publish_destination_transaction(transaction: Path, destination: Path, names: list[str]) -> list[Path]:
    """Publish same-filesystem staged directories and roll them back as one transaction."""
    transaction = Path(transaction).resolve()
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    published: list[tuple[Path, Path]] = []
    try:
        for name in names:
            source = transaction / name
            target = destination / name
            if target.exists():
                raise FileExistsError(f"Destination appeared during install: {target}")
            source.rename(target)
            published.append((target, source))
    except Exception as error:
        rollback_errors = []
        for target, source in reversed(published):
            try:
                target.rename(source)
            except OSError as rollback_error:
                rollback_errors.append(f"{target}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError(
                f"Installation failed ({error}); rollback also failed: " + "; ".join(rollback_errors)
            ) from error
        raise
    return [target for target, _source in published]


def install_from_manifest(
    manifest_path: Path,
    destination: Path,
    repository_root: Path | None = None,
    archive_provider: ArchiveProvider | None = None,
    host_runtime_python: Path | None = None,
) -> list[Path]:
    manifest_path = Path(manifest_path).resolve()
    repository_root = Path(repository_root).resolve() if repository_root else manifest_path.parent
    destination = Path(destination).expanduser().resolve()
    host_runtime = resolve_host_runtime(host_runtime_python)
    manifest = load_manifest(manifest_path)
    plan = build_plan(manifest, destination)

    collisions = [Path(item["destination"]) for item in plan if Path(item["destination"]).exists()]
    if collisions:
        raise FileExistsError("Refusing to overwrite existing skill(s): " + ", ".join(map(str, collisions)))

    with tempfile.TemporaryDirectory(prefix="robotics-design-install-") as raw:
        temporary = Path(raw)
        stage = temporary / "stage"
        stage.mkdir()

        for source in manifest["sources"]:
            archive = archive_provider(source) if archive_provider else download_archive(source, temporary)
            extracted = safe_extract_archive(archive, temporary / f"extract-{source['id']}")
            archive_root = _archive_root(extracted)
            license_text = (archive_root / source["license_path"]).read_text(encoding="utf-8")
            transforms = set(source.get("transforms", []))
            for skill in source["skills"]:
                staged = stage / skill["name"]
                _copy_skill((archive_root / skill["path"]).resolve(), staged)
                (staged / "UPSTREAM_LICENSE").write_text(license_text, encoding="utf-8")
                if "normalize_codex_frontmatter" in transforms:
                    normalize_codex_frontmatter(staged / "SKILL.md", source)

        for skill in manifest["local_skills"]:
            _copy_skill((repository_root / skill["path"]).resolve(), stage / skill["name"])

        if host_runtime is not None:
            robotics_skill = stage / "robotics-design"
            if not robotics_skill.is_dir():
                raise ValueError("Host runtime overlay requires the robotics-design local skill")
            write_host_runtime_overlay(robotics_skill, host_runtime, destination)

        names = [item["name"] for item in plan]
        transaction = prepare_destination_transaction(stage, destination, names)
        try:
            installed = publish_destination_transaction(transaction, destination, names)
        finally:
            if transaction.exists():
                shutil.rmtree(transaction)
    return installed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the pinned robotics design skill suite.")
    parser.add_argument("--dest", type=Path, default=default_destination(), help="Skills directory")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without network or writes")
    parser.add_argument(
        "--host-runtime-python",
        type=Path,
        help="Generate a host-runtime overlay for this Python executable",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        host_runtime = resolve_host_runtime(args.host_runtime_python)
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=os.sys.stderr)
        return 1
    if args.dry_run:
        for item in build_plan(manifest, args.dest):
            print(
                f"{item['name']} -> {item['destination']} "
                f"source={item['source']} source_commit={item['source_commit']}"
            )
        if host_runtime is not None:
            overlay = (
                Path(args.dest).expanduser().resolve()
                / "robotics-design"
                / "references"
                / "host-runtime.md"
            )
            print(f"host-runtime overlay -> {overlay} python={host_runtime}")
        return 0
    try:
        installed = install_from_manifest(
            args.manifest,
            args.dest,
            args.manifest.resolve().parent,
            host_runtime_python=host_runtime,
        )
    except (FileExistsError, OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=os.sys.stderr)
        return 1
    for path in installed:
        print(f"Installed {path.name} to {path}")
    print("Start a new Codex task to refresh skill discovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
