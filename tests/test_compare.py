import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildsys import benchmarks


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


if __name__ == "__main__":
    unittest.main()
