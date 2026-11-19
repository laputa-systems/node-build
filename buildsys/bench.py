from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from buildsys.node import source_dir
from buildsys.product import NODE_VERSION, archive_name

ROOT = Path(__file__).resolve().parents[1]
TIERS = ("edit", "change", "scenario", "full")


@dataclass(frozen=True)
class Workload:
    name: str
    tier: str
    area: str
    purpose: str
    cost: str
    target: str
    command: tuple[str, ...]
    requirement: str


WORKLOADS = (
    Workload("harness-tests", "edit", "harness", "comparison and size gate correctness", "estimated seconds", "any", (sys.executable, "-m", "unittest", "tests.test_compare", "tests.test_controller.ArchiveBudgetTest"), "python"),
    *(Workload(f"size-{short}", "change", "size", "compressed and installed archive size", "estimated seconds", target, (sys.executable, "build.py", "check-budgets", "--target", target), "archive") for short, target in (("darwin", "aarch64-apple-darwin"), ("musl", "x86_64-unknown-linux-musl"))),
    *(Workload(f"compare-{short}", "scenario", "runtime", "startup and JSON against reference", "estimated minutes", target, (sys.executable, "build.py", "compare-reference", "--target", target), "nodes") for short, target in (("darwin", "aarch64-apple-darwin"), ("musl", "x86_64-unknown-linux-musl"))),
    *(Workload(f"build-{short}", "full", "build", "native build and package elapsed time", "estimated 2 hours", target, ("make", "build", f"TARGET={target}"), "toolchain") for short, target in (("darwin", "aarch64-apple-darwin"), ("musl", "x86_64-unknown-linux-musl"))),
)


def supported(target: str) -> bool:
    return target == "any" or (target == "aarch64-apple-darwin" and sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64")) or (target == "x86_64-unknown-linux-musl" and sys.platform.startswith("linux") and platform.machine() == "x86_64")


def select(tier: str, names: list[str], areas: list[str], skips: list[str]) -> tuple[list[Workload], dict[str, str]]:
    known_names = {w.name for w in WORKLOADS}
    known_areas = {w.area for w in WORKLOADS}
    for values, known, label in ((names, known_names, "workload"), (areas, known_areas, "area"), (skips, known_names, "skip")):
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"unknown {label}: {', '.join(sorted(unknown))}")
    selected = []
    excluded = {}
    for workload in WORKLOADS:
        reason = None
        if TIERS.index(workload.tier) > TIERS.index(tier):
            reason = "above tier ceiling"
        elif names and workload.name not in names:
            reason = "workload selector"
        elif areas and workload.area not in areas:
            reason = "area selector"
        elif workload.name in skips:
            reason = "skipped"
        elif not supported(workload.target):
            reason = "unsupported platform"
        if reason:
            excluded[workload.name] = reason
        else:
            selected.append(workload)
    if not selected:
        raise ValueError("selection matches no supported workloads")
    return selected, excluded


def preflight(workloads: list[Workload]) -> list[str]:
    failures = []
    for w in workloads:
        if w.tier in ("scenario", "full"):
            gate = shutil.which("perf-gate-ready")
            if not gate or subprocess.run([gate], cwd=ROOT, check=False).returncode:
                failures.append(f"{w.name}: perf gate deferred: host busy or perf-gate-ready unavailable; establish host readiness")
        if w.requirement == "archive":
            path = ROOT / "dist" / w.target / archive_name(NODE_VERSION, w.target)
            if not path.is_file():
                failures.append(f"{w.name}: missing {path}; build and package the target")
            else:
                print(f"warning: {w.name}: archive freshness is not established; verify its provenance")
        elif w.requirement == "nodes":
            candidate = source_dir(ROOT) / "out" / "Release" / "node"
            reference = shutil.which("node")
            for label, path in (("candidate", str(candidate)), ("reference", reference)):
                if not path or not os.access(path, os.X_OK):
                    failures.append(f"{w.name}: missing executable {label} node; provide a built candidate and reference on PATH")
                else:
                    try:
                        version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
                        if version.returncode or version.stdout.strip() != f"v{NODE_VERSION}":
                            failures.append(f"{w.name}: {label} must be Node v{NODE_VERSION}; install the locked version")
                    except (OSError, subprocess.TimeoutExpired) as error:
                        failures.append(f"{w.name}: cannot run {label}: {error}; repair the executable")
            print(f"warning: {w.name}: candidate freshness is not established; verify its provenance")
        elif w.requirement == "toolchain":
            result = subprocess.run([sys.executable, "build.py", "doctor", "--target", w.target], cwd=ROOT, capture_output=True, text=True, check=False)
            if result.returncode:
                failures.append(f"{w.name}: doctor failed; install the locked toolchain: {result.stderr.strip()} {result.stdout.strip()}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tiered benchmark entrypoint")
    parser.add_argument("mode", choices=("run", "check", "list"))
    parser.add_argument("--tier", choices=TIERS, default=None)
    parser.add_argument("--workload", action="append", default=[])
    parser.add_argument("--area", action="append", default=[])
    parser.add_argument("--skip", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "list":
        for w in WORKLOADS:
            print(f"{w.name}: {w.tier} | {w.area} | {w.purpose} | {w.cost} | {w.target} | {w.requirement} | {shlex.join(w.command)}")
        return 0
    try:
        chosen, excluded = select(args.tier or ("full" if args.mode == "run" else "edit"), args.workload, args.area, args.skip)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    for name, reason in excluded.items():
        print(f"excluded {name}: {reason}")
    for w in chosen:
        print(f"selected {w.name}: {shlex.join(w.command)}")
    if args.dry_run:
        return 0
    print(f"host: {platform.platform()}; timing readiness not established")
    failures = preflight(chosen)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    if args.mode == "check":
        print("preflight passed")
        return 0
    output = ROOT / ".work" / "benchmark" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True)
    summary = {"exclusions": excluded, "workloads": {}}
    for w in chosen:
        start = time.monotonic()
        with (output / f"{w.name}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(w.command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        timing = "not a timing gate"
        if w.tier in ("scenario", "full"):
            gate = shutil.which("perf-gate-ready")
            valid = bool(gate) and subprocess.run([gate, "-1"], cwd=ROOT, check=False).returncode == 0
            timing = "host gate passed; inspect harness for discarded samples" if valid else "inconclusive: perf gate deferred: host busy"
        summary["workloads"][w.name] = {"exit_status": result.returncode, "duration_seconds": time.monotonic() - start, "timing_validity": timing, "verdict": ("within budget" if result.returncode == 0 else "regression or error; inspect log") if w.area == "size" else "completion is not a performance verdict"}
        if w.requirement == "nodes":
            record = ROOT / "build" / w.target / "compare-work" / "compare-record.json"
            if result.returncode == 0 and record.is_file():
                shutil.copy2(record, output / f"{w.name}-record.json")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"summary: {output / 'summary.json'}")
    return int(any(item["exit_status"] != 0 or item["timing_validity"].startswith("inconclusive") for item in summary["workloads"].values()))


if __name__ == "__main__":
    sys.exit(main())
