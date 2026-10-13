"""Load a sessions file and its gold file. Validate with validate.validate_dataset first.

  data_test/sessions*.jsonl   one session per line: session_id, items, meta (no gold)
  data_answer/gold*.jsonl     one gold span per line: session_id, item_id, span_id, span
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.dataset.schema import GoldSpan, Item, Session


def gold_path_for(sessions_path: str | Path) -> Path:
    """data_test/sessions_X.jsonl → data_answer/gold_X.jsonl; outside data_test/, the same folder."""
    sessions_path = Path(sessions_path)
    name = sessions_path.name
    if not name.startswith("sessions"):
        raise ValueError(f"cannot derive the gold file from {name}; pass --gold")
    folder = sessions_path.parent
    if folder.name == "data_test":
        folder = folder.with_name("data_answer")
    return folder / ("gold" + name[len("sessions"):])


def iter_records(path: str | Path):
    """Yield (line_number, raw_line) for non-blank lines."""
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                yield number, line


def gold_from_record(record: dict[str, Any]) -> tuple[str, GoldSpan]:
    span = record["span"]
    return record["session_id"], GoldSpan(record["item_id"], record["span_id"], span["start"], span["end"], span["type"])


def load_sessions(sessions_path: str | Path, gold_path: str | Path) -> list[Session]:
    gold: dict[str, list[GoldSpan]] = {}
    for _number, line in iter_records(gold_path):
        session_id, span = gold_from_record(json.loads(line))
        gold.setdefault(session_id, []).append(span)
    sessions = []
    for _number, line in iter_records(sessions_path):
        record = json.loads(line)
        sessions.append(Session(
            session_id=record["session_id"],
            items=[Item(item["item_id"], item["turn_id"], item["channel"], item["text"]) for item in record["items"]],
            gold=gold.get(record["session_id"], []),
            meta=dict(record.get("meta") or {}),
        ))
    return sessions


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
