from __future__ import annotations

import hashlib
import shutil
import subprocess
import tarfile
from pathlib import Path

from buildsys import inputs, macho, product, validate_product


class PackageError(Exception):
    pass


def stage_dir(repo_root: Path, triple: str) -> Path:
    return repo_root / "build" / triple / "stage"


def install_to_stage(source: Path, stage: Path) -> Path:
    install_root = stage / product.INSTALL_DIRNAME
    if install_root.exists():
        shutil.rmtree(install_root)
    completed = subprocess.run(
        ["make", "install", f"DESTDIR={stage}", "PREFIX=/node"],
        cwd=source, capture_output=True, text=True, timeout=1200,
    )
    if completed.returncode != 0:
        raise PackageError(f"make install failed:\n{completed.stdout}\n{completed.stderr}")
    if not install_root.is_dir():
        raise PackageError(f"make install produced no tree: {install_root}")
    return install_root


def prune_to_contract(install_root: Path) -> list[str]:
    removed: list[str] = []
    for relative in ("share", "lib/node_modules", "bin/npm", "bin/npx"):
        victim = install_root / relative
        if victim.is_symlink() or victim.is_file():
            victim.unlink()
            removed.append(relative)
        elif victim.is_dir():
            shutil.rmtree(victim)
            removed.append(relative)
    for leftover in sorted(install_root.rglob("*.pyc")):
        leftover.unlink()
        removed.append(str(leftover.relative_to(install_root)))
    return removed


def write_hardening_report(
    install_root: Path, deployment_target: str, destination: Path
) -> dict:
    info = macho.inspect(install_root / product.STAGED_NODE)
    record = {
        "binary": product.STAGED_NODE,
        "arch": f"{info.cputype:#x}",
        "filetype": info.filetype,
        "pie": info.pie,
        "minos": info.minos,
        "sdk": info.sdk,
        "dependencies": list(info.dependencies),
        "rpaths": list(info.rpaths),
        "deployment_target": deployment_target,
        "checks": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in macho.validate_executable(info, deployment_target)
        ],
    }
    inputs.render_json(record, destination)
    return record


def create_archive(install_root: Path, archive: Path) -> Path:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise PackageError(f"refusing to overwrite existing archive: {archive}")
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.add(install_root, arcname=product.INSTALL_DIRNAME, recursive=True)
    digest = hashlib.sha256()
    with open(archive, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return archive


def package(repo_root: Path, triple: str, source: Path) -> dict:
    from buildsys.targets import target_for_triple

    wanted = target_for_triple(triple)
    stage = stage_dir(repo_root, triple)
    install_root = install_to_stage(source, stage)
    removed = prune_to_contract(install_root)
    report = write_hardening_report(
        install_root, wanted.deployment_target, stage / "hardening-report.json"
    )
    findings = validate_product.validate_install_tree(
        install_root,
        wanted.deployment_target,
        [str(source).encode(), str(stage).encode()],
    )
    validate_product.gate(findings)
    archive_name = product.local_archive_name(product.NODE_VERSION, triple, 1)
    archive = create_archive(install_root, repo_root / "dist" / triple / archive_name)
    result = {
        "archive": str(archive),
        "sha256": inputs.sha256_of_file(archive),
        "size": archive.stat().st_size,
        "pruned": removed,
        "hardening": report,
        "product_checks": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in findings
        ],
    }
    inputs.render_json(result, repo_root / "build" / triple / "package-record.json")
    return result
