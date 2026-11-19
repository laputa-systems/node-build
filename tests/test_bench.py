import contextlib
import io
import unittest
from unittest.mock import patch

from buildsys import bench


class BenchSelectionTest(unittest.TestCase):
    def test_tier_and_exclusions(self):
        chosen, excluded = bench.select("edit", [], [], [])
        self.assertEqual([w.name for w in chosen], ["harness-tests"])
        self.assertEqual(excluded["compare-darwin"], "above tier ceiling")

    def test_names_and_areas_are_distinct_and_empty_selection_fails(self):
        for names, areas, skips in ((["size"], [], []), ([], ["harness-tests"], []), ([], [], ["missing"]), (["harness-tests"], ["size"], []), ([], [], ["harness-tests"])):
            with self.subTest(names=names, areas=areas, skips=skips), self.assertRaises(ValueError):
                bench.select("edit", names, areas, skips)

    def test_skip_is_visible(self):
        with patch.object(bench, "supported", return_value=True):
            chosen, excluded = bench.select("change", [], [], ["size-darwin"])
        self.assertNotIn("size-darwin", [w.name for w in chosen])
        self.assertEqual(excluded["size-darwin"], "skipped")

    def test_failed_preflight_runs_nothing(self):
        with patch.object(bench, "preflight", return_value=["missing requirement"]), patch.object(bench.platform, "platform", return_value="fixture"), patch.object(bench.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bench.main(["run", "--tier", "edit"]), 1)
        run.assert_not_called()

    def test_dry_run_does_not_preflight_or_write(self):
        with patch.object(bench, "preflight") as preflight, patch.object(bench.Path, "mkdir") as mkdir, patch.object(bench.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bench.main(["run", "--tier", "edit", "--dry-run"]), 0)
        preflight.assert_not_called()
        mkdir.assert_not_called()
        run.assert_not_called()
