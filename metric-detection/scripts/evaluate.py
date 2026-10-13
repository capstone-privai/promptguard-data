"""Score a system on a sessions/gold pair (metric-detection). See metric-detection/evaluation/README.md.

Run from the repository root:
  python metric-detection/scripts/evaluate.py validate [--sessions S] [--gold G]
  python metric-detection/scripts/evaluate.py run --system promptguard|credsweeper|gitleaks|oracle|identity [options]
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
