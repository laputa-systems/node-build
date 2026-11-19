from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path, PurePosixPath

CRITICAL = frozenset({
    "buildsys/budgets.py",
    "buildsys/comparison.py",
    "buildsys/inputs.py",
    "buildsys/package.py",
    "buildsys/release.py",
    "buildsys/targets.py",
})

CONFIGURATION = frozenset({
    ".gitignore",
    "Makefile",
    "bootstrap.lock.json",
    "buildsys/__init__.py",
    "pyproject.toml",
    "release-budgets.json",
    "sources.lock.json",
    "uv.lock",
})


def production_source(path: str) -> bool:
    file = PurePosixPath(path)
    return path == "build.py" or (
        file.parent == PurePosixPath("buildsys")
        and file.suffix == ".py"
        and file.stem.isidentifier()
    )


def select(changes: Mapping[str, str]) -> tuple[str, ...]:
    selected: set[str] = set()
    broad_change = False
    for path, status in sorted(changes.items()):
        if status not in {"A", "D", "M"}:
            raise ValueError(f"unsupported change status {status}: {path}")
        if path in CONFIGURATION or path.startswith((".github/", "tests/")):
            broad_change = True
        elif production_source(path):
            if status == "D":
                broad_change = True
            else:
                selected.add(path)
        elif not path.endswith(".md"):
            raise ValueError(f"unclassified mutation input: {path}")
    if broad_change:
        selected.update(CRITICAL)
    return tuple(sorted(selected))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("buildlib_scripts", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.buildlib_scripts.resolve(strict=True)))
    parse_changes = import_module("mutants_gate").parse_changes

    base = subprocess.check_output([
        "git", "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}",
    ], text=True).strip()
    data = subprocess.check_output(["git", "diff", "--name-status", "-M", "-z", f"{base}...HEAD"])
    for path in select(parse_changes(data)):
        print(path)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
