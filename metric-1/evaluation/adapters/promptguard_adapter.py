"""PromptGuard (promptguard-claude-demoV0): the mod's detector, then the mod's placeholder substitution.

The Claude Code mod (src/native-mod/hooks/register.mjs) sends each text bound for the model to the detector
worker (src/detector/worker.py) and writes a placeholder over every finding. Detection runs the checkout's
own detector in process (`pgdetector.load_detector().scan`, the ensemble the worker serves), without its HTTP
and MCP transport. The substitution is JavaScript, so `ModSession` follows its `placeholder` and `redactText`;
tests/test_system_contract.py runs register.mjs under Node and checks that both give the same text.

Load the detector package with system_root.load_worker() before constructing the adapter, or let the adapter
do it.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from types import ModuleType
from typing import Any

from evaluation.adapters.base import ItemOutput, passthrough
from evaluation.adapters.system_root import load_worker
from evaluation.dataset.schema import Session
from evaluation.scorer.edits import Edit

_WARMUP_TEXT = "DB_PASSWORD=warmup123\n"

# Dataset channel → the `source` the mod scans it as. prompt is the prompt.submit hook, instructions the
# CLAUDE.md blocks of prompt.context, tool_output the tool.call result. The arguments the model writes
# (tool_input) are nothing to mask: the mod restores placeholders in them before the tool runs. They pass
# through, and metric 1 does not score them. The keys must equal schema.SCORED_CHANNELS (test_system_contract).
CHANNEL_MAP: dict[str, str] = {"prompt": "user_prompt", "instructions": "claude_md", "tool_output": "tool_result"}


class ModFailure(Exception):
    """The mod's hook would throw. Its hooks have no .catch, so Claude Code skips them and the text goes out as is."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def type_name(value: object) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", str(value or "CREDENTIAL").upper()) or "CREDENTIAL"


def _code_point_offsets(text: str) -> dict[int, int] | None:
    """UTF-16 code unit offset → str index at every character boundary; None when the two coincide."""
    if len(text.encode("utf-16-le")) == 2 * len(text):
        return None
    offsets, units = {}, 0
    for index, char in enumerate(text):
        offsets[units] = index
        units += 2 if ord(char) > 0xFFFF else 1
    offsets[units] = len(text)
    return offsets


