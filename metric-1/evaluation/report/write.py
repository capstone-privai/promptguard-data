"""Write a run folder. Only debug/ may contain raw text; every other file holds offsets and counts."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.dataset.schema import CHANNELS, GOLD_TYPES
from evaluation.run import RunResult


def create_run_dir(out_root: str | Path, label: str, now: datetime) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip("-") or "run"
    base = Path(out_root) / f"{now:%Y%m%d-%H%M%S}_{safe}"
    base.parent.mkdir(parents=True, exist_ok=True)
    candidate, suffix = base, 2
    while True:
        try:
            candidate.mkdir()  # atomic, so concurrent runs never share a folder
            return candidate
        except FileExistsError:
            candidate, suffix = base.with_name(f"{base.name}-{suffix}"), suffix + 1


def _dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _per_span(result: RunResult) -> list[dict[str, Any]]:
    return [{"session_id": gold.session_id, "item_id": gold.item_id, "span_id": gold.span_id, "start": gold.start,
             "end": gold.end, "type": gold.type, "channel": score.channel, "status": gold.status.value,
             "exposed_chars": gold.exposed_chars}
            for score in result.scores for gold in score.gold_results]


def _per_edit(result: RunResult) -> list[dict[str, Any]]:
    return [{"session_id": edit.session_id, "item_id": edit.item_id, "start": edit.start, "end": edit.end,
             "overlaps_gold": edit.overlaps_gold}
            for score in result.scores for edit in score.edit_results]


def _metric_sections(metrics: dict[str, Any], level: str) -> list[str]:
    counts = metrics["counts"]
    latency = metrics["latency_ms"]
    lines = [
        f"{level} Primary metrics", "",
        "| Metric | Value |", "|---|---|",
        f"| Recall (span protection) | {fmt(metrics['recall'])} ({counts['full']}/{counts['gold_total']}) |",
        f"| Precision | {fmt(metrics['precision'])} ({counts['edits_tp']}/{counts['edits_total']}) |",
        "",
        f"{level} Secondary metrics", "",
        "| Metric | Value |", "|---|---|",
        f"| F2 | {fmt(metrics['f2'])} |",
        f"| Over-masking per 1,000 lines | {fmt(metrics['fp_per_1k_lines'], 2)} ({counts['edits_fp']} edits outside gold) |",
        f"| Character recall | {fmt(metrics['char_recall'])} |",
        f"| Partial exposure rate | {fmt(metrics['partial_rate'])} ({counts['partial']}) |",
        f"| Missed rate | {fmt(metrics['missed_rate'])} ({counts['missed']}) |",
        f"| Latency p50 / p95 / max (ms) | {fmt(latency['p50'], 2)} / {fmt(latency['p95'], 2)} / "
        f"{fmt(latency['max'], 2)} (n={latency['n']}) |",
        "",
        f"{level} Composition and recall by type", "",
        "| Type | Gold spans | Recall |", "|---|---|---|",
        *[f"| {kind} | {metrics['composition']['by_type'][kind]} | {fmt(metrics['recall_by_type'][kind])} |"
          for kind in GOLD_TYPES],
        "",
        f"{level} Composition and recall by channel", "",
        "| Channel | Gold spans | Recall |", "|---|---|---|",
        *[f"| {name} | {metrics['composition']['by_channel'][name]} | {fmt(metrics['recall_by_channel'][name])} |"
          for name in CHANNELS],
        "",
    ]
    return lines


def render_report(meta: dict[str, Any], result: RunResult) -> str:
    system = meta["system"]
    dataset = meta["dataset"]
    git = meta["git"]
    system_git = meta.get("system_git")
    metrics = result.metrics
    settings = ", ".join(f"{key}={value}" for key, value in system.items() if key != "system")
    lines = [
        "# PromptGuard metric 1 report", "",
        f"- System: `{system.get('system')}`" + (f" ({settings})" if settings else ""),
        f"- Dataset: `{dataset['sessions_path']}` (sha256 `{dataset['sessions_sha256'][:12]}`) + "
        f"`{dataset['gold_path']}` (sha256 `{dataset['gold_sha256'][:12]}`): {dataset['sessions']} sessions, "
        f"{dataset['items']} items, {dataset['gold_spans']} gold spans; used as `{dataset['use']}`",
        f"- Lines: {metrics['lines_total']}; secret density per 1,000 lines: {fmt(metrics['density_per_1k_lines'], 2)}",
        f"- Code: commit `{(git['commit'] or 'unknown')[:12]}` on `{git['branch'] or 'unknown'}`, "
        f"evaluation {meta['versions']['evaluation']}, started {meta['started_at']}",
    ]
    if system_git is not None:
        lines.append(f"- System code: `{system_git['root']}`, commit `{(system_git['commit'] or 'unknown')[:12]}` "
                     f"on `{system_git['branch'] or 'unknown'}`")
    lines.append("")
    if meta["debug"]:
        lines += ["> **Warning:** this run used `--debug`. `debug/` contains raw text, including secrets. "
                  "Do not share or commit it.", ""]
    lines += _metric_sections(metrics, "##")
    return "\n".join(lines)


def write_run(run_dir: Path, *, meta: dict[str, Any], result: RunResult, debug: bool = False) -> list[str]:
    """Write every result file; return the names written."""
    _dump(run_dir / "run_meta.json", meta)
    _dump(run_dir / "metrics.json", result.metrics)
    _jsonl(run_dir / "per_span.jsonl", _per_span(result))
    _jsonl(run_dir / "per_edit.jsonl", _per_edit(result))
    (run_dir / "report.md").write_text(render_report(meta, result), encoding="utf-8")
    written = ["run_meta.json", "metrics.json", "per_span.jsonl", "per_edit.jsonl", "report.md"]
    if debug:
        (run_dir / "debug").mkdir()
        rows = [{"session_id": session_id, "item_id": item_id, "debug": output.debug}
                for (session_id, item_id), output in result.outputs.items() if output.debug is not None]
        _jsonl(run_dir / "debug" / "items.jsonl", rows)
        written.append("debug/items.jsonl")
    return written
