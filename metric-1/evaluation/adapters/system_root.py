"""Locate the PromptGuard checkout under evaluation and load its detector.

The system is promptguard-claude-demoV0: a Claude Code Native Mod (src/native-mod) that sends every text
bound for the model to a detector worker (src/detector/worker.py) and replaces each finding with a
placeholder. The worker serves the pgdetector package (src/detector/pgdetector): an ensemble of adapters
(CredSweeper, gitleaks, in-house patterns) and a consensus vote, configured by src/detector/detector.json.
Lookup order: an explicit path (`--system-root`), then $PROMPTGUARD_CLAUDE_ROOT, then
../promptguard-claude-demoV0 next to this repository (the same as metric 2).
"""

from __future__ import annotations

import importlib
import os
import sys
from importlib import metadata
from pathlib import Path
from types import ModuleType

ENV_VAR = "PROMPTGUARD_CLAUDE_ROOT"
DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "promptguard-claude-demoV0"
DETECTOR_DIR = Path("src", "detector")
WORKER = DETECTOR_DIR / "worker.py"
PACKAGE = DETECTOR_DIR / "pgdetector" / "__init__.py"
MOD = Path("src", "native-mod", "hooks", "register.mjs")
_PACKAGE = "pgdetector"


class SystemRootError(Exception):
    pass


def resolve_system_root(root: str | Path | None = None) -> Path:
    candidate = Path(root or os.environ.get(ENV_VAR) or DEFAULT_ROOT).expanduser().resolve()
    for required in (WORKER, PACKAGE, MOD):
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
    """Import the checkout's pgdetector package, the code worker.py serves (its `load_detector()` builds the
    ensemble from detector.json). Refuses a second checkout once one is loaded."""
    resolved = resolve_system_root(root)
    package_dir = resolved / DETECTOR_DIR
    loaded = sys.modules.get(_PACKAGE)
    if loaded is not None:
        origin = Path(loaded.__file__ or "").resolve()
        if origin != resolved / PACKAGE:
            raise SystemRootError(f"the PromptGuard detector is already loaded from {origin}, not {resolved}")
        return loaded
    check_credsweeper(resolved)
    sys.path.insert(0, str(package_dir))
    try:
        return importlib.import_module(_PACKAGE)
    except BaseException:
        for name in [name for name in sys.modules if name == _PACKAGE or name.startswith(_PACKAGE + ".")]:
            del sys.modules[name]
        raise
    finally:
        sys.path.remove(str(package_dir))
