from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from buildsys import macho


@dataclass(frozen=True)
class ProductFinding:
    name: str
    ok: bool
    detail: str


class GateError(Exception):
    pass


REQUIRED_FILES = (
    "bin/node",
    "LICENSE",
)

REQUIRED_HEADERS = (
    "node_api.h",
    "node.h",
)

ABSENT_PATHS = (
    "bin/npm",
    "bin/npx",
    "lib/node_modules",
)


def validate_layout(install_root: Path) -> list[ProductFinding]:
    findings: list[ProductFinding] = []
    for relative in REQUIRED_FILES:
        present = (install_root / relative).is_file()
        findings.append(ProductFinding(f"layout-{relative}", present, "present" if present else "missing"))
    include = install_root / "include" / "node"
    for header in REQUIRED_HEADERS:
        present = (include / header).is_file()
        findings.append(ProductFinding(f"header-{header}", present, "present" if present else "missing"))
    for relative in ABSENT_PATHS:
        absent = not (install_root / relative).exists()
        findings.append(ProductFinding(f"absent-{relative}", absent, "absent" if absent else "must not ship"))
    return findings


def macho_tree_checks(
    install: Path, machine: str, deployment_target: str
) -> list[ProductFinding]:
    install = install.resolve()
    required = (install / "bin" / "node",)
    images = macho.find_machos(install)
    universal = [path for path in install.rglob("*") if path.is_file() and not path.is_symlink()
                 and _is_fat(path)]
    findings: list[ProductFinding] = [
        ProductFinding("macho-image-count", bool(images), f"{len(images)} images"),
        ProductFinding(
            "macho-no-universal",
            not universal,
            f"universal: {[str(p.relative_to(install)) for p in universal]}" if universal else "no fat images",
        ),
    ]
    try:
        executables = [image for image in images if macho.read_header(image).kind == "execute"]
    except macho.MachOError as error:
        return findings + [ProductFinding("macho-parse", False, str(error)[:200])]
    missing = [str(image.relative_to(install)) for image in required if image not in images]
    findings.append(
        ProductFinding("macho-required-images", not missing, f"missing: {missing}" if missing else "bin/node present")
    )
    buckets: dict[str, list[str]] = {
        "macho-arch": [], "macho-platform": [], "macho-minos": [],
        "macho-deps": [], "macho-unresolved-deps": [],
        "macho-rpaths": [], "macho-unresolved-rpaths": [],
        "macho-signatures": [], "macho-non-pie": [], "macho-version": [],
    }
    for image in images:
        name = str(image.relative_to(install))
        try:
            header = macho.read_header(image)
            deps = macho.dependencies(image)
            rpaths = macho.rpaths(image)
        except macho.MachOError as error:
            buckets["macho-version"].append(f"{name}: {error}")
            continue
        if header.arch != machine or not header.is_64:
            buckets["macho-arch"].append(f"{name}: {header.arch}")
        if header.kind == "execute" and not header.pie:
            buckets["macho-non-pie"].append(name)
        version_commands = [
            command for command in macho.load_commands(image)
            if command.cmd in (macho.LC_BUILD_VERSION, macho.LC_VERSION_MIN_MACOSX)
        ]
        if len(version_commands) != 1:
            buckets["macho-version"].append(f"{name}: {len(version_commands)} version commands")
            version = None
        else:
            version = macho.build_version(image)
        if version is not None:
            if version.platform != macho.PLATFORM_MACOS:
                buckets["macho-platform"].append(f"{name}: {version.platform_name}")
            if version.minos != deployment_target:
                buckets["macho-minos"].append(
                    f"{name}: expected {deployment_target}, got {version.minos}"
                )
        for rpath in rpaths:
            if rpath.startswith(("@loader_path", "@executable_path")):
                directories = macho.rpath_directories(rpath, image, install, executables)
                if not directories or any(directory is None for directory in directories):
                    buckets["macho-rpaths"].append(f"{name}: {rpath}")
                elif not all(directory.is_dir() for directory in directories if directory):
                    buckets["macho-unresolved-rpaths"].append(f"{name}: {rpath}")
            elif macho.system_load_path(rpath):
                if not Path(rpath).is_dir():
                    buckets["macho-unresolved-rpaths"].append(f"{name}: {rpath}")
            else:
                buckets["macho-rpaths"].append(f"{name}: {rpath}")
        for dependency in deps:
            if dependency.startswith("@rpath/"):
                suffix = dependency.removeprefix("@rpath/")
                if not suffix or Path(suffix).is_absolute() or ".." in Path(suffix).parts:
                    buckets["macho-deps"].append(f"{name} -> {dependency}")
                    continue
                directories = [
                    directory
                    for rpath in rpaths
                    for directory in macho.rpath_directories(rpath, image, install, executables)
                ]
                candidates = [
                    (directory / suffix).resolve()
                    for directory in directories
                    if directory is not None and directory.is_dir()
                ]
                if not any(macho._inside(candidate, install) and candidate.is_file() for candidate in candidates):
                    buckets["macho-unresolved-deps"].append(f"{name} -> {dependency}")
            elif dependency.startswith(("@loader_path/", "@executable_path/")) or dependency in ("@loader_path", "@executable_path"):
                resolved = macho.resolve_image_path(dependency, image, install)
                if resolved is None:
                    buckets["macho-deps"].append(f"{name} -> {dependency}")
                elif not resolved.is_file():
                    buckets["macho-unresolved-deps"].append(f"{name} -> {dependency}")
            elif macho.system_load_path(dependency):
                continue
            else:
                buckets["macho-deps"].append(f"{name} -> {dependency}")
        valid, detail = macho.signature_status(image)
        if not valid:
            buckets["macho-signatures"].append(f"{name}: {detail[:120]}")
    for bucket, entries in buckets.items():
        findings.append(
            ProductFinding(bucket, not entries, "; ".join(entries[:5]) if entries else "ok")
        )
    return findings


def _is_fat(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) in (
                b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
            )
    except OSError:
        return False


def validate_install_tree(
    install_root: Path,
    machine: str,
    deployment_target: str,
    stage_prefixes: list[bytes],
    source_prefixes: list[bytes],
) -> list[ProductFinding]:
    from buildsys import relocate

    findings = validate_layout(install_root)
    findings += macho_tree_checks(install_root, machine, deployment_target)
    node = install_root / "bin" / "node"
    stage_hits = relocate.scan_forbidden_refs(node, stage_prefixes)
    findings.append(
        ProductFinding(
            "no-stage-refs",
            not stage_hits,
            f"stage prefixes: {stage_hits}" if stage_hits else "no stage path leaks",
        )
    )
    source_hits = relocate.scan_forbidden_refs(node, source_prefixes)
    findings.append(
        ProductFinding(
            "info-source-refs",
            True,
            f"{len(source_hits)} upstream-inert config strings" if source_hits else "none",
        )
    )
    return findings


def gate(findings: list[ProductFinding]) -> None:
    failed = [finding for finding in findings if not finding.ok]
    if failed:
        names = ", ".join(finding.name for finding in failed)
        raise GateError(f"product gate failed: {names}")
