import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))

import resolve_release


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


if __name__ == "__main__":
    unittest.main()
