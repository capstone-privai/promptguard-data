"""Job order and index states, with results faked on disk (nothing is evaluated)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import runner  # noqa: E402
from pipeline.repo import Commit  # noqa: E402
from pipeline.service import Config, Service, result_key  # noqa: E402


def commit(sha: str, fingerprint: str) -> Commit:
    return Commit(sha * 40, "2026-10-13T00:00:00+09:00", "t", f"subject {sha}", f"title {sha}", fingerprint * 64)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.service = Service(Config(data_dir=self.data, repo_url="https://u:secret@github.com/org/name.git"))
        self.commits = [commit("a", "1"), commit("b", "2"), commit("c", "2"), commit("d", "3")]
        self.plan = {"commits": self.commits, "bench": {"fingerprint": "bench2"}, "env": {"fingerprint": "env1"},
                     "contexts": {"detection": "bench2", "latency": "env1"}}

    def tearDown(self):
        self.tmp.cleanup()

    def fake_result(self, track, fingerprint, context, headline, evaluated_at="2026-10-17T00:00:00+00:00"):
        key = result_key(track, fingerprint * 64, context)
        runner.write_json(self.data / "results" / track / key / "meta.json",
                          {"system_fingerprint": fingerprint * 64, "evaluated_at": evaluated_at, "headline": headline})
        return key

    def test_newest_first_detection_before_latency_one_job_per_key(self):
        jobs = [(track, item.sha[0]) for track, item, _key in self.service.jobs(self.plan)]
        self.assertEqual(jobs, [("detection", "d"), ("latency", "d"), ("detection", "c"), ("latency", "c"),
                                ("detection", "a"), ("latency", "a")])  # b shares c's detector

    def test_done_failed_and_stale_results_leave_the_queue(self):
        self.fake_result("detection", "3", "bench2", {"precision": 0.5, "recall": 0.4, "f1": 0.44})
        self.fake_result("detection", "2", "bench1", {"precision": 0.3, "recall": 0.2, "f1": 0.24})  # older benchmark
        failed = result_key("latency", "3" * 64, "env1")
        self.service.failures[f"latency:{failed}"] = {"error": "boom", "at": "x", "commit": "d" * 40}
        jobs = [(track, item.sha[0]) for track, item, _key in self.service.jobs(self.plan)]
        self.assertNotIn(("detection", "d"), jobs)
        self.assertNotIn(("latency", "d"), jobs)
        self.assertIn(("detection", "c"), jobs)  # a stale result does not count as done

        self.service.write_index(self.plan, self.service.jobs(self.plan), running=("detection", result_key("detection", "2" * 64, "bench2")))
        index = json.loads((self.data / "index.json").read_text())
        by_sha = {entry["sha"][0]: entry for entry in index["commits"]}
        self.assertEqual(by_sha["d"]["detection"]["state"], "done")
        self.assertEqual(by_sha["d"]["detection"]["headline"]["precision"], 0.5)
        self.assertEqual(by_sha["d"]["latency"]["state"], "failed")
        self.assertEqual(by_sha["d"]["latency"]["error"], "boom")
        self.assertEqual(by_sha["c"]["detection"]["state"], "running")
        self.assertEqual(by_sha["b"]["detection"]["state"], "running")  # same key as c
        self.assertEqual(by_sha["c"]["detection"]["stale"]["headline"]["precision"], 0.3)
        self.assertEqual(by_sha["a"]["detection"]["state"], "queued")
        self.assertEqual(index["latest"], "d" * 40)
        self.assertEqual(index["catalog"]["datasets"]["sessions_from_CredData"]["label"], "CredData")
        self.assertNotIn("u:secret", json.dumps(index))  # credentials never reach the UI

    def test_changed_code_stops_before_planning(self):
        self.service.code = "the code this process started with"
        self.service.plan = lambda: self.fail("planned with code it does not run")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(self.service.cycle())
        self.assertTrue(self.service.code_changed)
        self.assertTrue(self.service.stopping.is_set())
        self.assertIn("changed on disk", out.getvalue())

    def test_retry_clears_failures(self):
        self.service.failures["detection:0000000000000000"] = {"error": "x", "at": "x", "commit": "x"}
        self.service.request_refresh(retry=True)
        self.assertTrue(self.service.retry)
        self.assertTrue(self.service.wake.is_set())


if __name__ == "__main__":
    unittest.main()
