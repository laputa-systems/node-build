from __future__ import annotations

import tarfile
from pathlib import Path

from buildlib import locks


class BudgetError(Exception):
    pass


def archive_payload_bytes(archive: Path) -> tuple[int, int]:
    compressed = archive.stat().st_size
    with tarfile.open(archive, "r:*") as tar:
        payload = sum(member.size for member in tar.getmembers() if member.isfile())
    return compressed, payload


def check_budgets(repo_root: Path, triple: str) -> dict:
    from buildsys.product import NODE_VERSION, archive_name

    try:
        budget = locks.load_budgets(repo_root / "release-budgets.json").for_target(triple)
    except locks.LockError as error:
        raise BudgetError(str(error)) from error
    archive = repo_root / "dist" / triple / archive_name(NODE_VERSION, triple)
    if not archive.is_file():
        raise BudgetError(f"missing archive: {archive}")
    compressed, payload = archive_payload_bytes(archive)
    failures = []
    if compressed > budget["compressed_max_bytes"]:
        failures.append(f"compressed {compressed} > {budget['compressed_max_bytes']}")
    if payload > budget["installed_payload_max_bytes"]:
        failures.append(f"payload {payload} > {budget['installed_payload_max_bytes']}")
    record = {
        "triple": triple,
        "compressed": compressed,
        "payload": payload,
        "ceilings": {
            "compressed_max_bytes": budget["compressed_max_bytes"],
            "installed_payload_max_bytes": budget["installed_payload_max_bytes"],
        },
        "ok": not failures,
    }
    if failures:
        raise BudgetError("; ".join(failures))
    return record
