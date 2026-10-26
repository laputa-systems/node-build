from __future__ import annotations

import json
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Samples:
    label: str
    values_ms: tuple[float, ...]

    def median(self) -> float:
        return statistics.median(self.values_ms)

    def spread(self) -> float:
        return max(self.values_ms) - min(self.values_ms)


JSON_PROBE = (
    "const input = JSON.stringify({a: Array.from({length: 500}, (_, i) => ({i, s: 'x'.repeat(40)}))});"
    "let n = 0;"
    "const start = Date.now();"
    "for (let i = 0; i < 60; i++) { n += JSON.parse(input).a.length; }"
    "if (n !== 30000) { process.exit(1); }"
    "console.log(Date.now() - start);"
)

STARTUP_PROBE = "1"


def time_process(binary: Path, args: list[str], cwd: Path, timeout: int = 120) -> float:
    start = time.monotonic()
    completed = subprocess.run(
        [str(binary), *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    elapsed_ms = (time.monotonic() - start) * 1000
    if completed.returncode != 0:
        raise RuntimeError(f"{binary} {' '.join(args)} failed: {completed.stderr[:200]}")
    return elapsed_ms


def time_probe(binary: Path, probe: str, cwd: Path) -> float:
    completed = subprocess.run(
        [str(binary), "-e", probe], cwd=cwd, capture_output=True, text=True, timeout=120
    )
    if completed.returncode != 0:
        raise RuntimeError(f"probe failed on {binary}: {completed.stderr[:200]}")
    return float(completed.stdout.strip().split()[-1])


def collect(label: str, repeats: int, worker) -> Samples:
    return Samples(label, tuple(worker() for _ in range(repeats)))


def verdict(baseline: Samples, candidate: Samples) -> str:
    if not baseline.values_ms or not candidate.values_ms:
        return "inconclusive"
    gap = abs(candidate.median() - baseline.median())
    noise = (baseline.spread() + candidate.spread()) / 2
    if gap <= noise:
        return "no-measurable-difference"
    return "faster" if candidate.median() < baseline.median() else "slower"


def interleave(
    baseline_label: str, candidate_label: str, repeats: int, worker
) -> tuple[Samples, Samples]:
    baseline_values: list[float] = []
    candidate_values: list[float] = []
    for _ in range(repeats):
        baseline_values.append(worker(baseline_label))
        candidate_values.append(worker(candidate_label))
    return Samples(baseline_label, tuple(baseline_values)), Samples(candidate_label, tuple(candidate_values))


def record_json(record: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
