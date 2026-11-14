"""Per-adapter findings (ItemOutput.scan → per_finding.jsonl, per_scan.jsonl).

A fake detector with the ensemble's `scan` → `collect` shape checks the recording without a checkout; the real
checkout checks that the findings are in the scorer's offsets (code points) and that, merged the way the system
merges them, they give exactly the edits the run scored.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.adapters.promptguard_adapter import BLOCKED, PromptGuardAdapter
from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import GoldSpan, Item, Session
from evaluation.report.findings import match_gold, per_finding_rows, per_scan_rows
from evaluation.report.meta import build_run_meta
from evaluation.report.write import write_run
from evaluation.run import evaluate_sessions
from evaluation.tests.support import GOLD, HAS_PROMPTGUARD, SESSIONS, SKIP_REASON, utf16_len


@dataclass(frozen=True)
class Raw:  # the fields of pgdetector's RawFinding the adapter reads
    start: int
    end: int
    type: str
    rule_id: str
    confidence: str = "moderate"
    score: float | None = None


class FakeDetector:
    """`scan` calls `self.collect` and then merges the way pgdetector does (one finding per overlapping group)."""

    def __init__(self, ballots: dict[str, dict[str, list[Raw]]], errors: dict[str, list[str]]):
        self.ballots, self.errors = ballots, errors

    def describe(self) -> dict[str, Any]:
        return {"detector": "fake"}

    def collect(self, texts):
        return [self.ballots.get(text, {}) for text in texts], sorted({e for text in texts for e in self.errors.get(text, [])})

    def scan(self, text: str, source: str) -> dict[str, Any]:
        per_text, errors = self.collect([text])
        spans = sorted((f.start, f.end) for findings in per_text[0].values() for f in findings)
        merged: list[list[int]] = []
        for start, end in spans:
            if merged and start < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        findings = [{"type": "PASSWORD", "rule_id": "x", "confidence": "strong", "value_hash": text[s:e],
                     "start": utf16_len(text[:s]), "end": utf16_len(text[:e]), "offset_unit": "utf16_code_units"}
                    for s, e in merged]
        return {"ok": not errors, "findings": findings, "errors": errors}


class FakeWorker:
    def __init__(self, detector: FakeDetector):
        self.load_detector = lambda: detector


TEXT = "🔐 DB_PASSWORD=mysecret123 port=5432\n"
FAILING = "token=abcdefgh1234\n"


def _session() -> Session:
    secret = TEXT.index("mysecret123")
    return Session("s", [Item(0, "t0", "tool_output", TEXT), Item(1, "t0", "tool_input", TEXT),
                         Item(2, "t0", "tool_output", FAILING)],
                   [GoldSpan(0, 0, secret, secret + len("mysecret123"), "PASSWORD")])


def _fake_adapter() -> PromptGuardAdapter:
    secret, port = TEXT.index("mysecret123"), TEXT.index("5432")
    ballots = {
        TEXT: {"a": [Raw(secret, secret + 11, "PASSWORD", "rule-1")],
               "b": [Raw(secret - 3, secret + 11, "PASSWORD", "rule-2"), Raw(port, port + 4, "SECRET", "rule-3")]},
        FAILING: {"a": [Raw(6, 18, "TOKEN", "rule-1")]},
    }
    return PromptGuardAdapter(FakeWorker(FakeDetector(ballots, {FAILING: ["ADAPTER_FAILURE:c"]})))


class RecordedFindingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = evaluate_sessions([_session()], _fake_adapter())
        cls.rows = per_finding_rows(cls.result)
        cls.scans = per_scan_rows(cls.result)

    def test_rows_keep_each_adapter_span_in_code_points(self) -> None:
        secret, port = TEXT.index("mysecret123"), TEXT.index("5432")
        found = {(row["item_id"], row["adapter"], row["rule_id"], row["start"], row["end"]) for row in self.rows}
        self.assertEqual(found, {(0, "a", "rule-1", secret, secret + 11), (0, "b", "rule-2", secret - 3, secret + 11),
                                 (0, "b", "rule-3", port, port + 4), (2, "a", "rule-1", 6, 18)})

    def test_gold_match_is_the_scorers(self) -> None:
        by_rule = {(row["item_id"], row["rule_id"]): row for row in self.rows}
        self.assertEqual([by_rule[(0, "rule-1")][k] for k in ("overlaps_gold", "within_gold", "gold_span_ids")],
                         [True, True, [0]])
        self.assertEqual([by_rule[(0, "rule-2")][k] for k in ("overlaps_gold", "within_gold")], [True, False])
        self.assertEqual([by_rule[(0, "rule-3")][k] for k in ("overlaps_gold", "within_gold", "gold_span_ids")],
                         [False, False, []])

    def test_tool_input_is_not_scanned_or_recorded(self) -> None:
        self.assertIsNone(self.result.outputs[("s", 1)].scan)
        self.assertEqual({row["item_id"] for row in self.scans}, {0, 2})

    def test_failed_item_is_blocked_and_keeps_its_findings(self) -> None:
        output = self.result.outputs[("s", 2)]
        self.assertEqual(output.text, BLOCKED)
        scan = {row["item_id"]: row for row in self.scans}
        self.assertEqual((scan[2]["adapter_errors"], scan[2]["blocked"]), (["ADAPTER_FAILURE:c"], True))
        self.assertEqual((scan[0]["adapter_errors"], scan[0]["blocked"], scan[0]["findings"]), ([], False, 3))
        self.assertTrue(all(row["item_blocked"] == (row["item_id"] == 2) for row in self.rows))

    def test_scan_itself_is_unchanged(self) -> None:
        # The edits come from the detector's own scan; the recording only reads what collect returned.
        secret = TEXT.index("mysecret123")
        self.assertEqual([(e.start, e.end) for e in self.result.outputs[("s", 0)].edits],
                         [(secret - 3, secret + 11), (TEXT.index("5432"), TEXT.index("5432") + 4)])

    def test_invalid_span_is_recorded_but_not_matched(self) -> None:
        self.assertEqual(match_gold(0, 4, [GoldSpan(0, 7, 2, 6, "TOKEN")]), (True, False, [7]))
        detector = FakeDetector({TEXT: {"a": [Raw(-1, -1, "CREDENTIAL", "PEM")]}}, {})
        result = evaluate_sessions([_session()], PromptGuardAdapter(FakeWorker(detector)))
        (row,) = [row for row in per_finding_rows(result) if row["item_id"] == 0]
        self.assertEqual((row["valid"], row["overlaps_gold"], row["gold_span_ids"]), (False, False, []))

    def test_files_hold_no_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta = build_run_meta(started_at=datetime(2026, 11, 14), system=self.result.system, sessions_path=SESSIONS,
                                  gold_path=GOLD, sessions=self.result.sessions, use="rule_eval", debug=False)
            written = write_run(Path(tmp), meta=meta, result=self.result)
            self.assertIn("per_finding.jsonl", written)
            self.assertIn("per_scan.jsonl", written)
            for name in ("per_finding.jsonl", "per_scan.jsonl"):
                content = (Path(tmp) / name).read_text(encoding="utf-8")
                for value in ("mysecret123", "abcdefgh1234", "5432", "DB_PASSWORD"):
                    self.assertNotIn(value, content, name)

    def test_detector_without_collect_records_nothing(self) -> None:
        from evaluation.tests.support import ScriptedWorker

        adapter = PromptGuardAdapter(ScriptedWorker({}))
        self.assertFalse(adapter.records_findings)
        result = evaluate_sessions([_session()], adapter)
        self.assertTrue(all(output.scan is None for output in result.outputs.values()))
        self.assertEqual(per_finding_rows(result), [])


def merged_spans(findings: list[dict[str, Any]], length: int) -> list[tuple[int, int]]:
    """pgdetector core.normalize's merge on valid spans: sorted, a span that starts before the previous end joins it."""
    spans = sorted({(f["start"], f["end"]) for f in findings if 0 <= f["start"] < f["end"] <= length})
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


