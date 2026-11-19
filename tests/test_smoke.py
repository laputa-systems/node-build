import io
import subprocess
import tempfile
import time
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


class InspectorSmokeTest(unittest.TestCase):
    def run_probe(self, body, *, expected=None, error=None, response_body=None, deadline=2):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work" / "tmp") as temporary:
            work = Path(temporary)
            program = work / "node"
            program.write_text(
                "#!/bin/sh -e\n"
                'test "$1" = --inspect=127.0.0.1:0\n'
                'test "$(cat "$2")" = "setInterval(() => {}, 1000);"\n'
                f"{body}\n",
                encoding="utf-8",
            )
            program.chmod(0o755)
            spawned = []
            popen = subprocess.Popen

            def capture(*args, **kwargs):
                process = popen(*args, **kwargs)
                spawned.append(process)
                return process

            with (
                patch.object(smoke, "INSPECTOR_ANNOUNCE_TIMEOUT", deadline),
                patch.object(smoke.subprocess, "Popen", side_effect=capture),
                patch.object(smoke.urllib.request, "urlopen", return_value=io.BytesIO(response_body or b"")) as response,
            ):
                try:
                    started = time.monotonic()
                    if error is not None:
                        with self.assertRaisesRegex(smoke.SmokeError, error):
                            smoke.check_inspector(program, work, work)
                    else:
                        self.assertEqual(smoke.check_inspector(program, work, work), expected)
                    if response_body is None:
                        self.assertLess(time.monotonic() - started, 2)
                        response.assert_not_called()
                    else:
                        response.assert_called_once_with("http://127.0.0.1:43210/json/list", timeout=30)
                    self.assertEqual(len(spawned), 1)
                    self.assertIsNotNone(spawned[0].returncode)
                finally:
                    for child in spawned:
                        child.kill()
                        child.wait()
                        if child.stdout is not None:
                            child.stdout.close()
                        if child.stderr is not None:
                            child.stderr.close()

    def test_times_out_and_reaps_child_with_partial_stderr(self):
        self.run_probe(
            "printf starting >&2; exec sleep 4",
            error="inspector endpoint not announced: starting",
            deadline=0.15,
        )

    def test_preserves_diagnostic_at_eof_with_non_utf8_stderr(self):
        self.run_probe(
            "printf 'starting\\377' >&2",
            error="inspector endpoint not announced: starting�",
        )

    def test_reads_endpoint_and_reaps_child(self):
        self.run_probe(
            "printf 'Debugger listening on ws://127.0.0.1:43210/id\\n' >&2; exec sleep 4",
            expected="inspector target 12345678",
            response_body=b'[{"id":"123456789"}]',
        )

    def test_rejects_empty_target_list_and_reaps_child(self):
        self.run_probe(
            "printf 'Debugger listening on ws://127.0.0.1:43210/id' >&2; exec sleep 4",
            error=r"inspector list unexpected: \[\]",
            response_body=b"[]",
        )
