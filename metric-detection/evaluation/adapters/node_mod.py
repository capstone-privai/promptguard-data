"""The checkout's own Native Mod, run under Node, and its output mapped to original-text edits.

`NodeMod(register_mjs)` starts one Node process (mod_driver.mjs) for a checkout's src/native-mod/hooks/register.mjs and
keeps it for the life of the adapter; `NodeMod.session()` gives a fresh Mod instance (its own placeholder ledger and
known values) for one evaluated session, and `ModSession.process(text, worker_result)` runs one text through the Mod's
prompt.submit hook. So every commit is scored with its own placeholder rules, remask passes and failure handling.

The Mod returns text only. The scorer needs edits in original-text coordinates, so `map_edits` derives them, in two
steps that follow what the Mod did:
1. detector pass: the driver also returns the Mod's redactText output for the same findings (stage1). The findings say
   which original ranges it replaced, and each replacement is one placeholder ([TYPE_N]) at that place in stage1;
   with a public prefix, the prefix characters before it are kept text.
2. remask (only where the hook's text differs from stage1): stage1 and the final text are walked side by side. Equal
   text is kept; a placeholder in the final text that stage1 does not have there replaced the known value it stands
   for (reverseVault, which the driver returns), a [TYPE_N_PART] marker the longest run of that value's characters,
   and a bracket group with placeholders inside (a short value re-masked inside an earlier placeholder) the text it
   reads as once its inner placeholders are put back.
Each output character then stands for an original range (a kept character its own index, a placeholder character the
range its placeholder replaced), and consecutive placeholder characters whose ranges overlap are one edit, as the
evaluation has always counted them. Text the walk cannot explain raises ModMappingError: nothing is guessed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.scorer.edits import Edit, verify

DRIVER = Path(__file__).with_name("mod_driver.mjs")
NODE_ENV = "PROMPTGUARD_NODE"  # a node binary other than the one on PATH
PLACEHOLDER = re.compile(r"\[[A-Z0-9_]+_\d+(?:_PART)?\]")  # what every Mod writes: [TYPE_N] and [TYPE_N_PART]
WHOLE = re.compile(r"\[[A-Z0-9_]+_\d+\]")
GROUP_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_[]")
PART_MIN = 8  # remaskPartial's shortest run (UTF-16 units; the values here are ASCII)


class ModDriverError(RuntimeError):
    """The Node driver could not run the Mod (missing node, a Mod it cannot drive, a crash)."""


class ModMappingError(ValueError):
    """The Mod's output could not be mapped to original-text edits."""


def node_binary() -> str:
    node = os.environ.get(NODE_ENV) or shutil.which("node")
    if not node:
        raise ModDriverError(f"node is not installed (the Mod is JavaScript); put it on PATH or set {NODE_ENV}")
    return node


@dataclass(frozen=True)
class ModOutput:
    status: str  # ok, blocked (the Mod sent its blocked marker instead) or failed_open (the hook threw, text unchanged)
    text: str
    edits: list[Edit]
    error: str | None = None


class NodeMod:
    def __init__(self, register_mjs: str | Path):
        self.path = Path(register_mjs).resolve()
        if not self.path.is_file():
            raise ModDriverError(f"no Mod at {self.path}")
        self._lock = threading.Lock()
        self._process = subprocess.Popen([node_binary(), str(DRIVER), str(self.path)], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                         bufsize=1)
        info = self.request({"op": "describe"})
        self.node_version: str = info["node"]
        self.fail_closed: bool = bool(info["fail_closed"])
        self.exposed: list[str] = list(info["exposed"])

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            process = self._process
            if process.poll() is not None:
                raise ModDriverError(f"the Mod driver exited ({process.returncode}): {process.stderr.read()[-2000:]}")
            process.stdin.write(json.dumps(payload) + "\n")  # ASCII, so lone surrogates survive the pipe
            process.stdin.flush()
            line = process.stdout.readline()
        if not line:
            raise ModDriverError(f"the Mod driver stopped: {process.stderr.read()[-2000:]}")
        answer = json.loads(line)
        if "driver_error" in answer:
            raise ModDriverError(answer["driver_error"])
        return answer

    def session(self) -> "ModSession":
        self.request({"op": "session"})
        return ModSession(self)

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.stdin.close()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def __del__(self) -> None:  # noqa: D105
        try:
            self.close()
        except Exception:  # noqa: BLE001 - interpreter shutdown
            pass

    def describe(self) -> dict[str, Any]:
        return {"mod": str(self.path), "node": self.node_version, "fail_closed": self.fail_closed,
                "on_detector_failure": "block" if self.fail_closed else "pass"}


