from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation.adapters.gitleaks_adapter import REPLACEMENT, GitleaksAdapter
from evaluation.dataset.io import file_sha256, load_sessions
from evaluation.run import evaluate
from evaluation.tests.support import GOLD, SESSIONS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from run_gitleaks import locate  # noqa: E402


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def write_findings(directory: Path, rows: list[dict], sessions: Path = SESSIONS,
                   channels: tuple[str, ...] = ("tool_output",)) -> Path:
    path = directory / "findings.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    meta = {"gitleaks_version": "test", "sessions": str(sessions), "sessions_sha256": file_sha256(sessions),
            "channels": list(channels)}
    Path(f"{path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return path


class GitleaksAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_replays_findings_as_edits(self) -> None:
        gold = records(GOLD)
        rows = [{"session_id": g["session_id"], "item_id": g["item_id"], "rule_id": "test", **g["span"]} for g in gold]
        for row in rows:
            del row["type"]
        rows.append(dict(rows[0]))  # duplicate findings collapse into one edit
        metrics = evaluate(SESSIONS, GOLD, GitleaksAdapter(write_findings(self.dir, rows), SESSIONS)).metrics
        channels = {(s["session_id"], i["item_id"]): i["channel"] for s in records(SESSIONS) for i in s["items"]}
        scanned = sum(channels[(g["session_id"], g["item_id"])] == "tool_output" for g in gold)
        self.assertEqual(metrics["counts"]["edits_total"], scanned)  # only the scanned channel is masked
        self.assertEqual(metrics["precision"], 1.0)

    def test_replacement_and_describe(self) -> None:
        g = records(GOLD)[0]
        row = {"session_id": g["session_id"], "item_id": g["item_id"], "start": g["span"]["start"],
               "end": g["span"]["end"], "rule_id": "test"}
        adapter = GitleaksAdapter(write_findings(self.dir, [row], channels=("prompt", "instructions", "tool_input", "tool_output")), SESSIONS)
        session = next(s for s in load_sessions(SESSIONS, GOLD) if s.session_id == g["session_id"])
        output = adapter.run_session(session)[g["item_id"]]
        self.assertEqual(len(output.edits), 1)
        self.assertIn(REPLACEMENT, output.text)
        self.assertIsNone(output.elapsed_ms)
        self.assertEqual(adapter.describe()["system"], "gitleaks")

    def test_rejects_findings_from_another_sessions_file(self) -> None:
        other = self.dir / "sessions_other.jsonl"
        other.write_text(SESSIONS.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different sessions file"):
            GitleaksAdapter(write_findings(self.dir, [], sessions=other), SESSIONS)
        with self.assertRaisesRegex(ValueError, "missing"):
            GitleaksAdapter(self.dir / "absent.jsonl", SESSIONS)


class LocateTests(unittest.TestCase):
    TEXT = "a\nDB_PASSWORD=mysecret123\nb DB_PASSWORD=mysecret123\n"

    def test_secret_in_reported_lines_only(self) -> None:
        finding = {"StartLine": 2, "EndLine": 2, "Secret": "mysecret123", "Match": "DB_PASSWORD=mysecret123"}
        self.assertEqual(locate(self.TEXT, finding), [(14, 25)])
        finding = {**finding, "StartLine": 2, "EndLine": 3}
        self.assertEqual(locate(self.TEXT, finding), [(14, 25), (40, 51)])

    def test_decoded_secret_is_located_as_its_encoded_token(self) -> None:
        token = base64.b64encode(b"DB_PASSWORD=mysecret123").decode()
        text = f"kind: Secret\ndata:\n  env: {token}\n"
        start = text.index(token)
        finding = {"StartLine": 3, "EndLine": 3, "Secret": "mysecret123", "Match": "DB_PASSWORD=mysecret123"}
        self.assertEqual(locate(text, finding), [(start, start + len(token))])

    def test_unlocatable(self) -> None:
        self.assertEqual(locate(self.TEXT, {"StartLine": 1, "EndLine": 1, "Secret": "mysecret123", "Match": "x"}), [])
        self.assertEqual(locate(self.TEXT, {"StartLine": 9, "EndLine": 9, "Secret": "mysecret123", "Match": "x"}), [])


if __name__ == "__main__":
    unittest.main()
