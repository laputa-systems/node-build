from __future__ import annotations

import shutil
from pathlib import Path

from buildsys import inputs, relocate, smoke, validate_product
from buildsys.product import local_archive_name, NODE_VERSION


class QualifyError(Exception):
    pass


def qualify_dir(repo_root: Path, triple: str) -> Path:
    return repo_root / "build" / triple / "qualify"


def qualify(repo_root: Path, triple: str) -> dict:
    from buildsys import node as node_driver
    from buildsys.targets import target_for_triple

    wanted = target_for_triple(triple)
    archive = repo_root / "dist" / triple / local_archive_name(NODE_VERSION, triple, 1)
    if not archive.is_file():
        raise QualifyError(f"no packaged archive; run package first: {archive}")
    work = qualify_dir(repo_root, triple)
    if work.exists():
        shutil.rmtree(work)
    extracted = work / "extracted" / "node"
    extracted.parent.mkdir(parents=True, exist_ok=True)
    inputs.safe_extract(archive, extracted.parent)
    if not (extracted / "bin" / "node").is_file():
        raise QualifyError(f"archive has no bin/node: {archive}")
    findings = validate_product.validate_install_tree(
        extracted,
        wanted.machine,
        wanted.deployment_target,
        [str(repo_root / "build" / triple / "stage").encode()],
        [str(node_driver.source_dir(repo_root)).encode()],
    )
    smoke_work = work / "smoke-work"
    smoke_work.mkdir(parents=True, exist_ok=True)
    smoke_findings = smoke.run_suite(
        extracted / "bin" / "node",
        extracted,
        extracted / "include" / "node",
        smoke_work,
        repo_root / "tests" / "fixtures",
        triple,
    )
    reloc_findings = relocate.verify_relocation(
        extracted,
        work / "reloc-a",
        work / "reloc b with spaces",
        [str(repo_root / "build" / triple / "stage").encode()],
        [str(node_driver.source_dir(repo_root)).encode()],
    )
    record = {
        "archive": str(archive),
        "sha256": inputs.sha256_of_file(archive),
        "product_checks": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in findings
        ],
        "smoke": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in smoke_findings
        ],
        "relocation": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in reloc_findings
        ],
        "smoke_passed": sum(1 for finding in smoke_findings if finding.ok),
        "smoke_total": len(smoke_findings),
    }
    inputs.render_json(record, work / "qualify-record.json")
    failures = (
        [finding for finding in findings if not finding.ok]
        + [finding for finding in smoke_findings if not finding.ok]
        + [finding for finding in reloc_findings if not finding.ok]
    )
    if failures:
        names = ", ".join(finding.name for finding in failures)
        raise QualifyError(f"qualification failed: {names}")
    return record
