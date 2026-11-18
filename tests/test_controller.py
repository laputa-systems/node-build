import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildlib import locks

import build
import buildsys
from buildsys import bootstrap, budgets, inputs, node, product, recipes, targets


class TargetTest(unittest.TestCase):
    def test_darwin_arm64_supported(self):
        wanted = targets.target_for_triple("aarch64-apple-darwin")
        self.assertEqual(wanted.machine, "arm64")
        self.assertEqual(wanted.family, "macos")
        self.assertEqual(wanted.cpu_baseline_cflag, "-mcpu=apple-m1")

    def test_linux_x64_musl_supported(self):
        wanted = targets.target_for_triple("x86_64-unknown-linux-musl")
        self.assertEqual(wanted.machine, "x86_64")
        self.assertEqual(wanted.family, "linux-musl")
        self.assertEqual(wanted.cpu_baseline_cflag, "-march=x86-64-v2")

    def test_linux_arm64_still_deferred(self):
        with self.assertRaises(targets.UnsupportedTargetError):
            targets.target_for_triple("aarch64-unknown-linux-musl")

    def test_unknown_triple_rejected(self):
        with self.assertRaises(targets.UnsupportedTargetError):
            targets.target_for_triple("x86_64-apple-darwin")


class ArchiveBudgetTest(unittest.TestCase):
    triple = "aarch64-apple-darwin"

    def setUp(self):
        scratch = REPO_ROOT / ".work" / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.archive = self.root / "dist" / self.triple / product.archive_name(product.NODE_VERSION, self.triple)
        self.archive.parent.mkdir(parents=True)
        payloads = {"bin/node": b"node" * 4, "LICENSE": b"license\n"}
        with tarfile.open(self.archive, "w:xz") as tar:
            for name, data in payloads.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
            link = tarfile.TarInfo("bin/node-tool")
            link.type = tarfile.SYMTYPE
            link.linkname = "node"
            tar.addfile(link)
        self.compressed = self.archive.stat().st_size
        self.payload = sum(map(len, payloads.values()))

    def write_budget(self, compressed: int, payload: int) -> None:
        limits = {"compressed_max_bytes": compressed, "installed_payload_max_bytes": payload}
        record = {"schema_version": 1, "targets": {self.triple: limits}}
        (self.root / "release-budgets.json").write_text(json.dumps(record))

    def test_archive_budget_accepts_exact_ceilings(self):
        self.write_budget(self.compressed, self.payload)
        record = budgets.check_budgets(self.root, self.triple)
        self.assertEqual(record, {
            "triple": self.triple, "compressed": self.compressed, "payload": self.payload,
            "ceilings": {"compressed_max_bytes": self.compressed, "installed_payload_max_bytes": self.payload},
            "ok": True,
        })

    def test_archive_budget_reports_every_exceeded_ceiling(self):
        for compressed, payload, expected in (
            (0, self.payload, ["compressed"]),
            (self.compressed - 1, self.payload, ["compressed"]),
            (self.compressed, self.payload - 1, ["payload"]),
            (self.compressed - 1, self.payload - 1, ["compressed", "payload"]),
        ):
            with self.subTest(compressed=compressed, payload=payload):
                self.write_budget(compressed, payload)
                with self.assertRaises(budgets.BudgetError) as error:
                    budgets.check_budgets(self.root, self.triple)
                self.assertEqual([failure.split()[0] for failure in str(error.exception).split("; ")], expected)

    def test_archive_budget_requires_the_target_and_archive(self):
        self.write_budget(self.compressed, self.payload)
        with self.assertRaisesRegex(budgets.BudgetError, "x86_64-unknown-linux-musl"):
            budgets.check_budgets(self.root, "x86_64-unknown-linux-musl")
        self.archive.unlink()
        with self.assertRaisesRegex(budgets.BudgetError, "missing archive"):
            budgets.check_budgets(self.root, self.triple)

    def test_archive_budget_rejects_invalid_byte_ceilings_at_the_cli(self):
        for field, value in (
            ("compressed_max_bytes", "invalid"),
            ("installed_payload_max_bytes", True),
            ("compressed_max_bytes", -1),
            ("installed_payload_max_bytes", None),
        ):
            with self.subTest(field=field, value=value):
                limits: dict[str, object] = {
                    "compressed_max_bytes": self.compressed, "installed_payload_max_bytes": self.payload,
                }
                limits[field] = value
                document = {"schema_version": 1, "targets": {self.triple: limits}}
                (self.root / "release-budgets.json").write_text(json.dumps(document))
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(build, "REPO_ROOT", self.root), redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(build.main(["check-budgets", "--target", self.triple]), 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(f"{self.triple}.{field}", stderr.getvalue())


class ProductTest(unittest.TestCase):
    def test_archive_and_manifest_names(self):
        self.assertEqual(
            product.archive_name("26.12.1", "aarch64-apple-darwin"),
            "node-26.12.1-aarch64-apple-darwin.tar.xz",
        )
        self.assertEqual(
            product.manifest_name("26.12.1", "x86_64-unknown-linux-musl"),
            "node-26.12.1-x86_64-unknown-linux-musl.manifest.json",
        )

    def test_release_assets_are_sorted_and_checksummed(self):
        assets = product.expected_release_assets(
            "26.12.1", ("x86_64-unknown-linux-musl", "aarch64-apple-darwin")
        )
        self.assertEqual(
            assets,
            (
                "SHA256SUMS",
                "node-26.12.1-aarch64-apple-darwin.manifest.json",
                "node-26.12.1-aarch64-apple-darwin.tar.xz",
                "node-26.12.1-x86_64-unknown-linux-musl.manifest.json",
                "node-26.12.1-x86_64-unknown-linux-musl.tar.xz",
            ),
        )


class InputsTest(unittest.TestCase):
    def test_lock_schema_loads(self):
        entry = locks.load_sources(REPO_ROOT / "sources.lock.json").get("node")
        self.assertEqual(entry.version, "26.12.1")
        self.assertEqual(len(entry.sha256), 64)

    def test_lock_files_use_schema_version_one(self):
        for name in ("sources.lock.json", "bootstrap.lock.json", "release-budgets.json"):
            data = json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 1, name)
            self.assertNotIn("comment", data, name)
        budgets = locks.load_budgets(REPO_ROOT / "release-budgets.json").targets
        self.assertEqual(sorted(budgets), list(targets.SUPPORTED_TRIPLES))
        locks.load_bootstrap(REPO_ROOT / "bootstrap.lock.json")

    def test_buildlib_pin_is_one_version_everywhere(self):
        pinned = locks.load_sources(REPO_ROOT / "sources.lock.json").get("laputa-buildlib")
        wheel = pinned.url.rsplit("/", 1)[1]
        self.assertEqual(wheel, f"laputa_buildlib-{pinned.version}-py3-none-any.whl")
        self.assertIn(
            f'"laputa-buildlib=={pinned.version}"',
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )
        uv_lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
        self.assertIn(f'{{ url = "{pinned.url}", hash = "sha256:{pinned.sha256}" }}', uv_lock)

    def test_cached_wheel_is_used_without_network(self):
        data = b"wheel bytes"
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            entry = {
                "name": "laputa-buildlib",
                "url": "https://invalid.example/laputa_buildlib-0-py3-none-any.whl",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
            (root / "sources.lock.json").write_text(
                json.dumps({"schema_version": 1, "inputs": [entry]}), encoding="utf-8"
            )
            wheel = root / "build" / "cache" / "laputa_buildlib-0-py3-none-any.whl"
            wheel.parent.mkdir(parents=True)
            wheel.write_bytes(data)
            self.assertEqual(buildsys._pinned_wheel(root), wheel)

    def test_malformed_wheel_pin_is_rejected_before_cache_or_network(self):
        data = b"x"
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            entry = {
                "name": "laputa-buildlib",
                "url": "https://invalid.example/wheel.whl",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": True,
            }
            (root / "sources.lock.json").write_text(
                json.dumps({"schema_version": 1, "inputs": [entry]}), encoding="utf-8"
            )
            wheel = root / "build" / "cache" / "wheel.whl"
            wheel.parent.mkdir(parents=True)
            wheel.write_bytes(data)
            with (
                patch("urllib.request.urlopen", side_effect=AssertionError("network used")),
                self.assertRaisesRegex(ValueError, "invalid laputa-buildlib pin"),
            ):
                buildsys._pinned_wheel(root)

    def test_wheel_fallback_verifies_download_before_replacing_cache(self):
        data = b"verified wheel"
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            entry = {
                "name": "laputa-buildlib",
                "url": "https://invalid.example/wheel.whl",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
            (root / "sources.lock.json").write_text(
                json.dumps({"schema_version": 1, "inputs": [entry]}), encoding="utf-8"
            )
            wheel = root / "build" / "cache" / "wheel.whl"
            wheel.parent.mkdir(parents=True)
            wheel.write_bytes(b"bad cache")
            with (
                patch("urllib.request.urlopen", return_value=io.BytesIO(b"bad download")),
                self.assertRaisesRegex(RuntimeError, "bytes do not match"),
            ):
                buildsys._pinned_wheel(root)
            self.assertEqual(wheel.read_bytes(), b"bad cache")
            with patch("urllib.request.urlopen", return_value=io.BytesIO(data)):
                self.assertEqual(buildsys._pinned_wheel(root), wheel)
            self.assertEqual(wheel.read_bytes(), data)

    def test_safe_extract_rejects_escape(self):
        archive = REPO_ROOT / ".work" / "tmp" / "evil.tar"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo(name="../../evil.txt")
            payload = b"evil"
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        archive.write_bytes(buffer.getvalue())
        try:
            with self.assertRaises(inputs.UnsafeArchiveError):
                inputs.safe_extract(archive, REPO_ROOT / ".work" / "tmp" / "evil-out")
        finally:
            archive.unlink(missing_ok=True)

    def test_safe_extract_rejects_symlink(self):
        archive = REPO_ROOT / ".work" / "tmp" / "link.tar"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo(name="link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        archive.write_bytes(buffer.getvalue())
        try:
            with self.assertRaises(inputs.UnsafeArchiveError):
                inputs.safe_extract(archive, REPO_ROOT / ".work" / "tmp" / "link-out")
        finally:
            archive.unlink(missing_ok=True)


class RecipesTest(unittest.TestCase):
    def test_macos_recipe_valid(self):
        recipes.validate_recipe(recipes.macos_recipe())

    def test_linux_recipe_valid(self):
        recipe = recipes.linux_recipe()
        recipes.validate_recipe(recipe)
        self.assertIn("--dest-os=linux", recipe["configure"])
        self.assertIn("--dest-cpu=x64", recipe["configure"])

    def test_recipe_for_triple_dispatch(self):
        self.assertEqual(
            recipes.recipe_for_triple("aarch64-apple-darwin")["deployment_target"], "26.0"
        )
        self.assertEqual(
            recipes.recipe_for_triple("x86_64-unknown-linux-musl")["deployment_target"], "1.2.6"
        )

    def test_banned_flags_rejected(self):
        for banned in ("-march=native", "-ffast-math", "--fully-static", "--enable-thin-lto"):
            bad = recipes.macos_recipe()
            bad["cflags"] = [banned]
            with self.assertRaises(recipes.BannedFlagError):
                recipes.validate_recipe(bad)

    def test_missing_required_arg_rejected(self):
        bad = recipes.macos_recipe()
        bad["configure"] = ["--dest-os=mac"]
        with self.assertRaises(recipes.BannedFlagError):
            recipes.validate_recipe(bad)

    def test_configure_command_shape(self):
        command = recipes.configure_command("/tmp/nowhere", recipes.macos_recipe())
        self.assertEqual(command[0], "./configure")
        self.assertIn("--without-npm", command)
        self.assertIn("--with-intl=small-icu", command)


class PatchTest(unittest.TestCase):
    def test_patches_apply_once_and_reject_duplicates(self):
        from buildsys import node as node_driver

        for triple in ("aarch64-apple-darwin", "x86_64-unknown-linux-musl"):
            with self.subTest(triple=triple):
                probe = REPO_ROOT / ".work" / "tmp" / "patch-probe"
                patches = node_driver.HELP_PATCHES + (
                    node_driver.PRODUCT_PATCHES if triple == "aarch64-apple-darwin" else ()
                )
                for relative, old, _ in patches:
                    target = probe / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(old, encoding="utf-8")
                first = node_driver.apply_product_patches(probe, triple)
                self.assertEqual(len(first), len(patches))
                self.assertTrue(all("applied patch" in item for item in first))
                self.assertTrue(all("already applied" in item for item in node_driver.apply_product_patches(probe, triple)))
                help_text = (probe / "lib/internal/main/print_help.js").read_text(encoding="utf-8")
                self.assertEqual(help_text.count("Maintained by Joshua Li: https://github.com/laputa-systems/node-build"), 1)
                if triple == "aarch64-apple-darwin":
                    self.assertIn("'26.0'", (probe / "common.gypi").read_text(encoding="utf-8"))
                target = probe / patches[0][0]
                target.write_text("nothing relevant here\n", encoding="utf-8")
                with self.assertRaises(node_driver.BuildError):
                    node_driver.apply_product_patches(probe, triple)
                target.write_text(patches[0][1] * 2, encoding="utf-8")
                with self.assertRaises(node_driver.BuildError):
                    node_driver.apply_product_patches(probe, triple)
                import shutil
                shutil.rmtree(probe)


class ExtractedSourceTest(unittest.TestCase):
    def test_same_version_archive_change_rejects_the_existing_tree(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            triple = "aarch64-apple-darwin"
            lock_path = root / "sources.lock.json"
            lock = json.loads((REPO_ROOT / lock_path.name).read_text())
            entry = lock["inputs"][0]
            archive = root / "build" / "cache" / f"node-{entry['version']}.tar.gz"
            archive.parent.mkdir(parents=True)
            source = node.source_dir(root)

            def pin_archive(payload: bytes) -> None:
                with tarfile.open(archive, "w:gz") as tar:
                    for relative, data in (
                        ("configure", payload),
                        *((name, old.encode()) for name, old, _ in node.HELP_PATCHES + node.PRODUCT_PATCHES),
                    ):
                        info = tarfile.TarInfo(f"{source.name}/{relative}")
                        info.size = len(data)
                        tar.addfile(info, io.BytesIO(data))
                entry.update(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), size=archive.stat().st_size)
                lock_path.write_text(json.dumps(lock))

            pin_archive(b"old configure")
            self.assertEqual(node.ensure_extracted(root, triple), source)
            self.assertEqual(node.ensure_extracted(root, triple), source)
            pin_archive(b"new configure")
            with self.assertRaisesRegex(node.BuildError, "source archive.*clean build"):
                node.ensure_extracted(root, triple)
            self.assertEqual((source / "configure").read_bytes(), b"old configure")


class BuildReceiptTest(unittest.TestCase):
    def test_build_receipt_records_only_an_unchanged_clean_checkout(self):
        import shutil

        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            for name in ("sources.lock.json", "bootstrap.lock.json"):
                shutil.copyfile(REPO_ROOT / name, root / name)
            (root / ".gitignore").write_text("build/\n")
            for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "fixture"]):
                subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True)
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            nested_archive = root / "build" / "source-archive"
            nested_archive.mkdir(parents=True)
            self.assertIsNone(node.clean_build_revision(nested_archive))
            triple = "aarch64-apple-darwin"
            receipt = root / "build" / triple / "build-receipt.json"
            source = root / "build" / "source"
            source.mkdir(parents=True)
            (source / "node").write_bytes(b"node binary")
            stray = root / "stray.txt"
            with (
                patch.object(node, "ensure_extracted", return_value=source),
                patch.object(node, "needs_configure", return_value=False),
                patch.object(node, "run_make") as make,
                patch.object(node, "built_node", return_value=source / "node"),
                patch.object(node, "apply_product_patches", return_value=[]),
            ):
                node.build(root, triple, 1)
                original = receipt.read_text()
                self.assertEqual(json.loads(original)["source_revision"], revision)
                make.side_effect = lambda *args: stray.write_text("edited during build")
                with self.assertRaisesRegex(node.BuildError, "checkout changed during build"):
                    node.build(root, triple, 1)
                self.assertEqual(receipt.read_text(), original)
                make.side_effect = None
                node.build(root, triple, 1)
                self.assertNotIn("source_revision", json.loads(receipt.read_text()))

    def test_build_binds_lock_and_rejects_changes_before_writing_receipt(self):
        import shutil

        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            for name in ("sources.lock.json", "bootstrap.lock.json"):
                shutil.copyfile(REPO_ROOT / name, root / name)
            triple = "aarch64-apple-darwin"
            lock = root / "sources.lock.json"
            receipt = root / "build" / triple / "build-receipt.json"
            source = root / "source"
            binary = source / "node"
            source.mkdir()
            binary.write_bytes(b"node binary")
            with (
                patch.object(node, "ensure_extracted", return_value=source),
                patch.object(node, "needs_configure", return_value=False),
                patch.object(node, "run_make") as make,
                patch.object(node, "built_node", return_value=binary),
                patch.object(node, "apply_product_patches", return_value=[]),
            ):
                node.build(root, triple, 1)
                original = receipt.read_text(encoding="utf-8")
                self.assertNotIn("source_revision", json.loads(original))
                self.assertEqual(json.loads(original)["built_node_sha256"], hashlib.sha256(b"node binary").hexdigest())
                self.assertEqual(
                    json.loads(original)["sources_lock_sha256"], hashlib.sha256(lock.read_bytes()).hexdigest()
                )
                make.side_effect = lambda *args: lock.write_text(lock.read_text() + "\n")
                with self.assertRaisesRegex(node.BuildError, "source lock changed during build"):
                    node.build(root, triple, 1)
                self.assertEqual(receipt.read_text(encoding="utf-8"), original)


