"""metric-latency evaluator: workloads, the Guard replay rules, statistics and an end-to-end run on the null detector.

  python3 -m unittest discover -s metric-latency/tests
"""
from __future__ import annotations

import json
import lzma
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import m4  # noqa: E402
import m4_workloads as wl  # noqa: E402


class SynthTests(unittest.TestCase):
    def test_deterministic_and_sized(self) -> None:
        for size in (2, 128, 1000, 4096):
            text = wl.synth_text(size, "plain", "0")
            self.assertEqual(text, wl.synth_text(size, "plain", "0"))
            self.assertEqual(len(text), size)
            self.assertTrue(text.endswith("\n"))
        self.assertNotEqual(wl.synth_text(1024, "plain", "0"), wl.synth_text(1024, "plain", "1"))

    def test_secrets_kind_has_secret_lines(self) -> None:
        markers = ("DB_PASSWORD=", "api_key:", "GITHUB_TOKEN=", "AWS_ACCESS_KEY_ID=", "Bearer ")
        for size in (128, 4096):
            self.assertTrue(any(m in wl.synth_text(size, "secrets", "0") for m in markers))
            self.assertFalse(any(m in wl.synth_text(size, "plain", "0") for m in markers))

    def test_sweep_shape(self) -> None:
        calls = list(wl.synth_sessions()[0].calls)
        per_kind = len(wl.SYNTH_SIZES) + len(wl.SYNTH_BATCHES) - 1
        self.assertEqual(len(calls), 2 * per_kind)
        self.assertEqual(max(len(c.items) for c in calls), max(wl.SYNTH_BATCHES))
        self.assertEqual(sorted({c.items[0]["id"] for c in calls}), [0])


