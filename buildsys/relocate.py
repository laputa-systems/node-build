from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RelocationFinding:
    name: str
    ok: bool
    detail: str


def scan_forbidden_refs(binary: Path, forbidden: list[bytes]) -> list[bytes]:
    data = binary.read_bytes()
    return [prefix for prefix in forbidden if prefix in data]


def copy_tree(source: Path, destination: Path) -> Path:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing directory: {destination}")
    shutil.copytree(source, destination, symlinks=False)
    return destination


def run_version(node: Path, timeout: int = 60) -> str:
    completed = subprocess.run(
        [str(node), "--version"], capture_output=True, text=True, timeout=timeout
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{node} --version failed: {completed.stderr}")
    return completed.stdout.strip()


def verify_relocation(
    install_root: Path,
    first: Path,
    second: Path,
    stage_prefixes: list[bytes],
    source_prefixes: list[bytes],
) -> list[RelocationFinding]:
    findings: list[RelocationFinding] = []
    binary = install_root / "bin" / "node"
    stage_hits = scan_forbidden_refs(binary, stage_prefixes)
    findings.append(
        RelocationFinding(
            "no-stage-refs",
            not stage_hits,
            f"stage prefixes: {stage_hits}" if stage_hits else "no stage path leaks",
        )
    )
    source_hits = scan_forbidden_refs(binary, source_prefixes)
    findings.append(
        RelocationFinding(
            "info-source-refs",
            True,
            f"{len(source_hits)} upstream-inert config strings" if source_hits else "none",
        )
    )
    for label, destination in (("plain", first), ("with spaces", second)):
        try:
            copy_tree(install_root, destination)
            version = run_version(destination / "bin" / "node")
            findings.append(RelocationFinding(f"relocate-{label}", True, version))
        except (FileExistsError, OSError, RuntimeError) as error:
            findings.append(RelocationFinding(f"relocate-{label}", False, str(error)[:300]))
    return findings
