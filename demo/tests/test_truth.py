"""Grading of what the Mod forwards against the showcase's real secrets (pipeline_demo.Truth).

  python3 demo/tests/test_truth.py

Needs no PromptGuard checkout: the segments are built here the way ModReplica builds them. Values are synthetic.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from pipeline_demo import SHOWCASE, ModReplica, Truth  # noqa: E402


def truth(*values: str) -> Truth:
    folder = tempfile.mkdtemp()
    path = Path(folder) / "truth.json"
    path.write_text(json.dumps({"secrets": [{"name": f"s{i}", "value": v} for i, v in enumerate(values)]}), encoding="utf-8")
    return Truth(path)


def forwarded(text: str, *masked: str) -> list:
    """The Mod's segments when the detector flagged exactly these substrings."""
    findings = []
    for value in masked:
        start = text.index(value)
        findings.append({"start": start, "end": start + len(value), "type": "SECRET", "value_hash": value})
    mod = ModReplica()
    return mod.remask(mod.redact(text, findings))


class TruthTests(unittest.TestCase):
    def test_masked_partial_leaked_and_over_masking(self) -> None:
        text = "A=SynthAlpha_11\nB=\"two words here\"\nC=SynthGamma_33\nTTL=5400\n"
        t = truth("SynthAlpha_11", "two words here", "SynthGamma_33")
        graded = t.grade(text, forwarded(text, "SynthAlpha_11", "two", "5400"), ok=True)
        self.assertEqual([(s["name"], s["status"]) for s in graded["spans"]],
                         [("s0", "masked"), ("s1", "partial"), ("s2", "leaked")])
        self.assertEqual([text[f["start"]:f["end"]] for f in graded["fp"]], ["5400"])
        self.assertEqual(t.summary(), {"total": 3, "seen": 3, "leaked": 1, "partial": 1, "error": 0, "masked": 1, "fp": 1})

    def test_wider_mask_still_counts_as_masked(self) -> None:
        text = "password=SynthWide_77 ok"
        graded = truth("SynthWide_77").grade(text, forwarded(text, "password=SynthWide_77"), ok=True)
        self.assertEqual(graded["spans"][0]["status"], "masked")
        self.assertEqual(graded["fp"], [])

    def test_worst_copy_wins_across_texts(self) -> None:
        t = truth("SynthTwice_42")
        first = "key SynthTwice_42"
        t.grade(first, forwarded(first, "SynthTwice_42"), ok=True)
        second = "again: SynthTwice_42"
        t.grade(second, [second], ok=True)  # nothing masked this time
        self.assertEqual(t.summary()["leaked"], 1)
        self.assertEqual(t.summary()["masked"], 0)

    def test_detector_failure_is_error_not_leak(self) -> None:
        text = "token SynthErr_19"
        graded = truth("SynthErr_19").grade(text, [text], ok=False)
        self.assertEqual(graded["spans"][0]["status"], "error")

    def test_offsets_are_utf16_like_the_page(self) -> None:
        text = "🔐 비밀번호는 SynthEmoji_05 야"
        span = truth("SynthEmoji_05").grade(text, forwarded(text, "SynthEmoji_05"), ok=True)["spans"][0]
        as16 = text.encode("utf-16-le")[2 * span["start"]:2 * span["end"]].decode("utf-16-le")
        self.assertEqual(as16, "SynthEmoji_05")

    def test_nothing_to_grade(self) -> None:
        self.assertIsNone(truth("SynthNone_00").grade("tests passed", ["tests passed"], ok=True))

    def test_showcase_truth_matches_its_env(self) -> None:
        data = json.loads((SHOWCASE / "truth.json").read_text(encoding="utf-8"))
        env = (SHOWCASE / ".env").read_text(encoding="utf-8")
        in_env = [s for s in data["secrets"] if s.get("file") == ".env"]
        self.assertTrue(in_env)
        for secret in in_env:
            self.assertIn(secret["value"], env, secret["name"])
        Truth(SHOWCASE / "truth.json")  # loads


if __name__ == "__main__":
    unittest.main()
