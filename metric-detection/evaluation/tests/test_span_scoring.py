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

    def test_only_whitespace_left_unmasked_counts_as_masked(self) -> None:
        # A PEM body masked line by line: the newlines between the lines stay, but nothing secret is exposed.
        text = "-----BEGIN-----\nMIIEpAIB\nAAKCAQEA\r\n  x9Zq\n-----END-----"
        start, end = text.index("MIIE"), text.index("x9Zq") + 4
        lines = [Edit(text.index(part), text.index(part) + len(part), "[KEY]") for part in ("MIIEpAIB", "AAKCAQEA", "x9Zq")]
        score = _score(text, lines, [(start, end)]).gold_results[0]
        self.assertEqual((score.status, score.exposed_chars), (SpanStatus.EXACT, 5))
        over = _score(text, [Edit(0, text.index("AAKC") - 1, "[K]"), *lines[1:]], [(start, end)]).gold_results[0]
        self.assertEqual(over.status, SpanStatus.OVER)
        # One unmasked non-space character keeps it partial.
        partial = _score(text, lines[:2] + [Edit(text.index("x9Zq"), text.index("x9Zq") + 3, "[KEY]")], [(start, end)])
        self.assertEqual(partial.gold_results[0].status, SpanStatus.PARTIAL)

    def test_whitespace_only_span_with_nothing_masked_is_missed(self) -> None:
        self.assertEqual(_score("a \n b", [], [(1, 4)]).gold_results[0].status, SpanStatus.MISSED)

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


class MaskedCharTests(unittest.TestCase):
    """masked_chars and masked_gold_chars, the inputs of character precision, for each kind of outcome."""

    TEXT = "user=alice key=SECRETVALUE123 log=debug-output-line"  # gold [15, 29)

    def chars(self, edits: list[Edit], gold: list[tuple[int, int]], text: str | None = None) -> tuple[int, int]:
        score = _score(self.TEXT if text is None else text, edits, gold)
        return score.masked_chars, score.masked_gold_chars

    def test_exact(self) -> None:
        self.assertEqual(self.TEXT[15:29], "SECRETVALUE123")
        self.assertEqual(self.chars([Edit(15, 29, "[K]")], [(15, 29)]), (14, 14))

    def test_over_counts_the_spill_as_masked_non_secret(self) -> None:
        self.assertEqual(self.chars([Edit(11, 29, "[K]")], [(15, 29)]), (18, 14))

    def test_partial(self) -> None:
        self.assertEqual(self.chars([Edit(15, 22, "[K]")], [(15, 29)]), (7, 7))

    def test_missed_with_an_edit_elsewhere(self) -> None:
        self.assertEqual(self.chars([Edit(5, 10, "[U]")], [(15, 29)]), (5, 0))

    def test_nothing_masked(self) -> None:
        self.assertEqual(self.chars([], [(15, 29)]), (0, 0))

    def test_adjacent_edits_and_split_spans_count_each_character_once(self) -> None:
        # Edits may touch but not overlap (verify() rejects overlapping edits); gold spans may overlap.
        edits = [Edit(11, 20, "[A]"), Edit(20, 29, "[B]"), Edit(29, 33, "[C]")]
        self.assertEqual(self.chars(edits, [(15, 29), (18, 25)]), (22, 14))

    def test_one_edit_over_two_gold_spans(self) -> None:
        self.assertEqual(self.chars([Edit(5, 29, "[X]")], [(5, 10), (15, 29)]), (24, 19))

    def test_blocked_item_masks_every_character(self) -> None:
        # Fail-closed: the adapter reports one edit over the whole text.
        blocked = [Edit(0, len(self.TEXT), "[PROMPTGUARD_BLOCKED]")]
        self.assertEqual(self.chars(blocked, [(15, 29)]), (len(self.TEXT), 14))
        self.assertEqual(self.chars(blocked, []), (len(self.TEXT), 0))

    def test_item_without_gold(self) -> None:
        self.assertEqual(self.chars([Edit(34, 39, "[L]")], []), (5, 0))
        self.assertEqual(self.chars([], []), (0, 0))


