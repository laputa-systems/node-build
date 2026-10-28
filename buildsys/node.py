from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from buildsys import inputs, recipes
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
    if "--dest-os=mac" in recipe["configure"]:
        env["MACOSX_DEPLOYMENT_TARGET"] = recipe["deployment_target"]
    env["CFLAGS"] = " ".join(recipe["cflags"])
    env["CXXFLAGS"] = " ".join(recipe["cflags"])
    return env


PATCH_LEVEL = 1

PRODUCT_PATCHES = (
    (
        "common.gypi",
        "'MACOSX_DEPLOYMENT_TARGET': '13.5',       # -mmacosx-version-min=13.5",
        "'MACOSX_DEPLOYMENT_TARGET': '26.0',       # -mmacosx-version-min=26.0",
    ),
)


def apply_product_patches(source: Path) -> list[str]:
    applied: list[str] = []
    for relative, old, new in PRODUCT_PATCHES:
        target = source / relative
        text = target.read_text(encoding="utf-8")
        if new in text:
            applied.append(f"{relative}: already applied")
            continue
        if text.count(old) != 1:
            raise BuildError(f"patch target not found exactly once in {relative}")
        target.write_text(text.replace(old, new), encoding="utf-8")
        applied.append(f"{relative}: applied macOS floor 26.0 (patch level {PATCH_LEVEL})")
    return applied


def ensure_extracted(repo_root: Path, triple: str) -> Path:
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
    if triple == "aarch64-apple-darwin":
        apply_product_patches(target)
    return target


def configured_marker(repo_root: Path, triple: str) -> Path:
    return work_dir(repo_root, triple) / "configured.json"


def recipe_fingerprint(recipe: dict) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps({"recipe": recipe, "patch_level": PATCH_LEVEL}, sort_keys=True).encode("utf-8")
    ).hexdigest()


def needs_configure(source: Path, repo_root: Path, triple: str, recipe: dict) -> bool:
    marker = configured_marker(repo_root, triple)
    if not marker.is_file():
        return True
    try:
        recorded = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return recorded.get("recipe_sha256") != recipe_fingerprint(recipe) or not (
        source / "config.mk"
    ).exists()


def run_configure(source: Path, repo_root: Path, triple: str, recipe: dict) -> None:
    command = recipes.configure_command(str(source), recipe)
    completed = subprocess.run(
        command, cwd=source, env=configure_env(recipe),
        capture_output=True, text=True, timeout=600, check=False,
    )
    if completed.returncode != 0:
        raise BuildError(f"configure failed:\n{completed.stdout}\n{completed.stderr}")
    inputs.render_json(
        {"recipe_sha256": recipe_fingerprint(recipe), "command": command},
        configured_marker(repo_root, triple),
    )


def run_make(source: Path, recipe: dict, jobs: int, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(
            ["make", f"-j{jobs}"],
            cwd=source, env=configure_env(recipe),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        assert process.stdout is not None
        log.writelines(process.stdout)
        if process.wait() != 0:
            raise BuildError(f"make failed; see {log_path}")


def built_node(source: Path) -> Path:
    candidate = source / "out" / "Release" / "node"
    if not candidate.exists():
        raise BuildError(f"build produced no binary: {candidate}")
    return candidate


def write_receipt(repo_root: Path, triple: str, recipe: dict, extra: dict) -> Path:
    from buildsys.targets import target_for_triple

    wanted = target_for_triple(triple)
    source_lock = inputs.load_lock(repo_root / "sources.lock.json")
    toolchain_lock = inputs.load_json(repo_root / "bootstrap.lock.json")
    if wanted.family == "linux":
        toolchain_section = toolchain_lock["linux_toolchain"]
        baseline_section = toolchain_lock["linux_baseline"]
        effective_env = {
            "CFLAGS": " ".join(recipe["cflags"]),
            "CXXFLAGS": " ".join(recipe["cflags"]),
        }
    else:
        toolchain_section = toolchain_lock["toolchain"]
        baseline_section = toolchain_lock["cpu_baseline"]
        effective_env = {
            "MACOSX_DEPLOYMENT_TARGET": recipe["deployment_target"],
            "CFLAGS": " ".join(recipe["cflags"]),
            "CXXFLAGS": " ".join(recipe["cflags"]),
        }
    receipt = {
        "node_version": NODE_VERSION,
        "target": triple,
        "source": inputs.lock_entry(source_lock, "node"),
        "toolchain": toolchain_section,
        "cpu_baseline": baseline_section,
        "recipe": recipe,
        "effective_env": effective_env,
        "builder_python": ".".join(str(part) for part in sys.version_info[:3]),
    }
    receipt.update(extra)
    destination = work_dir(repo_root, triple) / "build-receipt.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    inputs.render_json(receipt, destination)
    return destination


def build(repo_root: Path, triple: str, jobs: int) -> Path:
    from buildsys.targets import target_for_triple

    target_for_triple(triple)
    recipe = recipes.recipe_for_triple(triple)
    source = ensure_extracted(repo_root, triple)
    if needs_configure(source, repo_root, triple, recipe):
        run_configure(source, repo_root, triple, recipe)
    run_make(source, recipe, jobs, work_dir(repo_root, triple) / "make.log")
    binary = built_node(source)
    applied = apply_product_patches(source) if triple == "aarch64-apple-darwin" else []
    write_receipt(repo_root, triple, recipe, {"built_node": str(binary), "patches": applied})
    return binary
