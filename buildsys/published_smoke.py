from __future__ import annotations

import shutil
from pathlib import Path

from buildsys import inputs, smoke


class PublishedSmokeError(Exception):
    pass


def published_smoke(repo_root: Path, triple: str, tag: str) -> dict:
    release_dir = repo_root / "dist" / tag
    metadata_path = release_dir / "smoke-metadata.json"
    if not release_dir.is_dir() or not metadata_path.is_file():
        raise PublishedSmokeError(f"no assembled release: {release_dir}")
    metadata = inputs.load_json(metadata_path)
    archives = sorted(path for path in release_dir.iterdir() if path.suffix == ".gz")
    if len(archives) != 1:
        raise PublishedSmokeError(f"release must hold exactly one archive: {release_dir}")
    archive = archives[0]
    if inputs.sha256_of_file(archive) != metadata["sha256"]:
        raise PublishedSmokeError(f"archive bytes do not match smoke-metadata: {archive.name}")
    work = repo_root / "build" / triple / "published-smoke"
    if work.exists():
        shutil.rmtree(work)
    extracted = work / "extracted" / "node"
    extracted.parent.mkdir(parents=True, exist_ok=True)
    inputs.safe_extract(archive, extracted.parent)
    node = extracted / "bin" / "node"
    smoke_work = work / "smoke-work"
    smoke_work.mkdir(parents=True, exist_ok=True)
    findings = smoke.run_suite(
        node, extracted, extracted / "include" / "node",
        smoke_work, repo_root / "tests" / "fixtures",
    )
    record = {
        "release": tag,
        "archive": archive.name,
        "smoke": [
            {"name": finding.name, "ok": finding.ok, "detail": finding.detail}
            for finding in findings
        ],
        "passed": sum(1 for finding in findings if finding.ok),
        "total": len(findings),
    }
    inputs.render_json(record, work / "published-smoke-record.json")
    failed = [finding for finding in findings if not finding.ok]
    if failed:
        names = ", ".join(finding.name for finding in failed)
        raise PublishedSmokeError(f"published-byte smoke failed: {names}")
    return record
