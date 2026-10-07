"""Baseline: gitleaks alone, masking every finding. Reads what scripts/run_gitleaks.py found.

The evaluator does not run subprocesses, so gitleaks runs beforehand and this adapter replays its
findings (item offsets, no secrets). The findings must come from the sessions file being scored:
its SHA-256 is checked against the one recorded next to the findings.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation.adapters.base import ItemOutput, passthrough, select_non_overlapping
from evaluation.dataset.io import file_sha256
from evaluation.dataset.schema import Session
from evaluation.scorer.edits import Edit, apply_edits

REPLACEMENT = "[SECRET]"


class GitleaksAdapter:
    name = "gitleaks"

    def __init__(self, findings_path: str | Path, sessions_path: str | Path):
        self.findings_path = Path(findings_path)
        meta_path = Path(f"{self.findings_path}.meta.json")
        if not self.findings_path.is_file() or not meta_path.is_file():
            raise ValueError(f"{self.findings_path} or its .meta.json is missing; run metric-1/scripts/run_gitleaks.py")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if self.meta["sessions_sha256"] != file_sha256(sessions_path):
            raise ValueError(f"{self.findings_path.name} was made from a different sessions file "
                             f"({self.meta['sessions']}); rerun metric-1/scripts/run_gitleaks.py --sessions {sessions_path}")
        self.channels = tuple(self.meta["channels"])
        self._spans: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
        for line in self.findings_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            self._spans[(r["session_id"], r["item_id"])].append((r["start"], r["end"]))

    def describe(self) -> dict[str, Any]:
        return {"system": self.name, "findings": str(self.findings_path),
                "findings_sha256": file_sha256(self.findings_path), **self.meta}

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        outputs: dict[int, ItemOutput] = {}
        for item in session.items:
            if item.channel not in self.channels:
                outputs[item.item_id] = passthrough(item.item_id, item.text)
                continue
            spans = select_non_overlapping(self._spans.get((session.session_id, item.item_id), []))
            edits = [Edit(start=start, end=end, replacement=REPLACEMENT) for start, end in spans]
            # gitleaks scans all items in one run, so there is no per-item latency (scan_seconds is in describe()).
            outputs[item.item_id] = ItemOutput(item.item_id, apply_edits(item.text, edits), edits)
        return outputs
