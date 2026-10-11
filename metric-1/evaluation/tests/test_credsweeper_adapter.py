from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation.tests.support import GOLD, SESSIONS, TOOL_INPUT_ITEM, require_credsweeper, write_tool_input_fixture

require_credsweeper()

from evaluation.adapters.credsweeper_adapter import REPLACEMENT, CredSweeperAdapter, select_non_overlapping  # noqa: E402
from evaluation.dataset.schema import CHANNELS, SCORED_CHANNELS  # noqa: E402
from evaluation.run import evaluate  # noqa: E402
from evaluation.scorer.span_scoring import SpanStatus  # noqa: E402


class CredSweeperAdapterTests(unittest.TestCase):
    def test_ml_off_and_on_pass_verification(self) -> None:
        for ml in (False, True):
            with self.subTest(ml=ml):
                result = evaluate(SESSIONS, GOLD, CredSweeperAdapter(ml=ml))  # raises if any edit fails verification
                self.assertEqual(result.system["ml"], ml)
                self.assertEqual(result.metrics["counts"]["gold_total"], 12)
                self.assertGreater(result.metrics["latency_ms"]["n"], 0)

    def test_ml_off_masks_repository_example(self) -> None:
        result = evaluate(SESSIONS, GOLD, CredSweeperAdapter(ml=False))
        output = result.outputs[("s-0001", 2)]
        self.assertIn(f"DB_PASSWORD={REPLACEMENT}\n", output.text)
        statuses = [gold.status for score in result.scores if (score.session_id, score.item_id) == ("s-0001", 2)
                    for gold in score.gold_results]
        self.assertEqual(statuses, [SpanStatus.FULL, SpanStatus.FULL])

    def test_default_channels_are_the_scored_channels(self) -> None:
        self.assertEqual(CredSweeperAdapter().channels, SCORED_CHANNELS)
        self.assertNotIn("tool_input", CredSweeperAdapter().channels)

    def test_scanning_tool_input_changes_no_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions, gold = write_tool_input_fixture(Path(tmp))
            default = evaluate(sessions, gold, CredSweeperAdapter())
            everything = evaluate(sessions, gold, CredSweeperAdapter(channels=CHANNELS))
        # Scanning tool_input masks the secret there, but neither that edit nor that gold span is scored.
        self.assertEqual(everything.outputs[TOOL_INPUT_ITEM].text, f"DB_PASSWORD={REPLACEMENT}\n")
        self.assertEqual(default.outputs[TOOL_INPUT_ITEM].edits, [])
        self.assertEqual((everything.metrics["counts"]["edits_excluded"], default.metrics["counts"]["edits_excluded"]),
                         (1, 0))
        self.assertEqual(default.metrics["counts"]["gold_total"], 11)
        for key in ("recall", "precision", "f2", "char_recall", "fp_per_1k_lines", "lines_total", "recall_by_channel"):
            self.assertEqual(everything.metrics[key], default.metrics[key], key)

    def test_overlap_keeps_longest_then_earliest(self) -> None:
        self.assertEqual(select_non_overlapping([(0, 5), (2, 10), (12, 15), (13, 16), (20, 22), (20, 22)]),
                         [(2, 10), (12, 15), (20, 22)])


if __name__ == "__main__":
    unittest.main()
