from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from buildsys import inputs, product


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


def tag_target(tag: str, repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", f"refs/tags/{tag}"], cwd=repo_root,
        capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def check_tag(tag: str, revision: str, repo_root: Path) -> None:
    existing = tag_target(tag, repo_root)
    if existing is not None and existing != revision:
        raise AssemblyError(f"tag {tag} already points at {existing}, not {revision}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_record(path: Path, what: str) -> dict:
    if not path.is_file():
        raise AssemblyError(f"missing {what}: {path} (run package/qualify first)")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def all_checks_ok(entries: list[dict]) -> bool:
    return all(entry["ok"] for entry in entries)


def validate_triple(repo_root: Path, triple: str, revision: str) -> dict:
    archive_name = product.local_archive_name(product.NODE_VERSION, triple, 1)
    archive = repo_root / "dist" / triple / archive_name
    if not archive.is_file():
        raise AssemblyError(f"missing packaged archive: {archive}")
    package_record = load_record(repo_root / "build" / triple / "package-record.json", "package record")
    build_receipt = load_record(repo_root / "build" / triple / "build-receipt.json", "build receipt")
    qualify_record = load_record(
        repo_root / "build" / triple / "qualify" / "qualify-record.json", "qualify record"
    )
    if qualify_record.get("sha256") != sha256_file(archive):
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
    validated: dict, triple: str, tag: str, release_dir: Path, base_url: str,
    title: str, revision: str,
) -> dict:
    archive = validated["archive"]
    package_record = validated["package_record"]
    build_receipt = validated["build_receipt"]
    qualify_record = validated["qualify_record"]
    release_name = product.release_archive_name(product.NODE_VERSION, tag, triple)
    release_archive = release_dir / release_name
    shutil.copyfile(archive, release_archive)
    archive_sha = sha256_file(release_archive)
    artifact_manifest = {
        "version": product.NODE_VERSION,
        "target": triple,
        "release_title": title,
        "archive": release_name,
        "sha256": archive_sha,
        "size": release_archive.stat().st_size,
        "source_revision": revision,
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
    }
    inputs.render_json(artifact_manifest, release_dir / product.release_manifest_name(triple))
    return {"archive": release_name, "sha256": archive_sha, "url": f"{base_url}/{release_name}"}


def assemble(repo_root: Path, triple: str, tag: str, github_repo: str) -> dict:
    return assemble_all(repo_root, (triple,), tag, github_repo)


def assemble_all(repo_root: Path, triples: tuple[str, ...], tag: str, github_repo: str) -> dict:
    from buildsys.targets import target_for_triple

    if "/" not in github_repo:
        raise AssemblyError(f"--repo must be owner/name, got {github_repo!r}")
    for triple in triples:
        target_for_triple(triple)
    if not triples:
        raise AssemblyError("no targets to assemble")
    revision = git_revision(repo_root)
    if git_dirty(repo_root):
        raise AssemblyError("refusing to assemble from a dirty checkout; commit first")
    check_tag(tag, revision, repo_root)

    validated = {triple: validate_triple(repo_root, triple, revision) for triple in triples}
    title = product.release_title(product.NODE_VERSION, tag)
    base_url = f"https://github.com/{github_repo}/releases/download/{title}"
    staging = repo_root / "build" / "assembly-tmp"
    if staging.exists():
        shutil.rmtree(staging)
    release_dir = staging
    release_dir.mkdir(parents=True)
    entries: dict[str, dict] = {}
    for triple in triples:
        entries[triple] = stage_triple(
            validated[triple], triple, tag, release_dir, base_url, title, revision,
        )
    inputs.render_json(
        {
            "version": product.NODE_VERSION,
            "targets": {
                triple: {
                    "version": product.NODE_VERSION,
                    "target": triple,
                    "url": entries[triple]["url"],
                    "sha256": entries[triple]["sha256"],
                }
                for triple in triples
            },
        },
        release_dir / product.DOWNLOAD_METADATA_NAME,
    )
    inputs.render_json(
        {
            "version": product.NODE_VERSION,
            "targets": {
                triple: {
                    "version": product.NODE_VERSION,
                    "target": triple,
                    "url": f"file://{release_dir / entries[triple]['archive']}",
                    "sha256": entries[triple]["sha256"],
                }
                for triple in triples
            },
        },
        release_dir / product.SMOKE_METADATA_NAME,
    )
    inputs.render_json(
        {
            "release_title": title,
            "tag": tag,
            "source_revision": revision,
            "targets": sorted(triples),
            "assets": sorted(path.name for path in release_dir.iterdir()),
        },
        release_dir / product.ASSEMBLY_MANIFEST_NAME,
    )
    checksums = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in sorted(release_dir.iterdir())
    )
    (release_dir / product.CHECKSUMS_NAME).write_text(checksums, encoding="utf-8")

    final_dir = repo_root / "dist" / tag
    if final_dir.exists():
        raise AssemblyError(f"refusing to overwrite existing release directory: {final_dir}")
    staging.rename(final_dir)
    return {
        "release_dir": str(final_dir),
        "release_title": title,
        "targets": sorted(triples),
        "assets": sorted(path.name for path in final_dir.iterdir()),
    }
