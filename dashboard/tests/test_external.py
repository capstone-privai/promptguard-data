"""Registered runs expose progress/results, while keeping logs, models and private paths unserved."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.external import Evaluations
import serve


class ExternalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.result = self.root / "result"
        self.log = self.root / "run.log"
        self.log.write_text('{"event":"progress","done":5}\n')
        launch = self.root / "launch.json"
        launch.write_text(json.dumps({"result": str(self.result), "log": str(self.log), "pid": os.getpid(),
                                      "scored_items": 10, "sessions": 3, "jobs": 4, "started_at": "2026-10-28"}))
        (self.root / "evaluations.json").write_text(json.dumps({"default": "ml-test", "runs": [
            {"id": "ml-test", "label": "ML 표본", "launch": str(launch), "key": "a" * 16,
             "model": {"model_id": "v9"}, "commit": {"sha": "b" * 40, "short": "bbbbbbb"}}]}))
        self.provider = Evaluations(self.root)

    def complete(self, **fields):
        self.result.mkdir(exist_ok=True)
        summary = {"benchmark": {"second_stage": {"model_id": "v9"}}, "totals": {"f1": .8}, **fields}
        (self.result / "summary.json").write_text(json.dumps(summary))

    def key(self):
        return self.provider.snapshot("ml-test")["key"]

    def test_progress_counts_only_active_shards_on_top_of_completed_items(self):
        work = self.root / "result.work-1"; (work / "logs").mkdir(parents=True); (work / "shards").mkdir()
        (work / "logs/active.log").write_text('{"event":"ml_progress","requests_processed":2}\n')
        (work / "logs/done.log").write_text('{"event":"ml_progress","requests_processed":5}\n')
        (work / "shards/done.json").write_text('{}')
        view = self.provider.snapshot("ml-test")
        self.assertEqual(view["status"]["progress"], {"done": 7, "total": 10})
        self.assertEqual(view["index"]["commits"][0]["detection"]["state"], "running")
        self.assertNotIn("launch", json.dumps(view["index"]))

    def test_completed_output_becomes_the_existing_dashboard_summary(self):
        self.result.mkdir()
        (self.result / "summary.json").write_text(json.dumps({"benchmark": {"second_stage": {"model_id": "v9"}},
                                                             "totals": {"f1": .8}}))
        view = self.provider.snapshot("ml-test")
        self.assertEqual(view["status"]["progress"]["done"], 10)
        self.assertEqual(view["index"]["commits"][0]["detection"]["state"], "done")
        self.assertEqual(view["index"]["commits"][0]["detection"]["headline"]["f1"], .8)

    def test_only_registered_result_paths_are_served(self):
        self.complete()
        key = self.key()
        self.assertEqual(self.provider.file("ml-test", "results/detection/" + key + "/summary.json"),
                         self.result / "summary.json")
        for relative in ("run.log", "../launch.json", "results/detection/" + key + "/meta.json",
                         "results/detection/" + "b" * 16 + "/summary.json"):
            self.assertIsNone(self.provider.file("ml-test", relative))
        self.assertIsNone(self.provider.snapshot("missing"))
        self.assertIsNone(self.provider.run("../ml-test"))

    def test_result_symlink_cannot_expose_private_files(self):
        (self.result / "examples").mkdir(parents=True)
        self.complete()
        (self.result / "examples/private.json").symlink_to(self.root / "launch.json")
        self.assertIsNone(self.provider.file("ml-test", "results/detection/" + self.key() + "/examples/private.json"))

    def test_published_shard_is_counted_before_the_parent_logs_completion(self):
        self.log.write_text('{"event":"progress","done":0}\n')
        work = self.root / "result.work-current"; (work / "shards").mkdir(parents=True); (work / "logs").mkdir()
        (work / "shards/done.json").write_text('{"items":[["group","prompt",5,0,20]]}')
        (work / "logs/active.log").write_text('{"event":"ml_progress","requests_processed":2}\n')
        self.assertEqual(self.provider.snapshot("ml-test")["status"]["progress"]["done"], 7)

    def test_missing_or_non_object_log_rows_do_not_crash_status(self):
        self.log.write_text('null\n[]\n42\ninvalid\n{"event":"progress","done":3}\n')
        self.assertEqual(self.provider.snapshot("ml-test")["status"]["progress"]["done"], 3)
        self.log.unlink()
        self.assertEqual(self.provider.snapshot("ml-test")["status"]["state"], "evaluating")

    def test_previous_runs_work_and_results_are_not_counted_as_current(self):
        stale = self.root / "result.work-old"; (stale / "logs").mkdir(parents=True)
        (stale / "logs/active.log").write_text('{"event":"ml_progress","requests_processed":100}\n')
        os.utime(stale, (0, 0))
        self.complete(evaluated_at="2026-10-27T00:00:00+00:00")
        view = self.provider.snapshot("ml-test")
        self.assertEqual(view["index"]["commits"][0]["detection"]["state"], "running")
        self.assertEqual(view["status"]["progress"]["done"], 5)
        self.assertIsNone(self.provider.file("ml-test", f'results/detection/{view["key"]}/summary.json'))

    def test_rerun_gets_a_new_result_cache_key(self):
        before = self.key()
        path = self.root / "launch.json"; launch = json.loads(path.read_text())
        launch["started_at"] = "2026-10-28T01:00:00+00:00"; path.write_text(json.dumps(launch))
        self.assertNotEqual(self.key(), before)

    def test_reused_pid_is_not_mistaken_for_a_running_evaluation(self):
        path = self.root / "launch.json"; launch = json.loads(path.read_text())
        launch["pid_start_ticks"] = -1; path.write_text(json.dumps(launch))
        self.assertEqual(self.provider.snapshot("ml-test")["status"]["state"], "error")

    def add_latency(self, pid=None):
        self.latency = self.root / "latency"
        launch = self.root / "latency.launch.json"
        launch.write_text(json.dumps({"result": str(self.latency), "log": str(self.root / "latency.log"),
                                      "pid": pid or os.getpid(), "started_at": "2026-10-29"}))
        registry = json.loads((self.root / "evaluations.json").read_text())
        registry["runs"][0]["latency"] = {"launch": str(launch)}
        (self.root / "evaluations.json").write_text(json.dumps(registry))
        self.provider = Evaluations(self.root)

    def finish_latency(self, evaluated_at="2026-10-29T05:00:00+00:00"):
        self.latency.mkdir(exist_ok=True)
        detector = {"label": "ensemble", "single_1k": {"p50": 1800.0}, "single_64k": {"p50": 9000.0},
                    "fit_items": {"ms_per_string": 900.0}, "guard": None, "over_timeout": 3, "startup_ms": 3400.0}
        (self.latency / "latency.json").write_text(json.dumps({"evaluated_at": evaluated_at, "detectors": [detector]}))

    def test_without_registered_latency_only_detection_is_a_track(self):
        self.assertEqual(self.provider.snapshot("ml-test")["index"]["tracks"], ["detection"])

    def test_registered_latency_runs_after_detection_and_becomes_the_latency_track(self):
        self.add_latency()
        self.complete()
        view = self.provider.snapshot("ml-test")
        self.assertEqual(view["index"]["tracks"], ["detection", "latency"])
        self.assertEqual(view["index"]["commits"][0]["latency"]["state"], "running")
        self.assertEqual(view["status"]["state"], "evaluating")
        self.assertIn("지연", view["status"]["message"])
        key = view["index"]["commits"][0]["latency"]["key"]
        self.assertNotEqual(key, view["key"])
        self.assertIsNone(self.provider.file("ml-test", f"results/latency/{key}/latency.json"))
        self.finish_latency()
        view = self.provider.snapshot("ml-test")
        record = view["index"]["commits"][0]["latency"]
        self.assertEqual(record["state"], "done")
        self.assertEqual(record["headline"]["single_1k_p50"], 1800.0)
        self.assertEqual(view["status"]["state"], "idle")
        self.assertEqual(self.provider.file("ml-test", f"results/latency/{key}/latency.json"), self.latency / "latency.json")
        for relative in (f"results/latency/{key}/summary.json", f"results/latency/{key}/meta.json",
                         f"results/detection/{key}/latency.json", f"results/latency/{'c' * 16}/latency.json"):
            self.assertIsNone(self.provider.file("ml-test", relative))

    def test_latency_from_before_the_launch_or_a_dead_process_is_not_shown_as_done(self):
        self.add_latency(pid=2 ** 22 + 1)
        self.complete()
        self.finish_latency(evaluated_at="2026-10-28T00:00:00+00:00")
        view = self.provider.snapshot("ml-test")
        self.assertEqual(view["index"]["commits"][0]["latency"]["state"], "failed")
        self.assertEqual(view["status"]["state"], "error")

    def test_http_running_to_done_transition_and_new_routes_auth(self):
        class Quiet(serve.Handler):
            def log_request(self, *_args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, service=None, data_dir=self.root, auth="Basic test"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_address[1]}'
        def fetch(path, auth=True):
            request = urllib.request.Request(base + path, headers={"Authorization": "Basic test"} if auth else {})
            with urllib.request.urlopen(request) as response:
                return json.load(response)
        for path in ("/api/evaluations", "/api/status?evaluation=ml-test", "/data/evaluations/ml-test/index.json"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                fetch(path, False)
            self.assertEqual(caught.exception.code, 401); caught.exception.close()
        index = fetch("/data/evaluations/ml-test/index.json")
        self.assertEqual(index["commits"][0]["detection"]["state"], "running")
        self.complete()
        index = fetch("/data/evaluations/ml-test/index.json")
        self.assertEqual(index["commits"][0]["detection"]["state"], "done")
        self.assertEqual(fetch(f'/data/evaluations/ml-test/results/detection/{index["commits"][0]["detection"]["key"]}/summary.json')["totals"]["f1"], .8)
