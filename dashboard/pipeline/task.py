"""metric-task results for the dashboard.

metric-task runs Claude Code and costs API money, so the dashboard never starts it. It reads the batches people ran
(metric-task/scripts/m2.py run). Only batches whose recorded provenance confirms a clean checkout are attributed to
system_commit; dirty checkouts and legacy batches with unknown history remain separately labeled.

From a batch folder only batch.json and runs.csv are read. runs.csv holds one row per run without secret values;
the run folders next to it hold transcripts and API captures with secrets and are never opened.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.runner import write_json

CONDITIONS = ("none", "gold", "promptguard")
CATEGORIES = {  # metric-task/README.md#과제, in its order
    "diagnose": "진단 (비밀과 무관)", "edit": "비밀이 든 파일 수정", "identity": "같은 비밀인지 비교",
    "overmask": "비밀 아닌 값 필요", "property": "비밀 값의 속성", "use": "비밀을 명령에 사용", "transport": "비밀 옮기기",
}
TASK_VERSION = 3  # provenance-aware summaries; version 2 separated unmeasured server leak counts


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def _int(value: str | None) -> int:
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def _float(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def _server_leaked(row: dict[str, str]) -> int | None:
    """A missing count is unmeasured; zero is a measured run with no leak."""
    try:
        value = int(row.get("server_leaked", ""))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def provenance(meta: dict[str, Any]) -> str:
    """Legacy HEAD-only metadata cannot establish whether the code matched that commit."""
    source = meta.get("system_provenance")
    if not isinstance(source, dict) or source.get("version") != 1:
        return "unknown"
    if (source.get("commit") != meta.get("system_commit")
            or not re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit") or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("fingerprint") or ""))):
        return "unknown"
    if source.get("dirty") is True:
        return "dirty"
    return "clean" if source.get("dirty") is False else "unknown"


def discover(roots: Sequence[str | Path]) -> list[Path]:
    """Batch folders (batch.json and runs.csv side by side) directly under each root, or the root itself."""
    found = []
    for root in map(Path, roots):
        candidates = [root, *sorted(path for path in root.iterdir() if path.is_dir())] if root.is_dir() else []
        found += [path for path in candidates if (path / "batch.json").is_file() and (path / "runs.csv").is_file()]
    return found


def batch_key(folder: Path) -> str:
    digest = hashlib.sha256(f"task|{TASK_VERSION}|{folder.name}".encode())
    for name in ("batch.json", "runs.csv"):
        digest.update((folder / name).read_bytes())
    return digest.hexdigest()[:16]


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(folder: Path) -> dict[str, Any]:
    meta = json.loads((folder / "batch.json").read_text(encoding="utf-8"))
    with (folder / "runs.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    conditions = [condition for condition in CONDITIONS if any(row["condition"] == condition for row in rows)]
    conditions += sorted({row["condition"] for row in rows} - set(conditions))
    valid = [row for row in rows if _truthy(row.get("valid"))]
    captured = any(_server_leaked(row) is not None for row in valid)

    def stats(selected: list[dict[str, str]]) -> dict[str, Any]:
        runs = len(selected)
        success = sum(_truthy(row["success"]) for row in selected)
        out = {"runs": runs, "success": success, "success_rate": _rate(success, runs),
               "task_ok": sum(_truthy(row.get("task_ok")) for row in selected),
               "integrity_broken": sum(not _truthy(row.get("integrity_ok", "True")) for row in selected),
               "seen": sum(_int(row.get("secrets_seen")) > 0 for row in selected),
               "placeholder_inputs": sum(_int(row.get("tool_inputs_with_placeholder")) > 0 for row in selected),
               "findings": sum(_int(row.get("masked_findings")) for row in selected),
               "cost_usd": round(sum(_float(row.get("cost_usd")) for row in selected), 4)}
        out["seen_rate"] = _rate(out["seen"], runs)
        measured = [value for row in selected if (value := _server_leaked(row)) is not None]
        out["leak_measured"] = len(measured)
        out["leak_unmeasured"] = runs - len(measured)
        out["leaked"] = sum(value > 0 for value in measured)
        out["leaked_rate"] = _rate(out["leaked"], len(measured))
        return out

    by_condition = {condition: stats([row for row in valid if row["condition"] == condition]) for condition in conditions}
    categories = [category for category in CATEGORIES if any(row["category"] == category for row in valid)]
    categories += sorted({row["category"] for row in valid} - set(categories))
    by_category = [{"key": category, "label": CATEGORIES.get(category, category),
                    "conditions": {condition: stats([row for row in valid if row["category"] == category
                                                     and row["condition"] == condition]) for condition in conditions}}
                   for category in categories]
    tasks: dict[str, dict[str, Any]] = {}
    marks: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for row in valid:
        tasks.setdefault(row["task"], {"task": row["task"], "category": row["category"],
                                       "needs_value": _truthy(row.get("needs_secret_value")),
                                       "channels": row.get("channels") or "file"})
        mark = "O" if _truthy(row["success"]) else "x" if _truthy(row.get("task_ok")) else "X"
        leaked = _server_leaked(row)
        if leaked is None:
            mark += "?"
        elif leaked > 0:
            mark += "*"
        marks[(row["task"], row["condition"])].append((_int(row.get("rep")), mark))
    by_task = []
    for name, info in sorted(tasks.items()):
        cells = {condition: [mark for _rep, mark in sorted(marks[(name, condition)])] for condition in conditions}
        rates = {condition: _rate(sum(mark.startswith("O") for mark in cells[condition]), len(cells[condition]))
                 for condition in conditions}
        by_task.append({**info, "marks": cells, "rates": rates})
    invalid = [{"task": row["task"], "condition": row["condition"], "rep": _int(row.get("rep")),
                "error": (row.get("error") or "")[:200]} for row in rows if not _truthy(row.get("valid"))]
    return {
        "version": TASK_VERSION,
        "name": folder.name,
        "started_at": meta.get("started_at"),
        "model": next((row["model"] for row in rows if row.get("model")), meta.get("model")),
        "reps": meta.get("reps"),
        "claude_version": meta.get("claude_version"),
        "system_commit": meta.get("system_commit"),
        "provenance": provenance(meta),
        "data_commit": meta.get("data_commit"),
        "captured": captured,
        "conditions": conditions,
        "tasks": len(tasks),
        "runs": len(rows),
        "valid": len(valid),
        "by_condition": by_condition,
        "by_category": by_category,
        "by_task": by_task,
        "invalid": invalid,
    }


def collect(roots: Sequence[str | Path], results: Path) -> list[dict[str, Any]]:
    """Summaries for the index (oldest first), writing results/<key>/task.json for any batch not seen yet."""
    entries = []
    for folder in discover(roots):
        try:
            key = batch_key(folder)
            target = results / key / "task.json"
            if target.is_file():
                summary = json.loads(target.read_text(encoding="utf-8"))
            else:
                summary = summarize(folder)
                write_json(target, summary)
        except (OSError, ValueError, KeyError, csv.Error):
            continue  # a batch still being written or not a metric-task batch
        entries.append({"key": key, "name": summary["name"], "started_at": summary["started_at"],
                        "model": summary["model"], "system_commit": summary["system_commit"],
                        "provenance": summary["provenance"],
                        "runs": summary["runs"], "valid": summary["valid"], "tasks": summary["tasks"],
                        "captured": summary["captured"],
                        "headline": {condition: {name: values.get(name) for name in ("success_rate", "seen_rate", "leaked_rate")}
                                     for condition, values in summary["by_condition"].items()}})
    return sorted(entries, key=lambda entry: entry["started_at"] or "")
