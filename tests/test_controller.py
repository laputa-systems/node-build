import io
import sys
import tarfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildsys import bootstrap, inputs, product, recipes, targets


class TargetTest(unittest.TestCase):
    def test_darwin_arm64_supported(self):
        wanted = targets.target_for_triple("aarch64-apple-darwin")
        self.assertEqual(wanted.machine, "arm64")
        self.assertEqual(wanted.family, "macos")
        self.assertEqual(wanted.cpu_baseline_cflag, "-mcpu=apple-m1")

    def test_linux_targets_fail_closed_as_deferred(self):
        for triple in ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"):
            with self.assertRaises(targets.UnsupportedTargetError):
                targets.target_for_triple(triple)

    def test_unknown_triple_rejected(self):
        with self.assertRaises(targets.UnsupportedTargetError):
            targets.target_for_triple("x86_64-apple-darwin")


class ProductTest(unittest.TestCase):
    def test_local_archive_name(self):
        self.assertEqual(
            product.local_archive_name("26.12.1", "aarch64-apple-darwin", 1),
            "node-26.12.1-aarch64-apple-darwin-r1.tar.gz",
        )

    def test_release_title_and_assets(self):
        self.assertEqual(product.release_title("26.12.1", "20261025"), "node-26.12.1+20261025")
        assets = product.expected_release_assets(
            "26.12.1", "20261025", ("aarch64-apple-darwin",)
        )
        self.assertIn(
            "node-26.12.1+20261025-aarch64-apple-darwin-install_only_stripped.tar.gz", assets
        )
        self.assertIn("artifact-aarch64-apple-darwin.json", assets)
        self.assertIn("assembly.json", assets)
        self.assertIn("SHA256SUMS", assets)

    def test_single_naming_source(self):
        first = product.release_archive_name("26.12.1", "20261025", "aarch64-apple-darwin")
        assets = product.expected_release_assets(
            "26.12.1", "20261025", ("aarch64-apple-darwin",)
        )
        self.assertIn(first, assets)


class InputsTest(unittest.TestCase):
    def test_lock_schema_loads(self):
        lock = inputs.load_lock(REPO_ROOT / "sources.lock.json")
        entry = inputs.lock_entry(lock, "node")
        self.assertEqual(entry["version"], "26.12.1")
        self.assertEqual(len(entry["sha256"]), 64)

    def test_lock_entry_missing(self):
        lock = inputs.load_lock(REPO_ROOT / "sources.lock.json")
        with self.assertRaises(inputs.VerificationError):
            inputs.lock_entry(lock, "does-not-exist")

    def test_verify_rejects_wrong_size(self):
        scratch = REPO_ROOT / ".work" / "tmp" / "wrong-size.bin"
        scratch.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_bytes(b"abc")
        try:
            with self.assertRaises(inputs.VerificationError):
                inputs.verify_file(scratch, "00" * 32, 999)
        finally:
            scratch.unlink(missing_ok=True)

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
    def test_patch_applies_once_and_is_idempotent(self):
        from buildsys import node as node_driver

        probe = REPO_ROOT / ".work" / "tmp" / "patch-probe"
        probe.mkdir(parents=True, exist_ok=True)
        gypi = probe / "common.gypi"
        gypi.write_text(
            "x = 1\n'MACOSX_DEPLOYMENT_TARGET': '13.5',       # -mmacosx-version-min=13.5\ny = 2\n",
            encoding="utf-8",
        )
        real = node_driver.PRODUCT_PATCHES
        node_driver.PRODUCT_PATCHES = (
            ("common.gypi", real[0][1], real[0][2]),
        )
        try:
            first = node_driver.apply_product_patches(probe)
            self.assertTrue(any("applied macOS floor" in line for line in first))
            second = node_driver.apply_product_patches(probe)
            self.assertTrue(any("already applied" in line for line in second))
            self.assertIn("'26.0'", gypi.read_text(encoding="utf-8"))
        finally:
            node_driver.PRODUCT_PATCHES = real
            gypi.unlink(missing_ok=True)
            probe.rmdir()

    def test_patch_rejects_unexpected_content(self):
        from buildsys import node as node_driver

        probe = REPO_ROOT / ".work" / "tmp" / "patch-probe-bad"
        probe.mkdir(parents=True, exist_ok=True)
        (probe / "common.gypi").write_text("nothing relevant here\n", encoding="utf-8")
        try:
            with self.assertRaises(Exception):
                node_driver.apply_product_patches(probe)
        finally:
            (probe / "common.gypi").unlink(missing_ok=True)
            probe.rmdir()


class BootstrapTest(unittest.TestCase):
    def test_lock_matches_host(self):
        lock = inputs.load_json(REPO_ROOT / "bootstrap.lock.json")
        bootstrap.validate_bootstrap_lock(lock)
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
