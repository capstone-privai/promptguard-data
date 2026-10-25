"""UI requests select isolated evaluations and keep the shared gitleaks cache."""

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
from pipeline.service import Config, Service, ensemble_config, ensemble_key, result_key


class EnsembleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.service = Service(Config(data_dir=self.data, repo_url="unused", task=False, latency=False))
        self.commit = Commit("a" * 40, "2026-10-25", "tester", "test", "test", "b" * 64)
        self.plan = {"commits": [self.commit], "bench": {"fingerprint": "bench"}, "env": None,
                     "contexts": {"detection": "bench"}, "datasets": []}
        self.service.write_index(self.plan, self.service.jobs(self.plan), None)

    def request(self, detectors=None, consensus="any"):
        return self.service.request_ensemble(self.commit.sha, detectors or ["gitleaks"], consensus)

    def test_rejects_empty_unknown_duplicate_modules_and_invalid_votes(self):
        for detectors, policy in (([], "any"), (["unknown"], "any"), (["gitleaks", "gitleaks"], "any"),
                                  ([{}], "any"), ("gitleaks", "any"), (["gitleaks"], "other")):
            with self.subTest(detectors=detectors, policy=policy), self.assertRaises(ValueError):
                self.service.request_ensemble(self.commit.sha, detectors, policy)
        with self.assertRaises(ValueError):
            self.service.request_ensemble("not-a-commit", ["gitleaks"], "any")
        self.assertEqual(self.service.requested_ensembles(), [])

    def test_normalized_requests_persist_deduplicate_and_run_before_defaults(self):
        first = self.request(["gitleaks", "credsweeper"])
        second = self.request(["credsweeper", "gitleaks"])
        self.assertEqual(first, second)
        restarted = Service(self.service.config)
        self.assertEqual(len(restarted.requested_ensembles()), 1)
        track, commit, key = restarted.jobs(self.plan)[0]
        self.assertEqual((track, commit), ("detection", self.commit))
        self.assertEqual(key, ensemble_key(commit, "bench", ensemble_config(first["detectors"], "any")))
        self.assertNotEqual(key, result_key(track, commit.fingerprint, "bench"))
        self.assertNotEqual(key, ensemble_key(commit, "new-benchmark", ensemble_config(first["detectors"], "any")))

    def test_variant_states_retry_and_completed_result_reuse_are_isolated(self):
        requested = self.request()
        job = self.service.jobs(self.plan)[0]
        key = job[2]
        self.service.write_index(self.plan, [job], ("detection", key))
        record = self.service._read("index.json")["commits"][0]["ensembles"][0]
        self.assertEqual(record["state"], "running")
        self.service.failures = {f"detection:{key}": {"error": "missing adapter"}, "detection:other": {"error": "keep"}}
        self.service.write_index(self.plan, [], None)
        self.assertEqual(self.service._read("index.json")["commits"][0]["ensembles"][0]["state"], "failed")
        self.request()
        self.assertEqual(self.service.failures, {"detection:other": {"error": "keep"}})
        runner.write_json(self.service.result_dir("detection", key) / "meta.json", {
            "system_fingerprint": self.commit.fingerprint, "ensemble": {k: requested[k] for k in ("detectors", "consensus")},
            "evaluated_at": "2026-10-25", "headline": {"precision": 1, "recall": 1, "f1": 1},
        })
        self.assertNotIn(job, self.service.jobs(self.plan))
        self.assertEqual(self.service.latest_by_system("detection"), {})
        self.service.write_index(self.plan, [], None)
        entry = self.service._read("index.json")["commits"][0]
        self.assertEqual(entry["ensembles"][0]["state"], "done")
        self.assertNotIn("stale", entry["detection"])
        self.assertNotEqual(entry["detection"]["state"], "done")

    def test_job_passes_selection_and_existing_cache_to_the_runner(self):
        self.request(["credsweeper", "gitleaks"], "unanimous")
        job = self.service.jobs(self.plan)[0]
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value="python"), \
                patch("pipeline.service.runner.evaluate") as evaluate, patch.object(self.service, "alert") as alert, \
                contextlib.redirect_stdout(io.StringIO()):
            self.service.run_job(self.plan, *job, [job])
        self.assertEqual(evaluate.call_args.kwargs["ensemble"], {
            "detectors": ["credsweeper", "gitleaks"], "consensus": "unanimous"})
        self.assertEqual(evaluate.call_args.kwargs["gitleaks_cache"], self.data / "gitleaks-cache.sqlite")
        self.assertEqual(evaluate.call_args.args[2], self.service.result_dir("detection", job[2]))
        alert.assert_not_called()

    def test_shard_command_keeps_cache_and_selection(self):
        dataset = runner.Dataset("sessions", self.data / "sessions.jsonl", self.data / "gold.jsonl", "s", "g")
        (self.data / "logs").mkdir()
        process = Mock()
        process.poll.return_value = 0
        with patch.object(runner.subprocess, "Popen", return_value=process) as popen, patch.object(runner.time, "sleep"):
            runner.run_shards([runner.Shard(dataset, 0, 1, 1)], self.data / "system", self.data,
                              "python", 1, lambda *_: None, lambda: False,
                              gitleaks_cache=self.data / "gitleaks-cache.sqlite",
                              ensemble={"detectors": ["gitleaks"], "consensus": "any"})
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("--detectors") + 1], "gitleaks")
        self.assertEqual(args[args.index("--consensus") + 1], "any")
        self.assertEqual(args[args.index("--gitleaks-cache") + 1], str(self.data / "gitleaks-cache.sqlite"))

    def test_shard_uses_selected_adapters_and_writes_scored_output(self):
        from tests.test_collect import FIXTURES, ScriptedAdapter

        out = self.data / "shard.json"
        with patch.object(shard, "load_worker", return_value="worker"), \
                patch("evaluation.adapters.promptguard_adapter.PromptGuardAdapter", return_value=ScriptedAdapter()) as adapter:
            code = shard.main(["run", "--sessions", str(FIXTURES / "sessions.jsonl"),
                               "--gold", str(FIXTURES / "gold.jsonl"), "--lines", "0:1",
                               "--dataset", "sessions", "--system-root", "unused", "--out", str(out),
                               "--detectors", "credsweeper,gitleaks", "--consensus", "unanimous"])
        self.assertEqual(code, 0)
        adapter.assert_called_once_with("worker", detectors=["credsweeper", "gitleaks"], consensus="unanimous")
        result = json.loads(out.read_text())
        self.assertEqual(result["sessions"], 1)
        self.assertGreater(sum(result["counts"][key] for key in ("exact", "over", "partial", "missed")), 0)

    def test_http_request_validation_authentication_and_read_only_mode(self):
        class QuietHandler(serve.Handler):
            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, service=self.service,
                                                              data_dir=self.data, auth="Basic dGVhbTpwdw=="))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(body, *, auth=True, origin=None):
            headers = {"Content-Type": "application/json"}
            if auth:
                headers["Authorization"] = "Basic dGVhbTpwdw=="
            if origin:
                headers["Origin"] = origin
            request = urllib.request.Request(base + "/api/ensemble", data=body, headers=headers)
            try:
                with urllib.request.urlopen(request) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, error.read()

        payload = json.dumps({"sha": self.commit.sha, "detectors": ["gitleaks"], "consensus": "any"}).encode()
        self.assertEqual(post(payload, auth=False)[0], 401)
        self.assertEqual(post(payload, origin="https://other.example")[0], 403)
        for invalid in (b"{", b"[]", b"{}", b" " * 4097):
            self.assertEqual(post(invalid)[0], 400)
        status, config = post(payload)
        self.assertEqual(status, 202)
        self.assertEqual(config["detectors"], ["gitleaks"])
        server.RequestHandlerClass = partial(QuietHandler, service=None, data_dir=self.data, auth="Basic dGVhbTpwdw==")
        self.assertEqual(post(payload)[0], 409)


if __name__ == "__main__":
    unittest.main()
