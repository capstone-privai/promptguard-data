"""metric-task batches are read from batch.json and runs.csv only, old and new runs.csv layouts alike."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import task  # noqa: E402

NEW_FIELDS = ["task", "suite", "family", "category", "channels", "needs_secret_value", "condition", "rep", "valid",
              "success", "task_ok", "integrity_ok", "secrets_seen", "secrets_written", "tool_inputs_with_placeholder",
              "server_leaked", "server_secrets_total", "server_channels", "server_tools", "server_encoded_only",
              "server_partial_only", "server_requests", "masked_findings", "mod_failures", "num_turns", "cost_usd",
              "elapsed_s", "model", "error"]
OLD_FIELDS = ["task", "category", "needs_secret_value", "condition", "rep", "valid", "success", "task_ok",
              "integrity_ok", "secrets_seen", "secrets_written", "tool_inputs_with_placeholder", "masked_findings",
              "mod_failures", "num_turns", "cost_usd", "elapsed_s", "model", "error"]


def row(task_id, category, condition, rep, success, seen=0, leaked=0, valid=True):
    return {"task": task_id, "suite": "core", "family": "", "category": category, "channels": "file",
            "needs_secret_value": str(category in ("use", "property")), "condition": condition, "rep": str(rep),
            "valid": str(valid), "success": str(success), "task_ok": str(success), "integrity_ok": "True",
            "secrets_seen": str(seen), "secrets_written": "0", "tool_inputs_with_placeholder": "0",
            "server_leaked": str(leaked), "server_secrets_total": "2", "server_channels": "", "server_tools": "",
            "server_encoded_only": "0", "server_partial_only": "0", "server_requests": "4", "masked_findings": "1",
            "mod_failures": "0", "num_turns": "3", "cost_usd": "0.05", "elapsed_s": "10", "model": "claude-sonnet-5-5",
            "error": "" if valid else "API Error: 429"}


def write_batch(folder: Path, rows, fields, capture=True, commit="a" * 40):
    folder.mkdir(parents=True)
    (folder / "batch.json").write_text(json.dumps({"started_at": "2026-10-16T10:00:00", "model": "sonnet", "reps": 2,
                                                   "system_commit": commit, "data_commit": "b" * 40,
                                                   "capture": capture}), encoding="utf-8")
    with (folder / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (folder / "t01" / "promptguard-r1").mkdir(parents=True)
    (folder / "t01" / "promptguard-r1" / "transcript.jsonl").write_text("SECRET-VALUE-NEVER-READ", encoding="utf-8")


class TaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        rows = []
        for rep in (1, 2):
            rows += [row("t01", "diagnose", "none", rep, True, seen=1, leaked=1),
                     row("t01", "diagnose", "gold", rep, True),
                     row("t01", "diagnose", "promptguard", rep, True),
                     row("t15", "identity", "none", rep, True, seen=2, leaked=2),
                     row("t15", "identity", "gold", rep, True),
                     row("t15", "identity", "promptguard", rep, rep == 1, seen=1, leaked=1)]
        rows.append(row("t15", "identity", "promptguard", 3, False, valid=False))
        write_batch(self.root / "runs" / "new_batch", rows, NEW_FIELDS)
        write_batch(self.root / "runs" / "old_batch", rows, OLD_FIELDS, capture=False, commit="c" * 40)
        (self.root / "runs" / "half_written").mkdir()
        (self.root / "runs" / "half_written" / "batch.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_summary(self):
        summary = task.summarize(self.root / "runs" / "new_batch")
        self.assertTrue(summary["captured"])
        self.assertEqual(summary["conditions"], ["none", "gold", "promptguard"])
        self.assertEqual((summary["runs"], summary["valid"], summary["tasks"]), (13, 12, 2))
        pg = summary["by_condition"]["promptguard"]
        self.assertEqual((pg["runs"], pg["success"], pg["seen"], pg["leaked"]), (4, 3, 2, 2))
        self.assertEqual(summary["by_condition"]["none"]["leaked_rate"], 1.0)
        identity = next(item for item in summary["by_category"] if item["key"] == "identity")
        self.assertEqual(identity["conditions"]["promptguard"]["success_rate"], 0.5)
        t15 = next(item for item in summary["by_task"] if item["task"] == "t15")
        self.assertEqual(t15["marks"]["promptguard"], ["O*", "X*"])
        self.assertEqual(t15["rates"], {"none": 1.0, "gold": 1.0, "promptguard": 0.5})
        self.assertEqual(summary["invalid"], [{"task": "t15", "condition": "promptguard", "rep": 3, "error": "API Error: 429"}])

    def test_old_layout_has_no_server_numbers(self):
        summary = task.summarize(self.root / "runs" / "old_batch")
        self.assertFalse(summary["captured"])
        self.assertNotIn("leaked_rate", summary["by_condition"]["promptguard"])
        self.assertEqual(summary["by_condition"]["promptguard"]["success"], 3)

    def test_collect_writes_once_and_skips_incomplete_folders(self):
        results = self.root / "results"
        entries = task.collect([self.root / "runs"], results)
        self.assertEqual(sorted(entry["name"] for entry in entries), ["new_batch", "old_batch"])
        for entry in entries:
            text = (results / entry["key"] / "task.json").read_text(encoding="utf-8")
            self.assertNotIn("SECRET-VALUE-NEVER-READ", text)
        self.assertEqual(task.collect([self.root / "runs"], results), entries)  # stable keys, cached summaries
        with (self.root / "runs" / "new_batch" / "runs.csv").open("a", encoding="utf-8") as handle:
            handle.write("t02,core,,diagnose,file,False,none,1,True,True,True,True,0,0,0,0,0,,,0,0,1,0,0,1,0.01,1,m,\n")
        self.assertNotEqual({entry["key"] for entry in task.collect([self.root / "runs"], results)},
                            {entry["key"] for entry in entries})  # a changed batch is read again


if __name__ == "__main__":
    unittest.main()
