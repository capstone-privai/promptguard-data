"""Shared test helpers: the fixture pair and the PromptGuard checkout."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any

from evaluation.adapters.system_root import SystemRootError, load_worker, resolve_system_root

FIXTURES = Path(__file__).parent / "fixtures"
SESSIONS = FIXTURES / "sessions.jsonl"
GOLD = FIXTURES / "gold.jsonl"

HAS_CREDSWEEPER = importlib.util.find_spec("credsweeper") is not None
CREDSWEEPER_REASON = "credsweeper is not installed (pip install -r metric-1/evaluation/requirements.txt)"

try:
    SYSTEM_ROOT: Path | None = resolve_system_root()
except SystemRootError:
    SYSTEM_ROOT = None
# The PromptGuard worker runs CredSweeper, so PromptGuard tests need the checkout and its pinned CredSweeper.
try:
    load_worker(SYSTEM_ROOT)
    HAS_PROMPTGUARD, SKIP_REASON = True, ""
except SystemRootError as exc:
    HAS_PROMPTGUARD = False
    SKIP_REASON = f"PromptGuard tests need a promptguard-claude-demoV0 checkout and its credsweeper: {exc}"


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def finding(text: str, value: str, kind: str = "PASSWORD", nth: int = 0, **override: Any) -> dict[str, Any]:
    """A worker finding over the nth occurrence of `value`; the value itself stands in for its hash."""
    start = -1
    for _ in range(nth + 1):
        start = text.index(value, start + 1)
    return {"type": kind, "rule_id": "scripted", "confidence": "strong", "value_hash": value,
            "start": utf16_len(text[:start]), "end": utf16_len(text[:start + len(value)]), "source": "scripted",
            "offset_unit": "utf16_code_units", **override}


def found(*findings: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "findings": list(findings), "errors": []}


class ScriptedWorker:
    """Stands in for the checkout's worker module: `Adapter().scan` answers from a text → result table
    (an exception is raised), and finds nothing in any other text."""

    CREDSWEEPER_VERSION = "scripted"

    def __init__(self, results: dict[str, Any]):
        table = results

        class Adapter:
            def scan(self, text: str, source: str) -> Any:
                result = table.get(text, found())
                if isinstance(result, Exception):
                    raise result
                return result

        self.Adapter = Adapter


def require_credsweeper() -> None:
    """Call at module top before importing credsweeper; skips the whole module without it."""
    if not HAS_CREDSWEEPER:
        raise unittest.SkipTest(CREDSWEEPER_REASON)


def require_promptguard() -> Path:
    """Call at module top before using the PromptGuard adapter; skips the whole module without a checkout."""
    if not HAS_PROMPTGUARD:
        raise unittest.SkipTest(SKIP_REASON)
    return SYSTEM_ROOT
