from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buildsys import bootstrap, inputs, node, package, qualify_runner, recipes
from buildsys import published_smoke as published_smoke_runner
from buildsys import release as release_assembler
from buildsys.targets import (
    SUPPORTED_TRIPLES,
    UnsupportedTargetError,
    native_target,
    target_for_triple,
)

REPO_ROOT = Path(__file__).resolve().parent
CACHE_DIR = REPO_ROOT / "build" / "cache"
SOURCES_LOCK = REPO_ROOT / "sources.lock.json"
BOOTSTRAP_LOCK = REPO_ROOT / "bootstrap.lock.json"


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        wanted = target_for_triple(args.target)
    except UnsupportedTargetError as error:
        return _fail(str(error))
    lock = inputs.load_json(BOOTSTRAP_LOCK)
    try:
        bootstrap.validate_bootstrap_lock(lock)
    except ValueError as error:
        return _fail(str(error))
    if wanted.family == "linux":
        from buildsys import recipes as recipe_mod

        try:
            identity = bootstrap.linux_current_identity()
        except (RuntimeError, OSError) as error:
            return _fail(f"toolchain inspection failed: {error}")
        print(f"target: {wanted.triple}")
        print(f"family: {wanted.family}")
        print(f"cpu baseline: {wanted.cpu_baseline_cflag}")
        print(f"deployment target: {wanted.deployment_target}")
        print(f"gcc: {identity.gcc_version}")
        print(f"clang: {identity.clang_version}")
        print(f"musl: {identity.musl_version}")
        print(f"kernel: {identity.kernel_release}")
        print(f"host: {identity.host_machine} {identity.host_system}")
        findings = bootstrap.check_linux_toolchain(lock, identity)
        findings += bootstrap.check_linux_baseline(lock)
        failed = [finding for finding in findings if not finding.ok]
        for finding in findings:
            print(f"[{'ok' if finding.ok else 'MISMATCH'}] {finding.name}: {finding.detail}")
        if failed:
            return _fail("toolchain does not match bootstrap.lock.json")
        recipe_mod.validate_recipe(recipe_mod.linux_recipe())
        print("[ok] recipe: required flags present, no banned flags")
        return 0
    try:
        identity = bootstrap.current_identity()
    except (RuntimeError, OSError) as error:
        return _fail(f"toolchain inspection failed: {error}")
    print(f"target: {wanted.triple}")
    print(f"family: {wanted.family}")
    print(f"cpu baseline: {wanted.cpu_baseline_cflag}")
    print(f"deployment target: {wanted.deployment_target}")
    print(f"xcode: {identity.xcode_version}")
    print(f"sdk: {identity.sdk_version} ({identity.sdk_path})")
    print(f"clang: {identity.clang_version}")
    print(f"host: {identity.host_machine} {identity.host_system}")
    findings = bootstrap.check_locked_toolchain(lock, identity)
    findings += bootstrap.check_locked_baseline(lock)
    failed = [finding for finding in findings if not finding.ok]
    for finding in findings:
        print(f"[{'ok' if finding.ok else 'MISMATCH'}] {finding.name}: {finding.detail}")
    if failed:
        return _fail("toolchain does not match bootstrap.lock.json")
    recipes.validate_recipe(recipes.macos_recipe())
    print("[ok] recipe: required flags present, no banned flags")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    try:
        wanted = target_for_triple(args.target)
    except UnsupportedTargetError as error:
        return _fail(str(error))
    _ = wanted
    try:
        lock = inputs.load_lock(SOURCES_LOCK)
    except (OSError, inputs.VerificationError) as error:
        return _fail(str(error))
    for entry in lock["inputs"]:
        if entry["role"] != "source":
            continue
        destination = CACHE_DIR / f"{entry['name']}-{entry['version']}.tar.gz"
        if destination.exists():
            try:
                inputs.verify_file(destination, entry["sha256"], entry["size"])
                print(f"cached: {destination} (verified)")
                continue
            except inputs.VerificationError as error:
                print(f"stale cache, refetching: {error}")
        print(f"fetching: {entry['url']}")
        try:
            inputs.fetch_url(entry["url"], destination, entry["sha256"], entry["size"])
        except (OSError, inputs.VerificationError) as error:
            return _fail(str(error))
        print(f"cached: {destination} (verified)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build.py")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "fetch", "build", "qualify", "package", "reproduce",
                 "compare-reference", "controller-test", "assemble", "published-smoke",
                 "check-budgets"):
        child = sub.add_parser(name)
        if name not in ("controller-test", "doctor"):
            child.add_argument("--target", default=None)
        if name == "doctor":
            child.add_argument("--target", default=None)
        if name in ("build", "reproduce"):
            child.add_argument("--jobs", type=int, default=10)
        if name in ("assemble", "published-smoke"):
            child.add_argument("--tag", required=True)
        if name == "assemble":
            child.add_argument("--repo", required=True)
        if name == "compare-reference":
            child.add_argument("--reference", default=None)
    return parser


