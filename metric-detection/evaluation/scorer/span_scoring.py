"""Score one item: gold span coverage and edit/gold overlap, in original-text coordinates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from evaluation.dataset.schema import GoldSpan
from evaluation.scorer.edits import Edit, verify


class SpanStatus(str, Enum):
    # "Masked" below allows unmasked whitespace: a span whose only unmasked characters are spaces, tabs or newlines
    # (a PEM body masked line by line, leaving the \n between lines) exposes nothing and counts as fully masked.
    EXACT = "exact"  # every character masked, and no edit touching the span masks text outside it
    OVER = "over"  # every character masked, but an edit touching the span spills outside it
    PARTIAL = "partial"  # some non-whitespace characters masked, some not
    MISSED = "missed"  # no character masked


@dataclass(frozen=True)
class GoldResult:
    session_id: str
    item_id: int
    span_id: int
    start: int
    end: int
    type: str
    status: SpanStatus
    exposed_chars: int  # characters left unmasked (whitespace included, so exact/over may have some)


@dataclass(frozen=True)
class EditResult:
    session_id: str
    item_id: int
    start: int
    end: int
    overlaps_gold: bool  # shares a character with some gold span
    within_gold: bool  # lies inside one gold span, so it masks secret characters only


@dataclass(frozen=True)
class ItemScore:
    session_id: str
    item_id: int
    channel: str
    gold_results: list[GoldResult]
    edit_results: list[EditResult]
    # Character counts for character-level precision, in original-text coordinates. A blocked item is one edit
    # over the whole text, so every character of it counts as masked.
    masked_chars: int = 0  # |union of the characters the edits replaced|, excluded spans left out
    masked_gold_chars: int = 0  # |masked characters that lie in some gold span|
    excluded_masked_chars: int = 0  # |masked characters that lie in some excluded span| (in no count above)


def _union(edits: Sequence[Edit]) -> list[tuple[int, int]]:
    return _merge((edit.start, edit.end) for edit in edits)


def _merge(ranges) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _covered(start: int, end: int, merged: Sequence[tuple[int, int]]) -> int:
    return sum(max(0, min(end, right) - max(start, left)) for left, right in merged)


def _gaps(start: int, end: int, merged: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """The unmasked parts of [start, end)."""
    gaps, cursor = [], start
    for left, right in merged:
        if right <= cursor or left >= end:
            continue
        if left > cursor:
            gaps.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def score_item(
    session_id: str,
    item_id: int,
    channel: str,
    original: str,
    output: str,
    edits: Sequence[Edit],
    gold: Sequence[GoldSpan],
    excluded: Sequence[GoldSpan] = (),
) -> ItemScore:
    """Verify the edits against the output, then judge each gold span and each edit.

    A gold span succeeds only when exactly its characters are masked: the edits cover all of it
    and none of the edits touching it extends past its boundaries. Splitting the span across
    several edits is fine, and so is leaving whitespace between them unmasked: a span whose
    only unmasked characters are whitespace counts as covered (exact or over), as long as some
    edit masks part of it. Replacement text is never inspected, so a placeholder that happens
    to share characters with the secret cannot affect the result.

    `excluded` spans are text that is neither gold nor a false positive (a value the data set planted where the
    label rules no longer see a credential). They are not gold spans, so leaving one unmasked is not a miss. Their
    characters are left out of masked_chars, and an edit lying wholly inside them is left out of edit_results. An
    edit that also masks other text is judged as before and its other characters count as before. Excluded spans
    must not overlap gold (the validator checks it).
    """
    ordered = verify(original, output, edits)
    merged = _union(ordered)
    gold_results: list[GoldResult] = []
    for span in sorted(gold, key=lambda span: (span.start, span.end)):
        length = span.end - span.start
        covered = _covered(span.start, span.end, merged)
        blank_rest = covered > 0 and all(original[left:right].isspace() for left, right in _gaps(span.start, span.end, merged))
        if covered == length or blank_rest:
            spills = any(edit.start < span.end and span.start < edit.end
                         and (edit.start < span.start or edit.end > span.end) for edit in ordered)
            status = SpanStatus.OVER if spills else SpanStatus.EXACT
        else:
            status = SpanStatus.MISSED if covered == 0 else SpanStatus.PARTIAL
        gold_results.append(GoldResult(session_id, item_id, span.span_id, span.start, span.end, span.type, status,
                                       length - covered))
    left_out = _merge((span.start, span.end) for span in excluded)
    edit_results = [
        EditResult(session_id, item_id, edit.start, edit.end,
                   any(edit.start < span.end and span.start < edit.end for span in gold),
                   any(span.start <= edit.start and edit.end <= span.end for span in gold))
        for edit in ordered
        if not (edit.end > edit.start and _covered(edit.start, edit.end, left_out) == edit.end - edit.start)
    ]
    excluded_masked = sum(_covered(start, end, merged) for start, end in left_out)
    masked_chars = sum(end - start for start, end in merged) - excluded_masked
    masked_gold_chars = sum(_covered(start, end, merged) for start, end in _merge((s.start, s.end) for s in gold))
    return ItemScore(session_id, item_id, channel, gold_results, edit_results, masked_chars, masked_gold_chars,
                     excluded_masked)
