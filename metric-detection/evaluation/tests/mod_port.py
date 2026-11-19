"""Test oracle: the Python port of the Mod's substitution as of 2026-11-06 (register.mjs of cca44c4 .. e9089c2).

Until v3 the evaluation scored every commit with this port. It now runs each checkout's own register.mjs under Node
(adapters/node_mod.py); the port is kept only to check that path: for a Mod of these rules both must give the same
text and the same edits (test_system_contract.py, test_node_mod.py). `redact` follows scanBatch's checks on one
worker result, then redactText (numbered top to bottom), then remaskText and remaskPartial.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from evaluation.scorer.edits import Edit


class ModFailure(Exception):
    """The mod could not scan this text: its hook answers with BLOCKED_TEXT instead of the text."""


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


def _units(text: str) -> int:
    """String.length: UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


# remaskPartial's constants. A word is all lower case, all upper case or capitalized, joined by - _ . or spaces.
PART_MIN = 8
_WORD = "(?:[a-z]+|[A-Z]+|[A-Z][a-z]+)"
_WORDS_ONLY = re.compile(f"[-_. ]*{_WORD}(?:[-_. ]+{_WORD})*[-_. ]*")


def _part_min_length(raw: str) -> int:
    return max(PART_MIN, (_units(raw) + 1) // 2)


def _part_marker(placeholder: str) -> str:
    return f"{placeholder[:-1]}_PART]"


class ModSession:
    """The mod's placeholder ledger for one Claude Code session: one placeholder per value hash (a value keeps the
    type it got first), numbered per type in text order, and its reverse map (raw value → the placeholder it first
    got), which re-masks known raw values, and runs of their characters, wherever they come back."""

    def __init__(self) -> None:
        self.ledger: dict[Any, str] = {}
        self.counters: Counter[str] = Counter()
        self.reverse: dict[str, str] = {}
        self._part_size = -1
        self._part_windows: dict[str, list[tuple[str, int]]] = {}

    def placeholder(self, finding: dict[str, Any], raw: str) -> str:
        key = finding.get("value_hash")
        if key not in self.ledger:
            kind = type_name(finding.get("type"))
            self.counters[kind] += 1
            self.ledger[key] = f"[{kind}_{self.counters[kind]}]"
            self.reverse.setdefault(raw, self.ledger[key])
        return self.ledger[key]

    def redact(self, text: str, result: Any) -> tuple[str, list[Edit]]:
        """scanBatch's checks on one worker result, then redactText (numbered top to bottom), then remaskText."""
        out, edits = self._redact(text, result)
        return self._remask(text, out, edits)

    def _windows(self) -> dict[str, list[tuple[str, int]]]:
        """partWindows: every PART_MIN-character window of every raw value long enough to have parts."""
        if self._part_size != len(self.reverse):
            windows: dict[str, list[tuple[str, int]]] = {}
            for raw in self.reverse:
                for offset in range(len(raw) - PART_MIN + 1):
                    windows.setdefault(raw[offset:offset + PART_MIN], []).append((raw, offset))
            self._part_size, self._part_windows = len(self.reverse), windows
        return self._part_windows

    def _part_spans(self, text: str) -> list[tuple[int, int, str]]:
        """remaskPartial's search: left to right, the longest run long enough for its value, unless only words."""
        if len(text) < PART_MIN or not self.reverse:
            return []
        windows = self._windows()
        if not windows:
            return []
        spans, start = [], 0
        while start + PART_MIN <= len(text):
            hits = windows.get(text[start:start + PART_MIN])
            if hits is None:
                start += 1
                continue
            best: tuple[int, int, str] | None = None
            for raw, offset in hits:
                end, at = start + PART_MIN, offset + PART_MIN
                while end < len(text) and at < len(raw) and text[end] == raw[at]:
                    end += 1
                    at += 1
                if end - start >= _part_min_length(raw) and (best is None or end > best[1]):
                    best = (start, end, raw)
            if best is None or _WORDS_ONLY.fullmatch(text[best[0]:best[1]]):
                start += 1
                continue
            spans.append(best)
            start = best[1]
        return spans

    def _remask(self, text: str, out: str, edits: list[Edit]) -> tuple[str, list[Edit]]:
        """remaskText: every known raw value, longest first, is replaced by its placeholder in the redacted text,
        including where the detector missed it (and, like the mod, inside placeholders it already wrote); then
        remaskPartial masks the runs of a known value's characters that are left as [TYPE_N_PART]."""
        whole = any(raw in out for raw in self.reverse)
        if not whole and not self._part_spans(out):
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
        for raw, replacement in sorted(self.reverse.items(), key=lambda pair: -_units(pair[0])) if whole else ():
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
        for at, stop, raw in reversed(self._part_spans("".join(char for char, *_ in chars))):
            covered = chars[at:stop]
            start, end = min(c[1] for c in covered), max(c[2] for c in covered)
            chars[at:stop] = [(char, start, end, False) for char in _part_marker(self.reverse[raw])]
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
        length = _units(text)
        to_index = _code_point_offsets(text)
        ordered = sorted(findings, key=lambda f: (f["start"], f["end"]), reverse=True)
        # Every span is checked before any gets a number, as redactText does: a bad result leaves the ledger alone.
        previous_start = length + 1
        for finding in ordered:
            start, end = finding["start"], finding["end"]
            if finding.get("offset_unit") != "utf16_code_units":
                raise ModFailure("PromptGuard detector offset unit mismatch")
            if start < 0 or end > length or start >= end:
                raise ModFailure("PromptGuard detector invalid span")
            if end > previous_start:
                raise ModFailure("PromptGuard detector overlapping normalized spans")
            previous_start = start
        out, edits = text, []
        for finding in ordered[::-1]:  # top to bottom, so the first value in a text gets the lowest number
            start, end = finding["start"], finding["end"]
            if to_index is not None:  # a split surrogate pair cannot be expressed as a str edit
                start, end = to_index[start], to_index[end]
            edits.append(Edit(start=start, end=end, replacement=self.placeholder(finding, text[start:end])))
        for edit in edits[::-1]:
            out = out[:edit.start] + edit.replacement + out[edit.end:]
        return out, edits
