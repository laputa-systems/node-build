from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from buildsys import bootstrap, inputs, recipes
from buildsys.product import NODE_VERSION


class BuildError(Exception):
    pass


def source_dir(repo_root: Path) -> Path:
    return repo_root / "build" / "src" / f"node-v{NODE_VERSION}"


def work_dir(repo_root: Path, triple: str) -> Path:
    return repo_root / "build" / triple


def configure_env(recipe: dict) -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["MACOSX_DEPLOYMENT_TARGET"] = recipe["deployment_target"]
    env["CFLAGS"] = " ".join(recipe["cflags"])
    env["CXXFLAGS"] = " ".join(recipe["cflags"])
    return env


def ensure_extracted(repo_root: Path) -> Path:
    lock = inputs.load_lock(repo_root / "sources.lock.json")
    entry = inputs.lock_entry(lock, "node")
    archive = repo_root / "build" / "cache" / f"node-{entry['version']}.tar.gz"
    if not archive.exists():
        raise BuildError(f"missing cached source; run fetch first: {archive}")
    inputs.verify_file(archive, entry["sha256"], entry["size"])
    target = source_dir(repo_root)
    marker = target / "configure"
    if not marker.exists():
        inputs.safe_extract(archive, repo_root / "build" / "src")
    if not marker.exists():
        raise BuildError(f"extracted source has no configure script: {target}")
    return target


def run_configure(source: Path, recipe: dict) -> None:
    command = recipes.configure_command(str(source), recipe)
    completed = subprocess.run(
        command, cwd=source, env=configure_env(recipe),
        capture_output=True, text=True, timeout=600,
    )
    if completed.returncode != 0:
        raise BuildError(f"configure failed:\n{completed.stdout}\n{completed.stderr}")


def run_make(source: Path, recipe: dict, jobs: int, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(
            ["make", f"-j{jobs}"],
            cwd=source, env=configure_env(recipe),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
        if process.wait() != 0:
            raise BuildError(f"make failed; see {log_path}")


def built_node(source: Path) -> Path:
    candidate = source / "out" / "Release" / "node"
    if not candidate.exists():
        raise BuildError(f"build produced no binary: {candidate}")
    return candidate


def write_receipt(repo_root: Path, triple: str, recipe: dict, extra: dict) -> Path:
    source_lock = inputs.load_lock(repo_root / "sources.lock.json")
    toolchain_lock = inputs.load_json(repo_root / "bootstrap.lock.json")
    receipt = {
        "node_version": NODE_VERSION,
        "target": triple,
        "source": inputs.lock_entry(source_lock, "node"),
        "toolchain": toolchain_lock["toolchain"],
        "cpu_baseline": toolchain_lock["cpu_baseline"],
        "recipe": recipe,
        "effective_env": {
            "MACOSX_DEPLOYMENT_TARGET": recipe["deployment_target"],
            "CFLAGS": " ".join(recipe["cflags"]),
            "CXXFLAGS": " ".join(recipe["cflags"]),
        },
        "builder_python": ".".join(str(part) for part in sys.version_info[:3]),
    }
    receipt.update(extra)
    destination = work_dir(repo_root, triple) / "build-receipt.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    inputs.render_json(receipt, destination)
    return destination


def build(repo_root: Path, triple: str, jobs: int) -> Path:
    from buildsys.targets import target_for_triple

    wanted = target_for_triple(triple)
    recipe = recipes.macos_recipe()
    source = ensure_extracted(repo_root)
    run_configure(source, recipe)
    run_make(source, recipe, jobs, work_dir(repo_root, triple) / "make.log")
    binary = built_node(source)
    write_receipt(repo_root, triple, recipe, {"built_node": str(binary)})
    return binary
