import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys import smoke

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureSmokeTest(unittest.TestCase):
    def test_rejects_failed_architecture_probe_with_matching_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work" / "tmp") as temporary:
            work = Path(temporary)
            program = work / "node"
            program.write_text(
                '#!/bin/sh\nprintf "x64/linux\\n"\nprintf "fixture failure\\n" >&2\nexit 7\n',
                encoding="utf-8",
            )
            program.chmod(0o755)
            with self.assertRaisesRegex(smoke.SmokeError, r"identity probe failed \(7\): fixture failure"):
                smoke.check_arch(program, work, work, "x86_64-unknown-linux-musl")
            program.write_text('#!/bin/sh\nprintf "x64/linux\\n"\n', encoding="utf-8")
            self.assertEqual(smoke.check_arch(program, work, work, "x86_64-unknown-linux-musl"), "x64/linux")
            with self.assertRaisesRegex(smoke.SmokeError, "^identity x64/linux != arm64/darwin$"):
                smoke.check_arch(program, work, work)


class SmokeSuiteTest(unittest.TestCase):
    def test_records_failures_and_continues_with_addon_and_payload_checks(self):
        work = Path("/fixture/work")
        install = work / "install"
        node = install / "bin" / "node"
        headers = install / "include" / "node"
        fixtures = work / "fixtures"
        triple = "x86_64-unknown-linux-musl"

        def timed_out(program, directory, assets):
            self.assertEqual((program, directory, assets), (node, work, fixtures))
            raise subprocess.TimeoutExpired("fixture", 60)

        def broken(program, directory, assets):
            self.assertEqual((program, directory, assets), (node, work, fixtures))
            raise smoke.SmokeError("x" * 400)

        with (
            patch.object(smoke, "check_arch", return_value="x64/linux") as architecture,
            patch.object(smoke, "CHECKS", (("architecture", architecture), ("deadline", timed_out), ("broken", broken))),
            patch.object(smoke, "check_napi_addon", side_effect=OSError("compiler unavailable")) as addon,
            patch.object(smoke, "check_exclusions", return_value="no excluded files") as exclusions,
        ):
            self.assertEqual(smoke.run_suite(node, install, headers, work, fixtures, triple), [
                smoke.SmokeFinding("architecture", True, "x64/linux"),
                smoke.SmokeFinding("deadline", False, "Command 'fixture' timed out after 60 seconds"),
                smoke.SmokeFinding("broken", False, "x" * 300),
                smoke.SmokeFinding("napi-addon", False, "compiler unavailable"),
                smoke.SmokeFinding("exclusions", True, "no excluded files"),
            ])
        architecture.assert_called_once_with(node, work, fixtures, triple)
        addon.assert_called_once_with(node, work, fixtures, headers, triple)
        exclusions.assert_called_once_with(node, work, fixtures, install)
