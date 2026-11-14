"""Per-adapter findings rows for systems that report them (ItemOutput.scan, PromptGuard only).

per_finding.jsonl has one row per finding an adapter returned before the system merged anything: adapter, rule id,
type, confidence, score (ML adapters) and the span in original-text code points, with its match against gold the
way the scorer matches an edit (`overlaps_gold`, `within_gold`) plus the ids of the gold spans it overlaps.
`valid` is false for a span the system rejects (empty, negative or past the text), which it never masks.

per_scan.jsonl has one row per item the system scanned: how many findings, the adapters that failed on it
(`ADAPTER_FAILURE:<name>`), and the mod's failure when it could not scan the item (`blocked` or passed unchanged).

Neither holds text: only names, offsets and flags.
"""

from __future__ import annotations

from typing import Any

from evaluation.dataset.schema import SCORED_CHANNELS, GoldSpan
from evaluation.run import RunResult


def match_gold(start: int, end: int, gold: list[GoldSpan]) -> tuple[bool, bool, list[int]]:
    """(overlaps_gold, within_gold, overlapping span ids), as span_scoring.score_item judges an edit."""
    overlapping = [span for span in gold if start < span.end and span.start < end]
    within = any(span.start <= start and end <= span.end for span in overlapping)
    return bool(overlapping), within, sorted(span.span_id for span in overlapping)


def per_finding_rows(result: RunResult) -> list[dict[str, Any]]:
    rows = []
    for session in result.sessions:
        for item in session.items:
            output = result.outputs.get((session.session_id, item.item_id))
            if output is None or output.scan is None:
                continue
            gold = session.gold_for(item.item_id)
            blocked = output.scan.get("failure") is not None and bool(output.edits)  # block mode masks it whole
            for finding in output.scan["findings"]:
                start, end = finding["start"], finding["end"]
                valid = 0 <= start < end <= len(item.text)
                overlaps, within, span_ids = match_gold(start, end, gold) if valid else (False, False, [])
                rows.append({"session_id": session.session_id, "item_id": item.item_id, "channel": item.channel,
                             "scored": item.channel in SCORED_CHANNELS, **finding, "valid": valid,
                             "overlaps_gold": overlaps, "within_gold": within, "gold_span_ids": span_ids,
                             "item_blocked": blocked})
    return rows


def per_scan_rows(result: RunResult) -> list[dict[str, Any]]:
    rows = []
    for session in result.sessions:
        for item in session.items:
            output = result.outputs.get((session.session_id, item.item_id))
            if output is None or output.scan is None:
                continue
            failure = output.scan.get("failure")
            rows.append({"session_id": session.session_id, "item_id": item.item_id, "channel": item.channel,
                         "scored": item.channel in SCORED_CHANNELS, "collected": output.scan.get("collected", True),
                         "findings": len(output.scan["findings"]), "adapter_errors": output.scan["adapter_errors"],
                         "failure": failure,
                         "blocked": failure is not None and bool(output.edits)})
    return rows
