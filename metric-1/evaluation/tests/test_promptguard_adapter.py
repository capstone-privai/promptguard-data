from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evaluation.adapters.promptguard_adapter import CHANNEL_MAP, PromptGuardAdapter
from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import Item, Session
from evaluation.run import evaluate_sessions
from evaluation.scorer.span_scoring import SpanStatus
from evaluation.tests.support import (GOLD, HAS_PROMPTGUARD, SESSIONS, SKIP_REASON, ScriptedWorker, finding, found)


def _session(*texts: str, channel: str = "tool_output") -> Session:
    return Session("x", [Item(index, "t0", channel, text) for index, text in enumerate(texts)], [])


@unittest.skipUnless(HAS_PROMPTGUARD, SKIP_REASON)
class PromptGuardAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sessions = load_sessions(SESSIONS, GOLD)
        cls.adapter = PromptGuardAdapter()
        cls.result = evaluate_sessions(cls.sessions, cls.adapter)  # verifies every item's edits
        cls.items = {(session.session_id, item.item_id): item for session in cls.sessions for item in session.items}
        cls.status = {(score.session_id, score.item_id, gold.start): gold.status
                      for score in cls.result.scores for gold in score.gold_results}

    def _status(self, session_id: str, item_id: int, value: str) -> SpanStatus:
        return self.status[(session_id, item_id, self.items[(session_id, item_id)].text.index(value))]

    def test_repository_examples_are_fully_masked(self) -> None:
        self.assertEqual(self._status("s-0001", 2, "mysecret123"), SpanStatus.FULL)
        self.assertEqual(self._status("s-0001", 2, "secret123@"), SpanStatus.FULL)
        # The mod substitutes from the end of the text, so the later value gets the lower number.
        text = self.result.outputs[("s-0001", 2)].text
        self.assertIn("DB_PASSWORD=[PASSWORD_2]\n", text)
        self.assertIn("postgresql://admin:[PASSWORD_1]@prod-db.internal:5432/payments", text)

    def test_placeholders_are_session_scoped(self) -> None:
        outputs = self.result.outputs
        self.assertEqual(outputs[("s-0004", 1)].text, "DB_PASSWORD=[PASSWORD_1]\n")
        self.assertEqual(outputs[("s-0004", 2)].text, "error: auth failed for DB_PASSWORD=[PASSWORD_1]\n")
        self.assertEqual(outputs[("s-0004", 3)].text, "BACKUP_PASSWORD=[PASSWORD_2]\n")
        self.assertEqual(outputs[("s-0005", 1)].text, "DB_PASSWORD=[PASSWORD_1]\n")
        self.assertEqual(outputs[("s-0008", 3)].text, "DB_PASSWORD=[PASSWORD_1]\n")

    def test_prompt_and_instructions_are_scanned(self) -> None:
        # Both channels go through the worker, which finds no key=value secret in these sentences.
        for key in (("s-0002", 0), ("s-0007", 1)):
            self.assertIsInstance(self.result.outputs[key].elapsed_ms, float)
        self.assertEqual(self._status("s-0002", 0, "hunter2pass"), SpanStatus.MISSED)
        self.assertEqual(self._status("s-0007", 1, "kangaroo42"), SpanStatus.MISSED)
        self.assertGreater(self.result.metrics["latency_ms"]["n"], 0)

    def test_tool_input_passes_through(self) -> None:
        text = "DB_PASSWORD=mysecret123\n"
        output = self.adapter.run_session(_session(text, channel="tool_input"))[0]
        self.assertEqual((output.text, output.edits, output.elapsed_ms), (text, [], None))

    def test_offsets_are_converted_to_code_points(self) -> None:
        text = "🔐 DB_PASSWORD=mysecret123\n"
        output = self.adapter.run_session(_session(text))[0]
        self.assertEqual(output.text, "🔐 DB_PASSWORD=[PASSWORD_1]\n")
        start = text.index("mysecret123")
        self.assertEqual([(edit.start, edit.end) for edit in output.edits], [(start, start + len("mysecret123"))])

    def test_describe(self) -> None:
        described = self.result.system
        self.assertEqual(described["processed_channels"], ["prompt", "instructions", "tool_output"])
        self.assertEqual(described["channel_map"], CHANNEL_MAP)
        self.assertEqual(described["failed_open_items"], 0)
        self.assertEqual(described["detector_version"], self.adapter.worker.CREDSWEEPER_VERSION)


class FailOpenTests(unittest.TestCase):
    """When the mod's hook throws, Claude Code skips it and the model gets the text unchanged."""

    TEXT = "DB_PASSWORD=mysecret123\n"

    def _assert_failed_open(self, result) -> None:
        adapter = PromptGuardAdapter(ScriptedWorker({self.TEXT: result}))
        output = adapter.run_session(_session(self.TEXT))[0]
        self.assertEqual((output.text, output.edits), (self.TEXT, []))
        self.assertIsInstance(output.elapsed_ms, float)
        self.assertEqual(adapter.describe()["failed_open_items"], 1)

    def test_unsafe_result(self) -> None:
        self._assert_failed_open({"ok": False, "findings": [], "errors": ["SPAN_TOO_LARGE"]})

    def test_detector_exception(self) -> None:
        self._assert_failed_open(RuntimeError("detector crashed"))

    def test_bad_findings(self) -> None:
        for override in ({"offset_unit": "code_points"}, {"end": 99}, {"start": None}):
            with self.subTest(override=override):
                self._assert_failed_open(found(finding(self.TEXT, "mysecret123", **override)))

    def test_numbers_taken_before_the_failure_stay_taken(self) -> None:
        first, second = "key=abcdefgh\n", "other=zzzzzzzz\n"
        # The later finding is numbered first; the earlier one then overlaps it and the hook throws.
        worker = ScriptedWorker({first: found(finding(first, "abcdef", value_hash="a"), finding(first, "efgh")),
                                 second: found(finding(second, "zzzzzzzz"))})
        outputs = PromptGuardAdapter(worker).run_session(_session(first, second))
        self.assertEqual(outputs[0].text, first)
        self.assertEqual(outputs[1].text, "other=[PASSWORD_2]\n")

    def test_fault_injection_mode_is_refused(self) -> None:
        with patch.dict(os.environ, {"PG_DETECTOR_MODE": "crash"}), self.assertRaises(ValueError):
            PromptGuardAdapter(ScriptedWorker({}))


if __name__ == "__main__":
    unittest.main()
