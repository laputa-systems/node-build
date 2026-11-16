from pathlib import Path
from subprocess import CompletedProcess
from unittest import TestCase, mock

from buildsys import smoke


class HelpFooterTest(TestCase):
    def test_check_accepts_built_help_and_rejects_bad_output(self):
        def run(_node, args, _work):
            if args[0] in ("-h", "--help"):
                output = "Usage: node\n\n" + smoke.OWNED_FOOTER + "\n"
            elif args[0] == "--version":
                output = "v26.12.1\n"
            elif args[0] == "-p":
                output = '{"answer":42}\n'
            else:
                output = "completion script\n"
            return CompletedProcess(args, 0, output, "")

        path = Path(".")
        with mock.patch.object(smoke, "run_node", side_effect=run):
            smoke.check_help_footer(path, path, path)

        def bad_run(node, args, work):
            result = run(node, args, work)
            if args[0] == "--help":
                result.stdout += "extra\n"
            return result

        with mock.patch.object(smoke, "run_node", side_effect=bad_run), self.assertRaises(smoke.SmokeError):
            smoke.check_help_footer(path, path, path)
