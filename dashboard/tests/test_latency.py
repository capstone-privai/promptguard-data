"""latency.condense reads what metric-latency/scripts/m4.py writes: a real run against its null detector."""

from __future__ import annotations

import subprocess
import json
import lzma
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import latency  # noqa: E402


def guard_call(request=0, batch=0, ms=10, ok=True, rep=0, session="t01/none-r1"):
    return {"detector": "ensemble", "source": "guard", "workload": "guard", "session": session,
            "request": request, "batch": batch, "rep": rep, "ok": ok, "detector_ms": ms,
            "call_ms": ms, "over_timeout": False}


def guard_request(request=0, calls=1, failed=False, session="t01/none-r1", leaves=1, unique=1, findings=0):
    return {"detector": "ensemble", "session": session, "request": request, "calls": calls,
            "failed": failed, "leaves": leaves, "unique": unique, "findings": findings}


def write_guard_run(root, calls, requests):
    meta = {"name": "guard-fixture", "detectors": [{"label": "ensemble"}], "repeat": 3, "warmup": 1,
            "timeout_ms": 5000, "started_at": "2026-10-17", "machine": {
                "platform": "test", "machine": "test", "cpu_count": 1, "python": "test"}}
    (root / "run.json").write_text(json.dumps(meta))
    for filename, rows in (("calls.jsonl", calls), ("requests.jsonl", requests)):
        (root / filename).write_text("".join(json.dumps(row) + "\n" for row in rows))


class GuardCondenseTest(unittest.TestCase):
    def condense(self, calls, requests):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_guard_run(root, calls, requests)
            return latency.condense(root)

    def test_failed_request_is_not_a_zero_ms_measurement(self):
        data = self.condense([guard_call(ms=None, ok=False)], [guard_request(failed=True)])
        guard = data["detectors"][0]["guard"]
        self.assertEqual((guard["p50"], guard["p95"], guard["max"]), (None, None, None))
        self.assertEqual((guard["n"], guard["failed"], guard["unmeasured"], guard["cache_only"]), (0, 1, 0, 0))
        headline = latency.headline(data)
        self.assertIsNone(headline["guard_p95"])
        self.assertEqual((headline["guard_measured"], headline["guard_failed"], headline["guard_unmeasured"]), (0, 1, 0))

    def test_missing_batch_time_does_not_produce_a_partial_request_time(self):
        data = self.condense([guard_call(batch=0, ms=10), guard_call(batch=1, ms=None)],
                             [guard_request(calls=2)])
        guard = data["detectors"][0]["guard"]
        self.assertIsNone(guard["p95"])
        self.assertEqual((guard["n"], guard["failed"], guard["unmeasured"]), (0, 0, 1))

    def test_failed_replay_is_excluded_even_if_later_repeats_succeed(self):
        data = self.condense([guard_call(rep=0, ms=None, ok=False), guard_call(rep=1, ms=10)],
                             [guard_request(failed=True)])
        guard = data["detectors"][0]["guard"]
        self.assertIsNone(guard["p50"])
        self.assertEqual((guard["n"], guard["failed"]), (0, 1))

    def test_mixed_requests_keep_cache_hits_and_unknown_times_separate(self):
        data = self.condense([guard_call(0, ms=None, ok=False), guard_call(1, ms=50), guard_call(2, ms=None)],
                             [guard_request(0, failed=True), guard_request(1), guard_request(2),
                              guard_request(3, calls=0, unique=0),
                              guard_request(4, calls=0, unique=0, leaves=0)])
        guard = data["detectors"][0]["guard"]
        self.assertEqual((guard["requests"], guard["n"], guard["failed"], guard["unmeasured"]), (5, 3, 1, 1))
        self.assertEqual(guard["cache_only"], 1)
        self.assertEqual((guard["p50"], guard["p95"], guard["max"]), (0, 50, 50))

    def test_measured_blocked_requests_and_batch_medians_are_preserved(self):
        calls = [guard_call(batch=batch, rep=rep, ms=value)
                 for batch, values in ((0, [10, 20, 30]), (1, [50, 60, 70]))
                 for rep, value in enumerate(values)]
        data = self.condense(calls, [guard_request(calls=2, findings=1)])
        guard = data["detectors"][0]["guard"]
        self.assertEqual((guard["p50"], guard["p95"], guard["max"], guard["n"]), (80, 80, 80, 1))
        self.assertEqual((guard["blocked"], guard["failed"]), (1, 0))

    def test_report_marks_missing_times_and_shows_request_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_guard_run(root, [guard_call(ms=None, ok=False)], [guard_request(failed=True)])
            latency.m4.main(["report", str(root), "--out", str(root / "report")])
            report = (root / "report/summary.md").read_text()
        section = report.split("## Final Guard 재생:")[1]
        lines = [line for line in section.splitlines() if line.startswith("|")]
        headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
        values = [cell.strip() for cell in lines[2].strip("|").split("|")]
        row = dict(zip(headers, values))
        self.assertEqual((row["측정"], row["실패"], row["미측정"]), ("0", "1", "0"))
        self.assertEqual(row["요청 시간 p50"], "-")
        self.assertEqual(row["max"], "-")

    def test_changed_latency_version_invalidates_cached_results(self):
        from pipeline.service import result_key
        with patch.object(latency, "tool_version", return_value=None):
            current = latency.environment([], 5, 3)["fingerprint"]
            with patch.object(latency, "LATENCY_VERSION", 2):
                old = latency.environment([], 5, 3)["fingerprint"]
        self.assertGreaterEqual(latency.LATENCY_VERSION, 3)
        self.assertNotEqual(result_key("latency", "system", old), result_key("latency", "system", current))


