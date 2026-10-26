from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from buildsys import benchmarks


class CompareError(Exception):
    pass


def binary_version(binary: Path, cwd: Path) -> str:
    completed = subprocess.run(
        [str(binary), "--version"], cwd=cwd, capture_output=True, text=True, timeout=60
    )
    if completed.returncode != 0:
        raise CompareError(f"{binary} --version failed")
    return completed.stdout.strip()


def resolve_reference(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_file():
            raise CompareError(f"reference binary not found: {explicit}")
        return candidate
    found = shutil.which("node")
    if not found:
        raise CompareError("no reference node on PATH; pass --reference")
    return Path(found)


def compare(repo_root: Path, triple: str, reference: str | None) -> dict:
    from buildsys import node as node_driver

    candidate = node_driver.built_node(node_driver.source_dir(repo_root))
    reference_binary = resolve_reference(reference)
    work = repo_root / "build" / triple / "compare-work"
    work.mkdir(parents=True, exist_ok=True)
    candidate_version = binary_version(candidate, work)
    reference_version = binary_version(reference_binary, work)
    if candidate_version != reference_version:
        raise CompareError(
            f"version mismatch: candidate {candidate_version} vs reference {reference_version}"
        )
    startup_baseline, startup_candidate = benchmarks.interleave(
        "reference", "candidate", 5,
        lambda side: benchmarks.time_process(
            reference_binary if side == "reference" else candidate, ["-e", benchmarks.STARTUP_PROBE], work
        ),
    )
    json_baseline, json_candidate = benchmarks.interleave(
        "reference", "candidate", 5,
        lambda side: benchmarks.time_probe(
            reference_binary if side == "reference" else candidate, benchmarks.JSON_PROBE, work
        ),
    )
    record = {
        "node_version": candidate_version,
        "machine": platform.machine(),
        "cpu": platform.processor(),
        "toolchain": "as recorded in build-receipt.json",
        "probes": {
            "startup": {
                "reference_ms": list(startup_baseline.values_ms),
                "candidate_ms": list(startup_candidate.values_ms),
                "verdict": benchmarks.verdict(startup_baseline, startup_candidate),
            },
            "json": {
                "reference_ms": list(json_baseline.values_ms),
                "candidate_ms": list(json_candidate.values_ms),
                "verdict": benchmarks.verdict(json_baseline, json_candidate),
            },
        },
        "limiter_note": "host-shared timing; interleave sides and treat gaps inside run-to-run spread as no-measurable-difference",
    }
    benchmarks.record_json(record, work / "compare-record.json")
    return record
