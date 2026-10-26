from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from buildsys import inputs, macho, product, validate_product
from buildsys.node import configure_env as node_configure_env


class PackageError(Exception):
    pass


def stage_dir(repo_root: Path, triple: str) -> Path:
    return repo_root / "build" / triple / "stage"


def install_to_stage(source: Path, stage: Path, recipe: dict) -> Path:
    install_root = stage / product.INSTALL_DIRNAME
    if install_root.exists():
        shutil.rmtree(install_root)
    log_path = stage / "install.log"
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "tools/install.py", "install",
             "--dest-dir", str(stage), "--prefix", "/node"],
            cwd=source, env=node_configure_env(recipe),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
        if process.wait() != 0:
            raise PackageError(f"install failed; see {log_path}")
    if not install_root.is_dir():
        raise PackageError(f"install produced no tree: {install_root}")
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
    install_root: Path, machine: str, deployment_target: str, destination: Path
) -> dict:
    images = macho.find_machos(install_root)
    record = {
        "images": {
            str(image.relative_to(install_root)): macho.inspect(image) for image in images
        },
        "deployment_target": deployment_target,
        "checks": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in validate_product.macho_tree_checks(
                install_root, machine, deployment_target
            )
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
    from buildsys import recipes

    recipe = recipes.macos_recipe()
    stage = stage_dir(repo_root, triple)
    install_root = install_to_stage(source, stage, recipe)
    removed = prune_to_contract(install_root)
    report = write_hardening_report(
        install_root, wanted.machine, wanted.deployment_target, stage / "hardening-report.json"
    )
    findings = validate_product.validate_install_tree(
        install_root,
        wanted.machine,
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
