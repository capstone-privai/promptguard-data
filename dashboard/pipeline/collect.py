"""Turn evaluated items into the dashboard's counts and example rows.

A cell counts, for one (sub-group, channel, type), the gold spans by outcome and the edits by class (catalog.STATUSES,
then catalog.EDIT_CLASSES). A gold span has its own type. An edit takes the type of the gold span it overlaps most, or,
touching none, the type its placeholder names (catalog.placeholder_type). All cells summed give exactly the counts of
evaluation.report.aggregate over the same items; merge() checks that.

Examples are picked per bucket, a (sub-group, channel, type, outcome), in the order of a hash of the item's id, so the
choice does not depend on how a dataset was split into shards. An example keeps a window of the item text around the
spans it was picked for. The text is the dataset's own, secrets included.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from evaluation.adapters.base import ItemOutput
from evaluation.dataset.schema import Item, Session
from evaluation.report.aggregate import count_lines
from evaluation.scorer.span_scoring import EditResult, GoldResult, ItemScore

from pipeline.taxonomy import CHANNELS, EDIT_CLASSES, MAX_GROUPS, OTHER_GROUP, STATUSES, placeholder_type

PER_BUCKET = 3  # examples kept per (sub-group, channel, type, outcome)
PAD = 200  # characters shown on each side of the spans an example was picked for
MAX_WINDOW = 1000  # spans further apart than this get separate windows
SNAP = 80  # a window edge this close to a line break moves to it
COUNT_KEYS = ("exact", "over", "partial", "missed", "edits_tp", "edits_over", "edits_fp")  # aggregate()["counts"]

Bucket = tuple[str, ...]  # ("gold", group, channel, type, status) | ("fp", group, channel, type) | ("clean", group, channel)


class MergeError(Exception):
    pass


def rank_of(dataset: str, session_id: str, item_id: int) -> str:
    return hashlib.sha1(f"{dataset}\0{session_id}\0{item_id}".encode()).hexdigest()


def edit_class(result: EditResult) -> str:
    if result.within_gold:
        return "tp"
    return "wide" if result.overlaps_gold else "fp"


def edit_type(edit: EditResult, gold: Sequence[GoldResult], replacement: str) -> str:
    best, most = None, 0
    for span in gold:
        overlap = min(edit.end, span.end) - max(edit.start, span.start)
        if overlap > most:
            best, most = span, overlap
    return best.type if best is not None else placeholder_type(replacement)


def _snap(text: str, start: int, end: int) -> tuple[int, int]:
    if start > 0:
        line_start = text.rfind("\n", 0, start) + 1
        if start - line_start <= SNAP:
            start = line_start
    if end < len(text):
        line_end = text.find("\n", end)
        line_end = len(text) if line_end == -1 else line_end
        if line_end - end <= SNAP:
            end = line_end
    return start, end


def windows(text: str, focuses: Sequence[tuple[int, int]]) -> tuple[list[tuple[int, int]], list[int]]:
    """Windows of `text` covering the focus ranges, and the window index of each focus."""
    order = sorted(range(len(focuses)), key=lambda index: focuses[index])
    clusters: list[list[int]] = []
    owner = [0] * len(focuses)
    for index in order:
        start, end = focuses[index]
        if clusters and max(end, clusters[-1][1]) - clusters[-1][0] <= MAX_WINDOW - 2 * PAD:
            clusters[-1][1] = max(clusters[-1][1], end)
        else:
            clusters.append([start, end])
        owner[index] = len(clusters) - 1
    spans = []
    for start, end in clusters:
        # An empty focus marks an item with nothing to show but its text: open with more of it.
        low, high = max(0, start - PAD), min(len(text), end + PAD if end > start else start + 3 * PAD)
        high = min(high, low + 2 * MAX_WINDOW)  # a single long secret (a PEM block) is cut, not shown whole
        spans.append(_snap(text, low, high))
    return spans, owner


class Collector:
    """Counts and example candidates for the items of one dataset (or one shard of it)."""

    def __init__(self, dataset: str, group_of: Callable[[Mapping[str, Any]], str], per_bucket: int = PER_BUCKET):
        self.dataset = dataset
        self.group_of = group_of
        self.per_bucket = per_bucket
        self.cells: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0] * (len(STATUSES) + len(EDIT_CLASSES)))
        self.items: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])  # items, clean items, lines
        self.picks: dict[Bucket, list[tuple[str, tuple[str, int], tuple[int, int]]]] = {}  # rank, item key, focus
        self.sources: dict[tuple[str, int], dict[str, Any]] = {}

    def add(self, session: Session, item: Item, score: ItemScore, output: ItemOutput) -> None:
        if item.channel not in CHANNELS:  # tool_input is never scored
            return
        group = self.group_of(session.meta)
        replacements = {(edit.start, edit.end): edit.replacement for edit in output.edits}
        gold = score.gold_results
        edits = [(edit, edit_class(edit), edit_type(edit, gold, replacements.get((edit.start, edit.end), "")))
                 for edit in score.edit_results]
        for span in gold:
            self.cells[(group, item.channel, span.type)][STATUSES.index(span.status.value)] += 1
        for _edit, kind, type_ in edits:
            self.cells[(group, item.channel, type_)][len(STATUSES) + EDIT_CLASSES.index(kind)] += 1
        totals = self.items[(group, item.channel)]
        totals[0] += 1
        totals[1] += int(not gold and not edits)
        totals[2] += count_lines(item.text)

        focus: dict[Bucket, tuple[int, int]] = {}
        for span in gold:
            focus.setdefault(("gold", group, item.channel, span.type, span.status.value), (span.start, span.end))
        for edit, kind, type_ in edits:
            if kind == "fp":
                focus.setdefault(("fp", group, item.channel, type_), (edit.start, edit.end))
        if not gold and not edits:
            focus[("clean", group, item.channel)] = (0, 0)
        key = (session.session_id, item.item_id)
        rank = rank_of(self.dataset, *key)
        if any([self._offer(bucket, rank, key, span) for bucket, span in focus.items()]):
            self.sources[key] = {
                "channel": item.channel, "group": group, "text": item.text,
                "gold": [(span.start, span.end, span.type, span.status.value) for span in gold],
                "edits": [(edit.start, edit.end, kind, type_, replacements.get((edit.start, edit.end), ""))
                          for edit, kind, type_ in edits],
            }

    def _offer(self, bucket: Bucket, rank: str, key: tuple[str, int], focus: tuple[int, int]) -> bool:
        kept = self.picks.setdefault(bucket, [])
        if len(kept) >= self.per_bucket and rank >= kept[-1][0]:
            return False
        kept.append((rank, key, focus))
        kept.sort()
        del kept[self.per_bucket:]
        return True

    def payload(self) -> dict[str, Any]:
        """JSON-ready counts, picks and example windows (only for items some bucket still keeps)."""
        focuses: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
        for kept in self.picks.values():
            for _rank, key, focus in kept:
                if focus not in focuses[key]:
                    focuses[key].append(focus)
        examples: dict[str, dict[str, Any]] = {}
        located: dict[tuple[tuple[str, int], tuple[int, int]], str] = {}
        for key, spans in focuses.items():
            source = self.sources[key]
            ranges, owner = windows(source["text"], spans)
            ids = [example_id(key, start) for start, _end in ranges]
            for (start, end), identifier in zip(ranges, ids):
                examples[identifier] = _example(key, source, start, end)
            for span, index in zip(spans, owner):
                located[(key, span)] = ids[index]
        return {
            "cells": [[*cell, *counts] for cell, counts in sorted(self.cells.items())],
            "items": [[*cell, *counts] for cell, counts in sorted(self.items.items())],
            "picks": [[list(bucket), rank, located[(key, focus)]]
                      for bucket, kept in sorted(self.picks.items()) for rank, key, focus in kept],
            "examples": examples,
        }


def example_id(key: tuple[str, int], start: int) -> str:
    return f"{key[0]}#{key[1]}@{start}"


def _example(key: tuple[str, int], source: Mapping[str, Any], start: int, end: int) -> dict[str, Any]:
    def clip(low: int, high: int) -> tuple[int, int] | None:
        if high <= start or low >= end:
            return None
        return max(low, start) - start, min(high, end) - start

    gold = [[*clipped, type_, status] for low, high, type_, status in source["gold"]
            if (clipped := clip(low, high))]
    edits = [[*clipped, kind, type_, replacement] for low, high, kind, type_, replacement in source["edits"]
             if (clipped := clip(low, high))]
    tags = {f"{type_}:{status}" for _s, _e, type_, status in gold}
    tags |= {f"{type_}:fp" for _s, _e, kind, type_, _r in edits if kind == "fp"}
    if not source["gold"] and not source["edits"]:
        tags.add("clean")
    text = source["text"]
    return {"id": example_id(key, start), "session": key[0], "item": key[1],
            "channel": source["channel"], "group": source["group"],
            "offset": start, "length": len(text), "text": text[start:end], "gold": gold, "edits": edits,
            "tags": sorted(tags)}


def merge(payloads: Iterable[Mapping[str, Any]], per_bucket: int = PER_BUCKET) -> dict[str, Any]:
    """Shard payloads (with "counts" from aggregate) → one dataset: summed cells and item totals, the best picks per
    bucket, their examples, and one example per (channel, type, outcome) for the all-datasets view."""
    cells: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0] * (len(STATUSES) + len(EDIT_CLASSES)))
    items: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0, 0, 0])
    counts = dict.fromkeys(COUNT_KEYS, 0)
    lines_total = 0
    picks: dict[tuple[str, ...], list[tuple[str, str]]] = defaultdict(list)
    examples: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in payload["cells"]:
            target = cells[tuple(row[:3])]
            for index, value in enumerate(row[3:]):
                target[index] += value
        for row in payload["items"]:
            target = items[tuple(row[:2])]
            for index, value in enumerate(row[2:]):
                target[index] += value
        for key in COUNT_KEYS:
            counts[key] += payload["counts"][key]
        lines_total += payload["lines_total"]
        for bucket, rank, example_id in payload["picks"]:
            picks[tuple(bucket)].append((rank, example_id))
        examples.update(payload["examples"])

    summed = [sum(values[index] for values in cells.values()) for index in range(len(COUNT_KEYS))]
    if summed != [counts[key] for key in COUNT_KEYS] or sum(row[2] for row in items.values()) != lines_total:
        raise MergeError(f"cell sums {dict(zip(COUNT_KEYS, summed))} differ from the scorer's counts {counts}")

    best = {bucket: sorted(kept)[:per_bucket] for bucket, kept in picks.items()}
    groups = _fold_groups(items)
    kept_ids = {example_id for kept in best.values() for _rank, example_id in kept}
    overview: dict[tuple[str, ...], tuple[str, str]] = {}
    for bucket, kept in best.items():
        coarse = (bucket[0], *bucket[2:])  # without the sub-group
        overview[coarse] = min(overview.get(coarse, kept[0]), kept[0])
    folded = [{**examples[example_id], "group": groups[examples[example_id]["group"]]} for example_id in sorted(kept_ids)]
    return {
        "cells": _fold_rows(cells, groups),
        "items": _fold_rows(items, groups),
        "counts": counts,
        "lines_total": lines_total,
        "examples": folded,
        "overview": sorted({example_id for _rank, example_id in overview.values()}),
    }


def _fold_groups(items: Mapping[tuple[str, ...], list[int]]) -> dict[str, str]:
    sizes: dict[str, int] = defaultdict(int)
    for (group, _channel), (count, _clean, _lines) in items.items():
        sizes[group] += count
    if len(sizes) <= MAX_GROUPS:
        return {group: group for group in sizes}
    keep = set(sorted(sizes, key=lambda group: (-sizes[group], group))[:MAX_GROUPS - 1])
    return {group: group if group in keep else OTHER_GROUP for group in sizes}


def _fold_rows(rows: Mapping[tuple[str, ...], list[int]], groups: Mapping[str, str]) -> list[list[Any]]:
    folded: dict[tuple[str, ...], list[int]] = {}
    for key, values in rows.items():
        target = folded.setdefault((groups[key[0]], *key[1:]), [0] * len(values))
        for index, value in enumerate(values):
            target[index] += value
    return [[*key, *values] for key, values in sorted(folded.items())]
