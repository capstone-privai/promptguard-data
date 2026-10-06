"""Verify sessions.jsonl and gold.jsonl written by build_dataset.py.

Run from the repository root: python metric-1/scripts/verify_dataset.py

Checks:
  1. sessions.jsonl schema: unique session_id, item_id = 0..n-1, known channel, no gold fields
  2. gold.jsonl schema: one span per row, span_id = 0..k-1 per item, items without spans omitted
  3. span bounds: 0 <= start < end <= len(text), no overlap within an item, known type
  4. coverage: every occurrence of a long (>= 9 chars) gold value in any item is inside a gold span
  5. reproduction: rebuilding with build_dataset.py yields byte-identical files
Exits 1 and lists every problem found if any check fails.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile

from build_dataset import build, write_jsonl

SESSION_KEYS = {"session_id", "items", "meta"}
ITEM_KEYS = {"item_id", "turn_id", "channel", "text"}
GOLD_KEYS = {"session_id", "item_id", "span_id", "span"}
SPAN_KEYS = {"start", "end", "type"}
CHANNELS = {"prompt", "stdout", "stderr", "agents_md"}
TYPES = {"PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY"}
MIN_COVERAGE_LEN = 9


def read_jsonl(path: Path, errors: list[str]) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}:{n}: invalid JSON ({e})")
    return rows


def check_sessions(sessions: list[dict], errors: list[str]) -> dict[tuple[str, int], str]:
    texts = {}
    seen = set()
    for n, s in enumerate(sessions, 1):
        where = f"sessions.jsonl:{n}"
        if set(s) != SESSION_KEYS:
            errors.append(f"{where}: keys {sorted(s)} != {sorted(SESSION_KEYS)}")
            continue
        sid = s["session_id"]
        if sid in seen:
            errors.append(f"{where}: duplicate session_id {sid}")
        seen.add(sid)
        for i, item in enumerate(s["items"]):
            if set(item) != ITEM_KEYS:
                errors.append(f"{where}: item {i} keys {sorted(item)} != {sorted(ITEM_KEYS)}")
                continue
            if item["item_id"] != i:
                errors.append(f"{where}: item at index {i} has item_id {item['item_id']!r}")
            if item["channel"] not in CHANNELS:
                errors.append(f"{where}: item {i} unknown channel {item['channel']!r}")
            if not isinstance(item["text"], str):
                errors.append(f"{where}: item {i} text is not a string")
                continue
            texts[(sid, item["item_id"])] = item["text"]
    return texts


def check_gold(gold: list[dict], texts: dict[tuple[str, int], str], errors: list[str]) -> list[tuple]:
    spans = []  # (session_id, item_id, start, end, type)
    next_span_id = {}
    for n, g in enumerate(gold, 1):
        where = f"gold.jsonl:{n}"
        if set(g) != GOLD_KEYS:
            errors.append(f"{where}: keys {sorted(g)} != {sorted(GOLD_KEYS)}")
            continue
        key = (g["session_id"], g["item_id"])
        if key not in texts:
            errors.append(f"{where}: no item {key}")
            continue
        span = g["span"]
        if not isinstance(span, dict) or set(span) != SPAN_KEYS:
            errors.append(f"{where}: span must be an object with keys {sorted(SPAN_KEYS)}, got {span!r}")
            continue
        expected = next_span_id.get(key, 0)
        if g["span_id"] != expected:
            errors.append(f"{where}: span_id {g['span_id']!r}, expected {expected}")
        next_span_id[key] = expected + 1
        start, end, kind = span["start"], span["end"], span["type"]
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(texts[key])):
            errors.append(f"{where}: bad bounds [{start}, {end}) for text length {len(texts[key])}")
            continue
        if kind not in TYPES:
            errors.append(f"{where}: unknown type {kind!r}")
        value = texts[key][start:end]
        if value != value.strip():
            errors.append(f"{where}: span has leading/trailing whitespace {value!r}")
        spans.append((*key, start, end, kind))

    # Rows must follow sessions.jsonl order, then item_id, then span_id.
    order = {key: i for i, key in enumerate(texts)}
    keys = [order[(s[0], s[1])] for s in spans]
    if keys != sorted(keys):
        errors.append("gold.jsonl: rows are not in session/item order")

    by_item = {}
    for sid, iid, start, end, _ in spans:
        by_item.setdefault((sid, iid), []).append((start, end))
    for key, ranges in by_item.items():
        if ranges != sorted(ranges):
            errors.append(f"gold.jsonl: spans of {key} are not ordered by start")
        ranges = sorted(ranges)
        for (_, prev_end), (start, _) in zip(ranges, ranges[1:]):
            if start < prev_end:
                errors.append(f"gold.jsonl: overlapping spans in {key} at {start}")
    return spans


def check_coverage(spans: list[tuple], texts: dict[tuple[str, int], str], errors: list[str]):
    # Short values ("postgres", "changeme") also occur as ordinary words, so they are exempt.
    covered = {}
    for sid, iid, start, end, _ in spans:
        covered.setdefault((sid, iid), []).append((start, end))
    values = {texts[(sid, iid)][start:end] for sid, iid, start, end, _ in spans}
    for value in values:
        if len(value) < MIN_COVERAGE_LEN:
            continue
        for key, text in texts.items():
            for m in re.finditer(re.escape(value), text):
                if not any(s <= m.start() and m.end() <= e for s, e in covered.get(key, [])):
                    errors.append(f"uncovered occurrence of {value[:20]!r}... in {key} at {m.start()}")


def check_reproduction(root: Path, errors: list[str]):
    corpus = build()
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        for name, rows in (("sessions.jsonl", corpus.sessions), ("gold.jsonl", corpus.gold)):
            write_jsonl(temp / name, rows)
            if (temp / name).read_bytes() != (root / name).read_bytes():
                errors.append(f"{name}: differs from a fresh build (edited or stale)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--skip-rebuild", action="store_true", help="skip the byte-reproduction check")
    args = parser.parse_args()
    root = args.dataset_dir

    errors: list[str] = []
    sessions = read_jsonl(root / "sessions.jsonl", errors)
    gold = read_jsonl(root / "gold.jsonl", errors)
    texts = check_sessions(sessions, errors)
    spans = check_gold(gold, texts, errors)
    check_coverage(spans, texts, errors)
    if not args.skip_rebuild:
        check_reproduction(root, errors)

    if errors:
        print(f"FAILED: {len(errors)} problem(s)", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(1)

    positive = {(s[0], s[1]) for s in spans}
    print(json.dumps({
        "sessions": len(sessions),
        "items": len(texts),
        "items_with_spans": len(positive),
        "items_without_spans": len(texts) - len(positive),
        "spans": len(spans),
        "spans_by_type": dict(sorted(Counter(s[4] for s in spans).items())),
        "reproduction": "skipped" if args.skip_rebuild else "passed",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