class GuardSessionIdentityTest(unittest.TestCase):
    def captures(self, root):
        paths = [root / batch / "t01/none-r1" / latency.workloads.CAPTURE_FILE for batch in ("one", "two")]
        for path in paths:
            path.parent.mkdir(parents=True)
            with lzma.open(path, "wt") as handle:
                handle.write(json.dumps({"method": "POST", "path": "/v1/messages", "body": '{"text":"same"}'}) + "\n")
        return paths

    def test_same_capture_content_from_different_sources_changes_result_key(self):
        from pipeline.service import result_key
        with tempfile.TemporaryDirectory() as tmp, patch.object(latency, "tool_version", return_value=None):
            paths = self.captures(Path(tmp))
            contexts = [latency.environment([str(path)], 1, 1)["fingerprint"] for path in paths]
        self.assertNotEqual(result_key("latency", "system", contexts[0]), result_key("latency", "system", contexts[1]))

    def test_environment_and_replay_deduplicate_the_same_capture(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(latency, "tool_version", return_value=None):
            root = Path(tmp)
            path = self.captures(root)[0]
            alias = root / "alias.xz"
            alias.symlink_to(path)
            one = latency.environment([str(path)], 1, 1)
            overlap = latency.environment([str(path.parent), str(path), str(alias)], 1, 1)
            self.assertEqual(overlap["guard_captures"], 1)
            self.assertEqual(one["fingerprint"], overlap["fingerprint"])

    def test_two_batches_keep_two_sessions_and_a_100ms_p95(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.captures(root)
            for path, value in zip(paths, (10, 100)):
                with lzma.open(path, "wt") as handle:
                    handle.write(json.dumps({"method": "POST", "path": "/v1/messages",
                                             "body": json.dumps({"text": str(value)})}) + "\n")
            run = root / "run"
            run.mkdir()
            detector = SimpleNamespace(label="ensemble", kind="fake", startup_ms=0, config=None, system_root=None,
                                       start=lambda folder: None, stop=lambda: None, describe=lambda: {})
            args = SimpleNamespace(timeout_ms=5000, client_timeout=1, warmup=1, repeat=1)

            def sample(recorder, items):
                ms = float(items[0]["text"]) if items[0]["source"] == "outbound" else 1
                return {"ok": True, "status": 200, "error": None, "call_ms": ms, "detector_ms": ms,
                        "over_timeout": False, "findings": 0}, [0] * len(items)

            with patch.object(latency.m4.Recorder, "sample", sample), patch.object(latency.m4, "say"):
                latency.m4.measure(detector, args, run, lambda: latency.workloads.guard_sessions([str(root)]))
            calls = [json.loads(line) for line in (run / "calls.jsonl").read_text().splitlines()]
            requests = [json.loads(line) for line in (run / "requests.jsonl").read_text().splitlines()]
            write_guard_run(run, calls, requests)
            guard = latency.condense(run)["detectors"][0]["guard"]
            self.assertEqual((guard["sessions"], guard["p95"], guard["requests"]), (2, 100, 2))
            latency.m4.main(["report", str(run), "--out", str(root / "report")])
            report = (root / "report/summary.md").read_text().split("## Final Guard 재생:")[1]
            row = next(line for line in report.splitlines() if line.startswith("| ensemble |"))
            self.assertTrue(row.startswith("| ensemble | 2 | 2 |"), row)
            self.assertIn("| 10.0 | 100.0 | 100.0 |", row)


class CondenseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.tmp.name) / "m4"
        subprocess.run([sys.executable, str(latency.M4), "run", "--out", str(cls.run_dir), "--detector", "null",
                        "--synth", "--repeat", "1", "--warmup", "1", "--timeout-ms", "3000"],
                       check=True, capture_output=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sweeps_fits_and_headline(self):
        data = latency.condense(self.run_dir)
        self.assertEqual(data["timeout_ms"], 3000)
        self.assertEqual(len(data["detectors"]), 1)
        null = data["detectors"][0]
        self.assertEqual(null["label"], "null")
        self.assertEqual([point["size"] for point in null["size_sweep"]], [128, 1024, 4096, 16384, 65536, 262144])
        self.assertEqual([point["batch"] for point in null["batch_sweep"]], [1, 4, 16, 64, 256])
        self.assertEqual(null["single_1k"]["n"], 2)  # plain and secrets, one repeat each
        self.assertIsNotNone(null["fit_items"])
        self.assertEqual(null["failed"], 0)
        self.assertIsNone(null["guard"])
        headline = latency.headline(data)
        self.assertEqual(headline["single_1k_p50"], null["single_1k"]["p50"])
        self.assertEqual(headline["over_timeout"], 0)

    def test_headline_counts_only_the_ensemble(self):
        data = latency.condense(self.run_dir)
        detector = data["detectors"][0]
        data["detectors"] = [{**detector, "label": "adapter", "over_timeout": 7},
                             {**detector, "label": "ensemble", "over_timeout": 2}]
        self.assertEqual(latency.headline(data)["over_timeout"], 2)

    def test_evaluate_passes_the_checkout_timeout_to_m4(self):
        data = latency.condense(self.run_dir)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "promptguard.config.json"
            for value in (3000, None):
                with self.subTest(timeout=value):
                    if value is None:
                        config.unlink()
                    else:
                        config.write_text('{"detectorTimeoutMs":3000}')
                    with patch.object(latency.subprocess, "Popen") as popen, \
                            patch.object(latency, "condense", return_value=data):
                        popen.return_value.wait.return_value = 0
                        latency.evaluate(root, root / "result", python=sys.executable, guard=[],
                                         repeat=1, warmup=1, commit={}, system_fingerprint="system",
                                         env={"fingerprint": "environment"})
                    command = popen.call_args.args[0]
                    self.assertNotIn("--consensus", command)
                    self.assertNotIn("--adapters", command)
                    self.assertIn("--timeout-ms", command)
                    self.assertEqual(command[command.index("--timeout-ms") + 1], str(value or 5000))

    def test_environment_fingerprint_follows_options(self):
        one = latency.environment([], 5, 3)
        self.assertEqual(one["fingerprint"], latency.environment([], 5, 3)["fingerprint"])
        self.assertNotEqual(one["fingerprint"], latency.environment([], 6, 3)["fingerprint"])


if __name__ == "__main__":
    unittest.main()