class ConfigureMarkerTest(unittest.TestCase):
    def test_reconfigures_when_marker_is_not_an_object(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            root = Path(scratch)
            triple = "aarch64-apple-darwin"
            recipe = {"configure": ["--prefix=/usr"]}
            source = root / "source"
            source.mkdir()
            (source / "config.mk").touch()
            marker = node.configured_marker(root, triple)
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps({"recipe_sha256": node.recipe_fingerprint(recipe)}))
            self.assertFalse(node.needs_configure(source, root, triple, recipe))

            marker.write_text("[]")
            self.assertTrue(node.needs_configure(source, root, triple, recipe))


class BootstrapTest(unittest.TestCase):
    def test_doctor_rejects_malformed_lock_sections_before_inspecting_host(self):
        base = json.loads((REPO_ROOT / "bootstrap.lock.json").read_text())
        cases = (
            ("toolchain", None, "bootstrap lock section must be an object: toolchain"),
            ("cpu_baseline", ["cflag", "deployment_target"], "bootstrap lock section must be an object: cpu_baseline"),
            ("linux_toolchain", "gcc clang musl host_machine", "bootstrap lock section must be an object: linux_toolchain"),
            ("linux_baseline", {**base["linux_baseline"], "cflag": 7}, "bootstrap lock linux_baseline cflag must be a nonempty string"),
        )
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as scratch:
            lock = Path(scratch) / "bootstrap.lock.json"
            with (
                patch.object(build, "BOOTSTRAP_LOCK", lock),
                patch.object(bootstrap, "current_identity", side_effect=AssertionError("inspected macOS")),
                patch.object(bootstrap, "linux_current_identity", side_effect=AssertionError("inspected Linux")),
            ):
                documents = [
                    (section, {**base, section: replacement}, message)
                    for section, replacement, message in cases
                ]
                documents.extend((
                    ("missing section", {name: value for name, value in base.items() if name != "linux_baseline"},
                     "bootstrap lock missing section: linux_baseline"),
                    ("missing field", {**base, "linux_baseline": {"cflag": "-march=x86-64-v2"}},
                     "bootstrap lock linux_baseline missing: deployment_target"),
                    ("unsupported schema", {**base, "schema_version": 9}, f"{lock}: schema_version must be 1, found 9"),
                ))
                for name, document, message in documents:
                    with self.subTest(case=name):
                        lock.write_text(json.dumps(document))
                        with redirect_stderr(io.StringIO()) as stderr, redirect_stdout(io.StringIO()) as stdout:
                            status = build.main(["doctor", "--target", "x86_64-unknown-linux-musl"])
                        self.assertEqual(status, 2)
                        self.assertEqual(stdout.getvalue(), "")
                        self.assertEqual(stderr.getvalue(), f"error: {message}\n")

    def test_lock_matches_host(self):
        import platform
        import subprocess

        lock = bootstrap.load_bootstrap_lock(REPO_ROOT / "bootstrap.lock.json")
        if platform.system() == "Linux":
            completed = subprocess.run(
                ["ldd", "--version"], capture_output=True, text=True, timeout=60, check=False
            )
            probe = (completed.stdout or "") + (completed.stderr or "")
            if "musl" not in probe:
                self.skipTest("linux lock check needs a musl host")
            identity = bootstrap.linux_current_identity()
            mismatches = [
                finding for finding in bootstrap.check_linux_toolchain(lock, identity)
                if not finding.ok
            ]
            self.assertEqual(mismatches, [])
            baseline_bad = [
                finding for finding in bootstrap.check_linux_baseline(lock) if not finding.ok
            ]
            self.assertEqual(baseline_bad, [])
            return
        identity = bootstrap.current_identity()
        mismatches = [
            finding for finding in bootstrap.check_locked_toolchain(lock, identity)
            if not finding.ok
        ]
        self.assertEqual(mismatches, [])
        baseline_bad = [
            finding for finding in bootstrap.check_locked_baseline(lock) if not finding.ok
        ]
        self.assertEqual(baseline_bad, [])


if __name__ == "__main__":
    unittest.main()


class RunMakeTest(unittest.TestCase):
    def test_inherited_make_variables_do_not_reach_node_make(self):
        from buildsys import node

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            seen = root / "seen"
            make = bin_dir / "make"
            make.write_text(
                f'#!/bin/sh\necho "$* TARGET=${{TARGET-unset}} MAKEFLAGS=${{MAKEFLAGS-unset}}" > "{seen}"\n',
                encoding="utf-8",
            )
            make.chmod(0o755)
            recipe = {"configure": [], "cflags": []}
            saved = {name: os.environ.get(name) for name in ("PATH", "TARGET", "MAKEFLAGS")}
            os.environ["PATH"] = f"{bin_dir}:{saved['PATH']}"
            os.environ["TARGET"] = "x86_64-unknown-linux-musl"
            os.environ["MAKEFLAGS"] = " -- TARGET=x86_64-unknown-linux-musl"
            try:
                node.run_make(root, recipe, 4, root / "make.log")
            finally:
                for name, value in saved.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

            self.assertEqual(seen.read_text(encoding="utf-8").strip(), "-j4 TARGET=unset MAKEFLAGS=unset")
