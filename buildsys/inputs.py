from __future__ import annotations

import json
import tarfile
from pathlib import Path


class UnsafeArchiveError(Exception):
    pass


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = base / member.name
            try:
                target.relative_to(base)
                target.resolve().relative_to(base)
            except ValueError:
                raise UnsafeArchiveError(f"archive escapes destination: {member.name}") from None
            if member.issym() or member.islnk():
                raise UnsafeArchiveError(f"archive contains link: {member.name}")
        tar.extractall(destination, filter="data")


def render_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
