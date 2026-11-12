from __future__ import annotations

import json
import shutil
from pathlib import Path

from buildsys import inputs, smoke
from buildsys.product import NODE_VERSION, RELEASE_DIRNAME, archive_name, manifest_name


class PublishedSmokeError(Exception):
    pass


def published_smoke(repo_root: Path, triple: str) -> dict:
    release_dir = repo_root / "dist" / RELEASE_DIRNAME
    manifest_path = release_dir / manifest_name(NODE_VERSION, triple)
    if not release_dir.is_dir() or not manifest_path.is_file():
        raise PublishedSmokeError(f"no assembled release for {triple}: {release_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = release_dir / archive_name(NODE_VERSION, triple)
    if not archive.is_file():
        raise PublishedSmokeError(f"release has no archive for {triple}: {archive.name}")
    if inputs.sha256_of_file(archive) != manifest.get("sha256"):
        raise PublishedSmokeError(f"archive bytes do not match manifest: {archive.name}")
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
        smoke_work, repo_root / "tests" / "fixtures", triple,
    )
    record = {
        "release": RELEASE_DIRNAME,
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
