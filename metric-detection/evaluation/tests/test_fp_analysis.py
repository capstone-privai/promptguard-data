"""evaluation.report.fp_analysis on a hand-made run folder: per-rule counts, union reproduction, FP types."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.report.fp_analysis import ALL_RULES, analyse, classify_fp, write

TEXT = "DB_PASSWORD=Zx9vQ2mLp7\nport=5432\nAPI_TOKEN=${API_TOKEN}\nkey=EXAMPLEKEY12345\nsecond=Zx9vQ2mLp7\n"


def _at(value: str, nth: int = 0) -> tuple[int, int]:
    start = -1
    for _ in range(nth + 1):
        start = TEXT.index(value, start + 1)
    return start, start + len(value)


GOLD = _at("Zx9vQ2mLp7")


def _finding(adapter: str, rule: str, span: tuple[int, int], valid: bool = True) -> dict:
    overlaps = span[0] < GOLD[1] and GOLD[0] < span[1]
    within = GOLD[0] <= span[0] and span[1] <= GOLD[1]
    return {"session_id": "s", "item_id": 0, "channel": "tool_output", "scored": True, "adapter": adapter,
            "rule_id": rule, "type": "PASSWORD", "start": span[0], "end": span[1], "confidence": "strong",
            "score": None, "valid": valid, "overlaps_gold": overlaps, "within_gold": within,
            "gold_span_ids": [0] if overlaps else [], "item_blocked": False}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_run(root: Path, edits: list[tuple[int, int]]) -> Path:
    data, answer, run = root / "data_test", root / "data_answer", root / "runs" / "r1"
    for folder in (data, answer, run):
        folder.mkdir(parents=True)
    _write_jsonl(data / "sessions_2.jsonl", [{"session_id": "s", "items": [
        {"item_id": 0, "turn_id": "t0", "channel": "tool_output", "text": TEXT}], "meta": {}}])
    _write_jsonl(answer / "gold_2.jsonl", [{"session_id": "s", "item_id": 0, "span_id": 0,
                                            "span": {"start": GOLD[0], "end": GOLD[1], "type": "PASSWORD"}}])
    describe = {"adapters": [{"name": "credsweeper", "version": "1.19.0"}, {"name": "ml-v9", "version": "v9:abc"}],
                "skipped": []}
    (run / "run_meta.json").write_text(json.dumps({"system": {"system": "promptguard", "detector": describe},
                                                   "dataset": {"sessions_path": str(data / "sessions_2.jsonl")}}))
    findings = [
        _finding("credsweeper", "Password", GOLD),                   # tp, found with ml-v9 → no solo gold
        _finding("ml-v9", "ml_v9-span", GOLD),                       # tp
        _finding("credsweeper", "Token", _at("5432")),               # fp, solo
        _finding("credsweeper", "Key", _at("${API_TOKEN}")),         # fp, shared with ml-v9 below
        _finding("ml-v9", "ml_v9-span", (_at("${API_TOKEN}")[0] + 2, _at("${API_TOKEN}")[1])),  # fp, shared
        _finding("ml-v9", "ml_v9-span", _at("EXAMPLEKEY12345")),     # fp, solo
        _finding("credsweeper", "PEM Private Key", (-1, -1), valid=False),
    ]
    _write_jsonl(run / "per_finding.jsonl", findings)
    _write_jsonl(run / "per_span.jsonl", [{"session_id": "s", "item_id": 0, "span_id": 0, "start": GOLD[0],
                                           "end": GOLD[1], "type": "PASSWORD", "channel": "tool_output",
                                           "scored": True, "status": "exact", "exposed_chars": 0}])
    _write_jsonl(run / "per_edit.jsonl", [{"session_id": "s", "item_id": 0, "start": s, "end": e,
                                           "channel": "tool_output", "scored": True,
                                           "overlaps_gold": s < GOLD[1] and GOLD[0] < e,
                                           "within_gold": GOLD[0] <= s and e <= GOLD[1]} for s, e in edits])
    _write_jsonl(run / "per_scan.jsonl", [{"session_id": "s", "item_id": 0, "channel": "tool_output", "scored": True,
                                           "collected": True, "findings": len(findings), "adapter_errors": [],
                                           "failure": None, "blocked": False}])
    return root


class FpAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _analyse(self, edits: list[tuple[int, int]]) -> dict:
        make_run(self.root, edits)
        return analyse([("cfg", [self.root / "runs"])], self.root / "data_test", self.root / "data_answer",
                       self.root)

    def test_rule_counts(self) -> None:
        edits = [GOLD, _at("5432"), _at("${API_TOKEN}"), _at("EXAMPLEKEY12345")]
        out = self._analyse(edits)
        rows = {(r["adapter"], r["rule_id"]): r for r in out["rules"] if r["dataset"] == "sessions_2"}
        self.assertEqual({k: (r["findings"], r["tp"], r["fp"], r["solo_fp"], r["shared_fp"], r["solo_gold"])
                          for k, r in rows.items()}, {
            ("credsweeper", "Password"): (1, 1, 0, 0, 0, 0),
            ("credsweeper", "Token"): (1, 0, 1, 1, 0, 0),
            ("credsweeper", "Key"): (1, 0, 1, 0, 1, 0),
            ("credsweeper", "PEM Private Key"): (0, 0, 0, 0, 0, 0),
            ("ml-v9", "ml_v9-span"): (3, 1, 2, 1, 1, 0),
            ("credsweeper", ALL_RULES): (3, 1, 2, 1, 1, 0),
            ("ml-v9", ALL_RULES): (3, 1, 2, 1, 1, 0),
        })
        self.assertEqual(rows[("ml-v9", "ml_v9-span")]["model"], "v9:abc")
        self.assertEqual(rows[("credsweeper", "PEM Private Key")]["invalid_spans"], 1)
        self.assertAlmostEqual(rows[("ml-v9", "ml_v9-span")]["precision"], 1 / 3)

    def test_union_is_reproduced_and_remask_reported(self) -> None:
        # The run also has a remask edit over the second "Zx9vQ2mLp7" that no adapter reported.
        edits = [GOLD, _at("5432"), _at("${API_TOKEN}"), _at("EXAMPLEKEY12345"), _at("Zx9vQ2mLp7", 1)]
        (union,) = [r for r in self._analyse(edits)["union"] if r["dataset"] == "sessions_2"]
        self.assertEqual((union["edits"], union["edits_tp"], union["edits_fp"], union["exact"], union["fn"]),
                         (5, 1, 4, 1, 0))
        self.assertEqual((union["findings_edits"], union["findings_edits_tp"], union["findings_edits_fp"]), (4, 1, 3))
        self.assertEqual((union["edits_same"], union["edits_only_in_run"], union["remask_fp"],
                          union["edits_only_in_findings"], union["gold_status_differs"]), (4, 1, 1, 0, 0))

    def test_fp_types_and_outputs_hold_no_text(self) -> None:
        out = self._analyse([GOLD, _at("5432"), _at("${API_TOKEN}"), _at("EXAMPLEKEY12345")])
        types = {r["type"]: r["fp_spans"] for r in out["fp_types"] if r["dataset"] == "sessions_2"}
        self.assertEqual(types, {"digits only": 1, "variable or attribute reference": 2,
                                 "example, test or dummy value": 1})
        write(out, self.root / "out")
        for path in (self.root / "out").iterdir():
            content = path.read_text(encoding="utf-8")
            for value in ("Zx9vQ2mLp7", "5432", "API_TOKEN}", "EXAMPLEKEY12345"):
                self.assertNotIn(value, content, path.name)
        with (self.root / "out" / "rules.csv").open(encoding="utf-8") as handle:
            self.assertTrue(any(row["rule_id"] == "Token" for row in csv.DictReader(handle)))

    def test_classify_fp(self) -> None:
        def kind(value: str, line: str = "x={}\n", gold: set[str] = frozenset()) -> str:
            text = line.format(value)
            start = text.index(value)
            return classify_fp(text, start, start + len(value), set(gold))

        self.assertEqual(kind("8080"), "digits only")
        self.assertEqual(kind("$DB_PASS"), "variable or attribute reference")
        self.assertEqual(kind("self.api_key"), "variable or attribute reference")
        self.assertEqual(kind("<your-token>"), "template or placeholder")
        self.assertEqual(kind("********"), "redaction or mask mark")
        self.assertEqual(kind("AKIAIOSFODNN7EXAMPLE"), "example, test or dummy value")
        self.assertEqual(kind("3f6c2a9e-8b1d-4c2e-9a7f-1b2c3d4e5f60"), "UUID")
        self.assertEqual(kind("da39a3ee5e6b4b0d3255bfef95601890afd80709"), "hex digest (hash, commit id)")
        self.assertEqual(kind("2026-10-04"), "number, date, version or IP")
        self.assertEqual(kind("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"), "JWT-like")
        self.assertEqual(kind("getPassword("), "code expression or type")
        self.assertEqual(kind("$HOME/.secrets"), "variable or attribute reference")
        self.assertEqual(kind("aB3dE5fG7hJ9kL1mN3pQ5rS7", "AUTH0_CLIENT_ID={}\n"),
                         "identifier by key name (client id, user, account)")
        self.assertEqual(kind("aB3dE5fG7hJ9kL1mN3pQ5rS7", "api_key={}\n"), "random-looking string (16+ chars)")
        self.assertEqual(kind("password:", "label={}\n"), "word or identifier")
        self.assertEqual(kind("hunter2pass", gold={"hunter2pass"}), "same value as a gold span in the session")
        self.assertEqual(kind("MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA",
                              "-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n"),
                         "public key or certificate material")


if __name__ == "__main__":
    unittest.main()
