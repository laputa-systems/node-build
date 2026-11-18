from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from buildlib import hashing, release

from buildsys import product


class AssemblyError(Exception):
    pass


def _git_query(repo_root: Path, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", command, *arguments], cwd=repo_root,
            capture_output=True, text=True, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AssemblyError(f"git {command} timed out") from error


def git_revision(repo_root: Path) -> str:
    completed = _git_query(repo_root, "rev-parse", "--show-toplevel", "HEAD")
    if completed.returncode != 0:
        raise AssemblyError("not a git checkout")
    checkout, revision = completed.stdout.rstrip("\n").rsplit("\n", 1)
    if not Path(checkout).samefile(repo_root):
        raise AssemblyError("not a git checkout root")
    return revision


def git_dirty(repo_root: Path) -> bool:
    completed = _git_query(repo_root, "status", "--porcelain", "--untracked-files=all")
    if completed.returncode != 0:
        raise AssemblyError("git status failed")
    return bool(completed.stdout.strip())


def clean_build_revision(repo_root: Path) -> str | None:
    try:
        revision = git_revision(repo_root)
        return None if git_dirty(repo_root) else revision
    except (AssemblyError, FileNotFoundError):
        return None


def load_record(path: Path, what: str) -> dict:
    if not path.is_file():
        raise AssemblyError(f"missing {what}: {path} (run package/qualify first)")
    try:
        record: object = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise AssemblyError(f"invalid {what}: {path}: {error}") from error
    if not isinstance(record, dict):
        raise AssemblyError(f"invalid {what}: {path}: expected an object")
    return record


def all_checks_ok(entries: object) -> bool:
    return isinstance(entries, list) and bool(entries) and all(
        isinstance(entry, dict) and entry.get("ok") is True for entry in entries
    )


def validate_triple(repo_root: Path, triple: str, lock_sha256: str, revision: str) -> dict:
    archive_name = product.archive_name(product.NODE_VERSION, triple)
    archive = repo_root / "dist" / triple / archive_name
    if not archive.is_file():
        raise AssemblyError(f"missing packaged archive: {archive}")
    package_record = load_record(repo_root / "build" / triple / "package-record.json", "package record")
    receipt_path = repo_root / "build" / triple / "build-receipt.json"
    build_receipt = load_record(receipt_path, "build receipt")
    if build_receipt.get("sources_lock_sha256") != lock_sha256:
        raise AssemblyError(f"build receipt source lock missing or stale; rebuild: {triple}")
    if build_receipt.get("source_revision") != revision:
        raise AssemblyError(f"build receipt checkout revision missing or stale; rebuild: {triple}")
    archive_sha256 = hashing.sha256_file(archive)
    if package_record.get("sha256") != archive_sha256:
        raise AssemblyError(f"package record does not match packaged archive bytes; repackage: {triple}")
    if package_record.get("build_receipt_sha256") != hashing.sha256_file(receipt_path):
        raise AssemblyError(f"package record does not match build receipt; repackage: {triple}")
    qualify_record = load_record(
        repo_root / "build" / triple / "qualify" / "qualify-record.json", "qualify record"
    )
    if qualify_record.get("sha256") != archive_sha256:
        raise AssemblyError(f"qualify record does not match packaged archive bytes: {triple}")
    for section in ("product_checks", "smoke", "relocation"):
        if not all_checks_ok(qualify_record.get(section)):
            raise AssemblyError(f"qualify section {section} is not all-ok: {triple}")
    smoke_count = len(qualify_record["smoke"])
    for field in ("smoke_passed", "smoke_total"):
        recorded: object = qualify_record.get(field)
        if type(recorded) is not int or recorded != smoke_count:
            raise AssemblyError(f"qualify smoke counts disagree with {field}: {triple}")
    if not all_checks_ok(package_record.get("product_checks")):
        raise AssemblyError(f"package product checks are not all-ok: {triple}")
    return {
        "archive": archive,
        "package_record": package_record,
        "build_receipt": build_receipt,
        "qualify_record": qualify_record,
    }


def stage_triple(
    validated: dict, triple: str, release_dir: Path, revision: str, lock_sha256: str,
) -> None:
    archive = validated["archive"]
    package_record = validated["package_record"]
    build_receipt = validated["build_receipt"]
    qualify_record = validated["qualify_record"]
    release_archive = release_dir / product.archive_name(product.NODE_VERSION, triple)
    shutil.copyfile(archive, release_archive)
    staged_sha256 = hashing.sha256_file(release_archive)
    if staged_sha256 != package_record["sha256"]:
        raise AssemblyError(f"packaged archive changed during staging: {triple}")
    manifest = release.build_manifest(
        product=product.PRODUCT,
        version=product.NODE_VERSION,
        target=triple,
        source_revision=revision,
        sources_lock_sha256=lock_sha256,
        extra={
            "archive": release_archive.name,
            "sha256": staged_sha256,
            "size": release_archive.stat().st_size,
            "source": build_receipt.get("source", {}),
            "toolchain": build_receipt.get("toolchain", {}),
            "recipe": build_receipt.get("recipe", {}),
            "hardening": package_record.get("hardening", {}),
            "qualification": {
                "product_checks": qualify_record["product_checks"],
                "smoke_passed": qualify_record["smoke_passed"],
                "smoke_total": qualify_record["smoke_total"],
                "relocation": qualify_record["relocation"],
            },
        },
    )
    release.write_manifest(release_dir, manifest)


def assemble_all(repo_root: Path, triples: tuple[str, ...]) -> dict:
    from buildsys.targets import target_for_triple

    for triple in triples:
        target_for_triple(triple)
    if not triples:
        raise AssemblyError("no targets to assemble")
    revision = git_revision(repo_root)
    if git_dirty(repo_root):
        raise AssemblyError("refusing to assemble from a dirty checkout; commit first")

    lock_sha256 = hashing.sha256_file(repo_root / "sources.lock.json")
    validated = {triple: validate_triple(repo_root, triple, lock_sha256, revision) for triple in triples}
    final_dir = repo_root / "dist" / product.RELEASE_DIRNAME
    if final_dir.exists():
        raise AssemblyError(f"refusing to overwrite existing release directory: {final_dir}")
    with tempfile.TemporaryDirectory(prefix="assembly-tmp-", dir=repo_root / "build") as scratch:
        staging = Path(scratch)
        for triple in triples:
            stage_triple(validated[triple], triple, staging, revision, lock_sha256)
        release.write_sha256sums(staging)
        try:
            staging.rename(final_dir)
        except OSError as error:
            if final_dir.exists():
                raise AssemblyError(f"refusing to overwrite existing release directory: {final_dir}") from error
            raise
    return {
        "release_dir": str(final_dir),
        "targets": sorted(triples),
        "assets": sorted(path.name for path in final_dir.iterdir()),
    }
