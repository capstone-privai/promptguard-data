"""Rule union ML: new discoveries, exact duplicates, merged masking, Unicode and timed IPC."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import latency, ml
from pipeline.ml_worker import make_handler
from evaluation.adapters.span_union_adapter import SpanUnionAdapter, union_findings
from evaluation.dataset.schema import Item, Session
from tests.test_ml import Detector, WORKER


SPAN_INFERENCE = '''import json,sys,time
for line in sys.stdin:
 r=json.loads(line); time.sleep(.025)
 start=r["text"].find("novel")
 spans=[{"start":start,"end":start+5,"score":.9999}] if start>=0 else []
 print(json.dumps({"version":1,"request_id":r["request_id"],"offset_unit":"code_points","spans":spans}),flush=True)
'''


class UnionTests(unittest.TestCase):
    def test_union_keeps_rule_findings_and_adds_ml_only_with_unicode(self):
        text = "🔐 secret public novel"
        result, counts = union_findings(text, Detector().scan(text, "tool_result"),
                                        [{"start": 16, "end": 21, "score": .99}])
        self.assertEqual([(f["start"], f["end"]) for f in result["findings"]], [(3, 9), (10, 16), (17, 22)])
        self.assertEqual(counts, {"rule": 2, "ml": 1, "final": 3, "ml_only": 1})

    def test_exact_duplicate_preserves_rule_type_and_is_masked_once(self):
        text = "secret"
        result, counts = union_findings(text, Detector().scan(text, "tool_result"),
                                        [{"start": 0, "end": 6, "score": .99}])
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["type"], "PASSWORD")
        self.assertEqual(counts["ml_only"], 0)

    def test_overlap_merges_but_adjacent_intervals_remain_separate(self):
        text = "secret public"
        result, counts = union_findings(text, Detector().scan(text, "tool_result"),
                                        [{"start": 5, "end": 7, "score": .99}])
        self.assertEqual([(f["start"], f["end"]) for f in result["findings"]], [(0, 7), (7, 13)])
        self.assertEqual(counts["ml_only"], 0)

    def test_adapter_scans_when_rule_has_no_candidates_and_skips_tool_input(self):
        calls = []
        classifier = SimpleNamespace(describe=lambda: {}, predict_spans=lambda r: (calls.append(r),
            [{"start": 0, "end": 5, "score": .99}])[1])
        adapter = SpanUnionAdapter(classifier, WORKER)
        session = Session("s", [Item(0, "t", "prompt", "novel"), Item(1, "t", "tool_input", "novel")], [])
        outputs = adapter.run_session(session)
        self.assertEqual(outputs[0].text, "[SECRET_1]")
        self.assertEqual(outputs[1].text, "novel")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("gold", calls[0])
        self.assertEqual(adapter.describe()["span_counts"]["ml_only"], 1)

    def test_invalid_spans_fail_instead_of_retaining_only_rules(self):
        for span in ({"start": 0, "end": 100, "score": .9}, {"start": 0, "end": 1, "score": float("nan")}):
            with self.subTest(span=span), self.assertRaises(ValueError):
                union_findings("secret", Detector().scan("secret", "tool_result"), [span])

    def test_existing_native_mod_remask_policy_is_preserved(self):
        responses = iter([[{"start": 0, "end": 5, "score": .99}], []])
        classifier = SimpleNamespace(describe=lambda: {}, predict_spans=lambda _: next(responses))
        adapter = SpanUnionAdapter(classifier, WORKER)
        outputs = adapter.run_session(Session("s", [Item(0, "t0", "prompt", "novel"),
                                                    Item(1, "t1", "tool_output", "again novel")], []))
        self.assertEqual(outputs[0].text, "[SECRET_1]")
        self.assertEqual(outputs[1].text, "again [SECRET_1]")
        self.assertTrue(adapter.describe()["remask"])

    def test_real_jsonl_process_and_http_measure_full_text_union(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"; bundle.mkdir()
            (bundle / "infer.py").write_text(SPAN_INFERENCE)
            config = root / "model.json"
            config.write_text(json.dumps({"model_id": "span-fixture", "bundle": "bundle", "mode": "span_union",
                                          "command": [sys.executable, "-u", "{bundle}/infer.py"]}))
            spec = ml.load_spec(config)
            self.assertEqual(ml.load_spec(ml.snapshot(spec, root / "pinned")).metadata(), spec.metadata())
            classifier = ml.inference(spec)
            self.addCleanup(classifier.close)
            self.assertIsInstance(classifier, ml.JsonlSpanDetector)
            adapter = SpanUnionAdapter(classifier, WORKER)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(adapter, classifier))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            url = f"http://127.0.0.1:{server.server_address[1]}"
            _, description, _ = latency.m4.http_json(url, "GET", "/status")
            self.assertEqual(description["pipeline"], "detector-span-union")
            recorder = latency.m4.Recorder(latency.m4.Detector("ensemble", "url", url=url), io.StringIO(), 1, 5000, 2)
            row, counts = recorder.sample([{"id": 0, "text": "novel", "source": "tool_result"}])
            self.assertTrue(row["ok"]); self.assertEqual(counts, [1])
            self.assertGreaterEqual(row["detector_ms"], 20)
            classifier.close()


if __name__ == "__main__":
    unittest.main()
