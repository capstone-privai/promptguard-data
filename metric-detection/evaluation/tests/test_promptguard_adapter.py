from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.adapters.promptguard_adapter import BLOCKED, CHANNEL_MAP, PromptGuardAdapter
from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import GoldSpan, Item, Session
from evaluation.run import evaluate, evaluate_sessions
from evaluation.scorer.edits import verify
from evaluation.scorer.span_scoring import SpanStatus, score_item
from evaluation.tests.support import (GOLD, HAS_PROMPTGUARD, SESSIONS, SKIP_REASON, TOOL_INPUT_ITEM, ScriptedWorker,
                                      finding, found, write_tool_input_fixture)


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

    def test_repository_examples_are_masked_exactly(self) -> None:
        self.assertEqual(self._status("s-0001", 2, "mysecret123"), SpanStatus.EXACT)
        self.assertEqual(self._status("s-0001", 2, "secret123@"), SpanStatus.EXACT)
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

    def test_tool_input_gold_is_not_counted(self) -> None:
        # The same secret masked as tool_output (one exact span, one edit) drops out of both sides as tool_input.
        with tempfile.TemporaryDirectory() as tmp:
            result = evaluate(*write_tool_input_fixture(Path(tmp)), self.adapter)
        self.assertEqual(result.outputs[TOOL_INPUT_ITEM].edits, [])
        before, after = self.result.metrics["counts"], result.metrics["counts"]
        self.assertEqual(self._status(*TOOL_INPUT_ITEM, "mysecret123"), SpanStatus.EXACT)
        self.assertEqual((after["gold_total"], after["gold_excluded"]), (before["gold_total"] - 1, 1))
        self.assertEqual(after["exact"], before["exact"] - 1)
        self.assertEqual((after["edits_total"], after["edits_tp"]), (before["edits_total"] - 1, before["edits_tp"] - 1))
        self.assertEqual(result.metrics["recall"], after["exact"] / after["gold_total"])
        self.assertNotIn("tool_input", result.metrics["recall_by_channel"])

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
        self.assertEqual(described["detector"], self.adapter.detector.describe())
        self.assertIn("credsweeper", [adapter["name"] for adapter in described["detector"]["adapters"]])


class FailOpenTests(unittest.TestCase):
    """on_failure="pass" (legacy launcher): when the mod's hook throws, Claude Code skips it and the model gets
    the text unchanged."""

    TEXT = "DB_PASSWORD=mysecret123\n"

    def _assert_failed_open(self, result) -> None:
        adapter = PromptGuardAdapter(ScriptedWorker({self.TEXT: result}), on_failure="pass")
        output = adapter.run_session(_session(self.TEXT))[0]
        self.assertEqual((output.text, output.edits), (self.TEXT, []))
        self.assertIsInstance(output.elapsed_ms, float)
        self.assertEqual((adapter.describe()["failed_open_items"], adapter.describe()["blocked_items"]), (1, 0))

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
        outputs = PromptGuardAdapter(worker, on_failure="pass").run_session(_session(first, second))
        self.assertEqual(outputs[0].text, first)
        self.assertEqual(outputs[1].text, "other=[PASSWORD_2]\n")

    def test_known_values_are_remasked_with_edits(self) -> None:
        first, second = "A_PASSWORD=Qw3rTy9uIo\n", "🔐 echo Qw3rTy9uIo B_PASSWORD=Zx8cVb7nMm Qw3rTy9uIo\n"
        worker = ScriptedWorker({first: found(finding(first, "Qw3rTy9uIo")),
                                 second: found(finding(second, "Zx8cVb7nMm"))})
        outputs = PromptGuardAdapter(worker).run_session(_session(first, second))
        self.assertEqual(outputs[1].text, "🔐 echo [PASSWORD_1] B_PASSWORD=[PASSWORD_2] [PASSWORD_1]\n")
        self.assertEqual([edit.replacement for edit in outputs[1].edits], ["[PASSWORD_1]", "[PASSWORD_2]", "[PASSWORD_1]"])
        self.assertEqual(verify(second, outputs[1].text, outputs[1].edits), outputs[1].edits)

    def test_remask_inside_a_placeholder_is_one_edit(self) -> None:
        # A one-character value also matches inside the placeholders already written, as in the mod.
        text = "A=Qw3rTy9uIo\n"
        worker = ScriptedWorker({text: found(finding(text, "Qw3rTy9uIo"), finding(text, "A", "api key"))})
        output = PromptGuardAdapter(worker).run_session(_session(text))[0]
        self.assertEqual(output.text, "[[API_KEY_1]PI_KEY_1]=[P[API_KEY_1]SSWORD_1]\n")
        self.assertEqual(verify(text, output.text, output.edits), output.edits)

    def test_fault_injection_mode_is_refused(self) -> None:
        with patch.dict(os.environ, {"PG_DETECTOR_MODE": "crash"}), self.assertRaises(ValueError):
            PromptGuardAdapter(ScriptedWorker({}))