class ModSession:
    """The mod's placeholder ledger for one Claude Code session: one placeholder per (type, value hash),
    numbered per type in the order the mod meets them, and its reverse map (raw value → the placeholder it
    first got), which re-masks known raw values wherever they come back."""

    def __init__(self) -> None:
        self.ledger: dict[str, str] = {}
        self.counters: Counter[str] = Counter()
        self.reverse: dict[str, str] = {}

    def placeholder(self, finding: dict[str, Any], raw: str) -> str:
        kind = type_name(finding.get("type"))
        key = f"{kind}:{finding.get('value_hash')}"
        if key not in self.ledger:
            self.counters[kind] += 1
            self.ledger[key] = f"[{kind}_{self.counters[kind]}]"
            self.reverse.setdefault(raw, self.ledger[key])
        return self.ledger[key]

    def redact(self, text: str, result: Any) -> tuple[str, list[Edit]]:
        """scanBatch's checks on one worker result, then redactText (the last finding first), then remaskText."""
        out, edits = self._redact(text, result)
        return self._remask(text, out, edits)

    def _remask(self, text: str, out: str, edits: list[Edit]) -> tuple[str, list[Edit]]:
        """remaskText: every known raw value, longest first, is replaced by its placeholder in the redacted text,
        including where the detector missed it (and, like the mod, inside placeholders it already wrote)."""
        if not any(raw in out for raw in self.reverse):
            return out, edits
        # Each output character with the original range it stands for: a kept character its own index, a
        # placeholder character the whole range its placeholder replaced.
        chars: list[tuple[str, int, int, bool]] = []
        cursor = 0
        for edit in edits:
            chars += [(char, index, index + 1, True) for index, char in enumerate(text[cursor:edit.start], cursor)]
            chars += [(char, edit.start, edit.end, False) for char in edit.replacement]
            cursor = edit.end
        chars += [(char, index, index + 1, True) for index, char in enumerate(text[cursor:], cursor)]
        for raw, replacement in sorted(self.reverse.items(), key=lambda pair: -len(pair[0])):
            current = "".join(char for char, *_ in chars)
            at = current.find(raw)
            if at == -1:
                continue
            rebuilt, cursor = [], 0
            while at != -1:  # non-overlapping, left to right, as String.split does
                covered = chars[at:at + len(raw)]
                start, end = min(c[1] for c in covered), max(c[2] for c in covered)
                rebuilt += chars[cursor:at] + [(char, start, end, False) for char in replacement]
                cursor = at + len(raw)
                at = current.find(raw, cursor)
            chars = rebuilt + chars[cursor:]
        # Consecutive placeholder characters whose ranges overlap are one edit.
        merged: list[list[Any]] = []
        previous_kept = True
        for char, start, end, kept in chars:
            if not kept:
                if not previous_kept and start < merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                    merged[-1][2] += char
                else:
                    merged.append([start, end, char])
            previous_kept = kept
        return "".join(char for char, *_ in chars), [Edit(start=s, end=e, replacement=r) for s, e, r in merged]

    def _redact(self, text: str, result: Any) -> tuple[str, list[Edit]]:
        findings = result.get("findings") if isinstance(result, dict) else None
        errors = result.get("errors") if isinstance(result, dict) else None
        if not isinstance(findings, list) or result.get("ok") is not True or (isinstance(errors, list) and errors):
            raise ModFailure("PromptGuard detector unsafe result")
        # redactText would throw on reaching such a finding; checked up front because it cannot be sorted.
        if not all(isinstance(f, dict) and _is_int(f.get("start")) and _is_int(f.get("end")) for f in findings):
            raise ModFailure("PromptGuard detector invalid span")
        length = len(text.encode("utf-16-le")) // 2
        to_index = _code_point_offsets(text)
        out, edits, previous_start = text, [], length + 1
        for finding in sorted(findings, key=lambda f: (f["start"], f["end"]), reverse=True):
            start, end = finding["start"], finding["end"]
            if finding.get("offset_unit") != "utf16_code_units":
                raise ModFailure("PromptGuard detector offset unit mismatch")
            if start < 0 or end > length or start >= end:
                raise ModFailure("PromptGuard detector invalid span")
            if end > previous_start:
                raise ModFailure("PromptGuard detector overlapping normalized spans")
            if to_index is not None:  # a split surrogate pair cannot be expressed as a str edit
                start, end = to_index[start], to_index[end]
            replacement = self.placeholder(finding, text[start:end])
            out = out[:start] + replacement + out[end:]
            edits.append(Edit(start=start, end=end, replacement=replacement))
            previous_start = finding["start"]
        return out, edits[::-1]


class PromptGuardAdapter:
    name = "promptguard"

    def __init__(self, worker: ModuleType | None = None, debug: bool = False):
        if os.environ.get("PG_DETECTOR_MODE", "normal") != "normal":
            # The worker's fault injection (crash exits the process) is for the demo's own failure tests.
            raise ValueError("unset PG_DETECTOR_MODE; the worker would inject faults")
        self.worker = worker or load_worker()
        self.detector = self.worker.load_detector()
        self.debug = debug
        self.failed_open = 0
        self.detector.scan(_WARMUP_TEXT, "warmup")  # keep rule loading out of the recorded latencies

    def describe(self) -> dict[str, Any]:
        return {
            "system": self.name,
            "detector": self.detector.describe(),  # adapters and their versions, consensus, skipped adapters
            "processed_channels": list(CHANNEL_MAP),
            "channel_map": dict(CHANNEL_MAP),
            "failed_open_items": self.failed_open,
        }

    def _scan(self, text: str, source: str) -> Any:
        try:
            return self.detector.scan(text, source)
        except Exception as exc:  # noqa: BLE001 - the worker answers any exception with HTTP 500, and the mod throws
            return {"ok": False, "exception": type(exc).__name__}

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        mod = ModSession()
        outputs: dict[int, ItemOutput] = {}
        for item in session.items:
            source = CHANNEL_MAP.get(item.channel)
            if source is None:
                outputs[item.item_id] = passthrough(item.item_id, item.text)
                continue
            started = time.perf_counter()
            result = self._scan(item.text, source)
            failure = None
            try:
                text, edits = mod.redact(item.text, result)
            except ModFailure as exc:
                text, edits, failure = item.text, [], str(exc)
                self.failed_open += 1
            elapsed_ms = (time.perf_counter() - started) * 1000
            debug = {"source": source, "result": result, "failed_open": failure} if self.debug else None
            outputs[item.item_id] = ItemOutput(item.item_id, text, edits, elapsed_ms, debug)
        return outputs
