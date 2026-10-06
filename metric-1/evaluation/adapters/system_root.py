"""Locate the PromptGuard checkout whose `promptguard` package is evaluated, and make it importable.

The system lives in its own repository (promptguard-demo-v0). Lookup order: an explicit path
(`--system-root`), then $PROMPTGUARD_ROOT, then ../promptguard-demo-v0 next to this repository.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_VAR = "PROMPTGUARD_ROOT"
DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "promptguard-demo-v0"


class SystemRootError(Exception):
    pass


def resolve_system_root(root: str | Path | None = None) -> Path:
    candidate = Path(root or os.environ.get(ENV_VAR) or DEFAULT_ROOT).expanduser().resolve()
    if not (candidate / "promptguard" / "pipeline.py").is_file():
        raise SystemRootError(f"no promptguard/pipeline.py under {candidate}; pass --system-root or set {ENV_VAR}")
    return candidate


def use_system_root(root: str | Path | None = None) -> Path:
    """Put the checkout first on sys.path. Refuses to switch once another checkout was imported."""
    resolved = resolve_system_root(root)
    loaded = sys.modules.get("promptguard")
    if loaded is not None:
        origin = Path(next(iter(getattr(loaded, "__path__", [])), "")).resolve()
        if origin != resolved / "promptguard":
            raise SystemRootError(f"promptguard is already imported from {origin}, not {resolved}")
        return resolved
    if str(resolved) not in sys.path:
        sys.path.insert(0, str(resolved))
    return resolved
