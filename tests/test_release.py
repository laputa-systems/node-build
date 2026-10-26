import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import resolve_release
from buildsys import release as release_assembler
from buildsys import reproduce as reproduce_runner


class ResolveReleaseTest(unittest.TestCase):
    def test_empty_defaults_to_yyyymmdd(self):
        tag = resolve_release.resolve_release_tag("")
        self.assertRegex(tag, r"^\d{8}$")

    def test_valid_tag_passes_through(self):
        self.assertEqual(resolve_release.resolve_release_tag("20261025"), "20261025")

    def test_invalid_tag_rejected(self):
        for bad in ("latest", "2026-10-25", "v20261025", "123"):
            with self.assertRaises(ValueError):
                resolve_release.resolve_release_tag(bad)


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

    def test_publish_uses_prerelease_and_sha_target(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("--prerelease", text)
        self.assertIn('--target "$GITHUB_SHA"', text)

    def test_least_privilege_and_gates(self):
        text = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("contents: write", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertIn("macos-14", text)

    def test_assembly_inputs_travel_through_artifact(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        for record in (
            "build-receipt.json",
            "package-record.json",
            "qualify/qualify-record.json",
        ):
            self.assertIn(record, workflow)


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
