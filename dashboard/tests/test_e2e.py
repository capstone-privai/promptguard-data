"""The dashboard evaluates only each commit's default system, including after an upgrade."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import serve
from pipeline import runner, shard
from pipeline.repo import Commit
from pipeline.service import Config, Service, result_key


class E2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.config = Config(data_dir=self.data, repo_url="unused", task=False, latency=False)
        self.service = Service(self.config)
        self.commit = Commit("a" * 40, "2026-10-25", "tester", "test", "test", "b" * 64)
        self.plan = {"commits": [self.commit], "bench": {"fingerprint": "bench"}, "env": None,
                     "contexts": {"detection": "bench"}, "datasets": []}

    def test_upgrade_ignores_saved_combination_requests_and_preserves_the_file(self):
        requests = {"old-request": {"sha": self.commit.sha, "id": "old", "detectors": ["unknown"],
                                    "consensus": "nested"}}
        runner.write_json(self.data / "ensemble_requests.json", requests)
        service = Service(self.config)
        jobs = service.jobs(self.plan)
        self.assertEqual(jobs, [("detection", self.commit, result_key("detection", self.commit.fingerprint, "bench"))])
        service.write_index(self.plan, jobs, None)
        entry = service._read("index.json")["commits"][0]
        self.assertNotIn("ensembles", entry)
        self.assertNotIn("default_ensemble", entry)
        self.assertNotIn("ensemble_requests", service.snapshot())
        self.assertNotIn("ensemble_writable", service.snapshot())
        self.assertEqual(service._read("ensemble_requests.json"), requests)

    def test_old_combination_results_never_become_default_or_stale_results(self):
        key = "c" * 16
        runner.write_json(self.service.result_dir("detection", key) / "meta.json", {
            "system_fingerprint": self.commit.fingerprint, "ensemble": {"detectors": ["gitleaks"], "consensus": "any"},
            "evaluated_at": "2026-10-25", "headline": {"f1": 1},
        })
        self.assertEqual(self.service.latest_by_system("detection"), {})
        self.service.write_index(self.plan, self.service.jobs(self.plan), None)
        record = self.service._read("index.json")["commits"][0]["detection"]
        self.assertEqual(record["state"], "queued")
        self.assertNotEqual(record["key"], key)
        self.assertNotIn("stale", record)

    def test_default_job_uses_existing_cache_without_configuration_overrides(self):
        job = self.service.jobs(self.plan)[0]
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.runner.evaluate") as evaluate, contextlib.redirect_stdout(io.StringIO()):
            self.service.run_job(self.plan, *job, [job])
        self.assertNotIn("ensemble", evaluate.call_args.kwargs)
        self.assertEqual(evaluate.call_args.kwargs["gitleaks_cache"], self.data / "gitleaks-cache.sqlite")
        self.assertEqual(evaluate.call_args.args[2], self.service.result_dir("detection", job[2]))

    def test_latency_planning_and_execution_use_the_whole_system(self):
        self.service.config.latency = True
        with patch("pipeline.service.repo.sync"), patch("pipeline.service.repo.commits", return_value=[self.commit]), \
                patch("pipeline.service.runner.discover", return_value=["dataset"]), \
                patch("pipeline.service.runner.benchmark", return_value=self.plan["bench"]), \
                patch("pipeline.service.latency.environment", return_value={"fingerprint": "env"}) as environment:
            plan = self.service.plan()
        self.assertEqual(environment.call_args.args[0], "ensemble")
        job = next(job for job in self.service.jobs(plan) if job[0] == "latency")
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.latency.evaluate") as evaluate, contextlib.redirect_stdout(io.StringIO()):
            self.service.run_job(plan, *job, [job])
        self.assertEqual(evaluate.call_args.kwargs["adapters"], "ensemble")

    def test_shard_command_keeps_cache_without_module_or_consensus_overrides(self):
        dataset = runner.Dataset("sessions", self.data / "sessions.jsonl", self.data / "gold.jsonl", "s", "g")
        (self.data / "logs").mkdir()
        process = Mock()
        process.poll.return_value = 0
        with patch.object(runner.subprocess, "Popen", return_value=process) as popen, patch.object(runner.time, "sleep"):
            runner.run_shards([runner.Shard(dataset, 0, 1, 1)], self.data / "system", self.data,
                              "python", 1, lambda *_: None, lambda: False,
                              gitleaks_cache=self.data / "gitleaks-cache.sqlite")
        args = popen.call_args.args[0]
        self.assertNotIn("--detectors", args)
        self.assertNotIn("--consensus", args)
        self.assertEqual(args[args.index("--gitleaks-cache") + 1], str(self.data / "gitleaks-cache.sqlite"))

    def test_shard_scores_default_system_output(self):
        from tests.test_collect import FIXTURES, ScriptedAdapter

        out = self.data / "shard.json"
        with patch.object(shard, "load_worker", return_value="worker"), \
                patch("evaluation.adapters.promptguard_adapter.PromptGuardAdapter", return_value=ScriptedAdapter()) as adapter:
            code = shard.main(["run", "--sessions", str(FIXTURES / "sessions.jsonl"),
                               "--gold", str(FIXTURES / "gold.jsonl"), "--lines", "0:1",
                               "--dataset", "sessions", "--system-root", "unused", "--out", str(out)])
        self.assertEqual(code, 0)
        adapter.assert_called_once_with("worker")
        result = json.loads(out.read_text())
        self.assertEqual(result["sessions"], 1)
        self.assertGreater(sum(result["counts"][key] for key in ("exact", "over", "partial", "missed")), 0)

    def test_removed_ensemble_api_does_not_queue_jobs_on_live_or_read_only_servers(self):
        class QuietHandler(serve.Handler):
            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, service=self.service,
                                                              data_dir=self.data, auth="Basic dGVhbTpwdw=="))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/api/ensemble"

        def post(auth):
            request = urllib.request.Request(url, data=b"{}", headers={"Authorization": auth})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            code = caught.exception.code
            caught.exception.close()
            return code

        self.assertEqual(post(""), 401)
        self.assertEqual(post("Basic dGVhbTpwdw=="), 404)
        server.RequestHandlerClass = partial(QuietHandler, service=None, data_dir=self.data, auth="Basic dGVhbTpwdw==")
        self.assertEqual(post("Basic dGVhbTpwdw=="), 404)
        self.assertFalse((self.data / "ensemble_requests.json").exists())


if __name__ == "__main__":
    unittest.main()
