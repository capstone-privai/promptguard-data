"""Job order and index states, with results faked on disk (nothing is evaluated)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import runner  # noqa: E402
from pipeline.repo import Commit  # noqa: E402
from pipeline.service import Config, DataDirBusy, Service, result_key  # noqa: E402


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

    def test_only_clean_batches_are_attributed_to_a_commit(self):
        self.plan["task_batches"] = [
            {"key": label, "system_commit": self.commits[-1].sha, "provenance": label}
            for label in ("clean", "dirty", "unknown")]
        self.service.write_index(self.plan, [], running=None)
        index = json.loads((self.data / "index.json").read_text())
        self.assertEqual(index["commits"][-1]["task"], ["clean"])
        self.assertEqual(len(index["task_batches"]), 3)

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

    def test_changed_inputs_are_not_saved_as_permanent_job_failures(self):
        self.plan["datasets"] = []
        job = self.service.jobs(self.plan)[0]
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.runner.evaluate", side_effect=runner.InputsChanged("data changed")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.service.run_job(self.plan, *job, [job])
        self.assertEqual(self.service.failures, {})
        self.assertIn(job, self.service.jobs(self.plan))
        self.assertFalse(self.service.stopping.is_set())

    def test_commits_merged_during_a_job_are_queued(self):
        self.plan["datasets"] = []
        job = self.service.jobs(self.plan)[0]
        merged = commit("e", "4")
        self.service.poll_seconds = 0.01

        def evaluate(*_args, **_kwargs):  # the job runs until the watcher has indexed the new commit
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if merged.sha in json.dumps(self.service._read("index.json")):
                    return
                time.sleep(0.01)
            raise AssertionError("the merged commit never reached index.json")

        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.repo.sync"), \
                patch("pipeline.service.repo.commits", return_value=[*self.commits, merged]), \
                patch("pipeline.service.runner.evaluate", side_effect=evaluate), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.service.run_job(self.plan, *job, [job])
        self.assertEqual(self.service.failures, {})
        index = json.loads((self.data / "index.json").read_text())
        by_sha = {entry["sha"][0]: entry for entry in index["commits"]}
        self.assertEqual(by_sha["d"]["detection"]["state"], "running")
        self.assertEqual(by_sha["e"]["detection"]["state"], "queued")
        self.assertIn("last_sync", index["status"])
        self.assertIn("eeeeeee queued", out.getvalue())
        self.assertEqual(self.service.jobs(self.plan)[0][1], merged)  # the next cycle starts the newest commit

    def test_a_failed_fetch_during_a_job_does_not_fail_the_job(self):
        self.plan["datasets"] = []
        job = self.service.jobs(self.plan)[0]
        self.service.poll_seconds = 0.01
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.repo.sync", side_effect=RuntimeError("network down")), \
                patch("pipeline.service.runner.evaluate", side_effect=lambda *_a, **_k: time.sleep(0.1)), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.service.run_job(self.plan, *job, [job])
        self.assertEqual(self.service.failures, {})
        self.assertIn("fetch during the running job failed: network down", out.getvalue())
        self.assertIn("done in", out.getvalue())

    def test_timeout_changes_only_the_latency_key_and_queue(self):
        self.plan["commits"] = [commit("a", "1"), replace(commit("b", "1"), timeout_ms=3000),
                                replace(commit("c", "1"), timeout_ms=3000)]
        self.fake_result("latency", "1", "env1", {"over_timeout": 0})
        jobs = self.service.jobs(self.plan)
        self.assertEqual([(track, item.sha[0]) for track, item, _key in jobs],
                         [("detection", "c"), ("latency", "c")])
        self.service.write_index(self.plan, jobs, running=None)
        entries = json.loads((self.data / "index.json").read_text())["commits"]
        before, after, same = entries
        self.assertEqual(before["detection"]["key"], after["detection"]["key"])
        self.assertNotEqual(before["latency"]["key"], after["latency"]["key"])
        self.assertEqual(after["latency"]["key"], same["latency"]["key"])
        self.assertEqual(before["latency"]["state"], "done")
        self.assertEqual(after["latency"]["state"], "queued")
        self.assertEqual(after["latency"]["key"], jobs[-1][2])

    def holder(self) -> Service:
        """Another evaluator holding the data directory (here: the same process, another open lock file)."""
        other = Service(Config(data_dir=self.data, repo_url="unused"))
        self.addCleanup(other.release)
        self.addCleanup(self.service.release)
        self.assertTrue(other.acquire())
        return other

    def test_one_evaluator_per_data_directory(self):
        other = self.holder()
        self.service.plan = lambda: self.fail("planned while another process evaluates here")
        with self.assertRaises(DataDirBusy) as caught:
            self.service.cycle()
        self.assertEqual(caught.exception.holder, str(os.getpid()))
        other.failures["detection:0000000000000000"] = {"error": "x", "at": "x", "commit": "x"}
        other._save_failures()
        other.release()
        self.assertTrue(self.service.acquire())
        self.assertIn("detection:0000000000000000", self.service.failures)  # what the other process recorded

    def test_the_server_keeps_serving_and_waits(self):
        self.holder()
        self.service.wake.wait = lambda timeout: self.service.stopping.set()  # one round of the loop
        with contextlib.redirect_stdout(io.StringIO()):
            self.service.run_forever(600)
        status = self.service.snapshot()
        self.assertEqual(status["state"], "waiting")
        self.assertIn(str(os.getpid()), status["message"])

    def test_once_releases_the_directory_when_finished(self):
        other = self.holder()
        other.release()
        self.plan["commits"] = []
        self.service.plan = lambda: self.plan
        self.service.run_until_done()
        self.assertTrue(other.acquire())

    def test_once_releases_the_directory_after_an_error(self):
        other = self.holder()
        other.release()

        def fail_plan():
            raise RuntimeError("planning failed")

        self.service.plan = fail_plan
        with self.assertRaisesRegex(RuntimeError, "planning failed"):
            self.service.run_until_done()
        self.assertTrue(other.acquire())

    def test_the_server_releases_the_directory_after_stopping(self):
        other = self.holder()
        other.release()
        self.plan["commits"] = []
        self.service.plan = lambda: self.plan
        self.service.wake.wait = lambda timeout: self.service.stop()
        self.service.run_forever(600)
        self.assertTrue(other.acquire())

    def test_retry_clears_failures(self):
        self.service.failures["detection:0000000000000000"] = {"error": "x", "at": "x", "commit": "x"}
        self.service.request_refresh(retry=True)
        self.assertTrue(self.service.retry)
        self.assertTrue(self.service.wake.is_set())

    def alerts_of(self, action):
        with patch("pipeline.service.notify.send") as send, contextlib.redirect_stdout(io.StringIO()):
            action()
        return [call.args[1] for call in send.call_args_list]

    def run_job_alerts(self, evaluate):
        self.plan["datasets"] = []
        job = self.service.jobs(self.plan)[0]
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.runner.evaluate", side_effect=evaluate):
            return self.alerts_of(lambda: self.service.run_job(self.plan, *job, [job, job]))

    def test_a_failed_job_alerts_its_start_and_the_failure(self):
        self.service.config.notify_url = "https://discord.test/hook"
        alerts = self.run_job_alerts(RuntimeError("shard 3 exited 1"))
        self.assertEqual(len(alerts), 2)  # latency of d is still to run: no report yet
        self.assertEqual(alerts[0], "▶️ 탐지 성능 평가 시작 · ddddddd title d\n뒤에 1개 대기")
        self.assertIn("탐지 성능 평가 실패 · ddddddd title d", alerts[1])
        self.assertIn("shard 3 exited 1", alerts[1])

    def test_no_webhook_no_alert(self):
        self.assertEqual(self.run_job_alerts(RuntimeError("boom")), [])

    def test_a_job_running_too_long_alerts_once(self):
        self.service.config.notify_url = "https://discord.test/hook"
        self.service.config.overdue_hours = 0.01 / 3600
        alerts = self.run_job_alerts(lambda *_a, **_k: time.sleep(0.2))
        self.assertEqual(len(alerts), 2)
        self.assertIn("탐지 성능 평가가", alerts[1])
        self.assertIn("ddddddd", alerts[1])

    def test_a_commit_is_reported_once_every_track_is_done(self):
        self.service.config.notify_url = "https://discord.test/hook"
        self.fake_result("detection", "2", "bench2", {"precision": 0.9, "recall": 0.8, "f1": 0.847})
        self.fake_result("latency", "3", "env1", {"single_1k_p50": 12.34, "single_64k_p50": 340.6,
                                                  "ms_per_string": 0.812, "over_timeout": 0})
        alerts = self.run_job_alerts(lambda *_a, **_k: self.fake_result(
            "detection", "3", "bench2", {"precision": 0.912, "recall": 0.834, "f1": 0.871}))
        self.assertEqual(alerts[-1], "✅ 평가 완료 · ddddddd title d\n"
                                     "탐지 성능: Precision 91.2% · Recall 83.4% · F1 87.1%\n"
                                     "  이전 탐지기 변경(ccccccc) 대비: P +1.2%p · R +3.4%p · F1 +2.4%p\n"
                                     "탐지 지연: 1KB 12ms · 64KB 341ms (p50) · 문자열당 +0.81ms · timeout 초과 0회")

    def test_a_commit_with_a_failed_track_is_reported_as_such(self):
        self.service.config.notify_url = "https://discord.test/hook"
        failed = result_key("latency", "3" * 64, "env1")
        self.service.failures[f"latency:{failed}"] = {"error": "boom", "at": "x", "commit": "d" * 40}
        alerts = self.run_job_alerts(lambda *_a, **_k: self.fake_result(
            "detection", "3", "bench2", {"precision": 0.5, "recall": None, "f1": None}))
        self.assertEqual(alerts[-1], "⚠️ 평가 끝 (일부 실패) · ddddddd title d\n"
                                     "탐지 성능: Precision 50.0% · Recall — · F1 —\n"
                                     "탐지 지연: 실패")

    def test_new_commits_are_announced_once(self):
        self.service.config.notify_url = "https://discord.test/hook"
        self.assertEqual(self.alerts_of(lambda: self.service.announce(self.plan)), [])  # a new data directory
        self.fake_result("detection", "3", "bench2", {})
        self.fake_result("latency", "3", "env1", {})
        self.plan["commits"] = [*self.commits, commit("e", "4"), commit("f", "3")]
        alerts = self.alerts_of(lambda: self.service.announce(self.plan))
        self.assertEqual(alerts, ["🆕 main에 새 커밋 2개\n"
                                  "• eeeeeee title e · 평가 대기 (탐지 성능, 탐지 지연)\n"
                                  "• fffffff title f · 탐지기가 같아 이전 결과를 씀"])
        self.assertEqual(self.alerts_of(lambda: self.service.announce(self.plan)), [])

    def test_a_restarted_service_announces_what_was_merged_meanwhile(self):
        self.service.write_index(self.plan, [], running=None)
        restarted = Service(Config(data_dir=self.data, repo_url="x", notify_url="https://discord.test/hook"))
        self.plan["commits"] = [*self.commits, commit("e", "4")]
        alerts = self.alerts_of(lambda: restarted.announce(self.plan))
        self.assertEqual(len(alerts), 1)
        self.assertIn("새 커밋 1개\n• eeeeeee", alerts[0])

    def test_an_outage_alerts_once_and_again_on_recovery(self):
        self.service.config.notify_url = "https://discord.test/hook"
        self.plan["commits"] = []
        outcomes = iter([RuntimeError("fetch failed"), RuntimeError("fetch failed"), None, None])

        def plan():
            outcome = next(outcomes)
            if outcome:
                raise outcome
            return self.plan

        rounds = iter(range(3))
        self.service.plan = plan
        self.service.wake.wait = lambda timeout: next(rounds, None) is None and self.service.stop()
        with patch("pipeline.service.notify.send") as send, contextlib.redirect_stdout(io.StringIO()):
            self.service.run_forever(600)
        alerts = [call.args[1] for call in send.call_args_list]
        self.assertEqual(len(alerts), 2)
        self.assertIn("평가 서비스 오류: fetch failed", alerts[0])
        self.assertIn("평가 서비스 복구", alerts[1])


if __name__ == "__main__":
    unittest.main()
