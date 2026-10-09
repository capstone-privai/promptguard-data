"""Locate the PromptGuard checkout under evaluation and load its detector.

The system is promptguard-claude-demoV0: a Claude Code Native Mod (src/native-mod) that sends every text
bound for the model to a CredSweeper worker (src/credsweeper-adapter/worker.py) and replaces each finding
with a placeholder. Lookup order: an explicit path (`--system-root`), then $PROMPTGUARD_CLAUDE_ROOT, then
../promptguard-claude-demoV0 next to this repository (the same as metric 2).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from importlib import metadata
from pathlib import Path
from types import ModuleType

ENV_VAR = "PROMPTGUARD_CLAUDE_ROOT"
DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "promptguard-claude-demoV0"
WORKER = Path("src", "credsweeper-adapter", "worker.py")
MOD = Path("src", "native-mod", "hooks", "register.mjs")
_MODULE = "promptguard_claude_worker"


class SystemRootError(Exception):
    pass


def resolve_system_root(root: str | Path | None = None) -> Path:
    candidate = Path(root or os.environ.get(ENV_VAR) or DEFAULT_ROOT).expanduser().resolve()
    for required in (WORKER, MOD):
        if not (candidate / required).is_file():
            raise SystemRootError(f"no {required.as_posix()} under {candidate}; pass --system-root or set {ENV_VAR}")
    return candidate


def check_credsweeper(root: Path) -> str:
    """Return the installed CredSweeper version if it is the one the checkout pins in requirements.txt."""
    try:
        installed = metadata.version("credsweeper")
    except metadata.PackageNotFoundError:
        raise SystemRootError("credsweeper is not installed (pip install -r metric-1/evaluation/requirements.txt)") from None
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name, separator, version = line.split("#", 1)[0].partition("==")
        if separator and name.strip().lower() == "credsweeper" and version.strip() != installed:
            raise SystemRootError(f"{root.name} pins credsweeper=={version.strip()}, but {installed} is installed "
                                  "(pip install -r metric-1/evaluation/requirements.txt)")
    return installed


def load_worker(root: str | Path | None = None) -> ModuleType:
    """Import the checkout's worker.py, as the demo's own tests do. Refuses a second checkout once one is loaded."""
    resolved = resolve_system_root(root)
    loaded = sys.modules.get(_MODULE)
    if loaded is not None:
        origin = Path(loaded.__file__ or "").resolve()
        if origin != resolved / WORKER:
            raise SystemRootError(f"the PromptGuard worker is already loaded from {origin}, not {resolved}")
        return loaded
    check_credsweeper(resolved)
    spec = importlib.util.spec_from_file_location(_MODULE, resolved / WORKER)
    if spec is None or spec.loader is None:
        raise SystemRootError(f"cannot load {resolved / WORKER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[_MODULE]
        raise
    return module
