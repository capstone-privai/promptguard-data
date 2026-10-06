"""Shared test helpers: the fixture pair and the PromptGuard checkout."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from evaluation.adapters.system_root import SystemRootError, use_system_root

FIXTURES = Path(__file__).parent / "fixtures"
SESSIONS = FIXTURES / "sessions.jsonl"
GOLD = FIXTURES / "gold.jsonl"

try:
    SYSTEM_ROOT: Path | None = use_system_root()
except SystemRootError:
    SYSTEM_ROOT = None

HAS_CREDSWEEPER = importlib.util.find_spec("credsweeper") is not None
CREDSWEEPER_REASON = "credsweeper is not installed (pip install -r metric-1/evaluation/requirements.txt)"
# The PromptGuard detector runs CredSweeper, so PromptGuard tests need both.
HAS_PROMPTGUARD = SYSTEM_ROOT is not None and HAS_CREDSWEEPER
SKIP_REASON = ("PromptGuard tests need credsweeper and a promptguard-demo-v0 checkout "
               "(set PROMPTGUARD_ROOT or clone it next to this repository)")


def require_credsweeper() -> None:
    """Call at module top before importing credsweeper; skips the whole module without it."""
    if not HAS_CREDSWEEPER:
        raise unittest.SkipTest(CREDSWEEPER_REASON)


def require_promptguard() -> Path:
    """Call at module top before importing promptguard; skips the whole module without a checkout."""
    if not HAS_PROMPTGUARD:
        raise unittest.SkipTest(SKIP_REASON)
    return SYSTEM_ROOT
