import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import build
from buildsys import reproduce


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