if __name__ == "__main__":
    unittest.main()


class BlockOnFailureTests(unittest.TestCase):
    """The default, Runtime V1: the Final Guard blocks a request whose detector call fails, so the item reaches
    the model as nothing; scored as one edit over the whole text."""

    TEXT = "DB_PASSWORD=mysecret123\n"

    def _run(self, result):
        adapter = PromptGuardAdapter(ScriptedWorker({self.TEXT: result}))
        return adapter, adapter.run_session(_session(self.TEXT))[0]

    def test_failure_masks_the_whole_item(self) -> None:
        adapter, output = self._run(RuntimeError("ml-v9 timed out"))
        self.assertEqual(output.text, BLOCKED)
        self.assertEqual(verify(self.TEXT, output.text, output.edits), output.edits)
        described = adapter.describe()
        self.assertEqual((described["on_detector_failure"], described["blocked_items"],
                          described["failed_open_items"]), ("block", 1, 0))

    def test_gold_in_a_blocked_item_is_over_masked_not_exposed(self) -> None:
        _adapter, output = self._run({"ok": False, "findings": [], "errors": ["ADAPTER_FAILURE:ml-v9"]})
        start = self.TEXT.index("mysecret123")
        gold = [GoldSpan(0, 0, start, start + len("mysecret123"), "PASSWORD")]
        score = score_item("x", 0, "tool_output", self.TEXT, output.text, output.edits, gold)
        self.assertEqual([result.status for result in score.gold_results], [SpanStatus.OVER])

    def test_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            PromptGuardAdapter(ScriptedWorker({}), on_failure="ignore")


class RequiredAdaptersTests(unittest.TestCase):
    @staticmethod
    def _worker(description):
        worker = ScriptedWorker({})
        make = worker.load_detector

        def load_detector():
            detector = make()
            detector.describe = lambda: description
            return detector

        worker.load_detector = load_detector
        return worker

    def test_running_adapter_passes(self) -> None:
        worker = self._worker({"adapters": [{"name": "credsweeper"}, {"name": "ml-v9"}], "skipped": []})
        PromptGuardAdapter(worker, required_adapters=["ml-v9"])

    def test_skipped_adapter_stops_with_the_system_reason(self) -> None:
        worker = self._worker({"adapters": [{"name": "credsweeper"}],
                               "skipped": [{"name": "ml-v9", "reason": "v9 dependencies are not installed"}]})
        with self.assertRaisesRegex(ValueError, r"ml-v9 \(v9 dependencies are not installed\)"):
            PromptGuardAdapter(worker, required_adapters=["ml-v9"])
        with self.assertRaisesRegex(ValueError, r"ml-qwen \(not configured\)"):
            PromptGuardAdapter(worker, required_adapters=["ml-qwen"])
