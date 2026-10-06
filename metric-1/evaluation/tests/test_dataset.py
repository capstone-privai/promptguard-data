from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.dataset.io import file_sha256, gold_path_for, load_sessions
from evaluation.dataset.validate import validate_dataset
from evaluation.run import DatasetInvalidError, load_dataset
from evaluation.tests.support import GOLD, SESSIONS

ITEM = {"item_id": 0, "turn_id": "t0", "channel": "tool_output", "text": "DB_PASSWORD=mysecret123\n"}


def _session(session_id: str = "s1", **overrides):
    record = {"session_id": session_id, "items": [dict(ITEM)],
              "meta": {"origin": "authored", "allowed_use": ["rule_eval", "ml_eval", "ml_train"]}}
    record.update(overrides)
    return record


def _gold(session_id: str = "s1", item_id=0, span_id=0, start=12, end=23, kind="PASSWORD", **overrides):
    row = {"session_id": session_id, "item_id": item_id, "span_id": span_id,
           "span": {"start": start, "end": end, "type": kind}}
    row.update(overrides)
    return row


class DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _write(self, sessions: list, gold: list) -> tuple[Path, Path]:
        root = Path(self._tmp.name)
        paths = root / "sessions.jsonl", root / "gold.jsonl"
        for path, rows in zip(paths, (sessions, gold)):
            lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
            path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return paths

    def _issues(self, sessions: list, gold: list) -> list[str]:
        return [str(issue) for issue in validate_dataset(*self._write(sessions, gold))]

    def test_fixture_is_valid_and_loads(self) -> None:
        self.assertEqual(validate_dataset(SESSIONS, GOLD), [])
        sessions = load_sessions(SESSIONS, GOLD)
        self.assertEqual(len(sessions), 8)
        first = sessions[0]
        self.assertEqual([item.channel for item in first.items], ["prompt", "instructions", "tool_output"])
        texts = {item.item_id: item.text for item in first.items}
        self.assertEqual([texts[span.item_id][span.start : span.end] for span in first.gold_for(2)],
                         ["mysecret123", "secret123"])
        self.assertEqual([span.span_id for span in first.gold_for(2)], [0, 1])
        self.assertEqual(sessions[2].gold, [])  # sessions without gold rows load with no spans
        self.assertEqual(first.meta["source"], "fixture")
        self.assertEqual(len(file_sha256(SESSIONS)), 64)

    def test_gold_path_for(self) -> None:
        self.assertEqual(gold_path_for(Path("metric-1/data_test/sessions_from_X.jsonl")),
                         Path("metric-1/data_answer/gold_from_X.jsonl"))
        self.assertEqual(gold_path_for(SESSIONS), GOLD)
        with self.assertRaises(ValueError):
            gold_path_for("other.jsonl")

    def test_valid_minimal_pair(self) -> None:
        self.assertEqual(self._issues([_session()], [_gold()]), [])

    def test_item_ids_are_per_session(self) -> None:
        self.assertEqual(self._issues([_session("s1"), _session("s2")], [_gold("s1"), _gold("s2")]), [])

    def test_each_error_kind_is_reported(self) -> None:
        cases = {
            "invalid JSON": (["{not json"], []),
            "missing or invalid 'session_id'": ([_session(session_id="")], []),
            "missing or invalid 'items'": ([{"session_id": "s1"}], []),
            "must not contain 'gold'": ([_session(gold=[])], []),
            "missing or invalid 'text'": ([_session(items=[{**ITEM, "text": 5}])], []),
            "missing or invalid 'item_id'": ([_session(items=[{**ITEM, "item_id": "0"}])], []),
            "duplicate session_id": ([_session(), _session()], []),
            "duplicate item_id": ([_session(items=[ITEM, ITEM])], []),
            "invalid channel": ([_session(items=[{**ITEM, "channel": "stdout"}])], []),
            "no sessions": ([], []),
            "invalid type": ([_session()], [_gold(kind="IP")]),
            "session_id not in the sessions file": ([_session()], [_gold("s9")]),
            "item_id not in this session": ([_session()], [_gold(item_id=9)]),
            "duplicate span_id": ([_session()], [_gold(end=15), _gold(start=16)]),
            "missing or invalid 'span_id'": ([_session()], [_gold(span_id=None)]),
            "missing or invalid 'span'": ([_session()], [_gold(span=[12, 23])]),
            "outside text": ([_session()], [_gold(end=99)]),
            "is empty": ([_session()], [_gold(end=12)]),
            "must be integers": ([_session()], [_gold(start="12")]),
            "overlap": ([_session()], [_gold(end=20), _gold(span_id=1, start=18)]),
        }
        for expected, (sessions, gold) in cases.items():
            with self.subTest(expected):
                messages = self._issues(sessions, gold)
                self.assertTrue(any(expected in message for message in messages), messages)

    def test_adjacent_gold_spans_are_allowed(self) -> None:
        self.assertEqual(self._issues([_session()], [_gold(end=18), _gold(span_id=1, start=18)]), [])

    def test_all_issues_are_collected_with_location(self) -> None:
        bad = _session(items=[{**ITEM, "channel": "browser", "text": "abc"}])
        issues = self._issues([bad, "{oops"], [_gold(end=9, kind="IP")])
        self.assertGreaterEqual(len(issues), 4)
        self.assertEqual(issues[0], "s1 / 0 / sessions.jsonl line 1: invalid channel; "
                                    "expected one of ['prompt', 'instructions', 'tool_input', 'tool_output']")
        self.assertTrue(any(issue.startswith("- / - / sessions.jsonl line 2") for issue in issues))
        self.assertTrue(any(issue.startswith("s1 / 0 / gold.jsonl line 1: invalid type") for issue in issues))

    def test_missing_gold_file_is_an_issue(self) -> None:
        sessions, _gold_path = self._write([_session()], [])
        issues = validate_dataset(sessions, Path(self._tmp.name) / "nope.jsonl")
        self.assertEqual([issue.message for issue in issues], ["cannot read nope.jsonl as UTF-8: FileNotFoundError"])

    def test_allowed_use_is_enforced(self) -> None:
        injected = _session("s2", meta={"origin": "injected", "allowed_use": ["rule_eval"]})
        paths = self._write([_session(), injected], [])
        self.assertEqual(len(load_dataset(*paths, "rule_eval")), 2)
        with self.assertRaises(DatasetInvalidError) as caught:
            load_dataset(*paths, "ml_eval")
        self.assertEqual([str(issue) for issue in caught.exception.issues],
                         ["s2 / - / meta.allowed_use does not include 'ml_eval'"])


if __name__ == "__main__":
    unittest.main()
