"""Verify a sessions/gold pair written by dataset_build.py or convert_creddata.py.

Run from the repository root:
  python metric-1/scripts/dataset_verify.py                                               data_test/sessions.jsonl + data_answer/gold.jsonl
  python metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_example.jsonl  + data_answer/gold_from_example.jsonl
  python metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_CredData.jsonl --creddata ../CredData

Checks:
  1. sessions schema: unique session_id, item_id = 0..n-1, known channel, no gold fields
  2. meta: one source per file; allowed_use matches dataset_policy.ALLOWED_USE[origin]
  3. gold schema: one span per row, span_id = 0..k-1 per item, items without spans omitted
  4. span bounds: 0 <= start < end <= len(text), no overlap within an item, known type
  5. coverage: every occurrence of a long (>= 9 chars) gold value in any item is inside a gold span
     (skipped for origin=external: those labels are the source dataset's, not ours)
  6. reproduction: regenerating from the recorded source yields byte-identical files
     (built-in corpus, meta.template, or --creddata; skipped for CredData without --creddata)
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

from dataset_build import CHANNELS, REPO_ROOT, TYPES, build, from_template, write_jsonl
from dataset_policy import ALLOWED_USE

SESSION_KEYS = {"session_id", "items", "meta"}
ITEM_KEYS = {"item_id", "turn_id", "channel", "text"}
GOLD_KEYS = {"session_id", "item_id", "span_id", "span"}
SPAN_KEYS = {"start", "end", "type"}
MIN_COVERAGE_LEN = 9


def read_jsonl(path: Path, errors: list[str]) -> list[dict]:
    rows = []
    # Split on "\n" only: str.splitlines() also breaks on U+2028 etc., which JSON leaves unescaped.
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}:{n}: invalid JSON ({e})")
    return rows


def check_sessions(sessions: list[dict], name: str, errors: list[str]) -> dict[tuple[str, int], str]:
    texts = {}
    seen = set()
    for n, s in enumerate(sessions, 1):
        where = f"{name}:{n}"
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


def check_meta(sessions: list[dict], name: str, errors: list[str]) -> tuple[str | None, str | None]:
    """Returns the file's single (source, origin)."""
    sources = Counter()
    for n, s in enumerate(sessions, 1):
        meta = s.get("meta")
        if not isinstance(meta, dict):
            errors.append(f"{name}:{n}: meta is not an object")
            continue
        origin = meta.get("origin")
        if origin not in ALLOWED_USE:
            errors.append(f"{name}:{n}: meta.origin {origin!r} not in {sorted(ALLOWED_USE)}")
        elif meta.get("allowed_use") != ALLOWED_USE[origin]:
            errors.append(f"{name}:{n}: meta.allowed_use {meta.get('allowed_use')!r} != {ALLOWED_USE[origin]!r} for origin {origin}")
        sources[(meta.get("source"), origin, meta.get("template"))] += 1
    if len(sources) > 1:
        errors.append(f"{name}: mixes sources/origins {sorted(sources, key=str)}; keep one per file")
    if not sources:
        return None, None
    (source, origin, _), _ = sources.most_common(1)[0]
    return source, origin


def check_gold(gold: list[dict], texts: dict[tuple[str, int], str], name: str, errors: list[str]) -> list[tuple]:
    spans = []  # (session_id, item_id, start, end, type)
    next_span_id = {}
    for n, g in enumerate(gold, 1):
        where = f"{name}:{n}"
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
        errors.append(f"{name}: rows are not in session/item order")

    by_item = {}
    for sid, iid, start, end, _ in spans:
        by_item.setdefault((sid, iid), []).append((start, end))
    for key, ranges in by_item.items():
        if ranges != sorted(ranges):
            errors.append(f"{name}: spans of {key} are not ordered by start")
        ranges = sorted(ranges)
        for (_, prev_end), (start, _) in zip(ranges, ranges[1:]):
            if start < prev_end:
                errors.append(f"{name}: overlapping spans in {key} at {start}")
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


def regenerate(sessions: list[dict], source: str | None, origin: str | None, creddata: Path | None):
    """Rows the recorded source would produce now, or None with the reason it cannot be regenerated."""
    if source == "authored_synthetic_injection":
        c = build()
        return (c.sessions, c.gold), None
    if source == "template":
        c = from_template(REPO_ROOT / sessions[0]["meta"]["template"], origin)
        return (c.sessions, c.gold), None
    if source == "creddata":
        if creddata is None:
            return None, "skipped (pass --creddata to regenerate)"
        from convert_creddata import convert
        new_sessions, new_gold, _, _ = convert(creddata, sessions[0]["meta"]["context_lines"])
        return (new_sessions, new_gold), None
    return None, f"skipped (unknown source {source!r})"


def check_reproduction(paths: tuple[Path, Path], rows, errors: list[str]):
    with tempfile.TemporaryDirectory() as directory:
        for path, new_rows in zip(paths, rows):
            fresh = Path(directory) / path.name
            write_jsonl(fresh, new_rows)
            if fresh.read_bytes() != path.read_bytes():
                errors.append(f"{path.name}: differs from a fresh build (edited or stale)")


def gold_path_for(sessions_path: Path) -> Path:
    name = sessions_path.name
    if not name.startswith("sessions"):
        raise ValueError(f"cannot derive the gold file from {name}; pass --gold")
    folder = sessions_path.parent
    if folder.name == "data_test":
        folder = folder.with_name("data_answer")
    return folder / ("gold" + name[len("sessions"):])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sessions", type=Path, nargs="?", default=Path(__file__).resolve().parents[1] / "data_test" / "sessions.jsonl")
    parser.add_argument("--gold", type=Path, help="default: data_test/sessions*.jsonl -> data_answer/gold*.jsonl")
    parser.add_argument("--creddata", type=Path, help="CredData checkout, to regenerate sessions_from_CredData.jsonl")
    parser.add_argument("--skip-rebuild", action="store_true", help="skip the byte-reproduction check")
    args = parser.parse_args()
    gold_path = args.gold or gold_path_for(args.sessions)

    errors: list[str] = []
    sessions = read_jsonl(args.sessions, errors)
    gold = read_jsonl(gold_path, errors)
    texts = check_sessions(sessions, args.sessions.name, errors)
    source, origin = check_meta(sessions, args.sessions.name, errors)
    spans = check_gold(gold, texts, gold_path.name, errors)
    coverage = "skipped (external labels)" if origin == "external" else "passed"
    if origin != "external":
        check_coverage(spans, texts, errors)
    reproduction = "skipped"
    if not args.skip_rebuild and sessions:
        rows, reproduction = regenerate(sessions, source, origin, args.creddata)
        if rows is not None:
            check_reproduction((args.sessions, gold_path), rows, errors)
            reproduction = "passed"

    if errors:
        print(f"FAILED: {len(errors)} problem(s)", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(1)

    positive = {(s[0], s[1]) for s in spans}
    print(json.dumps({
        "files": [args.sessions.name, gold_path.name],
        "source": source,
        "origin": origin,
        "allowed_use": ALLOWED_USE.get(origin),
        "sessions": len(sessions),
        "items": len(texts),
        "items_with_spans": len(positive),
        "items_without_spans": len(texts) - len(positive),
        "spans": len(spans),
        "spans_by_type": dict(sorted(Counter(s[4] for s in spans).items())),
        "coverage": coverage,
        "reproduction": reproduction,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
