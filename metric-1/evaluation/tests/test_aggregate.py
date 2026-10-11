from __future__ import annotations

import unittest

from evaluation.dataset.schema import Item, Session
from evaluation.report.aggregate import aggregate, count_lines, f2_score, percentile
from evaluation.scorer.span_scoring import EditResult, GoldResult, ItemScore, SpanStatus


def _gold(item_id: int, start: int, end: int, status: SpanStatus, exposed: int, kind: str = "PASSWORD") -> GoldResult:
    return GoldResult("s", item_id, 0, start, end, kind, status, exposed)


class AggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        # 4 items, 10 lines in total.
        self.sessions = [
            Session("s1", [Item(0, "t0", "tool_output", "x\n" * 4), Item(1, "t0", "prompt", "one line")], []),
            Session("s2", [Item(0, "t0", "tool_input", "y\n" * 3), Item(1, "t0", "tool_output", "z\nz")], []),
        ]
        self.scores = [
            ItemScore("s1", 0, "tool_output",
                      [_gold(0, 0, 10, SpanStatus.FULL, 0), _gold(0, 20, 30, SpanStatus.PARTIAL, 4)],
                      [EditResult("s1", 0, 0, 10, True), EditResult("s1", 0, 20, 26, True),
                       EditResult("s1", 0, 40, 45, False)]),
            ItemScore("s1", 1, "prompt", [_gold(1, 0, 5, SpanStatus.MISSED, 5, "TOKEN")], []),
            ItemScore("s2", 0, "tool_input", [_gold(0, 0, 5, SpanStatus.FULL, 0, "TOKEN")],
                      [EditResult("s2", 0, 0, 5, True)]),
            ItemScore("s2", 1, "tool_output", [], [EditResult("s2", 1, 0, 1, False)]),
        ]
        self.elapsed = {("s1", 0): 2.0, ("s1", 1): None, ("s2", 0): 4.0, ("s2", 1): 10.0}

    def test_metric_values(self) -> None:
        # The tool_input item (3 lines, one full gold span, one edit) is left out of every count.
        metrics = aggregate(self.sessions, self.scores, self.elapsed)
        self.assertEqual(metrics["lines_total"], 7)
        self.assertEqual(metrics["recall"], 1 / 3)
        self.assertEqual(metrics["precision"], 2 / 4)
        self.assertAlmostEqual(metrics["f2"], 5 * 0.5 * (1 / 3) / (4 * 0.5 + 1 / 3))
        self.assertEqual(metrics["char_recall"], (25 - 9) / 25)
        self.assertEqual(metrics["partial_rate"], 1 / 3)
        self.assertEqual(metrics["missed_rate"], 1 / 3)
        self.assertEqual(metrics["fp_per_1k_lines"], 2 / 7 * 1000)
        self.assertEqual(metrics["density_per_1k_lines"], 3 / 7 * 1000)
        self.assertEqual(metrics["counts"], {
            "gold_total": 3, "full": 1, "partial": 1, "missed": 1, "edits_total": 4, "edits_tp": 2,
            "edits_fp": 2, "gold_chars_total": 25, "exposed_chars_total": 9, "gold_excluded": 1, "edits_excluded": 1,
        })
        self.assertEqual(metrics["scored_channels"], ["prompt", "instructions", "tool_output"])
        self.assertEqual(metrics["excluded_by_channel"], {"tool_input": {"items": 1, "lines": 3, "gold": 1, "edits": 1}})
        self.assertEqual(metrics["composition"]["by_type"]["PASSWORD"], 2)
        self.assertEqual(metrics["composition"]["by_type"]["TOKEN"], 1)
        self.assertEqual(metrics["composition"]["by_channel"], {"prompt": 1, "instructions": 0, "tool_output": 2})
        self.assertEqual(metrics["recall_by_type"]["PASSWORD"], 0.5)
        self.assertEqual(metrics["recall_by_type"]["TOKEN"], 0.0)
        self.assertIsNone(metrics["recall_by_type"]["PRIVATE_KEY"])
        self.assertEqual(metrics["recall_by_channel"], {"prompt": 0.0, "instructions": None, "tool_output": 0.5})
        self.assertEqual((metrics["sessions"], metrics["items"]), (2, 4))

    def test_tool_input_changes_nothing_but_the_excluded_counts(self) -> None:
        # Whatever a tool_input item holds (gold missed, gold masked, edits outside gold, many lines), every
        # scored number equals the run without that item.
        without = aggregate(self.sessions[:1] + [Session("s2", [self.sessions[1].items[1]], [])],
                            [score for score in self.scores if score.channel != "tool_input"], self.elapsed)
        noisy = ItemScore("s2", 0, "tool_input",
                          [_gold(0, 0, 5, SpanStatus.MISSED, 5, "TOKEN"), _gold(0, 9, 12, SpanStatus.PARTIAL, 1)],
                          [EditResult("s2", 0, 10, 11, True), EditResult("s2", 0, 20, 30, False),
                           EditResult("s2", 0, 40, 50, False)])
        for tool_input in (self.scores[2], noisy):
            with self.subTest(gold=len(tool_input.gold_results), edits=len(tool_input.edit_results)):
                scores = self.scores[:2] + [tool_input] + self.scores[3:]
                metrics = aggregate(self.sessions, scores, self.elapsed)
                excluded = {"items": 1, "lines": 3, "gold": len(tool_input.gold_results),
                            "edits": len(tool_input.edit_results)}
                self.assertEqual(metrics["excluded_by_channel"], {"tool_input": excluded})
                self.assertEqual(metrics["counts"]["gold_excluded"], excluded["gold"])
                self.assertEqual(metrics["counts"]["edits_excluded"], excluded["edits"])
                for key in metrics.keys() - {"counts", "excluded_by_channel", "latency_ms", "sessions", "items"}:
                    self.assertEqual(metrics[key], without[key], key)
                for key in metrics["counts"].keys() - {"gold_excluded", "edits_excluded"}:
                    self.assertEqual(metrics["counts"][key], without["counts"][key], key)

    def test_empty_gold_and_edits_give_none(self) -> None:
        sessions = [Session("s", [Item(0, "t0", "tool_output", "")], [])]
        metrics = aggregate(sessions, [ItemScore("s", 0, "tool_output", [], [])], {("s", 0): None})
        for key in ("recall", "precision", "f2", "char_recall", "partial_rate", "missed_rate",
                    "fp_per_1k_lines", "density_per_1k_lines"):
            self.assertIsNone(metrics[key], key)

    def test_f2_edge_cases(self) -> None:
        self.assertEqual(f2_score(0.0, 0.0), 0.0)
        self.assertIsNone(f2_score(None, 1.0))
        self.assertIsNone(f2_score(1.0, None))
        self.assertEqual(f2_score(1.0, 1.0), 1.0)

    def test_count_lines(self) -> None:
        self.assertEqual(count_lines(""), 0)
        self.assertEqual(count_lines("a"), 1)
        self.assertEqual(count_lines("a\n"), 1)
        self.assertEqual(count_lines("a\nb"), 2)
        self.assertEqual(count_lines("a\r\nb\r\n"), 2)
        self.assertEqual(count_lines("\n\n"), 2)

    def test_latency(self) -> None:
        latency = aggregate(self.sessions, self.scores, self.elapsed)["latency_ms"]
        self.assertEqual(latency["n"], 3)
        self.assertEqual(latency["p50"], 4.0)
        self.assertAlmostEqual(latency["p95"], 4.0 + (10.0 - 4.0) * 0.9)
        self.assertEqual(latency["max"], 10.0)
        self.assertEqual(percentile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5)
        none = aggregate(self.sessions, self.scores, {key: None for key in self.elapsed})["latency_ms"]
        self.assertEqual(none, {"p50": None, "p95": None, "max": None, "n": 0})


if __name__ == "__main__":
    unittest.main()