class GuardReplayTests(unittest.TestCase):
    def _replay(self, requests, findings=frozenset(), fail_on=None):
        sent = []

        def scan(items, meta):
            sent.append([item["text"] for item in items])
            if fail_on is not None and fail_on in sent[-1]:
                return None
            return [1 if item["text"] in findings else 0 for item in items]
        return list(wl.guard_session(requests, scan)), sent

    def test_string_leaves_are_values_in_document_order(self) -> None:
        body = {"model": "m", "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}], "max_tokens": 5}
        self.assertEqual(wl.string_leaves(body), ["m", "user", "text", "hi"])

    def test_only_unseen_clean_leaves_are_sent(self) -> None:
        summaries, sent = self._replay([["a", "b", "a"], ["a", "b", "c"], ["c", "d"]], findings={"b"})
        # a is cached clean after the first request; b had a finding, so it is never cached and is sent again.
        self.assertEqual(sent, [["a", "b"], ["b", "c"], ["d"]])
        self.assertEqual([s["unique"] for s in summaries], [2, 2, 1])
        self.assertEqual([s["findings"] for s in summaries], [1, 1, 0])

    def test_batches_and_stop_at_first_finding(self) -> None:
        leaves = [f"leaf{i}" for i in range(600)]
        summaries, sent = self._replay([leaves])
        self.assertEqual([len(b) for b in sent], [256, 256, 88])
        self.assertEqual(summaries[0]["calls"], 3)
        summaries, sent = self._replay([leaves], findings={"leaf3"})
        self.assertEqual((len(sent), summaries[0]["calls"]), (1, 1))

    def test_failed_call_blocks_and_caches_nothing(self) -> None:
        summaries, sent = self._replay([["a", "x"], ["a"]], fail_on="x")
        self.assertTrue(summaries[0]["failed"])
        self.assertEqual(sent, [["a", "x"], ["a"]])

    def test_capture_file_to_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t01" / "none-r1" / wl.CAPTURE_FILE
            path.parent.mkdir(parents=True)
            records = [{"method": "POST", "path": "/v1/messages?beta=true", "body": json.dumps({"system": "s", "messages": ["m"]})},
                       {"method": "POST", "path": "/v1/messages/count_tokens", "body": json.dumps({"messages": ["m"]})},
                       {"method": "GET", "path": "/v1/models", "body": ""},
                       {"method": "POST", "path": "/v1/messages", "body": "not json"}]
            with lzma.open(path, "wt", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in records)
            sessions = wl.guard_sessions([tmp])
        self.assertEqual([(s.name, s.requests) for s in sessions], [("t01/none-r1", [["s", "m"], ["m"]])])


class RecordedTests(unittest.TestCase):
    def test_replayed_in_arrival_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t01" / "promptguard-r1" / wl.RECORDED_FILE
            path.parent.mkdir(parents=True)
            records = [{"seq": 1, "path": "/scan-batch", "items": [{"id": 0, "text": "second", "source": "bash_stdout"}]},
                       {"seq": 0, "path": "/scan-batch", "items": [{"id": 0, "text": "first", "source": "claude_md"}]},
                       {"seq": 2, "path": "/health"}]
            with lzma.open(path, "wt", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in records)
            calls = list(wl.recorded_sessions([tmp])[0].calls)
        self.assertEqual([c.items[0]["text"] for c in calls], ["first", "second"])
        self.assertEqual([c.workload for c in calls], ["recorded/claude_md", "recorded/bash_stdout"])


class StatisticsTests(unittest.TestCase):
    def test_quantile_is_nearest_rank(self) -> None:
        values = list(range(1, 101))
        self.assertEqual((m4.quantile(values, .5), m4.quantile(values, .95), m4.quantile(values, 1)), (50, 95, 100))
        self.assertEqual(m4.quantile([7.0], .99), 7.0)
        self.assertIsNone(m4.quantile([], .5))

    def test_fit(self) -> None:
        a, b = m4.fit([(1, 5), (2, 7), (4, 11)])
        self.assertAlmostEqual(a, 3)
        self.assertAlmostEqual(b, 2)
        self.assertIsNone(m4.fit([(1, 5), (1, 6)]))


class ConfigTests(unittest.TestCase):
    def test_single_adapter_config_makes_file_options_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rules").mkdir()
            (root / "rules" / "extra.yaml").write_text("x", encoding="utf-8")
            config = root / "detector.json"
            entry = {"name": "cs", "type": "credsweeper", "required": False,
                     "options": {"extra_rules": ["rules/extra.yaml"], "severity": "medium", "binary": "gitleaks"}}
            config.write_text(json.dumps({"consensus": {"mode": "majority"}, "adapters": [entry]}), encoding="utf-8")
            out = json.loads(m4.single_adapter_config(config, entry, root).read_text(encoding="utf-8"))
        self.assertEqual(out["consensus"], "any")
        options = out["adapters"][0]["options"]
        self.assertEqual(options["extra_rules"], [str((root / "rules" / "extra.yaml").resolve())])
        self.assertEqual((options["severity"], options["binary"]), ("medium", "gitleaks"))
        self.assertTrue(out["adapters"][0]["required"])


class EndToEndTests(unittest.TestCase):
    def test_null_detector_run_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, report_dir = Path(tmp) / "null", Path(tmp) / "report"
            m4.main(["run", "--out", str(run_dir), "--detector", "null", "--synth", "--repeat", "2", "--warmup", "1"])
            rows = [json.loads(line) for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
            meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            m4.main(["report", str(run_dir), "--out", str(report_dir)])
            summary = (report_dir / "summary.md").read_text(encoding="utf-8")
        calls = 2 * (len(wl.SYNTH_SIZES) + len(wl.SYNTH_BATCHES) - 1)
        self.assertEqual(len(rows), 2 * calls)
        self.assertTrue(all(r["ok"] and r["findings"] == 0 and r["detector_ms"] is not None for r in rows))
        self.assertTrue(all(r["call_ms"] >= r["detector_ms"] for r in rows))
        self.assertEqual(meta["name"], "null")
        self.assertEqual(meta["detectors"][0]["describe"]["detector"], "null")
        self.assertIn("| null | synth | 20 | 40 |", summary)


if __name__ == "__main__":
    unittest.main()