class ExcludedSpanTests(unittest.TestCase):
    """Excluded spans: neither gold nor a false positive."""

    TEXT = "user=alice key=SECRETVALUE123 log=debug-output-line"  # gold [15, 29), excluded "alice" [5, 10)

    def score(self, edits: list[Edit], excluded=((5, 10),)):
        left_out = [GoldSpan(0, 9 + index, start, end, "TOKEN") for index, (start, end) in enumerate(excluded)]
        return score_item("s", 0, "tool_output", self.TEXT, apply_edits(self.TEXT, edits), edits,
                          [GoldSpan(0, 0, 15, 29, "TOKEN")], left_out)

    def test_masking_an_excluded_span_is_not_a_false_positive(self) -> None:
        score = self.score([Edit(5, 10, "[A]"), Edit(15, 29, "[K]")])
        self.assertEqual((score.masked_chars, score.masked_gold_chars, score.excluded_masked_chars), (14, 14, 5))
        self.assertEqual([(e.start, e.overlaps_gold, e.within_gold) for e in score.edit_results], [(15, True, True)])
        self.assertEqual(score.gold_results[0].status, SpanStatus.EXACT)
        part = self.score([Edit(6, 9, "[A]")])  # part of the excluded span only
        self.assertEqual((part.masked_chars, part.excluded_masked_chars, part.edit_results), (0, 3, []))

    def test_not_masking_an_excluded_span_is_not_a_miss(self) -> None:
        score = self.score([Edit(15, 29, "[K]")])
        self.assertEqual([r.status for r in score.gold_results], [SpanStatus.EXACT])  # the gold span only
        self.assertEqual((score.masked_chars, score.masked_gold_chars, score.excluded_masked_chars), (14, 14, 0))
        self.assertEqual(len(self.score([]).gold_results), 1)

    def test_other_characters_of_an_edit_count_as_before(self) -> None:
        # "user=alice" [0, 10): five characters are excluded, the other five are still masked non-gold text.
        wide = self.score([Edit(0, 10, "[A]")])
        self.assertEqual((wide.masked_chars, wide.masked_gold_chars, wide.excluded_masked_chars), (5, 0, 5))
        self.assertEqual([(e.overlaps_gold, e.within_gold) for e in wide.edit_results], [(False, False)])
        # An edit over the excluded span and the gold span is over-masking, as it was.
        both = self.score([Edit(5, 29, "[K]")])
        self.assertEqual((both.masked_chars, both.masked_gold_chars, both.excluded_masked_chars), (19, 14, 5))
        self.assertEqual(both.gold_results[0].status, SpanStatus.OVER)
        self.assertEqual([(e.overlaps_gold, e.within_gold) for e in both.edit_results], [(True, False)])
        # A blocked item: all of its text but the excluded characters.
        blocked = self.score([Edit(0, len(self.TEXT), "[BLOCKED]")])
        self.assertEqual((blocked.masked_chars, blocked.masked_gold_chars), (len(self.TEXT) - 5, 14))

    def test_an_edit_inside_two_adjacent_excluded_spans_is_left_out(self) -> None:
        score = self.score([Edit(5, 14, "[A]")], excluded=((5, 10), (10, 14)))
        self.assertEqual((score.masked_chars, score.excluded_masked_chars, score.edit_results), (0, 9, []))

    def test_without_excluded_spans_nothing_changes(self) -> None:
        edits = [Edit(0, 10, "[A]"), Edit(15, 29, "[K]")]
        plain = score_item("s", 0, "tool_output", self.TEXT, apply_edits(self.TEXT, edits), edits,
                           [GoldSpan(0, 0, 15, 29, "TOKEN")])
        self.assertEqual(plain, self.score(edits, excluded=()))
        self.assertEqual((plain.masked_chars, plain.excluded_masked_chars, len(plain.edit_results)), (24, 0, 2))


if __name__ == "__main__":
    unittest.main()
