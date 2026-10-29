"""A later shard failure must not discard completed work; changed inputs must not reuse it."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import runner


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.cache = self.root / "checkpoints"
        dataset = runner.Dataset("sessions", self.root / "s", self.root / "g", "sessions-sha", "gold-sha")
        self.shards = [runner.Shard(dataset, n, n + 1, 1) for n in range(2)]

    def work(self, name):
        root = self.root / name
        (root / "logs").mkdir(parents=True); (root / "shards").mkdir()
        return root

    def write_result(self, command):
        out = Path(command[command.index("--out") + 1])
        payload = {"sessions": 1, "cells": [], "items": [["g", "prompt", 1, 1, 1]], "picks": [], "sources": [],
                   "counts": {}, "system": {}, "lines_total": 1, "item_count": 1, "seconds": .1}
        runner.write_json(out, payload)

    def run_shards(self, shards, work, popen):
        progress = []
        with patch.object(runner.subprocess, "Popen", side_effect=popen), patch.object(runner.time, "sleep"):
            runner.run_shards(shards, self.root / "system", work, sys.executable, 1,
                              lambda done, total: progress.append((done, total)), lambda: False,
                              checkpoint_dir=self.cache)
        return progress

    def test_completed_shard_survives_a_later_failure_and_is_not_rerun(self):
        calls = []
        def first_attempt(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                self.write_result(command); return Mock(poll=Mock(return_value=0))
            return Mock(poll=Mock(return_value=2))
        with self.assertRaises(runner.EvaluationError):
            self.run_shards(self.shards, self.work("first"), first_attempt)
        self.assertTrue((self.cache / f"{self.shards[0].name}.json").exists())
        retried = []
        def retry(command, **kwargs):
            retried.append(command); self.write_result(command); return Mock(poll=Mock(return_value=0))
        progress = self.run_shards(self.shards, self.work("retry"), retry)
        self.assertEqual(len(retried), 1)
        self.assertEqual(retried[0][retried[0].index("--lines") + 1], "1:2")
        self.assertIn((1, 2), progress); self.assertEqual(progress[-1], (2, 2))

    def test_completed_cache_can_finish_without_starting_workers(self):
        def run(command, **kwargs):
            self.write_result(command); return Mock(poll=Mock(return_value=0))
        self.run_shards(self.shards, self.work("first"), run)
        progress = self.run_shards(self.shards, self.work("retry"), Mock(side_effect=AssertionError("unexpected worker")))
        self.assertEqual(progress[-1], (2, 2))

    def test_changed_dataset_hash_forces_recomputation(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command); self.write_result(command); return Mock(poll=Mock(return_value=0))
        self.run_shards(self.shards[:1], self.work("first"), run)
        changed = runner.Shard(replace(self.shards[0].dataset, sessions_sha256="new-data"), 0, 1, 1)
        self.run_shards([changed], self.work("changed"), run)
        self.assertEqual(len(calls), 2)
