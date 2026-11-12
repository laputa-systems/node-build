import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildsys import inputs, product
from buildsys import release as release_assembler
from buildsys import reproduce as reproduce_runner

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
TRIPLE = "aarch64-apple-darwin"


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
        (build / "package-record.json").write_text(
            json.dumps({"product_checks": checks, "hardening": {}}), encoding="utf-8"
        )
        (build / "build-receipt.json").write_text("{}", encoding="utf-8")
        (build / "qualify" / "qualify-record.json").write_text(
            json.dumps({
                "sha256": inputs.sha256_of_file(archive),
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
            inputs.sha256_of_file(self.work / "sources.lock.json"),
        )
        lines = (release_dir / product.CHECKSUMS_NAME).read_text(encoding="utf-8").splitlines()
        names = [line.split("  ", 1)[1] for line in lines]
        self.assertEqual(names, sorted(names))
        self.assertNotIn(product.CHECKSUMS_NAME, names)
        self.assertEqual(len(names), 2)

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
