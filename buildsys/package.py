from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from buildlib import elf, hashing, macho, release

from buildsys import inputs, product, validate_product
from buildsys.node import configure_env as node_configure_env


class PackageError(Exception):
    pass


def stage_dir(repo_root: Path, triple: str) -> Path:
    return repo_root / "build" / triple / "stage"


def install_to_stage(source: Path, stage: Path, recipe: dict) -> Path:
    install_root = stage / product.INSTALL_DIRNAME
    if install_root.exists():
        shutil.rmtree(install_root)
    stage.mkdir(parents=True, exist_ok=True)
    log_path = stage / "install.log"
    with (
        open(log_path, "w", encoding="utf-8") as log,
        subprocess.Popen(
            [sys.executable, "tools/install.py", "install",
             "--dest-dir", str(stage), "--prefix", "/node"],
            cwd=source, env=node_configure_env(recipe) | {"PYTHONIOENCODING": "utf-8"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8",
        ) as process,
    ):
        assert process.stdout is not None
        log.writelines(process.stdout)
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
    install_root: Path, machine: str, deployment_target: str, destination: Path, *, family: str
) -> dict:
    if family == "linux-musl":
        images = elf.find_elfs(install_root)
        record = {
            "images": {
                str(image.relative_to(install_root)): elf.inspect(image) for image in images
            },
            "deployment_target": deployment_target,
            "checks": [
                {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
                for finding in validate_product.elf_tree_checks(install_root, machine)
            ],
        }
        inputs.render_json(record, destination)
        return record
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
    if archive.exists():
        raise PackageError(f"refusing to overwrite existing archive: {archive}")
    mtime = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    return release.create_archive(install_root, archive, mtime=mtime, prefix=product.INSTALL_DIRNAME)


def package(repo_root: Path, triple: str, source: Path) -> dict:
    from buildsys.targets import target_for_triple

    wanted = target_for_triple(triple)
    from buildsys import recipes

    recipe = recipes.recipe_for_triple(triple)
    build_receipt = repo_root / "build" / triple / "build-receipt.json"
    if not build_receipt.is_file():
        raise PackageError(f"missing build receipt; build first: {build_receipt}")
    receipt_bytes = build_receipt.read_bytes()
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    try:
        receipt: object = json.loads(receipt_bytes)
    except ValueError as error:
        raise PackageError(f"invalid build receipt: {build_receipt}: {error}") from error
    binary_digest: object = receipt.get("built_node_sha256") if isinstance(receipt, dict) else None
    if not isinstance(binary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", binary_digest) is None:
        raise PackageError(f"build receipt has no node binary digest; rebuild: {build_receipt}")
    stage = stage_dir(repo_root, triple)
    install_root = install_to_stage(source, stage, recipe)
    installed_node = install_root / "bin" / "node"
    if not installed_node.is_file() or hashing.sha256_file(installed_node) != binary_digest:
        raise PackageError(f"installed node does not match build receipt; rebuild: {installed_node}")
    shutil.copyfile(source / "LICENSE", install_root / "LICENSE")
    removed = prune_to_contract(install_root)
    report = write_hardening_report(
        install_root, wanted.machine, wanted.deployment_target, stage / "hardening-report.json",
        family=wanted.family,
    )
    findings = validate_product.validate_install_tree(
        install_root,
        wanted.machine,
        wanted.deployment_target,
        [str(stage).encode()],
        [str(source).encode()],
        family=wanted.family,
    )
    validate_product.gate(findings)
    if hashing.sha256_file(build_receipt) != receipt_sha256:
        raise PackageError(f"build receipt changed while packaging: {build_receipt}")
    archive_name = product.archive_name(product.NODE_VERSION, triple)
    archive = create_archive(install_root, repo_root / "dist" / triple / archive_name)
    result = {
        "archive": str(archive),
        "sha256": hashing.sha256_file(archive),
        "build_receipt_sha256": receipt_sha256,
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
