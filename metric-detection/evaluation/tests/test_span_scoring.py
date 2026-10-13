from __future__ import annotations

import unittest

from evaluation.dataset.schema import GoldSpan
from evaluation.scorer.edits import Edit, VerificationError, apply_edits
from evaluation.scorer.span_scoring import SpanStatus, score_item


def _score(text: str, edits: list[Edit], gold: list[tuple[int, int]]):
    spans = [GoldSpan(0, span_id, start, end, "TOKEN") for span_id, (start, end) in enumerate(gold)]
    return score_item("s", 0, "tool_output", text, apply_edits(text, edits), edits, spans)


class SpanScoringTests(unittest.TestCase):
    LONG = "API_TOKEN=eiwoevndksfleifwjdskfdnslvmeiwl\nLOG=debug"

    def test_exact_partial_missed(self) -> None:
        self.assertEqual(self.LONG[10:41], "eiwoevndksfleifwjdskfdnslvmeiwl")
        exact = _score(self.LONG, [Edit(10, 41, "[API_1]")], [(10, 41)])
        self.assertEqual((exact.gold_results[0].status, exact.gold_results[0].exposed_chars), (SpanStatus.EXACT, 0))
        self.assertEqual([(r.overlaps_gold, r.within_gold) for r in exact.edit_results], [(True, True)])
        partial = _score(self.LONG, [Edit(10, 31, "[API_1]")], [(10, 41)]).gold_results[0]
        self.assertEqual((partial.status, partial.exposed_chars), (SpanStatus.PARTIAL, 10))
        missed = _score(self.LONG, [], [(10, 41)]).gold_results[0]
        self.assertEqual((missed.status, missed.exposed_chars), (SpanStatus.MISSED, 31))

    def test_extra_edit_outside_gold_is_not_overlapping(self) -> None:
        debug = self.LONG.index("debug")
        score = _score(self.LONG, [Edit(10, 41, "[API_1]"), Edit(debug, debug + 5, "[X_1]")], [(10, 41)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)
        self.assertEqual([(r.overlaps_gold, r.within_gold) for r in score.edit_results], [(True, True), (False, False)])

    def test_replacement_content_is_ignored(self) -> None:
        text = "API_TOKEN=zq7API9x1mk\nLOG=debug"
        score = _score(text, [Edit(10, 21, "[API_1]")], [(10, 21)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)

    def test_wider_edit_is_over_and_not_within_gold(self) -> None:
        for edit in (Edit(0, 41, "[LINE]"), Edit(10, 42, "[API_1]")):
            with self.subTest(start=edit.start, end=edit.end):
                score = _score(self.LONG, [edit], [(10, 41)])
                self.assertEqual((score.gold_results[0].status, score.gold_results[0].exposed_chars), (SpanStatus.OVER, 0))
                self.assertEqual([(r.overlaps_gold, r.within_gold) for r in score.edit_results], [(True, False)])

    def test_wider_edit_that_misses_part_of_gold_is_partial(self) -> None:
        score = _score(self.LONG, [Edit(0, 30, "[LINE]")], [(10, 41)])
        self.assertEqual((score.gold_results[0].status, score.gold_results[0].exposed_chars), (SpanStatus.PARTIAL, 11))

    def test_split_edits_inside_gold_are_exact(self) -> None:
        score = _score(self.LONG, [Edit(10, 25, "[A]"), Edit(25, 41, "[B]")], [(10, 41)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)
        self.assertEqual([(r.overlaps_gold, r.within_gold) for r in score.edit_results], [(True, True), (True, True)])

    def test_separate_edit_next_to_gold_keeps_gold_exact(self) -> None:
        # The key is masked by its own edit: the secret is still masked exactly, and the key's edit is over-masking.
        score = _score(self.LONG, [Edit(0, 9, "[K]"), Edit(10, 41, "[A]")], [(10, 41)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)
        self.assertEqual([(r.overlaps_gold, r.within_gold) for r in score.edit_results], [(False, False), (True, True)])

    def test_one_edit_over_two_adjacent_gold_spans_is_over(self) -> None:
        score = _score(self.LONG, [Edit(10, 41, "[A]")], [(10, 25), (25, 41)])
        self.assertEqual([result.status for result in score.gold_results], [SpanStatus.OVER, SpanStatus.OVER])
        self.assertEqual([(r.overlaps_gold, r.within_gold) for r in score.edit_results], [(True, False)])

    def test_unicode_offsets_are_code_points(self) -> None:
        text = "설정 🔑 비밀번호=Δpässwörd9 끝"
        start = text.index("Δ")
        end = start + len("Δpässwörd9")
        score = _score(text, [Edit(start, end, "[P]")], [(start, end)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)
        partial = _score(text, [Edit(start + 1, end, "[P]")], [(start, end)]).gold_results[0]
        self.assertEqual((partial.status, partial.exposed_chars), (SpanStatus.PARTIAL, 1))

    def test_crlf_offsets(self) -> None:
        text = "A=1\r\nDB_PASSWORD=qwerty7788\r\nB=2\r\n"
        start = text.index("qwerty7788")
        score = _score(text, [Edit(start, start + 10, "[P]")], [(start, start + 10)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)

    def test_verification_runs_first(self) -> None:
        with self.assertRaises(VerificationError):
            score_item("s", 0, "tool_output", "key=abc", "key=abc", [Edit(4, 7, "[K]")], [GoldSpan(0, 0, 4, 7, "SECRET")])


if __name__ == "__main__":
    unittest.main()
