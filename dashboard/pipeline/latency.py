"""metric-latency for one PromptGuard checkout: run metric-latency/scripts/m4.py against it, then condense the
samples into what the UI shows (latency.json).

Statistics come from m4.py itself (nearest-rank quantiles, least-squares fits), so the numbers match its reports.
m4.py writes no text, only timings, sizes and finding counts.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.repo import detector_timeout
from pipeline.paths import METRIC_LATENCY, REPO_ROOT
from pipeline.runner import EvaluationError, child_env, tool_version, write_json

SCRIPTS = METRIC_LATENCY / "scripts"
M4 = SCRIPTS / "m4.py"
LATENCY_VERSION = 2  # bump when condense() or latency.json changes, so every commit is measured again

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import m4  # noqa: E402
import m4_workloads as workloads  # noqa: E402


def capture_files(paths: Sequence[str]) -> list[Path]:
    """The metric-task API captures behind --guard paths (folders are searched like m4.py does)."""
    found = []
    for raw in paths:
        path = Path(raw)
        found += sorted(path.rglob(workloads.CAPTURE_FILE)) if path.is_dir() else [path]
    return found


def environment(adapters: str, guard: Sequence[str], repeat: int, warmup: int) -> dict[str, Any]:
    """What latency numbers depend on besides the system: the evaluator, its options, the machine, gitleaks."""
    digest = hashlib.sha256()
    for path in (M4, SCRIPTS / "m4_workloads.py"):
        digest.update(path.read_bytes())
    captures = capture_files(guard)
    machine = {"platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count()}
    parts = {"code": digest.hexdigest(), "adapters": adapters, "repeat": repeat, "warmup": warmup,
             "guard": [hashlib.sha256(path.read_bytes()).hexdigest() for path in captures],
             "machine": machine, "gitleaks": tool_version(["gitleaks", "version"]), "version": LATENCY_VERSION}
    return {"fingerprint": hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest(),
            "adapters": adapters, "repeat": repeat, "warmup": warmup, "guard_captures": len(captures),
            "machine": machine, "gitleaks": parts["gitleaks"]}


def _stats(values: list[float]) -> dict[str, Any]:
    return {"p50": m4.quantile(values, 0.5), "p95": m4.quantile(values, 0.95),
            "max": max(values) if values else None, "n": len(values)}


def condense(run_dir: Path) -> dict[str, Any]:
    meta, calls, requests = m4.load_run(run_dir)
    single, batch_item = 1, workloads.SYNTH_BATCH_ITEM
    detectors = []
    for detector in meta["detectors"]:
        label = detector["label"]
        rows = [row for row in calls if row["detector"] == label]
        ok = [row for row in rows if row["ok"] and row.get("detector_ms") is not None]
        synth = [row for row in ok if row["source"] == "synth"]

        def synth_ms(**fixed: int) -> list[float]:
            return [row["detector_ms"] for row in synth if all(row.get(key) == value for key, value in fixed.items())]

        sizes = sorted({row["size"] for row in synth if row.get("batch") == single})
        batches = sorted({row["batch"] for row in synth if row.get("size") == batch_item})
        by_size = m4.fit([(row["bytes"] / 1024, row["detector_ms"]) for row in synth if row.get("batch") == single])
        by_items = m4.fit([(row["n_items"], row["detector_ms"]) for row in synth if row.get("size") == batch_item])
        guard = None
        mine = [request for request in requests if request["detector"] == label]
        if mine:
            per_call: dict[tuple, list[float]] = defaultdict(list)
            for row in ok:
                if row["source"] == "guard":
                    per_call[(row["session"], row["request"], row["batch"])].append(row["detector_ms"])
            totals = [sum(m4.quantile(per_call[(request["session"], request["request"], index)], 0.5) or 0
                          for index in range(request["calls"])) for request in mine]
            guard = {"sessions": len({request["session"] for request in mine}), "requests": len(mine),
                     **_stats(totals), "blocked": sum(1 for request in mine if request["findings"] or request["failed"])}
        describe = detector.get("describe") or {}
        detectors.append({
            "label": label,
            "adapters": [adapter.get("name") for adapter in describe.get("adapters", [])],
            "versions": {adapter.get("name"): adapter.get("version") for adapter in describe.get("adapters", [])},
            "consensus": describe.get("consensus"),
            "skipped": describe.get("skipped", []),
            "startup_ms": detector.get("startup_ms"),
            "cold": detector.get("cold"),
            "single_1k": _stats(synth_ms(size=1024, batch=single)),
            "single_64k": _stats(synth_ms(size=65536, batch=single)),
            "size_sweep": [{"size": size, **_stats(synth_ms(size=size, batch=single))} for size in sizes],
            "batch_sweep": [{"batch": batch, **_stats(synth_ms(size=batch_item, batch=batch))} for batch in batches],
            "fit_size": {"fixed_ms": by_size[0], "ms_per_kb": by_size[1]} if by_size else None,
            "fit_items": {"fixed_ms": by_items[0], "ms_per_string": by_items[1]} if by_items else None,
            "all": _stats([row["detector_ms"] for row in ok]),
            "over_timeout": sum(1 for row in rows if row.get("over_timeout")),
            "failed": sum(1 for row in rows if not row["ok"]),
            "gap_p50": m4.quantile([row["call_ms"] - row["detector_ms"] for row in ok], 0.5),
            "guard": guard,
        })
    return {"machine": meta["machine"], "repeat": meta["repeat"], "warmup": meta["warmup"],
            "timeout_ms": meta["timeout_ms"], "batch_item_chars": batch_item,
            "started_at": meta["started_at"], "finished_at": meta.get("finished_at"), "detectors": detectors}


def headline(data: dict[str, Any]) -> dict[str, Any]:
    ensemble = next((detector for detector in data["detectors"] if detector["label"] == "ensemble"),
                    data["detectors"][0] if data["detectors"] else None)
    if ensemble is None:
        return {}
    return {"single_1k_p50": ensemble["single_1k"]["p50"], "single_64k_p50": ensemble["single_64k"]["p50"],
            "ms_per_string": (ensemble["fit_items"] or {}).get("ms_per_string"),
            "guard_p95": (ensemble["guard"] or {}).get("p95"),
            "over_timeout": ensemble["over_timeout"],
            "startup_ms": ensemble["startup_ms"]}


def evaluate(system_root: Path, out_dir: Path, *, python: str, adapters: str, guard: Sequence[str], repeat: int,
             warmup: int, commit: dict[str, Any], system_fingerprint: str, env: dict[str, Any],
             cancelled: Callable[[], bool] = lambda: False) -> dict[str, Any]:
    """Measure, condense and write out_dir (latency.json, meta.json, m4/ with the raw samples)."""
    tmp_dir = out_dir.with_name(out_dir.name + ".tmp")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    try:
        config = (system_root / "promptguard.config.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        config = "{}"
    timeout_ms = detector_timeout(config)
    command = [sys.executable, str(M4), "run", "--out", str(tmp_dir / "m4"), "--detector", "promptguard",
               "--system-root", str(system_root), "--python", python, "--synth", "--adapters", adapters,
               "--repeat", str(repeat), "--warmup", str(warmup), "--timeout-ms", str(timeout_ms),
               *(["--guard", *guard] if guard else [])]
    with (tmp_dir / "m4.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=child_env(), cwd=REPO_ROOT)
        while True:
            try:
                code = process.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if cancelled():
                    # SIGINT lets m4.py run its finally blocks, which stop the detector worker it started.
                    process.send_signal(signal.SIGINT if hasattr(signal, "SIGINT") else signal.SIGTERM)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise EvaluationError("cancelled") from None
    if code != 0:
        lines = (tmp_dir / "m4.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()
        raise EvaluationError(f"m4.py run failed (exit {code}): {lines[-1] if lines else ''}")
    data = condense(tmp_dir / "m4")
    evaluated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary = headline(data)
    write_json(tmp_dir / "latency.json", {"version": LATENCY_VERSION, "evaluated_at": evaluated_at, "commit": commit,
                                          "system": {"fingerprint": system_fingerprint}, "environment": env, **data})
    write_json(tmp_dir / "meta.json", {"commit": commit, "system_fingerprint": system_fingerprint,
                                       "environment_fingerprint": env["fingerprint"], "evaluated_at": evaluated_at,
                                       "headline": summary}, pretty=True)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp_dir, out_dir)
    return summary
