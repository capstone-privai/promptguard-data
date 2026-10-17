"""The benchmark fingerprint: what the detection numbers depend on, and nothing that is display only."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import catalog, runner  # noqa: E402


class BenchmarkTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data_test = Path(tmp.name) / "data_test"
        answers = Path(tmp.name) / "data_answer"
        self.data_test.mkdir()
        answers.mkdir()
        for stem in ("sessions", "sessions_2"):  # both listed in catalog.DATASETS, in this order
            (self.data_test / f"{stem}.jsonl").write_text(f'{{"session_id": "{stem}"}}\n', encoding="utf-8")
            (answers / f"gold{stem[len('sessions'):]}.jsonl").write_text("", encoding="utf-8")

    def fingerprint(self) -> str:
        return runner.benchmark(runner.discover(self.data_test))["fingerprint"]

    def test_the_display_order_is_not_part_of_it(self):
        before = self.fingerprint()
        saved = list(catalog.DATASETS.items())
        self.addCleanup(lambda: (catalog.DATASETS.clear(), catalog.DATASETS.update(saved)))
        catalog.DATASETS.clear()
        catalog.DATASETS.update(reversed(saved))
        self.assertEqual([dataset.stem for dataset in runner.discover(self.data_test)], ["sessions_2", "sessions"])
        self.assertEqual(self.fingerprint(), before)

    def test_dataset_content_is(self):
        before = self.fingerprint()
        (self.data_test / "sessions_2.jsonl").write_text('{"session_id": "a longer session id"}\n', encoding="utf-8")
        self.assertNotEqual(self.fingerprint(), before)

    def test_parent_tests_directory_does_not_hide_scoring_code(self):
        fingerprints = []
        with tempfile.TemporaryDirectory() as tmp:
            for location in ("normal", "tests/nested"):
                with self.subTest(location=location):
                    root = Path(tmp) / location / "promptguard-data"
                    metric = root / "metric-detection"
                    scorer = metric / "evaluation/scorer.py"
                    test = metric / "evaluation/tests/test_scorer.py"
                    collector = root / "dashboard/pipeline/collect.py"
                    for path in (scorer, test, collector):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("# original\n")
                    with patch.object(runner, "METRIC_DETECTION", metric), \
                            patch.object(runner, "SCORING_CODE", [scorer, test, collector]):
                        before = runner.code_fingerprint()
                        fingerprints.append(before)
                        test.write_text("# only a test changed\n")
                        self.assertEqual(runner.code_fingerprint(), before)
                        scorer.write_text("# scorer changed\n")
                        changed = runner.code_fingerprint()
                        self.assertNotEqual(changed, before)
                        collector.write_text("# counting changed\n")
                        self.assertNotEqual(runner.code_fingerprint(), changed)
        self.assertEqual(fingerprints[0], fingerprints[1])


if __name__ == "__main__":
    unittest.main()
