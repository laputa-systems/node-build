from __future__ import annotations

import subprocess
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


def validate_signature(node: Path) -> ProductFinding:
    completed = subprocess.run(
        ["codesign", "--verify", "--verbose", str(node)],
        capture_output=True, text=True, timeout=120,
    )
    ok = completed.returncode == 0
    return ProductFinding("codesign", ok, (completed.stderr or completed.stdout).strip()[:200])


def validate_install_tree(
    install_root: Path, deployment_target: str, build_prefixes: list[bytes]
) -> list[ProductFinding]:
    from buildsys import relocate

    findings = validate_layout(install_root)
    node = install_root / "bin" / "node"
    try:
        info = macho.inspect(node)
        for finding in macho.validate_executable(info, deployment_target):
            findings.append(ProductFinding(f"macho-{finding.name}", finding.ok, finding.detail))
        findings.append(
            ProductFinding(
                "macho-deps",
                True,
                f"linked: {list(info.dependencies)}",
            )
        )
    except macho.MachOError as error:
        findings.append(ProductFinding("macho-parse", False, str(error)[:300]))
    findings.append(validate_signature(node))
    hits = relocate.scan_forbidden_refs(node, build_prefixes)
    findings.append(
        ProductFinding(
            "no-build-refs",
            not hits,
            f"forbidden prefixes: {hits}" if hits else "no absolute build refs",
        )
    )
    return findings


def gate(findings: list[ProductFinding]) -> None:
    failed = [finding for finding in findings if not finding.ok]
    if failed:
        names = ", ".join(finding.name for finding in failed)
        raise GateError(f"product gate failed: {names}")
