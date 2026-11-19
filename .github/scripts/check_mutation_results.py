from __future__ import annotations

import argparse
import platform
import sys
import tomllib
from collections import Counter
from importlib import import_module
from pathlib import Path

from select_mutation_sources import CRITICAL


def regular_file(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or not path.is_file() or path.resolve() != path:
        raise ValueError(f"expected a regular file in the checkout: {relative}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=sorted(CRITICAL))
    parser.add_argument("checkout", type=Path)
    parser.add_argument("dispositions", type=Path)
    parser.add_argument("buildlib_scripts", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.buildlib_scripts.resolve(strict=True)))
    gate = import_module("mutants_gate")
    root = args.checkout.resolve(strict=True)
    source = regular_file(root, args.source)
    generated = regular_file(root, f"mutants/{args.source}")
    meta = regular_file(root, f"mutants/{args.source}.meta")
    spans = regular_file(root, f"mutants/{args.source}.spans")
    module = source.stem
    prefix = f"buildsys.{module}."

    with args.dispositions.open("rb") as stream:
        dispositions = tomllib.load(stream)
    host = platform.system()
    try:
        module_record = dispositions["qualified"][module]
        record = {"source_sha256": module_record["source_sha256"], "survivors": module_record[host]}
    except KeyError as error:
        raise ValueError(f"missing dispositions for {module} on {host}") from error

    try:
        outcomes = gate.read_results(meta, spans, prefix)
        allowed = gate.qualified_survivors(source, generated, spans, prefix, record)
    except gate.GateError as error:
        raise ValueError(str(error)) from error
    print(f"{module} on {host}: {dict(sorted(Counter(outcomes.values()).items()))}")
    unqualified = [
        f"{outcome}: {name}"
        for name, outcome in sorted(outcomes.items())
        if outcome != "killed" and not (outcome == "survived" and name in allowed)
    ]
    if unqualified:
        raise ValueError("unqualified mutation outcomes:\n" + "\n".join(unqualified))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
