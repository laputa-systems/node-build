from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path, PurePosixPath

CRITICAL = frozenset({
    "buildsys/bootstrap.py",
    "buildsys/budgets.py",
    "buildsys/comparison.py",
    "buildsys/inputs.py",
    "buildsys/package.py",
    "buildsys/product.py",
    "buildsys/qualify_runner.py",
    "buildsys/recipes.py",
    "buildsys/release.py",
    "buildsys/relocate.py",
    "buildsys/reproduce.py",
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
    parser.add_argument("--qualified-modules", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.buildlib_scripts.resolve(strict=True)))
    parse_changes = import_module("mutants_gate").parse_changes

    base = subprocess.check_output([
        "git", "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}",
    ], text=True).strip()
    data = subprocess.check_output(["git", "diff", "--name-status", "-M", "-z", f"{base}...HEAD"])
    sources = select(parse_changes(data))
    if args.qualified_modules is None:
        print(*sources, sep="\n", end="\n" if sources else "")
        return
    with args.qualified_modules.open("rb") as stream:
        dispositions = tomllib.load(stream)
    modules = sorted(PurePosixPath(path).stem for path in sources if path in CRITICAL)
    unknown = set(sources) - CRITICAL
    unqualified = set(modules) - dispositions["qualified"].keys()
    if unknown or unqualified:
        raise ValueError(f"sources still need qualification: {sorted(unknown | unqualified)}")
    print(json.dumps(modules))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
