from __future__ import annotations

import hashlib
import json
import tarfile
import urllib.request
from pathlib import Path


class VerificationError(Exception):
    pass


class UnsafeArchiveError(Exception):
    pass


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, expected_sha256: str, expected_size: int) -> None:
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise VerificationError(
            f"{path}: size {actual_size} != locked {expected_size}"
        )
    actual_sha256 = sha256_of_file(path)
    if actual_sha256 != expected_sha256:
        raise VerificationError(
            f"{path}: sha256 {actual_sha256} != locked {expected_sha256}"
        )


def fetch_url(url: str, destination: Path, expected_sha256: str, expected_size: int) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(url) as response, open(scratch, "wb") as handle:
        for chunk in iter(lambda: response.read(65536), b""):
            handle.write(chunk)
            digest.update(chunk)
            received += len(chunk)
    if received != expected_size:
        scratch.unlink(missing_ok=True)
        raise VerificationError(
            f"{url}: downloaded size {received} != locked {expected_size}"
        )
    if digest.hexdigest() != expected_sha256:
        scratch.unlink(missing_ok=True)
        raise VerificationError(f"{url}: downloaded sha256 does not match lock")
    scratch.replace(destination)
    return destination


def load_lock(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "inputs" not in data:
        raise VerificationError(f"{path}: lock must be an object with an 'inputs' list")
    if not isinstance(data["inputs"], list):
        raise VerificationError(f"{path}: lock 'inputs' must be a list")
    for entry in data["inputs"]:
        for key in ("name", "version", "url", "sha256", "size", "role"):
            if key not in entry:
                raise VerificationError(f"{path}: lock entry missing {key!r}: {entry}")
    return data


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise VerificationError(f"{path}: lock must be a JSON object")
    return data


def lock_entry(lock: dict, name: str) -> dict:
    for entry in lock["inputs"]:
        if entry["name"] == name:
            return entry
    raise VerificationError(f"lock has no entry named {name!r}")


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
