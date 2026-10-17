"""Where things are, relative to this repository."""

from __future__ import annotations

from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DASHBOARD_ROOT.parent
METRIC_DETECTION = REPO_ROOT / "metric-detection"
METRIC_LATENCY = REPO_ROOT / "metric-latency"
DATA_TEST = METRIC_DETECTION / "data_test"
WEB_ROOT = DASHBOARD_ROOT / "web"
DEFAULT_DATA_DIR = REPO_ROOT / "runs" / "dashboard"  # runs/ is git-ignored: results hold dataset text
