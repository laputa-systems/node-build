import io
import os
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


class CommandSmokeContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / ".work" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.node = self.work / "node fixture"
        self.node.write_text(
            "#!/bin/sh -e\n"
            'case "$1" in\n'
            '  --version) cat version;;\n'
            '  -h|--help) cat "help.$1";;\n'
            "  -p) test \"$2\" = 'JSON.stringify({answer:42})'; cat evaluate;;\n"
            '  --completion-bash) cat completion;;\n'
            '  -e) test -f addon.node; test "$2" = "$(cat addon-script)"; printf "addon ok\\n";;\n'
            '  *) exit 8;;\n'
            'esac\n'
            'if [ -f "stderr.$1" ]; then cat "stderr.$1" >&2; fi\n'
            'if [ -f "status.$1" ]; then exit "$(cat "status.$1")"; fi\n',
            encoding="utf-8",
        )
        self.node.chmod(0o755)
        self.help = "Usage: node [options]\n" + smoke.OWNED_FOOTER + "\n"
        for name, body in (
            ("version", "v26.12.1\n"), ("evaluate", '{"answer":42}\n'),
            ("help.-h", self.help), ("help.--help", self.help), ("completion", "complete -F _node node\n"),
            ("addon-script", "const addon = require('./addon.node'); if (addon.answer() !== 42) { process.exit(1); } console.log('addon ok');"),
        ):
            (self.work / name).write_text(body, encoding="utf-8")

    def test_version_and_help_probe_statuses_and_contents(self):
        self.assertEqual(smoke.check_version(self.node, self.work, self.work), "v26.12.1")
        self.assertEqual(
            smoke.check_help_footer(self.node, self.work, self.work),
            "help footer, version, JSON and completion ok",
        )
        for name, invalid, diagnostic in (
            ("help.-h", self.help.replace("Usage: node", "options"), "-h footer or help unexpected"),
            ("help.--help", "header\n" + self.help, "^-h and --help differ$"),
            ("help.-h", "Usage: node\n" + smoke.OWNED_FOOTER + "\n" + self.help, "-h footer or help unexpected"),
            ("help.-h", self.help.rstrip(), "-h footer or help unexpected"),
            ("version", "v26.12.0\n", "unexpected output for --version"),
            ("evaluate", '{"answer":41}\n', "unexpected output for -p"),
            ("completion", smoke.OWNED_FOOTER, "^completion output unexpected$"),
        ):
            with self.subTest(name=name, diagnostic=diagnostic):
                path = self.work / name
                original = path.read_text(encoding="utf-8")
                path.write_text(invalid, encoding="utf-8")
                try:
                    with self.assertRaisesRegex(smoke.SmokeError, diagnostic):
                        smoke.check_help_footer(self.node, self.work, self.work)
                finally:
                    path.write_text(original, encoding="utf-8")
        for name, value, error in (
            ("stderr.-h", "fixture stderr", "^-h footer or help unexpected$"),
            ("status.-h", "8", "^-h footer or help unexpected$"),
            ("stderr.--version", "fixture stderr", "^unexpected output for --version$"),
            ("status.-p", "8", "^unexpected output for -p$"),
        ):
            with self.subTest(name=name):
                path = self.work / name
                path.write_text(value, encoding="utf-8")
                try:
                    with self.assertRaisesRegex(smoke.SmokeError, error):
                        smoke.check_help_footer(self.node, self.work, self.work)
                finally:
                    path.unlink()
        version = self.work / "version"
        version.write_text("v26.12.0", encoding="utf-8")
        with self.assertRaisesRegex(smoke.SmokeError, r"^version v26\.12\.0 != v26\.12\.1$"):
            smoke.check_version(self.node, self.work, self.work)
        version.unlink()
        with self.assertRaisesRegex(smoke.SmokeError, "^--version failed: .*"):
            smoke.check_version(self.node, self.work, self.work)

    def test_excluded_programs_do_not_ship(self):
        install = self.work / "install"
        (install / "bin").mkdir(parents=True)
        self.assertEqual(
            smoke.check_exclusions(self.node, self.work, self.work, install),
            "npm/npx absent, --help ok",
        )
        for program in ("npm", "npx"):
            candidate = install / "bin" / program
            candidate.touch()
            try:
                with self.assertRaisesRegex(smoke.SmokeError, f"^excluded payload present: bin/{program}$"):
                    smoke.check_exclusions(self.node, self.work, self.work, install)
            finally:
                candidate.unlink()
        (self.work / "help.--help").write_text("fixture help", encoding="utf-8")
        with self.assertRaisesRegex(smoke.SmokeError, "^--help unexpected: fixture help$"):
            smoke.check_exclusions(self.node, self.work, self.work, install)

    def test_addon_compiles_with_platform_flags_and_is_loaded_from_workdir(self):
        compiler = (
            "#!/bin/sh -e\n"
            'printf "%s\\n" "$@" > "$FIXTURE_ARGUMENTS"\n'
            'for arg do destination="$arg"; done\n'
            'printf "addon fixture" > "$destination"\n'
        )
        headers = self.work / "shipped headers"
        arguments = self.work / "compiler-args"
        package = self.work / "addon.node"
        for triple, name, flags in (
            ("x86_64-unknown-linux-musl", "g++", ["-shared", "-fPIC"]),
            ("aarch64-apple-darwin", "clang++", ["-bundle", "-undefined", "dynamic_lookup"]),
        ):
            with self.subTest(triple=triple):
                tool = self.work / name
                tool.write_text(compiler, encoding="utf-8")
                tool.chmod(0o755)
                with patch.dict(os.environ, {"PATH": f"{self.work}:{os.environ['PATH']}", "FIXTURE_ARGUMENTS": str(arguments)}):
                    with patch.object(smoke.subprocess, "run", wraps=subprocess.run) as run:
                        self.assertEqual(
                            smoke.check_napi_addon(self.node, self.work, self.work, headers, triple),
                            "compiled against shipped headers and loaded",
                        )
                        self.assertEqual(run.call_args_list[0].kwargs["timeout"], 60)
                    self.assertEqual(package.read_bytes(), b"addon fixture")
                    self.assertEqual(arguments.read_text().splitlines(), [
                        *flags, f"-I{headers}", str(self.work / "smoke/addon.cc"), "-o", str(package),
                    ])
                    status = self.work / "status.-e"
                    status.write_text("8", encoding="utf-8")
                    error = self.work / "stderr.-e"
                    error.write_text("load failure", encoding="utf-8")
                    with self.assertRaisesRegex(smoke.SmokeError, "^addon load failed: load failure$"):
                        smoke.check_napi_addon(self.node, self.work, self.work, headers, triple)
                    status.unlink()
                    error.unlink()
                    tool.write_text('#!/bin/sh\nprintf "compile failure\\n" >&2\nexit 9\n', encoding="utf-8")
                    with self.assertRaisesRegex(smoke.SmokeError, "^addon compile failed: compile failure"):
                        smoke.check_napi_addon(self.node, self.work, self.work, headers, triple)
