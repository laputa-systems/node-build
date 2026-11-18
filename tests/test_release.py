import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildlib import hashing, release

from buildsys import package, product, validate_product
from buildsys import release as release_assembler
from buildsys import reproduce as reproduce_runner

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
TRIPLE = "aarch64-apple-darwin"


class PackageRecordTest(unittest.TestCase):
    def test_packaging_links_receipt_and_archive(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp_root) as scratch:
            root = Path(scratch)
            source = root / "source"
            source.mkdir()
            (source / "LICENSE").write_text("fixture license")
            receipt = root / "build" / TRIPLE / "build-receipt.json"
            stage = root / "fixture-install"
            (stage / "bin").mkdir(parents=True)
            (stage / "bin" / "node").write_bytes(b"fixture binary")
            with (
                patch.object(package, "install_to_stage", return_value=stage) as install,
                patch.object(package, "write_hardening_report", return_value={}),
                patch.object(validate_product, "validate_install_tree", return_value=[
                    validate_product.ProductFinding("fixture", True, ""),
                ]),
            ):
                with self.assertRaisesRegex(package.PackageError, "missing build receipt"):
                    package.package(root, TRIPLE, source)
                install.assert_not_called()
                receipt.parent.mkdir(parents=True)
                receipt.write_text('{"fixture": true}\n')
                with self.assertRaisesRegex(package.PackageError, "build receipt has no node binary digest"):
                    package.package(root, TRIPLE, source)
                install.assert_not_called()
                receipt.write_text(json.dumps({"built_node_sha256": "0" * 64}))
                with self.assertRaisesRegex(package.PackageError, "installed node does not match build receipt"):
                    package.package(root, TRIPLE, source)
                self.assertFalse((root / "dist").exists())
                self.assertFalse((receipt.parent / "package-record.json").exists())
                receipt.write_text(json.dumps({"built_node_sha256": hashing.sha256_file(stage / "bin" / "node")}))
                result = package.package(root, TRIPLE, source)
            archive = Path(result["archive"])
            record = json.loads((receipt.parent / "package-record.json").read_text())
            self.assertEqual(record["build_receipt_sha256"], hashing.sha256_file(receipt))
            self.assertEqual(record["sha256"], hashing.sha256_file(archive))


