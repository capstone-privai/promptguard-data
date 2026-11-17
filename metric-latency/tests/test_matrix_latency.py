"""matrix_latency: 4 KB inputs, percentiles, cell selection and the summary table. No detector is loaded.

  python3 -m unittest discover -s metric-latency/tests
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import matrix_latency as ml  # noqa: E402


def session(items):
    return json.dumps({"session_id": "s", "items": [{"item_id": i, "turn_id": "t", "channel": c, "text": t}
                                                    for i, (c, t) in enumerate(items)]})


class InputTests(unittest.TestCase):
    def test_cut_utf8_is_exactly_the_size(self) -> None:
        text = "가" * 2000  # 3 bytes each: 4096 is not a multiple of 3
        cut = ml.cut_utf8(text.encode(), 4096)
        self.assertEqual(len(cut.encode("utf-8")), 4096)
        self.assertTrue(cut.startswith("가" * 1365))
        self.assertEqual(ml.cut_utf8(b"a" * 5000, 4096), "a" * 4096)

    def test_eval_windows_scored_channels_only_and_seeded(self) -> None:
        line = "x" * 99 + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            path.write_text("\n".join([
                session([("prompt", "short"), ("tool_output", "가나다\n" + line * 60)]),
                session([("tool_input", line * 80), ("instructions", line * 50)]),
            ]) + "\n", encoding="utf-8")
            texts, info = ml.eval_windows(path, 30, seed=1)
            again, _ = ml.eval_windows(path, 30, seed=1)
            other, _ = ml.eval_windows(path, 30, seed=2)
        self.assertEqual(texts, again)
        self.assertNotEqual(texts, other)
        self.assertEqual(info["eligible_items"], 2)  # tool_input is not scored, the prompt is too short
        self.assertEqual({source for _, source in texts}, {"tool_result", "claude_md"})
        self.assertTrue(all(len(text.encode("utf-8")) == 4096 for text, _ in texts))
        self.assertLessEqual(info["distinct_windows"], 30)

    def test_eval_windows_needs_a_long_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            path.write_text(session([("prompt", "short")]) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ml.eval_windows(path, 3)

    def test_synthetic_workload(self) -> None:
        texts, info = ml.build_workload("synthetic", 5, 0)
        self.assertEqual(info["kind"], "synthetic")
        self.assertTrue(all(len(t.encode("utf-8")) == 4096 and s == "tool_result" for t, s in texts))
        self.assertEqual(len({t for t, _ in texts}), 5)
        self.assertEqual(info["fingerprint"], ml.build_workload("synthetic", 5, 0)[1]["fingerprint"])
        self.assertNotEqual(info["fingerprint"], ml.build_workload("synthetic", 5, 1)[1]["fingerprint"])

    def test_auto_falls_back_to_synthetic(self) -> None:
        _, info = ml.build_workload("auto", 2, 0, eval_set=Path("/nonexistent/sessions.jsonl"))
        self.assertEqual(info["kind"], "synthetic")


class PercentileTests(unittest.TestCase):
    def test_nearest_rank(self) -> None:
        values = [float(v) for v in range(100, 0, -1)]  # 1..100, unsorted
        self.assertEqual(ml.percentiles(values), {"p50": 50.0, "p90": 90.0, "p95": 95.0, "p99": 99.0})
        self.assertEqual(ml.percentiles([7.0]), {"p50": 7.0, "p90": 7.0, "p95": 7.0, "p99": 7.0})
        self.assertEqual(ml.percentiles(list(range(1, 1001)))["p99"], 990)


def fake_commits():
    def commit(sha, date, models, subject):
        return {"sha": sha * 7 + "abc", "time": datetime.fromisoformat(date + "T00:00+09:00"), "date": date,
                "subject": subject, "ml_adapters": [], "models": models}
    return [commit("1", "2026-10-01", ["base"], "first"),
            commit("2", "2026-11-01", ["base", "v10"], "Merge pull request #9 from x/y")]


def ok(p):
    return {"status": "ok", "calls": 10, "failed_calls": 0,
            "latency_ms": {"p50": p, "p90": p + 1, "p95": p + 2, "p99": p + 3, "mean": p, "min": p, "max": p + 3}}


class TableTests(unittest.TestCase):
    def test_cells_and_selection(self) -> None:
        cells = ml.matrix_cells(fake_commits())
        self.assertEqual([c["key"] for c in cells], ["prototype", "1111111/base", "2222222/base", "2222222/v10"])
        self.assertEqual([c["key"] for c in ml.select_cells(cells, ["prototype", "2222/v10"])], ["prototype", "2222222/v10"])
        self.assertEqual([c["key"] for c in ml.select_cells(cells, ["*/base"])], ["1111111/base", "2222222/base"])
        self.assertEqual([c["key"] for c in ml.select_cells(cells, ["2"])], ["2222222/base", "2222222/v10"])
        with self.assertRaises(ValueError):
            ml.select_cells(cells, ["1111111/v10"])
        self.assertEqual(ml.cell_file("2222222/v10"), "2222222__v10.json")

    def test_table_layout(self) -> None:
        records = {"prototype": ok(0.5), "2222222/base": ok(25.0),
                   "2222222/v10": {"status": "skipped", "reason": "model missing"}}
        md = ml.table(fake_commits(), ["base", "v10", "qwen"], records)
        rows = [line for line in md.splitlines() if line.startswith("| ")]
        self.assertEqual(rows[0], "| 시스템 | 날짜 | base | v10 | qwen |")
        self.assertEqual(rows[1], f"| prototype {ml.PROTOTYPE_LABEL} |  | 0.50 / 1.50 / 2.50 / 3.50 | - | - |")
        self.assertEqual(rows[2], "| 1111111 first | 2026-10-01 | (not run) | - | - |")
        self.assertEqual(rows[3], "| 2222222 #9 | 2026-11-01 | 25.0 / 26.0 / 27.0 / 28.0 | (skipped) | - |")
        self.assertIn("2222222/v10: model missing", md)

    def test_csv_rows_follow_the_matrix(self) -> None:
        records = {"2222222/v10": ok(5.0), "prototype": ok(1.0)}
        rows = ml.csv_rows(fake_commits(), records)
        self.assertEqual([r["cell"] for r in rows], ["prototype", "2222222/v10"])
        self.assertEqual(rows[1]["p99_ms"], 8.0)
        self.assertEqual(rows[1]["date"], "2026-11-01")
        self.assertEqual(set(rows[0]), set(ml.CSV_FIELDS))


class MatrixImportTests(unittest.TestCase):
    def test_uses_the_matrix_definition(self) -> None:
        cm = ml.matrix_module()
        self.assertEqual(set(ml.WEIGHTS_SHA256), set(cm.MODELS))
        self.assertTrue(set(ml.TOKEN_BUNDLES) <= set(cm.MODELS))


if __name__ == "__main__":
    unittest.main()
