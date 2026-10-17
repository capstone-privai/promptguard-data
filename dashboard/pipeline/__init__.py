"""Dashboard pipeline: evaluate PromptGuard commits and write the files the web UI reads.

The metric-detection scorer (metric-detection/evaluation) is a plain folder, not an installed package, so importing
this package puts metric-detection/ on sys.path.
"""

import sys

from pipeline.paths import METRIC_DETECTION

if str(METRIC_DETECTION) not in sys.path:
    sys.path.insert(0, str(METRIC_DETECTION))