def resolve_target(raw: str | None) -> str:
    if raw is not None:
        return raw
    try:
        return native_target().triple
    except UnsupportedTargetError:
        print(
            f"error: no --target given and this machine has no target description "
            f"(supported: {sorted(SUPPORTED_TRIPLES)})",
            file=sys.stderr,
        )
        raise SystemExit(2) from None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        args.target = resolve_target(args.target)
        return cmd_doctor(args)
    if args.command == "fetch":
        args.target = resolve_target(args.target)
        return cmd_fetch(args)
    if args.command == "controller-test":
        import unittest

        loader = unittest.TestLoader()
        suite = loader.discover("tests", pattern="test_*.py", top_level_dir=str(REPO_ROOT))
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1
    if args.command == "build":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            binary = node.build(REPO_ROOT, args.target, args.jobs)
        except (node.BuildError, Exception) as error:
            return _fail(str(error))
        print(f"built: {binary}")
        return 0
    if args.command == "package":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            from buildsys import node as node_driver

            result = package.package(REPO_ROOT, args.target, node_driver.source_dir(REPO_ROOT))
        except (package.PackageError, Exception) as error:
            return _fail(str(error))
        print(f"archive: {result['archive']}")
        print(f"sha256: {result['sha256']}")
        return 0
    if args.command == "qualify":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            record = qualify_runner.qualify(REPO_ROOT, args.target)
        except (qualify_runner.QualifyError, Exception) as error:
            return _fail(str(error))
        print(f"qualified: {record['archive']}")
        print(f"smoke: {record['smoke_passed']}/{record['smoke_total']} passed")
        return 0
    if args.command == "assemble":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            result = release_assembler.assemble(REPO_ROOT, args.target, args.tag, args.repo)
        except (release_assembler.AssemblyError, Exception) as error:
            return _fail(str(error))
        print(f"release: {result['release_title']} -> {result['release_dir']}")
        print(f"assets: {', '.join(result['assets'])}")
        return 0
    if args.command == "published-smoke":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            record = published_smoke_runner.published_smoke(REPO_ROOT, args.target, args.tag)
        except (published_smoke_runner.PublishedSmokeError, Exception) as error:
            return _fail(str(error))
        print(f"published smoke: {record['passed']}/{record['total']} passed")
        return 0
    if args.command == "compare-reference":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            from buildsys import comparison

            record = comparison.compare(REPO_ROOT, args.target, args.reference)
        except (comparison.CompareError, Exception) as error:
            return _fail(str(error))
        for name, probe in record["probes"].items():
            print(f"{name}: {probe['verdict']}")
        return 0
    if args.command == "check-budgets":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            from buildsys import budgets

            record = budgets.check_budgets(REPO_ROOT, args.target)
        except (budgets.BudgetError, Exception) as error:
            return _fail(str(error))
        print(f"budgets ok: compressed {record['compressed']}, payload {record['payload']}")
        return 0
    if args.command == "reproduce":
        if args.target is None:
            args.target = resolve_target(None)
        try:
            from buildsys import reproduce as reproduce_runner

            record = reproduce_runner.reproduce(REPO_ROOT, args.target, args.jobs)
        except (reproduce_runner.ReproduceError, Exception) as error:
            return _fail(str(error))
        print(f"reproduce verdict: {record['verdict']}")
        return 0
    return _fail(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
