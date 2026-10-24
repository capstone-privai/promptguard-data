"""The benchmark fingerprint: what the detection numbers depend on, and nothing that is display only."""

from __future__ import annotations

import sys
import json
import shutil
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

    def test_changed_input_is_discarded_and_can_be_planned_again(self):
        datasets = runner.discover(self.data_test)
        bench = runner.benchmark(datasets)
        datasets[0].sessions.write_text('{"session_id":"changed"}\n')
        with self.assertRaises(runner.InputsChanged):
            runner.snapshot_inputs(datasets, self.data_test.parent / "snapshot", bench)
        current = runner.discover(self.data_test)
        runner.snapshot_inputs(current, self.data_test.parent / "retry", runner.benchmark(current))

    def test_snapshot_pins_data_and_scoring_code(self):
        datasets = runner.discover(self.data_test)
        bench = runner.benchmark(datasets)
        pinned, script = runner.snapshot_inputs(datasets, self.data_test.parent / "snapshot", bench)
        self.assertNotEqual(script, runner.SHARD_SCRIPT)
        self.assertEqual(script.read_bytes(), runner.SHARD_SCRIPT.read_bytes())
        for source, copy in zip(datasets, pinned):
            expected = source.sessions.read_bytes()
            source.sessions.write_text("changed after snapshot\n")
            self.assertEqual(copy.sessions.read_bytes(), expected)
            self.assertEqual(runner.file_sha256(copy.sessions), copy.sessions_sha256)
            self.assertEqual(runner.file_sha256(copy.gold), copy.gold_sha256)

    def test_snapshot_rejects_mismatched_scoring_code(self):
        datasets = runner.discover(self.data_test)
        bench = {**runner.benchmark(datasets), "code": "another scorer"}
        with self.assertRaises(runner.InputsChanged):
            runner.snapshot_inputs(datasets, self.data_test.parent / "snapshot", bench)

    def test_code_changed_while_copying_is_discarded(self):
        datasets = runner.discover(self.data_test)
        bench = runner.benchmark(datasets)
        copytree = shutil.copytree

        def changed_copy(source, target, *args, **kwargs):
            result = copytree(source, target, *args, **kwargs)
            if Path(source) == runner.DASHBOARD_ROOT / "pipeline":
                (Path(target) / "collect.py").write_text("# a newer collector\n")
            return result

        with patch.object(shutil, "copytree", side_effect=changed_copy):
            with self.assertRaises(runner.InputsChanged):
                runner.snapshot_inputs(datasets, self.data_test.parent / "snapshot", bench)


class EvaluateSnapshotTest(unittest.TestCase):
    def test_changes_during_validation_do_not_change_shard_inputs_or_metadata(self):
        from tests.test_collect import FIXTURES, ScriptedAdapter, payload_for
        from pipeline.shard import load_range

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data_test"
            answers = root / "data_answer"
            data.mkdir()
            answers.mkdir()
            shutil.copyfile(FIXTURES / "sessions.jsonl", data / "sessions.jsonl")
            shutil.copyfile(FIXTURES / "gold.jsonl", answers / "gold.jsonl")
            datasets = runner.discover(data)
            bench = runner.benchmark(datasets)
            original = datasets[0].sessions.read_bytes()
            validate = runner.validate

            def change_after_validation(*args, **kwargs):
                weights = validate(*args, **kwargs)
                datasets[0].sessions.write_text("changed while shards run\n")
                datasets[0].gold.write_text("changed gold\n")
                return weights

            def fake_shards(shards, system_root, work_dir, python, jobs, progress, cancelled, *, shard_script,
                            gitleaks_cache):
                self.assertNotEqual(shard_script, runner.SHARD_SCRIPT)
                for shard in shards:
                    self.assertEqual(shard.dataset.sessions.read_bytes(), original)
                    sessions = load_range(shard.dataset.sessions, shard.dataset.gold, shard.low, shard.high)
                    payload, metrics = payload_for(sessions, ScriptedAdapter(), shard.dataset.stem)
                    payload.update(sessions=len(sessions), item_count=metrics["items"], seconds=0, system={})
                    runner.write_json(work_dir / "shards" / f"{shard.name}.json", payload)

            out = root / "result"
            with patch.object(runner, "validate", side_effect=change_after_validation), \
                    patch.object(runner, "run_shards", side_effect=fake_shards):
                runner.evaluate(root / "system", datasets, out, python=sys.executable, jobs=2,
                                cache_dir=root / "validated", commit={"sha": "test"},
                                system_fingerprint="system", bench=bench)
            summary = json.loads((out / "summary.json").read_text())
            meta = json.loads((out / "meta.json").read_text())
            self.assertEqual(summary["datasets"][0]["sessions_sha256"], datasets[0].sessions_sha256)
            self.assertEqual(meta["benchmark_fingerprint"], bench["fingerprint"])
            self.assertFalse(out.with_name("result.work").exists())


if __name__ == "__main__":
    unittest.main()