class ModSession:
    """One evaluated session's Mod instance. Sessions of one NodeMod must be used one after the other."""

    def __init__(self, mod: NodeMod):
        self.mod = mod

    def process(self, text: str, result: Any) -> ModOutput:
        answer = self.mod.request({"op": "item", "text": text, "result": result})
        status, out = answer["status"], answer["text"]
        if status == "blocked":  # an empty text has nothing to mask; scored as sent empty
            return ModOutput(status, out if text else "", [Edit(0, len(text), out)] if text else [], answer.get("error"))
        if status == "failed_open" or out == text:
            return ModOutput(status, out, [], answer.get("error"))
        edits = map_edits(text, result, out, answer.get("stage1"), answer.get("vault"))
        return ModOutput(status, out, edits)


# ---- mapping ---------------------------------------------------------------------------------------------------

def _code_point_offsets(text: str) -> dict[int, int] | None:
    """UTF-16 code unit offset -> str index at every character boundary; None when the two coincide."""
    if len(text.encode("utf-16-le")) == 2 * len(text):
        return None
    offsets, units = {}, 0
    for index, char in enumerate(text):
        offsets[units] = index
        units += 2 if ord(char) > 0xFFFF else 1
    offsets[units] = len(text)
    return offsets


@dataclass
class _Piece:
    """A run of a Mod output: kept original text from `start`, or placeholder text for original [start, end)."""
    text: str
    start: int
    end: int
    kept: bool


def _stage1(text: str, result: dict[str, Any], stage1: str) -> list[_Piece]:
    to_index = _code_point_offsets(text)
    spans = []
    for finding in result.get("findings") or []:
        start, end = finding["start"], finding["end"]
        if to_index is not None:
            if start not in to_index or end not in to_index:
                raise ModMappingError("a finding splits a surrogate pair")
            start, end = to_index[start], to_index[end]
        spans.append((start, end))
    pieces: list[_Piece] = []
    cursor = at = 0
    for start, end in sorted(spans):
        keep = text[cursor:start]
        if not stage1.startswith(keep, at):
            raise ModMappingError("detector-pass text does not keep the text between findings")
        if keep:
            pieces.append(_Piece(keep, cursor, start, True))
        at += len(keep)
        match, prefix = None, 0
        while prefix < end - start:  # a public prefix stays in front of the placeholder as kept text
            match = WHOLE.match(stage1, at + prefix)
            if match or stage1[at + prefix] != text[start + prefix]:
                break
            prefix += 1
        if match is None:
            raise ModMappingError("no placeholder where the detector found a value")
        if prefix:
            pieces.append(_Piece(text[start:start + prefix], start, start + prefix, True))
        pieces.append(_Piece(match.group(), start + prefix, end, False))
        at, cursor = match.end(), end
    if stage1[at:] != text[cursor:]:
        raise ModMappingError("detector-pass text does not end with the text after the last finding")
    if cursor < len(text):
        pieces.append(_Piece(text[cursor:], cursor, len(text), True))
    return pieces


