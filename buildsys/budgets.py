from __future__ import annotations

import tarfile
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict

from buildlib import locks


class BudgetError(Exception):
    pass


class _Ceilings(TypedDict):
    compressed_max_bytes: int
    installed_payload_max_bytes: int


class _BudgetReport(TypedDict):
    triple: str
    compressed: int
    payload: int
    ceilings: _Ceilings
    ok: bool


def archive_payload_bytes(archive: Path) -> tuple[int, int]:
    compressed = archive.stat().st_size
    with tarfile.open(archive, "r:*") as tar:
        payload = sum(member.size for member in tar.getmembers() if member.isfile())
    return compressed, payload


def _byte_limit(budget: Mapping[str, object], triple: str, field: str) -> int:
    value = budget.get(field)
    if type(value) is not int or value < 0:
        raise BudgetError(f"{triple}.{field}: expected a nonnegative integer byte limit")
    return value


def check_budgets(repo_root: Path, triple: str) -> _BudgetReport:
    from buildsys.product import NODE_VERSION, archive_name

    try:
        budget = locks.load_budgets(repo_root / "release-budgets.json").for_target(triple)
    except locks.LockError as error:
        raise BudgetError(str(error)) from error
    compressed_limit = _byte_limit(budget, triple, "compressed_max_bytes")
    payload_limit = _byte_limit(budget, triple, "installed_payload_max_bytes")
    archive = repo_root / "dist" / triple / archive_name(NODE_VERSION, triple)
    if not archive.is_file():
        raise BudgetError(f"missing archive: {archive}")
    compressed, payload = archive_payload_bytes(archive)
    failures = []
    if compressed > compressed_limit:
        failures.append(f"compressed {compressed} > {compressed_limit}")
    if payload > payload_limit:
        failures.append(f"payload {payload} > {payload_limit}")
    record: _BudgetReport = {
        "triple": triple,
        "compressed": compressed,
        "payload": payload,
        "ceilings": {
            "compressed_max_bytes": compressed_limit,
            "installed_payload_max_bytes": payload_limit,
        },
        "ok": not failures,
    }
    if failures:
        raise BudgetError("; ".join(failures))
    return record
