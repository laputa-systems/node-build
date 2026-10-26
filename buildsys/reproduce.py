from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from buildsys import inputs, macho


def normalize_for_triple(binary: Path, triple: str) -> bytes:
    if triple == "x86_64-unknown-linux-musl":
        from buildsys import elf

        return elf.normalized_bytes(binary)
    return macho.normalized_bytes(binary)


class ReproduceError(Exception):
    pass


def wipe_tree(repo_root: Path, triple: str) -> None:
    source_root = repo_root / "build" / "src"
    work = repo_root / "build" / triple
    for victim in (source_root, work):
        if victim.exists():
            shutil.rmtree(victim)


def differing_chunks(first: bytes, second: bytes, size: int = 1 << 20) -> list[int]:
    offsets: list[int] = []
    for offset in range(0, min(len(first), len(second)), size):
        if first[offset:offset + size] != second[offset:offset + size]:
            offsets.append(offset)
    if len(first) != len(second):
        offsets.append(min(len(first), len(second)))
    return offsets


def reproduce(repo_root: Path, triple: str, jobs: int) -> dict:
    from buildsys import node as node_driver

    keep = repo_root / "build" / "reproduce-keep"
    if keep.exists():
        shutil.rmtree(keep)
    keep.mkdir(parents=True)
    attempts: list[dict] = []
    retained: list[Path] = []
    for attempt in (1, 2):
        wipe_tree(repo_root, triple)
        binary = node_driver.build(repo_root, triple, jobs)
        raw = binary.read_bytes()
        normalized = normalize_for_triple(binary, triple)
        kept = keep / f"attempt-{attempt}-node"
        kept.write_bytes(raw)
        retained.append(kept)
        attempts.append(
            {
                "attempt": attempt,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
                "size": len(raw),
            }
        )
    first_normalized = normalize_for_triple(retained[0], triple)
    second_normalized = normalize_for_triple(retained[1], triple)
    chunks = differing_chunks(first_normalized, second_normalized)
    record = {
        "triple": triple,
        "attempts": attempts,
        "raw_match": attempts[0]["raw_sha256"] == attempts[1]["raw_sha256"],
        "normalized_match": (
            attempts[0]["normalized_sha256"] == attempts[1]["normalized_sha256"]
        ),
        "differing_chunk_offsets": chunks,
        "verdict": "",
    }
    if record["raw_match"]:
        record["verdict"] = "bit-for-bit reproducible"
    elif record["normalized_match"]:
        if triple == "x86_64-unknown-linux-musl":
            record["verdict"] = (
                "content identical outside ELF build-ID "
                "(NT_GNU_BUILD_ID regenerates per link)"
            )
        else:
            record["verdict"] = (
                "content identical outside Mach-O signing metadata "
                "(UUID and ad-hoc signature regenerate per link)"
            )
    else:
        record["verdict"] = "content differs beyond signing metadata; not reproducible"
    inputs.render_json(record, repo_root / "build" / triple / "reproduce-record.json")
    return record
