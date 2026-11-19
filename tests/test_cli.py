import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import build
from buildsys import budgets, comparison, reproduce


class ControllerTestCommandContract(unittest.TestCase):
    def test_discovers_repository_suite_and_reports_failure(self):
        suite = unittest.TestSuite()
        complete = unittest.TestResult()
        failed = unittest.TestResult()
        failed.failures.append((unittest.FunctionTestCase(lambda: None), "fixture failure"))
        with (
            patch.object(unittest, "TestLoader") as loader,
            patch.object(unittest, "TextTestRunner") as runner,
        ):
            loader.return_value.discover.return_value = suite
            runner.return_value.run.side_effect = (complete, failed)
            self.assertEqual(build.main(["controller-test"]), 0)
            loader.return_value.discover.assert_called_once_with(
                "tests", pattern="test_*.py", top_level_dir=str(build.REPO_ROOT),
            )
            runner.assert_called_once_with(verbosity=2)
            runner.return_value.run.assert_called_once_with(suite)
            self.assertEqual(build.main(["controller-test"]), 1)


class TargetAdmissionTest(unittest.TestCase):
    def test_unsupported_explicit_target_reports_usage_before_running_any_command(self):
        commands = (
            "doctor", "fetch", "build", "qualify", "package", "reproduce",
            "compare-reference", "assemble", "published-smoke", "check-budgets",
        )
        for command in commands:
            with (
                self.subTest(command=command),
                redirect_stdout(io.StringIO()) as stdout,
                redirect_stderr(io.StringIO()) as stderr,
            ):
                status = build.main([command, "--target", "aarch64-unknown-linux-musl"])
                self.assertEqual(status, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertTrue(stderr.getvalue().startswith(f"error: {command} --target: "))
                self.assertIn("target deferred, not implemented in this campaign: aarch64-unknown-linux-musl", stderr.getvalue())
                self.assertTrue(stderr.getvalue().endswith(f". See build.py {command} --help\n"))

    def test_assemble_rejects_unsupported_target_in_list_before_looking_up_revision(self):
        with (
            patch.object(build.release_assembler, "git_revision", side_effect=AssertionError("unexpected checkout access")),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(build.main(["assemble", "--target", "x86_64-unknown-linux-musl,unknown"]), 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("assemble --target: target not implemented: unknown", stderr.getvalue())

    def test_native_and_explicit_targets_keep_build_and_reproduce_arguments(self):
        binary = Path("/fixture/node")
        explicit = "x86_64-unknown-linux-musl"
        native = "aarch64-apple-darwin"
        with (
            patch.object(build, "native_target", return_value=build.target_for_triple(native)),
            patch.object(build.node, "build", return_value=binary) as compile_node,
            patch.object(reproduce, "reproduce", return_value={"verdict": "same"}) as rebuild,
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(build.main(["build"]), 0)
            self.assertEqual(build.main(["reproduce", "--target", explicit, "--jobs", "3"]), 0)
        compile_node.assert_called_once_with(build.REPO_ROOT, native, 10)
        rebuild.assert_called_once_with(build.REPO_ROOT, explicit, 3)
        self.assertEqual(stdout.getvalue(), "built: /fixture/node\nreproduce verdict: same\n")
        self.assertEqual(stderr.getvalue(), "")


class CommandContractTest(unittest.TestCase):
    def test_artifact_commands_report_each_backend_result_and_error(self):
        target = "aarch64-apple-darwin"
        fixture = Path("/fixture/node")
        root = build.REPO_ROOT
        cases = (
            ("fetch", build.node, "fetch_sources", [fixture], (root,),
             "cached: /fixture/node (verified)\n", build.node.BuildError),
            ("package", build.package, "package", {"archive": "/fixture/dist/node", "sha256": "hash"},
             (root, target, build.node.source_dir(root)), "archive: /fixture/dist/node\nsha256: hash\n",
             build.package.PackageError),
            ("qualify", build.qualify_runner, "qualify", {"archive": "/fixture/node", "smoke_passed": 2, "smoke_total": 3},
             (root, target), "qualified: /fixture/node\nsmoke: 2/3 passed\n",
             build.qualify_runner.QualifyError),
            ("assemble", build.release_assembler, "assemble_all",
             {"release_dir": "/fixture/release", "targets": [target], "assets": ["node.tar.xz", "SHA256SUMS"]},
             (root, (target,)), f"release: /fixture/release\ntargets: {target}\nassets: node.tar.xz, SHA256SUMS\n",
             build.release_assembler.AssemblyError),
            ("published-smoke", build.published_smoke_runner, "published_smoke", {"passed": 1, "total": 2},
             (root, target), "published smoke: 1/2 passed\n", build.published_smoke_runner.PublishedSmokeError),
            ("compare-reference", comparison, "compare", {"probes": {"tool": {"verdict": "same"}}},
             (root, target, "/fixture/reference"), "tool: same\n", comparison.CompareError),
            ("check-budgets", budgets, "check_budgets", {"compressed": 11, "payload": 19},
             (root, target), "budgets ok: compressed 11, payload 19\n", budgets.BudgetError),
        )
        for command, owner, action, result, arguments, output, error in cases:
            argv = [command, "--target", target]
            if command == "compare-reference":
                argv.extend(("--reference", "/fixture/reference"))
            with (
                self.subTest(command=command),
                patch.object(owner, action, return_value=result) as invoke,
                redirect_stdout(io.StringIO()) as stdout,
                redirect_stderr(io.StringIO()) as stderr,
            ):
                self.assertEqual(build.main(argv), 0)
                invoke.assert_called_once_with(*arguments)
                self.assertEqual(stdout.getvalue(), output)
                self.assertEqual(stderr.getvalue(), "")
                stdout.truncate(0)
                stdout.seek(0)
                invoke.side_effect = error("fixture unavailable")
                self.assertEqual(build.main(argv), 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(stderr.getvalue(), "error: fixture unavailable\n")

    def test_assembly_default_and_trimmed_targets(self):
        target = "aarch64-apple-darwin"
        linux = "x86_64-unknown-linux-musl"
        result = {"release_dir": "/fixture/release", "targets": [target, linux], "assets": []}
        with (
            patch.object(build.release_assembler, "assemble_all", return_value=result) as assemble,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(build.main(["assemble"]), 0)
            self.assertEqual(build.main(["assemble", "--target", f"  {linux}, ,{target} "]), 0)
            self.assertEqual(build.main(["assemble", "--target", ",  "]), 2)
        self.assertEqual(assemble.call_count, 2)
        self.assertEqual(assemble.call_args_list[0].args, (build.REPO_ROOT, (target, linux)))
        self.assertEqual(assemble.call_args_list[1].args, (build.REPO_ROOT, (linux, target)))
        self.assertEqual(stderr.getvalue(), "error: no --target given\n")