class AssembleTest(unittest.TestCase):
    def setUp(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix="assemble-", dir=tmp_root))
        self.addCleanup(self.cleanup)
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        (self.work / "sources.lock.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
        (self.work / ".gitignore").write_text("build/\ndist/\n", encoding="utf-8")
        for command in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
            subprocess.run(["git", *command], cwd=self.work, env=env, check=True)
        self.revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.work, env=env,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        archive = self.work / "dist" / TRIPLE / product.archive_name(product.NODE_VERSION, TRIPLE)
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"archive bytes")
        checks = [{"name": "c", "ok": True, "detail": ""}]
        build = self.work / "build" / TRIPLE
        (build / "qualify").mkdir(parents=True)
        receipt = build / "build-receipt.json"
        receipt.write_text(
            json.dumps({
                "sources_lock_sha256": hashing.sha256_file(self.work / "sources.lock.json"),
                "source_revision": self.revision,
            }),
            encoding="utf-8",
        )
        (build / "package-record.json").write_text(
            json.dumps({
                "product_checks": checks, "hardening": {},
                "sha256": hashing.sha256_file(archive),
                "build_receipt_sha256": hashing.sha256_file(receipt),
            }),
            encoding="utf-8",
        )
        (build / "qualify" / "qualify-record.json").write_text(
            json.dumps({
                "sha256": hashing.sha256_file(archive),
                "product_checks": checks, "smoke": checks, "relocation": checks,
                "smoke_passed": 1, "smoke_total": 1,
            }),
            encoding="utf-8",
        )

    def cleanup(self):
        import shutil

        shutil.rmtree(self.work, ignore_errors=True)

    def test_assembles_standard_assets_with_sorted_checksums(self):
        result = release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertEqual(
            tuple(result["assets"]), product.expected_release_assets(product.NODE_VERSION, (TRIPLE,))
        )
        release_dir = self.work / "dist" / product.RELEASE_DIRNAME
        manifest = json.loads(
            (release_dir / product.manifest_name(product.NODE_VERSION, TRIPLE)).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["product"], "node")
        self.assertEqual(manifest["version"], product.NODE_VERSION)
        self.assertEqual(manifest["target"], TRIPLE)
        self.assertEqual(manifest["source_revision"], self.revision)
        self.assertEqual(
            manifest["sources_lock_sha256"],
            hashing.sha256_file(self.work / "sources.lock.json"),
        )
        lines = (release_dir / release.CHECKSUMS_NAME).read_text(encoding="utf-8").splitlines()
        names = [line.split("  ", 1)[1] for line in lines]
        self.assertEqual(names, sorted(names))
        self.assertNotIn(release.CHECKSUMS_NAME, names)
        self.assertEqual(len(names), 2)

    def test_rejects_malformed_records_before_staging(self):
        build = self.work / "build" / TRIPLE
        for relative, label in (
            ("package-record.json", "package record"),
            ("build-receipt.json", "build receipt"),
            ("qualify/qualify-record.json", "qualify record"),
        ):
            path = build / relative
            valid = path.read_bytes()
            for contents in ("[]", "{"):
                with self.subTest(label=label, contents=contents):
                    path.write_text(contents)
                    try:
                        with self.assertRaisesRegex(release_assembler.AssemblyError, f"invalid {label}"):
                            release_assembler.assemble_all(self.work, (TRIPLE,))
                        self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                    finally:
                        path.write_bytes(valid)

    def test_rejects_incomplete_package_checks_before_staging(self):
        path = self.work / "build" / TRIPLE / "package-record.json"
        record = json.loads(path.read_text())
        for checks in ([], None, [{"name": "c", "ok": "yes"}]):
            with self.subTest(checks=checks):
                path.write_text(json.dumps(record | {"product_checks": checks}))
                with self.assertRaisesRegex(release_assembler.AssemblyError, "package product checks are not all-ok"):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())

    def test_rejects_a_package_record_from_another_archive_or_receipt(self):
        path = self.work / "build" / TRIPLE / "package-record.json"
        valid = json.loads(path.read_text())
        for field, message in (
            ("sha256", "package record does not match packaged archive"),
            ("build_receipt_sha256", "package record does not match build receipt"),
        ):
            with self.subTest(field=field):
                path.write_text(json.dumps(valid | {field: "0" * 64}))
                with self.assertRaisesRegex(release_assembler.AssemblyError, message):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                self.assertFalse((self.work / "build" / "assembly-tmp").exists())

    def test_rejects_a_receipt_from_a_different_checkout_revision(self):
        (self.work / "controller.txt").write_text("another committed controller")
        subprocess.run(["git", "add", "controller.txt"], cwd=self.work, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "change controller"],
            cwd=self.work, check=True,
        )
        with self.assertRaisesRegex(release_assembler.AssemblyError, "build receipt checkout revision.*rebuild"):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
        self.assertFalse((self.work / "build" / "assembly-tmp").exists())

    def test_rejects_stale_or_unbound_lock_before_creating_release(self):
        lock = self.work / "sources.lock.json"
        lock.write_text('{"schema_version": 1, "revision": "new"}\n', encoding="utf-8")
        subprocess.run(["git", "add", "sources.lock.json"], cwd=self.work, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "change lock"],
            cwd=self.work, check=True,
        )
        receipt = self.work / "build" / TRIPLE / "build-receipt.json"
        for record in (json.loads(receipt.read_text(encoding="utf-8")), {}):
            with self.subTest(record=record):
                receipt.write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaisesRegex(release_assembler.AssemblyError, "source lock.*rebuild"):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                self.assertFalse((self.work / "build" / "assembly-tmp").exists())

    def test_rejects_incomplete_qualification_before_creating_release(self):
        path = self.work / "build" / TRIPLE / "qualify" / "qualify-record.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        destination = self.work / "dist" / product.RELEASE_DIRNAME
        cases = (
            ({"product_checks": []}, "product_checks"),
            ({"smoke": None}, "smoke"),
            ({"relocation": [{"name": "c", "ok": "yes"}]}, "relocation"),
            ({"smoke_passed": 0}, "smoke counts"),
            ({"smoke_total": True}, "smoke counts"),
        )
        for changes, diagnostic in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(release_assembler.AssemblyError, diagnostic):
                path.write_text(json.dumps(record | changes), encoding="utf-8")
                release_assembler.assemble_all(self.work, (TRIPLE,))
            self.assertFalse(destination.exists())

    def test_rejects_bad_checks_in_each_record_section(self):
        build = self.work / "build" / TRIPLE
        for relative, sections in (
            ("package-record.json", ("product_checks",)),
            ("qualify/qualify-record.json", ("product_checks", "smoke", "relocation")),
        ):
            path = build / relative
            original = path.read_text()
            record = json.loads(original)
            for section in sections:
                for checks in ([{"ok": True}, {"ok": False}], [{"ok": 1}], [None], {"ok": True}):
                    with self.subTest(record=relative, section=section, checks=checks):
                        path.write_text(json.dumps(record | {section: checks}))
                        with self.assertRaisesRegex(release_assembler.AssemblyError, "not all-ok"):
                            release_assembler.assemble_all(self.work, (TRIPLE,))
                        self.assertFalse((self.work / "build" / "assembly-tmp").exists())
                path.write_text(original)

    def test_reports_the_exact_missing_archive(self):
        archive = self.work / "dist" / TRIPLE / product.archive_name(product.NODE_VERSION, TRIPLE)
        archive.unlink()
        with self.assertRaises(release_assembler.AssemblyError) as error:
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertEqual(str(error.exception), f"missing packaged archive: {archive}")
        self.assertFalse((self.work / "build" / "assembly-tmp").exists())

    def test_rejects_qualification_for_different_archive(self):
        path = self.work / "build" / TRIPLE / "qualify" / "qualify-record.json"
        record = json.loads(path.read_text())
        for digest in (None, "0" * 64):
            with self.subTest(digest=digest):
                path.write_text(json.dumps(record | {"sha256": digest}))
                with self.assertRaisesRegex(release_assembler.AssemblyError, "qualify record does not match"):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "build" / "assembly-tmp").exists())

    def test_refuses_dirty_checkout_and_existing_release(self):
        (self.work / "stray.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(release_assembler.AssemblyError):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        (self.work / "stray.txt").unlink()
        release_assembler.assemble_all(self.work, (TRIPLE,))
        with self.assertRaises(release_assembler.AssemblyError):
            release_assembler.assemble_all(self.work, (TRIPLE,))


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_action_pins_are_full_shas(self):
        pins = re.findall(r"uses:\s*\S+@(\S+)", self.text)
        self.assertTrue(pins)
        for pin in pins:
            self.assertRegex(pin, r"^[0-9a-f]{40}$")

    def test_dispatch_only_with_preflight_before_builds(self):
        self.assertIn("on:\n  workflow_dispatch:\n", self.text)
        self.assertNotIn("inputs:", self.text)
        self.assertLess(self.text.index("  preflight:"), self.text.index("  controller-test:"))
        self.assertLess(self.text.index("  controller-test:"), self.text.index("  build:"))
        self.assertIn("needs: [preflight, controller-test]", self.text)

    def test_targets_and_release_gate_use_current_contract(self):
        self.assertIn("aarch64-apple-darwin", self.text)
        self.assertIn("x86_64-unknown-linux-musl", self.text)
        self.assertIn("xcode-27", self.text)
        self.assertNotIn("macos-14", self.text)
        self.assertIn("RELEASE_TAG: release-${{ github.sha }}", self.text)
        self.assertIn("python3 build.py assemble", self.text)
        self.assertIn("build.py published-smoke --target", self.text)
        self.assertIn("sha256sum -c SHA256SUMS", self.text)
        self.assertIn(
            '--target "$GITHUB_SHA" --prerelease --verify-tag', self.text
        )
        self.assertIn('--notes-file "$RUNNER_TEMP/release-notes.md"', self.text)
        self.assertNotIn("GH_TOKEN", self.text.split("  release:", 1)[0].split("  build:", 1)[1])

    def test_least_privilege_and_gates(self):
        self.assertIn("permissions: {}", self.text)
        self.assertIn("contents: read", self.text)
        self.assertIn("contents: write", self.text)
        self.assertIn("if-no-files-found: error", self.text)
        self.assertIn("persist-credentials: false", self.text)

    def test_assembly_inputs_travel_through_artifact(self):
        for record in (
            "build-receipt.json",
            "package-record.json",
            "qualify/qualify-record.json",
        ):
            self.assertIn(record, self.text)


class ReproduceDiffTest(unittest.TestCase):
    def test_identical_bytes_have_no_chunks(self):
        data = bytes(range(256)) * 8192
        self.assertEqual(reproduce_runner.differing_chunks(data, data), [])

    def test_locates_differing_chunks(self):
        first = bytes(6 << 20)
        second = bytearray(first)
        second[3 << 20] ^= 1
        second[(5 << 20) - 1] ^= 1
        self.assertEqual(
            reproduce_runner.differing_chunks(bytes(first), bytes(second)),
            [3 << 20, 4 << 20],
        )

    def test_size_change_reported(self):
        self.assertEqual(
            reproduce_runner.differing_chunks(b"abc", b"abcd"), [0, 3]
        )


if __name__ == "__main__":
    unittest.main()
