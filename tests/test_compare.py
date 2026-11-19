import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import build
from buildsys import benchmarks, comparison, node


class VerdictTest(unittest.TestCase):
    def test_clear_win_is_faster(self):
        baseline = benchmarks.Samples("reference", (100.0, 101.0, 100.5, 99.5, 100.2))
        candidate = benchmarks.Samples("candidate", (80.0, 81.0, 80.5, 79.5, 80.2))
        self.assertEqual(benchmarks.verdict(baseline, candidate), "faster")

    def test_clear_loss_is_slower(self):
        baseline = benchmarks.Samples("reference", (80.0, 81.0, 80.5, 79.5, 80.2))
        candidate = benchmarks.Samples("candidate", (100.0, 101.0, 100.5, 99.5, 100.2))
        self.assertEqual(benchmarks.verdict(baseline, candidate), "slower")

    def test_overlap_is_no_measurable_difference(self):
        baseline = benchmarks.Samples("reference", (100.0, 110.0, 105.0, 95.0, 102.0))
        candidate = benchmarks.Samples("candidate", (101.0, 109.0, 104.0, 96.0, 103.0))
        self.assertEqual(benchmarks.verdict(baseline, candidate), "no-measurable-difference")

    def test_empty_is_inconclusive(self):
        self.assertEqual(
            benchmarks.verdict(benchmarks.Samples("a", ()), benchmarks.Samples("b", (1.0,))),
            "inconclusive",
        )

    def test_median_and_spread(self):
        samples = benchmarks.Samples("x", (3.0, 1.0, 2.0))
        self.assertEqual(samples.median(), 2.0)
        self.assertEqual(samples.spread(), 2.0)

    def test_record_json_roundtrips(self):
        path = REPO_ROOT / ".work" / "tmp" / "record.json"
        record = {"verdict": "faster"}
        benchmarks.record_json(record, path)
        try:
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
        finally:
            path.unlink(missing_ok=True)


class ComparisonTest(unittest.TestCase):
    triple = "aarch64-apple-darwin"

    def setUp(self):
        scratch = REPO_ROOT / ".work" / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.candidate = node.source_dir(self.root) / "out" / "Release" / "node"
        self.candidate.parent.mkdir(parents=True)
        self.reference = self.root / "reference-node"
        for binary in (self.candidate, self.reference):
            binary.write_text("#!/bin/sh\nprintf '%s\\n' v26.12.1\n")
            binary.chmod(0o700)

    def test_version_spawn_failure_reports_the_reference_at_the_cli(self):
        self.reference.chmod(0o600)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(build, "REPO_ROOT", self.root), redirect_stdout(stdout), redirect_stderr(stderr):
            code = build.main(["compare-reference", "--target", self.triple, "--reference", str(self.reference)])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(f"{self.reference} --version could not run", stderr.getvalue())
        self.assertFalse((self.root / "build" / self.triple / "compare-work" / "compare-record.json").exists())

    def test_version_timeout_reports_the_binary(self):
        error = subprocess.TimeoutExpired([str(self.reference), "--version"], 60)
        with (
            patch.object(comparison.subprocess, "run", side_effect=error) as run,
            self.assertRaises(comparison.CompareError) as failure,
        ):
            comparison.binary_version(self.reference, self.root)
        self.assertEqual(str(failure.exception), f"{self.reference} --version timed out")
        run.assert_called_once()
        self.assertEqual(run.call_args.args, ([str(self.reference), "--version"],))
        self.assertEqual(run.call_args.kwargs["cwd"], self.root)
        self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_version_probe_reports_a_nonzero_exit(self):
        self.reference.write_text("#!/bin/sh\nexit 7\n")
        with self.assertRaises(comparison.CompareError) as failure:
            comparison.binary_version(self.reference, self.root)
        self.assertEqual(str(failure.exception), f"{self.reference} --version failed")

    def test_reference_resolution_uses_the_explicit_path_or_path_lookup(self):
        missing = self.root / "missing-node"
        with self.assertRaises(comparison.CompareError) as failure:
            comparison.resolve_reference(str(missing))
        self.assertEqual(str(failure.exception), f"reference binary not found: {missing}")

        with patch.dict(os.environ, {"PATH": str(self.root)}):
            with self.assertRaises(comparison.CompareError) as failure:
                comparison.resolve_reference(None)
            self.assertEqual(str(failure.exception), "no reference node on PATH; pass --reference")
            found = self.root / "node"
            found.symlink_to(self.reference)
            self.assertEqual(comparison.resolve_reference(None), found)
            self.assertEqual(comparison.resolve_reference(str(self.reference)), self.reference)

    def test_mismatched_versions_stop_before_sampling(self):
        self.reference.write_text("#!/bin/sh\nprintf '%s\\n' v25.0.0\n")
        with (
            patch.object(benchmarks, "time_process") as startup,
            self.assertRaises(comparison.CompareError) as failure,
        ):
            comparison.compare(self.root, self.triple, str(self.reference))
        startup.assert_not_called()
        self.assertEqual(str(failure.exception), "version mismatch: candidate v26.12.1 vs reference v25.0.0")

    def test_comparison_preserves_sample_sides_in_the_written_report(self):
        with (
            patch.object(benchmarks, "time_process", side_effect=[10.0, 5.0] * 5) as startup,
            patch.object(benchmarks, "time_probe", side_effect=[20.0, 30.0] * 5) as json_probe,
            patch.object(comparison.platform, "machine", return_value="fixture-architecture"),
            patch.object(comparison.platform, "processor", return_value="fixture-processor"),
        ):
            record = comparison.compare(self.root, self.triple, str(self.reference))
        expected_order = [self.reference, self.candidate] * 5
        work = self.root / "build" / self.triple / "compare-work"
        self.assertEqual(
            startup.call_args_list,
            [call(binary, ["-e", benchmarks.STARTUP_PROBE], work) for binary in expected_order],
        )
        self.assertEqual(
            json_probe.call_args_list,
            [call(binary, benchmarks.JSON_PROBE, work) for binary in expected_order],
        )
        self.assertEqual(set(record), {"node_version", "machine", "cpu", "toolchain", "probes", "limiter_note"})
        self.assertEqual(record["node_version"], "v26.12.1")
        self.assertEqual(record["machine"], "fixture-architecture")
        self.assertEqual(record["cpu"], "fixture-processor")
        self.assertEqual(record["toolchain"], "as recorded in build-receipt.json")
        self.assertIn("host-shared timing", record["limiter_note"])
        self.assertIn("no-measurable-difference", record["limiter_note"])
        self.assertEqual(record["probes"], {
            "startup": {"reference_ms": [10.0] * 5, "candidate_ms": [5.0] * 5, "verdict": "faster"},
            "json": {"reference_ms": [20.0] * 5, "candidate_ms": [30.0] * 5, "verdict": "slower"},
        })
        report = work / "compare-record.json"
        self.assertEqual(json.loads(report.read_text()), record)


if __name__ == "__main__":
    unittest.main()
