import io
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys import product, smoke

ROOT = Path(__file__).resolve().parents[1]


class ProcessSmokeRunnerTest(unittest.TestCase):
    def test_passes_workdir_arguments_environment_and_failed_status(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp") as temporary:
            work = Path(temporary)
            (work / "owner fixture").touch()
            program = work / "node fixture"
            program.write_text(
                '#!/bin/sh -e\n'
                'test -f "owner fixture"\n'
                'printf "%s:%s" "$TEST_SMOKE_RUNNER" "$1"\n'
                'printf "probe stderr" >&2\n'
                'exit 7\n',
                encoding="utf-8",
            )
            program.chmod(0o755)
            with patch.dict(os.environ, {"TEST_SMOKE_RUNNER": "inherited"}):
                result = smoke.run_node(program, ["two words"], work)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (7, "inherited:two words", "probe stderr"))

    def test_applies_the_probe_deadline(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp") as temporary:
            with patch.object(smoke, "CHECK_TIMEOUT", 0.2), self.assertRaises(subprocess.TimeoutExpired) as caught:
                smoke.run_node(Path("/bin/sh"), ["-c", "exec sleep 1"], Path(temporary))
            self.assertEqual(caught.exception.timeout, 0.2)


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
            (work / "identity-workdir").touch()
            program.write_text(
                "#!/bin/sh -e\n"
                'test -f identity-workdir\n'
                'test "$#" -eq 2 && test "$1" = -p\n'
                "test \"$2\" = \"process.arch + '/' + process.platform\"\n"
                'printf "x64/linux\\n"\n',
                encoding="utf-8",
            )
            self.assertEqual(smoke.check_arch(program, work, work, "x86_64-unknown-linux-musl"), "x64/linux")
            with self.assertRaisesRegex(smoke.SmokeError, "^identity x64/linux != arm64/darwin$"):
                smoke.check_arch(program, work, work)


class FileSystemSmokeTest(unittest.TestCase):
    def test_requires_matching_async_readback_and_successful_exit(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp") as temporary:
            work = Path(temporary)
            program = work / "node fixture"
            program.write_text(
                '#!/bin/sh -e\n'
                'test "$#" -eq 2 && test "$1" = -e\n'
                'cat readback\n'
                'if [ -f failing ]; then printf "fixture failure" >&2; exit 7; fi\n',
                encoding="utf-8",
            )
            program.chmod(0o755)
            readback = work / "readback"
            readback.write_bytes(b"x" * 1000)
            self.assertEqual(smoke.check_fs_async(program, work, work), "fs ok")
            readback.write_bytes(b"y" * 1000)
            with self.assertRaisesRegex(smoke.SmokeError, "^fs check returned unexpected data$"):
                smoke.check_fs_async(program, work, work)
            readback.write_bytes(b"x" * 1000)
            (work / "failing").touch()
            with self.assertRaisesRegex(smoke.SmokeError, "^fs check failed: fixture failure$"):
                smoke.check_fs_async(program, work, work)


class InlineSmokeProbeTest(unittest.TestCase):
    def test_requires_a_success_line_and_zero_exit(self):
        work = Path("/probe/work")
        fixtures = Path("/probe/fixtures")
        node = work / "installed node"
        cases = (
            (smoke.check_modules, "cjs+esm ok", "cjs+esm ok", "module", fixtures / "smoke"),
            (smoke.check_dns_tcp, "dns+tcp ok", "dns+tcp ok", r"dns\+tcp", work),
            (smoke.check_http, "http ok", "http ok", "http", work),
            (smoke.check_https, "https ok", "trusted accepted, untrusted rejected", "https", work),
            (smoke.check_crypto, "crypto ok", "webcrypto vector + aes-gcm roundtrip", "crypto", work),
            (smoke.check_compression, "compression ok", "zlib + brotli roundtrips", "compression", work),
            (smoke.check_fetch_streams, "fetch ok", "fetch ok", "fetch", work),
            (smoke.check_intl, "intl ok", "en-US currency + weekday", "intl", work),
        )
        for check, marker, detail, error_label, cwd in cases:
            with self.subTest(probe=check.__name__), patch.object(smoke, "run_node") as invoke:
                invoke.return_value = subprocess.CompletedProcess([], 0, f"probe log\n{marker}\n", "")
                self.assertEqual(check(node, work, fixtures), detail)
                program, args, directory = invoke.call_args.args
                self.assertEqual((program, args[0], directory), (node, "-e", cwd))
                if check is not smoke.check_https:
                    self.assertEqual(len(args), 2)
                for status, stdout in ((0, f"did not report {marker}\n"), (8, f"{marker}\n")):
                    invoke.return_value = subprocess.CompletedProcess([], status, stdout, "probe error")
                    with self.assertRaisesRegex(smoke.SmokeError, rf"^{error_label} check failed.*: probe error$"):
                        check(node, work, fixtures)

    def test_startup_requires_zero_exit_and_reports_the_measured_interval(self):
        work = Path("/probe/work")
        node = work / "installed node"
        with (
            patch.object(smoke.time, "monotonic", side_effect=(1.0, 1.012, 2.0, 2.004)),
            patch.object(smoke, "run_node", return_value=subprocess.CompletedProcess([], 0, "", "")) as invoke,
        ):
            self.assertEqual(smoke.check_startup(node, work, work), "cold start 12 ms")
            invoke.assert_called_once_with(node, ["-e", "1"], work)
            invoke.return_value = subprocess.CompletedProcess([], 7, "", "fixture error")
            with self.assertRaisesRegex(smoke.SmokeError, "^startup probe failed: fixture error$"):
                smoke.check_startup(node, work, work)


class HttpsSmokeTest(unittest.TestCase):
    def test_passes_fixture_paths_as_separate_node_arguments(self):
        work = Path("/probe/work")
        fixtures = Path("/probe/owner's fixtures")
        node = work / "installed node"
        with patch.object(smoke, "run_node", return_value=subprocess.CompletedProcess([], 0, "https ok\n", "")) as invoke:
            self.assertEqual(smoke.check_https(node, work, fixtures), "trusted accepted, untrusted rejected")
        program, args, directory = invoke.call_args.args
        self.assertEqual((program, directory), (node, work))
        self.assertEqual(args[0], "-e")
        self.assertEqual(args[2:], ["--", str(fixtures / "test-key.pem"), str(fixtures / "test-cert.pem")])
        self.assertNotIn(str(fixtures), args[1])

    def test_rejects_failed_probe_even_with_success_output(self):
        with (
            patch.object(smoke, "run_node", return_value=subprocess.CompletedProcess([], 3, "https ok\n", "fixture error")),
            self.assertRaisesRegex(smoke.SmokeError, r"^https check failed \(3\): fixture error$"),
        ):
            smoke.check_https(Path("/probe/node"), Path("/probe/work"), Path("/probe/fixtures"))


class TestRunnerSmokeTest(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".work/tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.work = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch)))
        self.fixtures = self.work / "fixtures"
        self.testdir = self.fixtures / "smoke"
        self.testdir.mkdir(parents=True)
        self.node = self.work / "node"
        self.node.write_text(
            "#!/bin/sh -e\n"
            'printf "%s\\n" "$@" > arguments\n'
            "cat report\n"
            'if [ -f failure ]; then cat failure >&2; exit 7; fi\n',
            encoding="utf-8",
        )
        self.node.chmod(0o755)

    def test_requires_one_passing_test_in_the_tap_report(self):
        output = "TAP version 13\nok 1 - fixture\n1..1\n# tests 1\n# pass 1\n# fail 0\n"
        (self.testdir / "report").write_text(output, encoding="utf-8")
        self.assertEqual(smoke.check_node_test(self.node, self.work, self.fixtures), "pass 1")
        self.assertEqual(
            (self.testdir / "arguments").read_text(encoding="utf-8").splitlines(),
            ["--test", "--test-reporter=tap", "sample.test.js"],
        )
        (self.testdir / "failure").write_text("fixture stderr", encoding="utf-8")
        with self.assertRaises(smoke.SmokeError) as error:
            smoke.check_node_test(self.node, self.work, self.fixtures)
        self.assertEqual(str(error.exception), f"node:test failed: {output}fixture stderr")

    def test_rejects_other_pass_counts_and_unrelated_output(self):
        for output in ("# pass 10\n", "status: pass 1\n", "# pass 1\n# pass 10\n"):
            with self.subTest(output=output):
                (self.testdir / "report").write_text(output, encoding="utf-8")
                with self.assertRaisesRegex(smoke.SmokeError, "node:test unexpected output"):
                    smoke.check_node_test(self.node, self.work, self.fixtures)


class WorkerSmokeTest(unittest.TestCase):
    def test_child_uses_the_running_node_instead_of_interpolating_the_install_path(self):
        scratch = ROOT / ".work/tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        work = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="owner's build ", dir=scratch)))
        node = work / "node"
        node.write_text(
            "#!/bin/sh -e\n"
            'test "$#" = 1 && test "$1" = "$PWD/worker-probe.cjs" || exit 8\n'
            'case "$(cat "$1")" in\n'
            "  *\"execFile(process.execPath, ['-p', '6*7']\"*);;\n"
            '  *) printf "worker did not use the running node executable\\n" >&2; exit 8;;\n'
            "esac\n"
            'if test -e decorated; then printf "did not report workers ok\\n"; '
            'elif test ! -e silent; then printf "workers ok\\n"; fi\n'
            'if test -e failed; then printf "fixture stderr\\n" >&2; exit 9; fi\n',
            encoding="utf-8",
        )
        node.chmod(0o755)
        self.assertEqual(smoke.check_workers_child(node, work, work), "worker + child ok")

        (work / "silent").touch()
        with self.assertRaisesRegex(smoke.SmokeError, "^workers check failed: $"):
            smoke.check_workers_child(node, work, work)

        (work / "silent").unlink()
        (work / "decorated").touch()
        with self.assertRaisesRegex(smoke.SmokeError, "^workers check failed: $"):
            smoke.check_workers_child(node, work, work)
        (work / "decorated").unlink()
        (work / "failed").touch()
        with self.assertRaisesRegex(smoke.SmokeError, "^workers check failed: fixture stderr$"):
            smoke.check_workers_child(node, work, work)


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
            patch.object(smoke, "check_napi_addon", side_effect=OSError("x" * 301)) as addon,
            patch.object(smoke, "check_exclusions", return_value="no excluded files") as exclusions,
        ):
            self.assertEqual(smoke.run_suite(node, install, headers, work, fixtures, triple), [
                smoke.SmokeFinding("architecture", True, "x64/linux"),
                smoke.SmokeFinding("deadline", False, "Command 'fixture' timed out after 60 seconds"),
                smoke.SmokeFinding("broken", False, "x" * 300),
                smoke.SmokeFinding("napi-addon", False, "x" * 300),
                smoke.SmokeFinding("exclusions", True, "no excluded files"),
            ])
        architecture.assert_called_once_with(node, work, fixtures, triple)
        addon.assert_called_once_with(node, work, fixtures, headers, triple)
        exclusions.assert_called_once_with(node, work, fixtures, install)


    def test_records_successful_addon_and_truncates_exclusions_failure(self):
        work = Path("/fixture/work")
        install = work / "install"
        node = install / "bin/node"
        headers = install / "include/node"
        fixtures = work / "fixtures"
        with (
            patch.object(smoke, "CHECKS", ()),
            patch.object(smoke, "check_napi_addon", return_value="loaded") as addon,
            patch.object(smoke, "check_exclusions", side_effect=smoke.SmokeError("x" * 301)) as exclusions,
        ):
            self.assertEqual(smoke.run_suite(node, install, headers, work, fixtures), [
                smoke.SmokeFinding("napi-addon", True, "loaded"),
                smoke.SmokeFinding("exclusions", False, "x" * 300),
            ])
        addon.assert_called_once_with(node, work, fixtures, headers, "aarch64-apple-darwin")
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


    def test_reports_wrong_target_shapes_and_reaps_child(self):
        for payload in (b'{"other":true}', b'[null]', b'["id"]', b'[{"id":null}]', b'[{"id":""}]'):
            with self.subTest(payload=payload):
                self.run_probe(
                    "printf 'Debugger listening on ws://127.0.0.1:43210/id' >&2; exec sleep 4",
                    error="^inspector list unexpected:",
                    response_body=payload,
                )

    def test_reports_malformed_target_list_and_reaps_child(self):
        for payload in (b'[', b'\xff'):
            with self.subTest(payload=payload):
                self.run_probe(
                    "printf 'Debugger listening on ws://127.0.0.1:43210/id' >&2; exec sleep 4",
                    error="^cannot decode inspector list:",
                    response_body=payload,
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
            '  -e) test -f addon.node; test "$2" = "$(cat addon-script)"; '
            'if test -f addon-report; then cat addon-report; else printf "addon ok\\n"; fi;;\n'
            '  *) exit 8;;\n'
            'esac\n'
            'if [ -f "stderr.$1" ]; then cat "stderr.$1" >&2; fi\n'
            'if [ -f "status.$1" ]; then exit "$(cat "status.$1")"; fi\n',
            encoding="utf-8",
        )
        self.node.chmod(0o755)
        self.help = "Usage: node [options]\n" + smoke.OWNED_FOOTER + "\n"
        for name, body in (
            ("version", f"v{product.NODE_VERSION}\n"), ("evaluate", '{"answer":42}\n'),
            ("help.-h", self.help), ("help.--help", self.help), ("completion", "complete -F _node node\n"),
            ("addon-script", "const addon = require('./addon.node'); if (addon.answer() !== 42) { process.exit(1); } console.log('addon ok');"),
        ):
            (self.work / name).write_text(body, encoding="utf-8")

    def test_version_and_help_probe_statuses_and_contents(self):
        self.assertEqual(smoke.check_version(self.node, self.work, self.work), f"v{product.NODE_VERSION}")
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
        with self.assertRaisesRegex(smoke.SmokeError, rf"^version v26\.12\.0 != v{re.escape(product.NODE_VERSION)}$"):
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
            for dangling in (False, True):
                with self.subTest(program=program, dangling=dangling):
                    candidate = install / "bin" / program
                    if dangling:
                        candidate.symlink_to("missing-program")
                    else:
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
            ("aarch64-unknown-linux-musl", "g++", ["-shared", "-fPIC"]),
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
                    report = self.work / "addon-report"
                    report.write_text("did not report addon ok\n", encoding="utf-8")
                    with self.assertRaisesRegex(smoke.SmokeError, "^addon load failed: $"):
                        smoke.check_napi_addon(self.node, self.work, self.work, headers, triple)
                    report.unlink()
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
