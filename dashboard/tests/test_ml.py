"""Offline integration coverage for candidate decisions, model IPC, latency and job identities."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import latency, ml, runner, shard
from pipeline.ml_worker import make_handler
from pipeline.repo import Commit
from pipeline.service import Config, Service, result_key
from evaluation.adapters.two_stage_adapter import TwoStageAdapter
from evaluation.dataset.schema import Item, Session
from evaluation.run import ScoringError


INFERENCE = '''import json, sys, time
for line in sys.stdin:
    request = json.loads(line)
    time.sleep(0.025)
    response = {"version": 1, "request_id": request["request_id"], "decisions": [
        {"id": c["id"], "label": "KEEP" if request["text"][c["start"]:c["end"]] == "public" else "MASK"}
        for c in reversed(request["candidates"])]}
    print(json.dumps(response), flush=True)
'''


class Detector:
    def scan(self, text, source):
        findings = []
        for value in ("secret", "public"):
            if value not in text:
                continue
            start = len(text[:text.index(value)].encode("utf-16-le")) // 2
            findings.append({"start": start, "end": start + len(value), "offset_unit": "utf16_code_units",
                             "type": "PASSWORD", "value_hash": value, "rule_id": "test-rule"})
        return {"ok": True, "findings": findings, "errors": []}

    def describe(self):
        return {"adapters": [{"name": "fixture", "version": "1"}], "consensus": "any"}


WORKER = SimpleNamespace(load_detector=Detector)


class ModelTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.script = self.bundle / "infer.py"
        self.script.write_text(INFERENCE)
        self.config = self.root / "model.json"
        self.config.write_text(json.dumps({"model_id": "fixture-v1", "bundle": "bundle", "timeout_seconds": 2,
                                          "command": [sys.executable, "-u", "{bundle}/infer.py"],
                                          "datasets": ["sessions"]}))

    def classifier(self):
        classifier = ml.JsonlClassifier(ml.load_spec(self.config))
        self.addCleanup(classifier.close)
        return classifier

    def test_keep_mask_roundtrip_and_unicode_spans_without_gold(self):
        classifier = self.classifier()
        requests = []
        predict = classifier.predict
        classifier.predict = lambda request: (requests.append(request), predict(request))[1]
        adapter = TwoStageAdapter(classifier, WORKER)
        text = "🔐 secret public"
        session = Session("s", [Item(0, "t0", "prompt", text), Item(1, "t1", "tool_input", text)], [])
        outputs = adapter.run_session(session)
        self.assertEqual(outputs[0].text, "🔐 [PASSWORD_1] public")
        self.assertEqual((outputs[0].edits[0].start, outputs[0].edits[0].end), (2, 8))
        self.assertGreaterEqual(outputs[0].elapsed_ms, 20)
        self.assertEqual(outputs[1].text, text)
        self.assertIsNone(outputs[1].elapsed_ms)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["offset_unit"], "code_points")
        self.assertNotIn("gold", requests[0])
        self.assertEqual(adapter.describe()["candidate_counts"], {"candidates": 2, "keep": 1, "mask": 1})

    def test_keep_is_not_overridden_by_a_previous_mask(self):
        labels = iter([["MASK"], ["KEEP"]])
        classifier = SimpleNamespace(predict=lambda _: next(labels), describe=lambda: {})
        adapter = TwoStageAdapter(classifier, WORKER)
        outputs = adapter.run_session(Session("s", [Item(i, "t0", "prompt", "secret") for i in range(2)], []))
        self.assertEqual(outputs[0].text, "[PASSWORD_1]")
        self.assertEqual(outputs[1].text, "secret")

    def test_invalid_model_response_fails_quality_evaluation(self):
        self.script.write_text(INFERENCE.replace('"request_id": request["request_id"]', '"request_id": -1'))
        classifier = self.classifier()
        adapter = TwoStageAdapter(classifier, WORKER)
        with self.assertRaises(ScoringError):
            adapter.run_session(Session("s", [Item(0, "t0", "prompt", "secret")], []))
        self.assertTrue(classifier.closed)
        self.assertIsNotNone(classifier.process.poll())

    def test_timeout_kills_the_model_instead_of_reusing_detector_output(self):
        config = json.loads(self.config.read_text())
        config["timeout_seconds"] = 0.05
        self.config.write_text(json.dumps(config))
        self.script.write_text("import time\ntime.sleep(30)\n")
        classifier = self.classifier()
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            classifier.predict({"text": "secret", "candidates": [{"id": 0}]})
        self.assertTrue(classifier.closed)
        self.assertIsNotNone(classifier.process.poll())

    def test_bundle_snapshot_and_model_changes_invalidate_both_tracks(self):
        first = ml.load_spec(self.config)
        pinned = ml.load_spec(ml.snapshot(first, self.root / "snapshot"))
        self.assertEqual(pinned.fingerprint, first.fingerprint)
        with patch.object(latency, "tool_version", return_value=None):
            env1 = latency.environment("ensemble", [], 1, 1, first.metadata())
            bench1 = runner.benchmark([], first.metadata())
            self.script.write_text(INFERENCE + "\n# model update\n")
            second = ml.load_spec(self.config)
            self.assertNotEqual(first.fingerprint, second.fingerprint)
            self.assertNotEqual(env1["fingerprint"], latency.environment("ensemble", [], 1, 1, second.metadata())["fingerprint"])
            self.assertNotEqual(bench1["fingerprint"], runner.benchmark([], second.metadata())["fingerprint"])
        self.assertEqual(pinned.fingerprint, ml.load_spec(self.root / "snapshot/config.json").fingerprint)
        with self.assertRaises(ValueError):
            ml.snapshot(first, self.root / "stale-snapshot")

    def test_http_latency_includes_ml_and_reports_only_final_mask_findings(self):
        classifier = self.classifier()
        adapter = TwoStageAdapter(classifier, WORKER)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(adapter, classifier))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        _, description, _ = latency.m4.http_json(url, "GET", "/status")
        self.assertEqual(description["second_stage"]["model_id"], "fixture-v1")
        recorder = latency.m4.Recorder(latency.m4.Detector("ensemble", "url", url=url), io.StringIO(), 1, 5000, 2)
        row, counts = recorder.sample([{"id": 0, "text": "🔐 secret public", "source": "user_prompt"}])
        self.assertTrue(row["ok"])
        self.assertEqual(counts, [1])
        self.assertGreaterEqual(row["detector_ms"], 20)
        self.assertGreaterEqual(row["call_ms"], row["detector_ms"])
        self.assertFalse(row["over_timeout"])
        classifier.close()
        failed, counts = recorder.sample([{"id": 0, "text": "secret", "source": "user_prompt"}])
        self.assertFalse(failed["ok"])
        self.assertIsNone(failed["detector_ms"])
        self.assertIsNone(counts)

    def test_shard_scores_final_predictions_using_ml_policy(self):
        from tests.test_collect import FIXTURES
        out = self.root / "shard.json"
        with patch.object(shard, "load_worker", return_value=WORKER):
            code = shard.main(["run", "--sessions", str(FIXTURES / "sessions.jsonl"),
                               "--gold", str(FIXTURES / "gold.jsonl"), "--lines", "0:1",
                               "--dataset", "sessions", "--system-root", "unused", "--out", str(out),
                               "--ml-config", str(self.config)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text())["system"]["pipeline"], "detector-ml")

    def test_service_schedules_and_executes_ml_latency(self):
        service = Service(Config(self.root / "service", "unused", ml_config=str(self.config), task=False))
        commit = Commit("a" * 40, "2026-10-28", "t", "test", "test", "b" * 64)
        dataset = runner.Dataset("sessions", self.root / "s", self.root / "g", "s", "g")
        with patch("pipeline.service.repo.sync"), patch("pipeline.service.repo.commits", return_value=[commit]), \
                patch("pipeline.service.runner.discover", return_value=[dataset]), \
                patch.object(runner, "tool_version", return_value=None), \
                patch.object(latency, "tool_version", return_value=None):
            plan = service.plan()
        self.assertEqual(set(plan["contexts"]), {"detection", "latency"})
        self.assertEqual(plan["env"]["second_stage"], plan["bench"]["second_stage"])
        job = next(job for job in service.jobs(plan) if job[0] == "latency")
        with patch("pipeline.service.repo.export"), patch("pipeline.service.repo.python_for", return_value=sys.executable), \
                patch("pipeline.service.latency.evaluate") as evaluate, contextlib.redirect_stdout(io.StringIO()):
            service.run_job(plan, *job, [job])
        self.assertEqual(evaluate.call_args.kwargs["ml_spec"], plan["ml_spec"])

    def test_rule_only_results_are_not_shown_as_ml_results_or_the_reverse(self):
        service = Service(Config(self.root / "service", "unused"))
        for key, second_stage in (("a" * 16, None), ("b" * 16, ml.load_spec(self.config).metadata())):
            runner.write_json(service.result_dir("detection", key) / "meta.json", {
                "system_fingerprint": "system", "evaluated_at": "2026-10-28", "headline": {},
                **({"second_stage": second_stage} if second_stage else {})})
        self.assertEqual(service.latest_by_system("detection")["system"][1], "a" * 16)
        self.assertEqual(service.latest_by_system("detection", second_stage)["system"][1], "b" * 16)

    def test_latency_command_uses_a_pinned_model_and_does_not_publish_weights(self):
        from tests.test_latency import write_guard_run
        spec = ml.load_spec(self.config)
        env = {"fingerprint": "env", "second_stage": spec.metadata()}
        observed = {}

        def start(command, **kwargs):
            import shlex
            ml_command = shlex.split(command[command.index("--detector") + 1][4:])
            pinned = Path(ml_command[ml_command.index("--ml-config") + 1])
            observed["pinned"] = pinned
            self.assertEqual(ml.load_spec(pinned).fingerprint, spec.fingerprint)
            self.assertNotEqual(pinned, self.config)
            run = Path(command[command.index("--out") + 1])
            run.mkdir()
            write_guard_run(run, [], [])
            return SimpleNamespace(wait=lambda **_: 0)

        with patch.object(latency.subprocess, "Popen", side_effect=start):
            latency.evaluate(self.root, self.root / "result", python=sys.executable, adapters="ensemble", guard=[],
                             repeat=1, warmup=1, commit={}, system_fingerprint="system", env=env, ml_spec=spec)
        self.assertFalse(observed["pinned"].exists())
        self.assertFalse(list((self.root / "result").rglob("infer.py")))
        meta = json.loads((self.root / "result/meta.json").read_text())
        self.assertEqual(meta["second_stage"], spec.metadata())

    def test_training_split_is_rejected_before_starting_a_model(self):
        from tests.test_collect import FIXTURES
        sessions = self.root / "sessions.jsonl"
        first = json.loads((FIXTURES / "sessions.jsonl").read_text().splitlines()[0])
        first["meta"]["split"] = "train"
        sessions.write_text(json.dumps(first) + "\n")
        with patch.object(shard, "load_worker", return_value=WORKER), \
                patch.object(ml, "JsonlClassifier") as classifier, contextlib.redirect_stderr(io.StringIO()):
            code = shard.main(["run", "--sessions", str(sessions), "--gold", str(FIXTURES / "gold.jsonl"),
                               "--lines", "0:1", "--dataset", "sessions", "--system-root", "unused",
                               "--out", str(self.root / "shard.json"), "--ml-config", str(self.config)])
        self.assertEqual(code, shard.EXIT_DATASET)
        classifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
