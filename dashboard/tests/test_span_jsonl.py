"""The span-model bridge preserves the requested rule-candidate gate semantics."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.span_jsonl import decide


class SpanBridgeTests(unittest.TestCase):
    def request(self):
        return {"version": 1, "request_id": 1, "offset_unit": "code_points", "text": "🔐 secret public",
                "candidates": [{"id": 4, "start": 2, "end": 8}, {"id": 7, "start": 9, "end": 15}]}

    def test_unicode_offsets_and_original_rule_ids(self):
        self.assertEqual(decide(self.request(), [{"start": 2, "end": 8}]),
                         [{"id": 4, "label": "MASK"}, {"id": 7, "label": "KEEP"}])

    def test_partial_overlap_is_mask_but_touching_boundaries_are_keep(self):
        self.assertEqual(decide(self.request(), [{"start": 7, "end": 9}]),
                         [{"id": 4, "label": "MASK"}, {"id": 7, "label": "KEEP"}])

    def test_ml_only_span_does_not_create_a_rule_candidate(self):
        request = self.request()
        request["candidates"] = []
        self.assertEqual(decide(request, [{"start": 2, "end": 8}]), [])

    def test_invalid_model_spans_or_duplicate_candidates_are_rejected(self):
        with self.assertRaises(ValueError):
            decide(self.request(), [{"start": 0, "end": 100}])
        request = self.request()
        request["candidates"][1]["id"] = 4
        with self.assertRaises(ValueError):
            decide(request, [])


if __name__ == "__main__":
    unittest.main()