class _Stage1Text:
    """stage1 as pieces, with the original range behind any stretch of it."""

    def __init__(self, pieces: list[_Piece]):
        self.pieces = pieces
        self.offsets, at = [], 0
        for piece in pieces:
            self.offsets.append(at)
            at += len(piece.text)

    def slices(self, a: int, b: int):
        """The pieces' parts covering stage1[a:b], as _Piece."""
        for index in range(max(0, bisect_right(self.offsets, a) - 1), len(self.pieces)):
            piece, offset = self.pieces[index], self.offsets[index]
            if offset >= b:
                break
            low, high = max(a, offset), min(b, offset + len(piece.text))
            if low >= high:
                continue
            if piece.kept:
                yield _Piece(piece.text[low - offset:high - offset], piece.start + low - offset,
                             piece.start + high - offset, True)
            else:
                yield _Piece(piece.text[low - offset:high - offset], piece.start, piece.end, False)

    def span(self, a: int, b: int) -> tuple[int, int]:
        parts = list(self.slices(a, b))
        return min(p.start for p in parts), max(p.end for p in parts)


def _group(out: str, at: int) -> str | None:
    """A bracket group of placeholder characters starting at `at` with a placeholder inside, else None."""
    depth = 0
    for index in range(at, len(out)):
        char = out[index]
        if char not in GROUP_CHARS:
            return None
        depth += (char == "[") - (char == "]")
        if depth == 0:
            group = out[at:index + 1]
            return group if PLACEHOLDER.search(group[1:-1]) else None
    return None


