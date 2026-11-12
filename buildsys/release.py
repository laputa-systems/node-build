from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from buildlib import hashing, release

from buildsys import product


class AssemblyError(Exception):
    pass


def git_revision(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode != 0:
        raise AssemblyError("not a git checkout")
    return completed.stdout.strip()


def git_dirty(repo_root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root, capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode != 0:
        raise AssemblyError("git status failed")
    return bool(completed.stdout.strip())


def load_record(path: Path, what: str) -> dict:
    if not path.is_file():
        raise AssemblyError(f"missing {what}: {path} (run package/qualify first)")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def all_checks_ok(entries: list[dict]) -> bool:
    return all(entry["ok"] for entry in entries)


def validate_triple(repo_root: Path, triple: str, revision: str) -> dict:
    archive_name = product.archive_name(product.NODE_VERSION, triple)
    archive = repo_root / "dist" / triple / archive_name
    if not archive.is_file():
        raise AssemblyError(f"missing packaged archive: {archive}")
    package_record = load_record(repo_root / "build" / triple / "package-record.json", "package record")
    build_receipt = load_record(repo_root / "build" / triple / "build-receipt.json", "build receipt")
    qualify_record = load_record(
        repo_root / "build" / triple / "qualify" / "qualify-record.json", "qualify record"
    )
    if qualify_record.get("sha256") != hashing.sha256_file(archive):
        raise AssemblyError(f"qualify record does not match packaged archive bytes: {triple}")
    for section in ("product_checks", "smoke", "relocation"):
        if not all_checks_ok(qualify_record[section]):
            raise AssemblyError(f"qualify section {section} is not all-ok: {triple}")
    for entry in package_record.get("product_checks", []):
        if not entry["ok"]:
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
    manifest = release.build_manifest(
        product=product.PRODUCT,
        version=product.NODE_VERSION,
        target=triple,
        source_revision=revision,
        sources_lock_sha256=lock_sha256,
        extra={
            "archive": release_archive.name,
            "sha256": hashing.sha256_file(release_archive),
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


def assemble(repo_root: Path, triple: str) -> dict:
    return assemble_all(repo_root, (triple,))


def assemble_all(repo_root: Path, triples: tuple[str, ...]) -> dict:
    from buildsys.targets import target_for_triple

    for triple in triples:
        target_for_triple(triple)
    if not triples:
        raise AssemblyError("no targets to assemble")
    revision = git_revision(repo_root)
    if git_dirty(repo_root):
        raise AssemblyError("refusing to assemble from a dirty checkout; commit first")

    validated = {triple: validate_triple(repo_root, triple, revision) for triple in triples}
    lock_sha256 = hashing.sha256_file(repo_root / "sources.lock.json")
    staging = repo_root / "build" / "assembly-tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for triple in triples:
        stage_triple(validated[triple], triple, staging, revision, lock_sha256)
    release.write_sha256sums(staging)

    final_dir = repo_root / "dist" / product.RELEASE_DIRNAME
    if final_dir.exists():
        raise AssemblyError(f"refusing to overwrite existing release directory: {final_dir}")
    staging.rename(final_dir)
    return {
        "release_dir": str(final_dir),
        "targets": sorted(triples),
        "assets": sorted(path.name for path in final_dir.iterdir()),
    }
