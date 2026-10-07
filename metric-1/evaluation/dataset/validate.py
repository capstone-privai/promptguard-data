"""Collect every format error in a sessions/gold pair instead of stopping at the first one.

This checks only what scoring relies on. scripts/dataset_verify.py checks the full data contract
(key sets, span_id order, origin/allowed_use policy, coverage, reproduction).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.dataset.io import iter_records
from evaluation.dataset.schema import CHANNELS, GOLD_TYPES


@dataclass(frozen=True)
class ValidationIssue:
    session_id: str | None
    item_id: int | None
    message: str

    def __str__(self) -> str:
        item = "-" if self.item_id is None else self.item_id
        return f"{self.session_id or '-'} / {item} / {self.message}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def _records(path: Path, issues: list[ValidationIssue]) -> Iterator[tuple[str, Any]]:
    """Yield (location, parsed record); unreadable files and invalid JSON become issues."""
    try:
        lines = list(iter_records(path))
    except (OSError, UnicodeDecodeError) as exc:
        issues.append(ValidationIssue(None, None, f"cannot read {path.name} as UTF-8: {type(exc).__name__}"))
        return
    for line, raw in lines:
        where = f"{path.name} line {line}"
        try:
            yield where, json.loads(raw)
        except json.JSONDecodeError as exc:
            issues.append(ValidationIssue(None, None, f"{where}: invalid JSON ({exc.msg} at column {exc.colno})"))


def validate_session(record: Any, *, where: str = "") -> tuple[list[ValidationIssue], dict[int, str]]:
    """Check one parsed session record; return its issues and the texts of its valid items."""
    prefix = f"{where}: " if where else ""
    if not isinstance(record, dict):
        return [ValidationIssue(None, None, f"{prefix}session must be a JSON object")], {}
    session_id = record.get("session_id") if _is_id(record.get("session_id")) else None
    issues: list[ValidationIssue] = []

    def issue(item_id: int | None, message: str) -> None:
        issues.append(ValidationIssue(session_id, item_id, prefix + message))

    if session_id is None:
        issue(None, "missing or invalid 'session_id' (non-empty string)")
    if "gold" in record:
        issue(None, "sessions must not contain 'gold'; gold spans belong in the gold file")
    if "meta" in record and not isinstance(record["meta"], dict):
        issue(None, "'meta' must be an object")

    texts: dict[int, str] = {}
    seen: set[int] = set()
    items = record.get("items")
    if not isinstance(items, list) or not items:
        issue(None, "missing or invalid 'items' (non-empty list)")
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issue(None, f"items[{index}] must be an object")
            continue
        item_id = item.get("item_id") if _is_int(item.get("item_id")) and item["item_id"] >= 0 else None
        if item_id is None:
            issue(None, f"items[{index}]: missing or invalid 'item_id' (non-negative integer)")
        elif item_id in seen:
            issue(item_id, "duplicate item_id")
        if not isinstance(item.get("turn_id"), str):
            issue(item_id, "missing or invalid 'turn_id' (string)")
        if item.get("channel") not in CHANNELS:
            issue(item_id, f"invalid channel; expected one of {list(CHANNELS)}")
        if not isinstance(item.get("text"), str):
            issue(item_id, "missing or invalid 'text' (string)")
        elif item_id is not None and item_id not in seen:
            texts[item_id] = item["text"]
        if item_id is not None:
            seen.add(item_id)
    return issues, texts


def validate_dataset(sessions_path: str | Path, gold_path: str | Path) -> list[ValidationIssue]:
    sessions_path, gold_path = Path(sessions_path), Path(gold_path)
    issues: list[ValidationIssue] = []
    texts: dict[tuple[str, int], str] = {}
    session_ids: set[str] = set()
    sessions = 0
    for where, record in _records(sessions_path, issues):
        sessions += 1
        found, session_texts = validate_session(record, where=where)
        issues.extend(found)
        session_id = record.get("session_id") if isinstance(record, dict) else None
        if not _is_id(session_id):
            continue
        if session_id in session_ids:
            issues.append(ValidationIssue(session_id, None, f"{where}: duplicate session_id"))
            continue
        session_ids.add(session_id)
        texts.update(((session_id, item_id), text) for item_id, text in session_texts.items())
    if sessions == 0 and not issues:
        issues.append(ValidationIssue(None, None, f"{sessions_path.name} contains no sessions"))

    ranges: dict[tuple[str, int], list[tuple[int, int]]] = {}
    span_ids: set[tuple[str, int, int]] = set()
    for where, row in _records(gold_path, issues):
        if not isinstance(row, dict):
            issues.append(ValidationIssue(None, None, f"{where}: gold row must be a JSON object"))
            continue
        session_id = row.get("session_id") if _is_id(row.get("session_id")) else None
        item_id = row.get("item_id") if _is_int(row.get("item_id")) else None

        def issue(message: str) -> None:
            issues.append(ValidationIssue(session_id, item_id, f"{where}: {message}"))

        if session_id is None or item_id is None:
            issue("missing or invalid 'session_id' (non-empty string) or 'item_id' (integer)")
            continue
        key = (session_id, item_id)
        if session_id not in session_ids:
            issue("refers to a session_id not in the sessions file")
        elif key not in texts:
            issue("refers to an item_id not in this session")
        span_id = row.get("span_id")
        if not _is_int(span_id):
            issue("missing or invalid 'span_id' (integer)")
        elif (session_id, item_id, span_id) in span_ids:
            issue(f"duplicate span_id {span_id}")
        else:
            span_ids.add((session_id, item_id, span_id))
        span = row.get("span")
        if not isinstance(span, dict):
            issue("missing or invalid 'span' (object with start, end, type)")
            continue
        if span.get("type") not in GOLD_TYPES:
            issue(f"invalid type; expected one of {list(GOLD_TYPES)}")
        start, end = span.get("start"), span.get("end")
        if not (_is_int(start) and _is_int(end)):
            issue("'start' and 'end' must be integers")
            continue
        if key in texts:
            if not (0 <= start < end <= len(texts[key])):
                issue(f"span [{start}, {end}) is empty or outside text of length {len(texts[key])}")
                continue
            ranges.setdefault(key, []).append((start, end))
    for (session_id, item_id), spans in ranges.items():
        spans.sort()
        for (left_start, left_end), (right_start, right_end) in zip(spans, spans[1:]):
            if left_end > right_start:
                issues.append(ValidationIssue(session_id, item_id, f"{gold_path.name}: gold spans "
                                              f"[{left_start}, {left_end}) and [{right_start}, {right_end}) overlap"))
    return issues