@unittest.skipUnless(HAS_PROMPTGUARD, SKIP_REASON)
class CheckoutFindingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sessions = load_sessions(SESSIONS, GOLD)
        cls.result = evaluate_sessions(cls.sessions, PromptGuardAdapter())
        cls.rows = per_finding_rows(cls.result)

    def test_findings_are_code_point_offsets(self) -> None:
        text = "🔐 DB_PASSWORD=mysecret123\n"
        result = evaluate_sessions([Session("u", [Item(0, "t0", "tool_output", text)], [])], PromptGuardAdapter())
        scan = result.outputs[("u", 0)].scan
        self.assertTrue(scan["findings"])
        start = text.index("mysecret123")
        self.assertIn((start, start + 11), {(f["start"], f["end"]) for f in scan["findings"]})

    def test_every_value_finding_names_its_adapter_and_rule(self) -> None:
        self.assertTrue(self.rows)
        for row in self.rows:
            self.assertTrue(row["adapter"] and row["rule_id"], row)
        adapters = {row["adapter"] for row in self.rows}
        self.assertTrue(adapters <= {"credsweeper", "gitleaks", "promptguard-rules", "shell-aware"}, adapters)

    def test_merged_findings_reproduce_the_scored_edits(self) -> None:
        # The fixture has no remask (a known value the detector missed), so the edits are exactly the merged findings.
        texts = {(s.session_id, i.item_id): i.text for s in self.sessions for i in s.items}
        compared = 0
        for key, output in self.result.outputs.items():
            if output.scan is None:
                continue
            spans = merged_spans(output.scan["findings"], len(texts[key]))
            self.assertEqual(spans, [(edit.start, edit.end) for edit in output.edits], key)
            compared += bool(spans)
        self.assertEqual(compared, 9)

    def test_run_folder_rows_match_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta = build_run_meta(started_at=datetime(2026, 11, 14), system=self.result.system, sessions_path=SESSIONS,
                                  gold_path=GOLD, sessions=self.sessions, use="rule_eval", debug=False)
            write_run(Path(tmp), meta=meta, result=self.result)
            lines = (Path(tmp) / "per_finding.jsonl").read_text(encoding="utf-8").splitlines()
            scans = (Path(tmp) / "per_scan.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), sum(len(o.scan["findings"]) for o in self.result.outputs.values() if o.scan))
        self.assertEqual(len(scans), sum(o.scan is not None for o in self.result.outputs.values()))
        self.assertEqual(set(json.loads(lines[0])), {
            "session_id", "item_id", "channel", "scored", "adapter", "rule_id", "type", "start", "end", "confidence",
            "score", "valid", "overlaps_gold", "within_gold", "gold_span_ids", "item_blocked"})


if __name__ == "__main__":
    unittest.main()
