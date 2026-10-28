import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import resolve_release

from buildsys import release as release_assembler
from buildsys import reproduce as reproduce_runner


class ResolveReleaseTest(unittest.TestCase):
    def test_empty_defaults_to_yyyymmdd(self):
        commit = "a" * 40
        now = datetime(2026, 10, 27, 1, tzinfo=UTC)
        self.assertEqual(
            resolve_release.resolve_release_tag("", commit, commit, now), "20261027"
        )

    def test_valid_tag_requires_matching_checkout_and_existing_ref(self):
        commit = "a" * 40
        self.assertEqual(
            resolve_release.resolve_release_tag("20261025", commit, commit),
            "20261025",
        )
        resolve_release.verify_existing_tag_target("20261025", commit, commit)

    def test_invalid_tag_and_mismatched_commit_fail(self):
        commit = "a" * 40
        with self.assertRaises(ValueError):
            resolve_release.resolve_release_tag("$(touch bad)", commit, commit)
        with self.assertRaises(ValueError):
            resolve_release.resolve_release_tag("2026-10-25", commit, commit)
        with self.assertRaises(ValueError):
            resolve_release.resolve_release_tag("20261025", commit, "b" * 40)
        with self.assertRaises(ValueError):
            resolve_release.verify_existing_tag_target("20261025", commit, "b" * 40)
        with self.assertRaises(ValueError):
            resolve_release.resolve_release_tag("20261025", "deadbeef", "deadbeef")


class TagCollisionTest(unittest.TestCase):
    def test_matching_tag_accepted_and_collision_rejected(self):
        work = Path(tempfile.mkdtemp(prefix="tagprobe-"))
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        try:
            subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
            (work / "f.txt").write_text("x", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=work, env=env, check=True)
            subprocess.run(["git", "commit", "-qm", "x"], cwd=work, env=env, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=work, env=env,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            subprocess.run(["git", "tag", "20261026"], cwd=work, env=env, check=True)
            release_assembler.check_tag("20261026", head, work)
            with self.assertRaises(release_assembler.AssemblyError):
                release_assembler.check_tag("20261026", "0" * 40, work)
        finally:
            import shutil

            shutil.rmtree(work, ignore_errors=True)


class WorkflowTest(unittest.TestCase):
    def test_action_pins_are_full_shas(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        pins = re.findall(r"uses:\s*\S+@(\S+)", text)
        self.assertTrue(pins)
        for pin in pins:
            self.assertRegex(pin, r"^[0-9a-f]{40}$")

    def test_preflight_validates_tag_and_runs_tests_before_builds(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        tests = text.index("- name: Run fast controller tests")
        macos_build = text.index("  build-macos:")
        linux_build = text.index("  build-linux:")
        self.assertLess(tests, macos_build)
        self.assertLess(tests, linux_build)
        self.assertIn("RELEASE_TAG_INPUT: ${{ inputs.release_tag }}", text)
        self.assertIn(".github/scripts/resolve_release.py", text)
        self.assertIn("needs: [prepare]", text)
        self.assertNotIn('TAG="${{ inputs.release_tag }}"', text)

    def test_targets_and_release_gate_use_current_contract(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn('NODE_VERSION: "26.12.1"', text)
        self.assertIn("aarch64-apple-darwin", text)
        self.assertIn("x86_64-unknown-linux-musl", text)
        self.assertIn("build.py assemble --tag", text)
        self.assertIn("build.py published-smoke --target aarch64-apple-darwin", text)
        self.assertIn("build.py published-smoke --target x86_64-unknown-linux-musl", text)
        self.assertIn('gh release create "$RELEASE_TAG" --target "$GITHUB_SHA"', text)
        self.assertIn("xcode-27", text)
        self.assertNotIn("macos-14", text)
        self.assertNotIn("GH_TOKEN", text.split("  publish:", 1)[0])

    def test_publish_uses_prerelease_and_sha_target(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("--prerelease", text)
        self.assertIn('--target "$GITHUB_SHA"', text)

    def test_least_privilege_and_gates(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("contents: write", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("fetch-depth: 0", text)

    def test_assembly_inputs_travel_through_artifact(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        for record in (
            "build-receipt.json",
            "package-record.json",
            "qualify/qualify-record.json",
        ):
            self.assertIn(record, workflow)

    def test_smokes_verify_exact_assembled_bytes(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("SHA256SUMS", text)
        self.assertIn("shasum -a 256 --check SHA256SUMS", text)
        self.assertIn("sha256sum --check SHA256SUMS", text)


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