class _Vault:
    def __init__(self, vault: list[list[str]] | None):
        self.whole: dict[str, str] = {}  # placeholder -> the secret part of its value (after a public prefix)
        for raw, masked, placeholder in vault or []:
            prefix = masked[:len(masked) - len(placeholder)] if masked.endswith(placeholder) else ""
            self.whole.setdefault(placeholder, raw[len(prefix):] if raw.startswith(prefix) else raw)

    def part_length(self, token: str, stage1: str, at: int) -> int | None:
        """remaskPartial's run at stage1[at:]: the longest run of the owner value's characters from here."""
        value = self.whole.get(token[:-len("_PART]")] + "]")
        if value is None or len(value) < PART_MIN:
            return None
        window, best = stage1[at:at + PART_MIN], None
        offset = value.find(window)
        while offset != -1 and len(window) == PART_MIN:
            end, source = at + PART_MIN, offset + PART_MIN
            while end < len(stage1) and source < len(value) and stage1[end] == value[source]:
                end += 1
                source += 1
            best = max(best or 0, end - at)
            offset = value.find(window, offset + 1)
        return best

    def length(self, token: str, stage1: str, at: int) -> int | None:
        """How much of stage1 from `at` the placeholder or part marker `token` replaced, if it can have."""
        if token.endswith("_PART]"):
            return self.part_length(token, stage1, at)
        value = self.whole.get(token)
        return len(value) if value and stage1.startswith(value, at) else None

    def lengths(self, token: str, stage1: str, at: int) -> list[int]:
        """`length`, and for a part marker the shorter runs too, longest first: the Mod extends a run over the text
        left after the whole-value pass, where a value right after the run is already a placeholder, so the run in
        stage1 can be shorter than the longest match there."""
        best = self.length(token, stage1, at)
        if not best or not token.endswith("_PART]"):
            return [best] if best else []
        value = self.whole.get(token[:-len("_PART]")] + "]") or ""
        return list(range(best, max(PART_MIN, -(-len(value) // 2)) - 1, -1))

    def _expansions(self, token: str) -> list[str]:
        """What an inner placeholder can stand for: its value; for a part marker, the runs of its value long enough
        to be one (remaskPartial's minimum, max(8, half the value)), longest first."""
        if not token.endswith("_PART]"):
            value = self.whole.get(token)
            return [value] if value else []
        value = self.whole.get(token[:-len("_PART]")] + "]") or ""
        shortest = max(PART_MIN, -(-len(value) // 2))
        return [value[start:start + size] for size in range(len(value), shortest - 1, -1)
                for start in range(len(value) - size + 1)]

    def ungroup(self, group: str, stage1: str, at: int) -> int | None:
        """A placeholder re-masked inside another (a short value, or a run of one, that also matches placeholder
        letters): put inner values back, innermost first, until it reads as stage1 here."""
        if stage1.startswith(group, at):
            return len(group)
        if PLACEHOLDER.fullmatch(group) and (length := self.length(group, stage1, at)):
            return length
        inner = PLACEHOLDER.search(group, 1, len(group) - 1)
        if inner is None:
            return None
        for expansion in self._expansions(inner.group()):
            candidate = group[:inner.start()] + expansion + group[inner.end():]
            stop = inner.start() + len(expansion)
            # keep a run only where it completes an outer placeholder or reads as stage1 so far
            if not (stage1.startswith(candidate[:stop], at)
                    or any(m.start() < stop and inner.start() < m.end() for m in PLACEHOLDER.finditer(candidate))):
                continue
            if (length := self.ungroup(candidate, stage1, at)) is not None:
                return length
        return None


def _continues(stage1: str, out: str, i: int, j: int, vault: _Vault) -> bool:
    """Whether the walk can go on from stage1[i:] and out[j:] (one step's look-ahead)."""
    if j >= len(out):
        return i == len(stage1)
    if out[j] == "[":
        match = PLACEHOLDER.match(out, j)
        if match and (stage1.startswith(match.group(), i) or vault.length(match.group(), stage1, i)):
            return True
        if match is None and _group(out, j):
            return True  # a group is checked when the walk gets there
    stop = out.find("[", j + 1)
    stop = len(out) if stop == -1 else stop
    return stage1.startswith(out[j:stop], i)


def _remask(stage1: str, out: str, base: _Stage1Text, vault: _Vault) -> list[_Piece]:
    pieces: list[_Piece] = []
    i = j = 0
    while j < len(out):
        if out[j] == "[":
            match = PLACEHOLDER.match(out, j)
            if match and not stage1.startswith(match.group(), i):
                length = next((n for n in vault.lengths(match.group(), stage1, i)
                               if _continues(stage1, out, i + n, match.end(), vault)), None)
                if length:
                    start, end = base.span(i, i + length)
                    pieces.append(_Piece(match.group(), start, end, False))
                    i, j = i + length, match.end()
                    continue
            if not (i < len(stage1) and stage1[i] == "["):
                group = _group(out, j)
                length = vault.ungroup(group, stage1, i) if group and not stage1.startswith(group, i) else None
                if length:
                    start, end = base.span(i, i + length)
                    pieces.append(_Piece(group, start, end, False))
                    i, j = i + length, j + len(group)
                    continue
        stop = out.find("[", j + 1)
        stop = len(out) if stop == -1 else stop
        if stage1[i:i + stop - j] != out[j:stop]:
            raise ModMappingError(f"remask output differs from the detector-pass text at offset {j} with no "
                                  "placeholder to explain it")
        pieces.extend(base.slices(i, i + stop - j))
        i, j = i + stop - j, stop
    if i != len(stage1):
        raise ModMappingError("remask output ends before the detector-pass text")
    return pieces


def _edits(pieces: list[_Piece]) -> list[Edit]:
    """Consecutive placeholder pieces whose original ranges overlap are one edit."""
    merged: list[list[Any]] = []
    previous_kept = True
    for piece in pieces:
        if not piece.kept:
            if not previous_kept and piece.start < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], piece.end)
                merged[-1][2] += piece.text
            else:
                merged.append([piece.start, piece.end, piece.text])
        previous_kept = piece.kept
    return [Edit(start, end, replacement) for start, end, replacement in merged]


def map_edits(text: str, result: dict[str, Any], out: str, stage1: str | None, vault: list[list[str]] | None) -> list[Edit]:
    """Original-text edits that turn `text` into the Mod's `out` (see the module docstring)."""
    stage1 = out if stage1 is None else stage1
    pieces = _stage1(text, result, stage1)
    if stage1 != out:
        pieces = _remask(stage1, out, _Stage1Text(pieces), _Vault(vault))
    edits = _edits(pieces)
    try:
        verify(text, out, edits)
    except ValueError as exc:
        raise ModMappingError(str(exc)) from None
    return edits
