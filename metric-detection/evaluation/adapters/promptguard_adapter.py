"""PromptGuard (promptguard-claude-demoV0): the checkout's detector, then the checkout's own Native Mod.

The Claude Code mod (src/native-mod/hooks/register.mjs) sends each text bound for the model to the detector
worker (src/detector/worker.py) and writes a placeholder over every finding. Detection runs the checkout's
own detector in process (`pgdetector.load_detector().scan`, the ensemble the worker serves), without its HTTP
and MCP transport. The substitution runs the same checkout's register.mjs under Node (node_mod.py, mod_driver.mjs):
its scanBatch checks, placeholder numbering, remask passes and failure handling are the commit's own, with one Mod
instance per evaluated session, as the plugin has one per Claude Code session.

When the Mod cannot scan a text (an unsafe worker result, a worker exception, an ML module's timeout), it does what
that commit does. A fail-closed Mod (ca858be and later) sends its blocked marker instead of the text: the item is
scored as one edit over its whole text (its gold spans count as over-masked, never as exposed). An older Mod's hook
throws and Claude Code skips it, so the text goes out unchanged (failed open).

`required_adapters` names adapters that must be running, as the system's own `describe()` reports them: an
optional adapter the system skipped (an ML module without its packages or weights) stops the run instead of
leaving a result that silently lacks it.

Per-adapter findings: the detector's `scan` runs every adapter (`Detector.collect`) and then votes and merges
overlapping spans, which joins their rule ids and loses each contributor's own span. The adapter records what
`collect` returned for each item (adapter name, rule id, type, code point offsets; never text) by wrapping that
method on its own detector instance, so `scan` itself runs unchanged. The rows land in `ItemOutput.scan` and the
run folder's per_finding.jsonl / per_scan.jsonl. A detector without `collect` (a scripted test worker) records none.

Saved detections: with `detections_out`, every scanned item's worker result (the ensemble's final findings with
offsets, types, rules and scores, or its failure) and per-adapter rows are written to a gzipped JSON lines file.
They hold secret-shaped data (value hashes), so they belong in git-ignored run folders. `PromptGuardAdapter.replaying`
scores saved detections again with a checkout's Mod and no detector at all (no GPU, no ML packages).

Load the detector package with system_root.load_worker() before constructing the adapter, or let the adapter
do it. The detector is the system's own `load_detector()` with the checkout's own configuration: which adapters
run, how they vote and any ML modules are the system's business, and this adapter only records what it reports
(`describe()`).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from evaluation.adapters.base import ItemOutput, passthrough
from evaluation.adapters.node_mod import NodeMod
from evaluation.adapters.system_root import MOD, load_worker, resolve_system_root
from evaluation.dataset.schema import Session

_WARMUP_TEXT = "DB_PASSWORD=warmup123\n"
DETECTIONS_FORMAT = "promptguard-detections-v1"

# Dataset channel → the `source` the mod scans it as. prompt is the prompt.submit hook, instructions the
# CLAUDE.md blocks of prompt.context, tool_output the tool.call result. The arguments the model writes
# (tool_input) are nothing to mask: the mod restores placeholders in them before the tool runs. They pass
# through, and metric-detection does not score them. The keys must equal schema.SCORED_CHANNELS (test_system_contract).
# Every hook runs the same sanitize step on its text; the scorer drives it through prompt.submit.
CHANNEL_MAP: dict[str, str] = {"prompt": "user_prompt", "instructions": "claude_md", "tool_output": "tool_result"}


def mod_of(worker: ModuleType | None) -> Path:
    """The register.mjs of the checkout a worker package was loaded from; the default checkout for a test double."""
    origin = getattr(worker, "__file__", None)
    if origin:
        candidate = Path(origin).resolve().parents[3] / MOD  # <root>/src/detector/pgdetector/__init__.py
        if candidate.is_file():
            return candidate
    return resolve_system_root() / MOD


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SavedDetections:
    """Detections files (`*.jsonl.gz` in a folder, or one file) read back: worker results by (session, item)."""

    def __init__(self, location: str | Path):
        location = Path(location)
        files = sorted(location.glob("*.jsonl.gz")) if location.is_dir() else [location]
        if not files:
            raise FileNotFoundError(f"no detections (*.jsonl.gz) in {location}")
        self.items: dict[tuple[str, int], dict[str, Any]] = {}
        self.detector: dict[str, Any] | None = None
        for path in files:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    if row.get("format") == DETECTIONS_FORMAT:
                        self.detector = self.detector or row.get("detector")
                        continue
                    self.items[(row["session_id"], row["item_id"])] = row

    def get(self, session_id: str, item_id: int) -> dict[str, Any]:
        try:
            return self.items[(session_id, item_id)]
        except KeyError:
            raise KeyError(f"no saved detection for session {session_id} item {item_id}") from None


class PromptGuardAdapter:
    name = "promptguard"

    def __init__(self, worker: ModuleType | None = None, debug: bool = False, required_adapters: Sequence[str] = (),
                 *, mod: str | Path | None = None, detections_out: str | Path | None = None,
                 replay: SavedDetections | None = None):
        if os.environ.get("PG_DETECTOR_MODE", "normal") != "normal":
            # The worker's fault injection (crash exits the process) is for the demo's own failure tests.
            raise ValueError("unset PG_DETECTOR_MODE; the worker would inject faults")
        self.replay = replay
        self.debug = debug
        self.failed_open = 0
        self.blocked = 0
        self._collected: tuple[list[Any], list[str]] | None = None
        if replay is None:
            self.worker = worker or load_worker()
            self.detector = self.worker.load_detector()
            self._require(required_adapters)
            self.records_findings = self._record_collect()
            self.detector.scan(_WARMUP_TEXT, "warmup")  # keep rule loading out of the recorded latencies
            detector_info = self.detector.describe()
        else:
            self.worker = self.detector = None
            self.records_findings = True
            detector_info = replay.detector or {}
            if required_adapters:
                running = {adapter.get("name") for adapter in detector_info.get("adapters", [])}
                if missing := [name for name in required_adapters if name not in running]:
                    raise ValueError(f"the saved detections lack required adapter(s) {missing}")
        self.detector_info = detector_info
        self.mod_path = Path(mod) if mod else mod_of(self.worker)
        self.mod = NodeMod(self.mod_path)
        self._detections = None
        if detections_out is not None:
            Path(detections_out).parent.mkdir(parents=True, exist_ok=True)
            self._detections = gzip.open(detections_out, "wt", encoding="utf-8")
            self._write_detection({"format": DETECTIONS_FORMAT, "detector": detector_info,
                                   "mod_sha256": _sha256(self.mod_path)})

    @classmethod
    def replaying(cls, detections: str | Path, system_root: str | Path, **kwargs: Any) -> "PromptGuardAdapter":
        """Score saved detections with the Mod of `system_root` (a PromptGuard checkout); no detector runs."""
        return cls(replay=SavedDetections(detections), mod=resolve_system_root(system_root) / MOD, **kwargs)

    def _write_detection(self, row: dict[str, Any]) -> None:
        self._detections.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def close(self) -> None:
        if self._detections is not None:
            self._detections.close()
            self._detections = None
        self.mod.close()

    def _record_collect(self) -> bool:
        """Wrap this detector instance's `collect` so each scan leaves its per-adapter ballots in `_collected`."""
        collect = getattr(self.detector, "collect", None)
        if not callable(collect):
            return False

        def recording(texts: Sequence[str]) -> tuple[list[Any], list[str]]:
            per_text, errors = collect(texts)
            self._collected = (per_text, list(errors))
            return per_text, errors

        self.detector.collect = recording
        return True

    def _collect_record(self) -> dict[str, Any] | None:
        """The last scan's per-adapter findings as offset rows (RawFinding offsets are code points, as gold is)."""
        if not self.records_findings:
            return None
        collected, self._collected = self._collected, None
        record: dict[str, Any] = {"collected": collected is not None, "adapter_errors": [], "findings": []}
        if collected is None:  # scan raised before every adapter had answered
            return record
        per_text, errors = collected
        record["adapter_errors"] = sorted(set(errors))
        ballots = per_text[0] if per_text else {}
        rows = []
        for adapter, findings in ballots.items():
            for raw in findings:
                score = getattr(raw, "score", None)  # RawFinding has no score before the ML adapters (424df6a)
                rows.append({"adapter": str(adapter), "rule_id": str(raw.rule_id), "type": str(raw.type),
                             "start": int(raw.start), "end": int(raw.end), "confidence": str(raw.confidence),
                             "score": None if score is None else float(score)})
        record["findings"] = sorted(rows, key=lambda row: (row["start"], row["end"], row["adapter"], row["rule_id"]))
        return record

    def _require(self, names: Sequence[str]) -> None:
        if not names:
            return
        described = self.detector.describe()
        running = {adapter.get("name") for adapter in described.get("adapters", [])}
        if missing := [name for name in names if name not in running]:
            skipped = {entry.get("name"): entry.get("reason") for entry in described.get("skipped", [])}
            reasons = ", ".join(f"{name} ({skipped[name]})" if skipped.get(name) else f"{name} (not configured)"
                                for name in missing)
            raise ValueError(f"required detector adapter(s) not running: {reasons}; running: {sorted(running)}")

    def describe(self) -> dict[str, Any]:
        return {
            "system": self.name,
            "detector": self.detector_info,  # as the system reports it: adapters, versions, policy, skipped
            "mod": {"register_mjs_sha256": _sha256(self.mod_path), "node": self.mod.node_version,
                    "fail_closed": self.mod.fail_closed},
            "processed_channels": list(CHANNEL_MAP),
            "channel_map": dict(CHANNEL_MAP),
            "on_detector_failure": "block" if self.mod.fail_closed else "pass",
            "detections": "replayed" if self.replay is not None else "live",
            "failed_open_items": self.failed_open,
            "blocked_items": self.blocked,
        }

    def _scan(self, text: str, source: str) -> Any:
        try:
            return self.detector.scan(text, source)
        except Exception as exc:  # noqa: BLE001 - the worker answers any exception with HTTP 500, and the mod throws
            return {"ok": False, "exception": type(exc).__name__}

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        mod = self.mod.session()
        outputs: dict[int, ItemOutput] = {}
        for item in session.items:
            source = CHANNEL_MAP.get(item.channel)
            if source is None:
                outputs[item.item_id] = passthrough(item.item_id, item.text)
                continue
            started = time.perf_counter()
            if self.replay is not None:
                saved = self.replay.get(session.session_id, item.item_id)
                result, collect = saved["result"], saved.get("collect")
            else:
                self._collected = None
                result = self._scan(item.text, source)
                collect = self._collect_record()
                if self._detections is not None:
                    self._write_detection({"session_id": session.session_id, "item_id": item.item_id,
                                           "channel": item.channel, "source": source, "result": result,
                                           "collect": collect})
            output = mod.process(item.text, result)
            failure = None
            if output.status == "blocked":
                failure = "blocked" + (f": {output.error}" if output.error else "")
                self.blocked += 1
            elif output.status == "failed_open":
                failure = f"failed open: {output.error}"
                self.failed_open += 1
            elapsed_ms = (time.perf_counter() - started) * 1000
            debug = {"source": source, "result": result, "failure": failure} if self.debug else None
            scan = None if collect is None else {**collect, "failure": failure}
            outputs[item.item_id] = ItemOutput(item.item_id, output.text, output.edits, elapsed_ms, debug, scan)
        return outputs
