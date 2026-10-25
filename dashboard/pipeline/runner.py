"""Evaluate one PromptGuard checkout on every metric-detection dataset and write the result folder the UI reads.

The datasets are split into shards of about equal work (scored items), each evaluated by its own process
(shard.py run), `jobs` at a time. The shards of a dataset are merged with collect.merge, which also checks that the
dashboard's counts equal the scorer's.

Result folder (results/detection/<key>/):
  summary.json          dimensions, count cells and per-dataset facts for the UI
  examples/<stem>.json  example windows of one dataset; examples/_all.json one per (channel, type, outcome) per dataset
  meta.json             what was evaluated, on what, and how long it took
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.catalog import CHANNEL_LABELS, TYPE_LABELS, dataset_info, dataset_order
from pipeline.collect import merge
from pipeline.paths import DASHBOARD_ROOT, METRIC_DETECTION
from pipeline.taxonomy import CHANNELS, EDIT_CLASSES, STATUSES, TYPES

from evaluation.dataset.io import file_sha256, gold_path_for

SHARD_SCRIPT = DASHBOARD_ROOT / "pipeline" / "shard.py"
# Code whose change changes the numbers: the scorer, and the parts of this pipeline that count and pick examples.
# Display names (catalog.py) are not here: index.json carries the current ones.
SCORING_CODE = [*sorted((METRIC_DETECTION / "evaluation").rglob("*.py")),
                *(DASHBOARD_ROOT / "pipeline" / name
                  for name in ("__init__.py", "paths.py", "runner.py", "taxonomy.py", "collect.py", "shard.py",
                              "gitleaks_cache.py"))]
SUMMARY_VERSION = 2  # earlier results did not pin the evaluated inputs to their key


class EvaluationError(Exception):
    pass


class InputsChanged(EvaluationError):
    """The planned inputs changed before they could be pinned; re-plan without caching a job failure."""


@dataclass(frozen=True)
class Dataset:
    stem: str
    sessions: Path
    gold: Path
    sessions_sha256: str
    gold_sha256: str


_sha_cache: dict[tuple, str] = {}


def cached_sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    if key not in _sha_cache:
        _sha_cache[key] = file_sha256(path)
    return _sha_cache[key]


def discover(data_test: Path) -> list[Dataset]:
    """Every data_test/sessions*.jsonl with its gold file, in the UI's order (the same files run_all.py uses)."""
    found = {}
    for sessions in sorted(data_test.glob("sessions*.jsonl")):
        gold = gold_path_for(sessions)
        if gold.is_file():
            found[sessions.stem] = Dataset(sessions.stem, sessions, gold, cached_sha256(sessions), cached_sha256(gold))
    return [found[stem] for stem in dataset_order(list(found))]


def code_fingerprint(root: Path | None = None) -> str:
    digest = hashlib.sha256()
    for path in SCORING_CODE:
        relative = path.relative_to(METRIC_DETECTION.parent)
        if "tests" not in relative.parts:
            source = root / relative if root else path
            digest.update(relative.as_posix().encode() + b"\0" + source.read_bytes())
    return digest.hexdigest()


# The merger already imported by this process must match the code copied for its child processes.
LOADED_SCORING_CODE = code_fingerprint()


def snapshot_inputs(datasets: Sequence[Dataset], root: Path, bench: dict[str, Any]) -> tuple[list[Dataset], Path]:
    """Copy and verify the planned bytes. All validation and shards read this private copy."""
    if bench.get("code") != LOADED_SCORING_CODE:
        raise InputsChanged("scoring code changed; restart the service before evaluating")
    pinned = []
    try:
        for source, relative in ((DASHBOARD_ROOT / "pipeline", "dashboard/pipeline"),
                                 (METRIC_DETECTION / "evaluation", "metric-detection/evaluation")):
            shutil.copytree(source, root / relative, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        if code_fingerprint(root) != bench["code"]:
            raise InputsChanged("scoring code changed while taking the evaluation snapshot")
        for dataset in datasets:
            copies = []
            for source, expected, directory in ((dataset.sessions, dataset.sessions_sha256, "data_test"),
                                                (dataset.gold, dataset.gold_sha256, "data_answer")):
                target = root / directory / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if file_sha256(target) != expected:
                    raise InputsChanged(f"{source.name} changed before evaluation; re-planning")
                copies.append(target)
            pinned.append(Dataset(dataset.stem, *copies, dataset.sessions_sha256, dataset.gold_sha256))
    except FileNotFoundError as exc:
        raise InputsChanged("evaluation inputs were removed while taking the snapshot") from exc
    return pinned, root / "dashboard/pipeline/shard.py"


def tool_version(command: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def benchmark(datasets: Sequence[Dataset]) -> dict[str, Any]:
    """What the numbers depend on besides the system: datasets, scoring code and the gitleaks binary on PATH."""
    gitleaks = tool_version(["gitleaks", "version"])
    parts = {
        # sorted: the order the UI lists datasets in comes from catalog.py, which is display only
        "datasets": sorted([dataset.stem, dataset.sessions_sha256, dataset.gold_sha256] for dataset in datasets),
        "code": code_fingerprint(),
        "gitleaks": gitleaks,
        "summary_version": SUMMARY_VERSION,
    }
    fingerprint = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return {"fingerprint": fingerprint, "code": parts["code"], "gitleaks": gitleaks,
            "datasets": [{"stem": dataset.stem, "label": dataset_info(dataset.stem).label,
                          "sessions_sha256": dataset.sessions_sha256, "gold_sha256": dataset.gold_sha256}
                         for dataset in datasets]}


def child_env() -> dict[str, str]:
    """The service's environment without PG_* variables, which would change the detector's configuration."""
    return {key: value for key, value in os.environ.items() if not key.startswith("PG_")}


def write_json(path: Path, payload: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None,
                      separators=None if pretty else (",", ":"))
    temporary.write_text(text + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate(datasets: Sequence[Dataset], cache_dir: Path, python: str, log_dir: Path, *,
             shard_script: Path = SHARD_SCRIPT) -> dict[str, list[int]]:
    """Each dataset's per-session scored item counts, validating each sessions/gold version once."""
    weights = {}
    for dataset in datasets:
        cached = cache_dir / LOADED_SCORING_CODE[:16] / f"{dataset.sessions_sha256[:16]}-{dataset.gold_sha256[:16]}.json"
        if not cached.is_file():
            log = log_dir / f"validate_{dataset.stem}.log"
            out = cached.with_name(cached.name + ".new")
            cached.parent.mkdir(parents=True, exist_ok=True)
            with log.open("w", encoding="utf-8") as handle:
                code = subprocess.run([python, str(shard_script), "validate", "--sessions", str(dataset.sessions),
                                       "--gold", str(dataset.gold), "--out", str(out)],
                                      stdout=handle, stderr=subprocess.STDOUT, env=child_env()).returncode
            if not out.is_file():
                raise EvaluationError(f"{dataset.sessions.name}: validation crashed (exit {code}); see {log}")
            os.replace(out, cached)
        report = json.loads(cached.read_text(encoding="utf-8"))
        if report["issue_count"]:
            raise EvaluationError(f"{dataset.sessions.name}: {report['issue_count']} validation issue(s), first: "
                                  f"{report['issues'][0]}")
        weights[dataset.stem] = report["weights"]
    return weights


@dataclass
class Shard:
    dataset: Dataset
    low: int
    high: int
    weight: int

    @property
    def name(self) -> str:
        return f"{self.dataset.stem}_{self.low:06d}-{self.high:06d}"


def plan(datasets: Sequence[Dataset], weights: dict[str, list[int]], jobs: int) -> list[Shard]:
    """Contiguous session ranges of about total/(3·jobs) scored items each, heaviest first."""
    total = sum(sum(values) for values in weights.values())
    target = max(500, total // max(1, 3 * jobs))
    shards = []
    for dataset in datasets:
        values = weights[dataset.stem]
        low, weight = 0, 0
        for index, value in enumerate(values):
            weight += value
            if weight >= target and index + 1 < len(values):
                shards.append(Shard(dataset, low, index + 1, weight))
                low, weight = index + 1, 0
        shards.append(Shard(dataset, low, len(values), weight))
    return sorted(shards, key=lambda shard: -shard.weight)


def run_shards(shards: Sequence[Shard], system_root: Path, work_dir: Path, python: str, jobs: int,
               progress: Callable[[int, int], None], cancelled: Callable[[], bool], *,
               shard_script: Path = SHARD_SCRIPT, gitleaks_cache: Path | None = None,
               ensemble: dict[str, Any] | None = None) -> None:
    cache_args = ["--gitleaks-cache", str(gitleaks_cache)] if gitleaks_cache else []
    if ensemble:
        cache_args += ["--detectors", ",".join(ensemble["detectors"]), "--consensus", ensemble["consensus"]]
    total = sum(shard.weight for shard in shards)
    done = 0
    pending = list(shards)
    running: list[tuple[Shard, subprocess.Popen, Any]] = []
    progress(0, total)
    try:
        while pending or running:
            while pending and len(running) < jobs:
                shard = pending.pop(0)
                log = (work_dir / "logs" / f"{shard.name}.log").open("w", encoding="utf-8")
                process = subprocess.Popen(
                    [python, str(shard_script), "run", "--dataset", shard.dataset.stem,
                     "--sessions", str(shard.dataset.sessions), "--gold", str(shard.dataset.gold),
                     "--lines", f"{shard.low}:{shard.high}", "--system-root", str(system_root),
                     "--out", str(work_dir / "shards" / f"{shard.name}.json"), *cache_args],
                    stdout=log, stderr=subprocess.STDOUT, env=child_env())
                running.append((shard, process, log))
            time.sleep(0.5)
            for entry in list(running):
                shard, process, log = entry
                code = process.poll()
                if code is None:
                    continue
                log.close()
                running.remove(entry)
                if code != 0:
                    tail = (work_dir / "logs" / f"{shard.name}.log").read_text(encoding="utf-8", errors="replace")
                    raise EvaluationError(f"{shard.dataset.sessions.name} sessions {shard.low}-{shard.high} failed "
                                          f"(exit {code}): {tail.strip().splitlines()[-1] if tail.strip() else ''}")
                done += shard.weight
                progress(done, total)
            if cancelled():
                raise EvaluationError("cancelled")
    finally:
        for _shard, process, log in running:
            process.kill()
            process.wait()
            log.close()


def prf(counts: dict[str, int]) -> dict[str, float | None]:
    gold = counts["exact"] + counts["over"] + counts["partial"] + counts["missed"]
    edits = counts["edits_tp"] + counts["edits_over"] + counts["edits_fp"]
    recall = counts["exact"] / gold if gold else None
    precision = counts["edits_tp"] / edits if edits else None
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate(system_root: Path, datasets: Sequence[Dataset], out_dir: Path, *, python: str, jobs: int,
             cache_dir: Path, commit: dict[str, Any], system_fingerprint: str, bench: dict[str, Any],
             progress: Callable[[int, int], None] = lambda done, total: None,
             cancelled: Callable[[], bool] = lambda: False, gitleaks_cache: Path | None = None,
             ensemble: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate, merge and write out_dir; return the headline numbers (overall and per dataset).

    gitleaks_cache: SQLite file the shards share for gitleaks runs (gitleaks_cache.py); None runs gitleaks per text."""
    started = time.perf_counter()
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=out_dir.name + ".work-", dir=out_dir.parent) as temporary:
        work_dir = Path(temporary)
        (work_dir / "logs").mkdir(parents=True)
        (work_dir / "shards").mkdir()
        datasets, shard_script = snapshot_inputs(datasets, work_dir / "inputs", bench)
        weights = validate(datasets, cache_dir, python, work_dir / "logs", shard_script=shard_script)
        shards = plan(datasets, weights, jobs)
        run_shards(shards, system_root, work_dir, python, jobs, progress, cancelled, shard_script=shard_script,
                   gitleaks_cache=gitleaks_cache, **({"ensemble": ensemble} if ensemble else {}))

        merged, system = {}, None
        for dataset in datasets:
            payloads = [json.loads((work_dir / "shards" / f"{shard.name}.json").read_text(encoding="utf-8"))
                        for shard in sorted(shards, key=lambda shard: shard.low) if shard.dataset is dataset]
            merged[dataset.stem] = merge(payloads)
            merged[dataset.stem]["facts"] = {
                "sessions": sum(payload["sessions"] for payload in payloads),
                "items": sum(payload["item_count"] for payload in payloads),
                "failed_open": sum(payload["system"].get("failed_open_items", 0) for payload in payloads),
                "seconds": round(sum(payload["seconds"] for payload in payloads), 1),
            }
            if system is None and payloads:
                system = {key: value for key, value in payloads[0]["system"].items() if key != "failed_open_items"}

        tmp_dir = out_dir.with_name(out_dir.name + ".tmp")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if ensemble:
            system = {**(system or {}), "ensemble": ensemble}
        headline = write_result(tmp_dir, datasets, merged, system or {}, commit=commit,
                                system_fingerprint=system_fingerprint, bench=bench,
                                wall_seconds=time.perf_counter() - started)
        shutil.rmtree(out_dir, ignore_errors=True)
        os.replace(tmp_dir, out_dir)
        return headline


def write_result(out_dir: Path, datasets: Sequence[Dataset], merged: dict[str, dict[str, Any]],
                 system: dict[str, Any], *, commit: dict[str, Any], system_fingerprint: str, bench: dict[str, Any],
                 wall_seconds: float) -> dict[str, Any]:
    channel_index = {channel: index for index, channel in enumerate(CHANNELS)}
    type_index = {type_: index for index, type_ in enumerate(TYPES)}
    cells, items, facts, overview, by_dataset = [], [], [], [], {}
    totals = dict.fromkeys(("exact", "over", "partial", "missed", "edits_tp", "edits_over", "edits_fp"), 0)
    for d, dataset in enumerate(datasets):
        result = merged[dataset.stem]
        info = dataset_info(dataset.stem)
        groups = sorted({row[0] for row in result["items"]})
        group_index = {group: index for index, group in enumerate(groups)}
        for group, channel, type_, *values in result["cells"]:
            cells.append([d, group_index[group], channel_index[channel], type_index[type_], *values])
        for group, channel, *values in result["items"]:
            items.append([d, group_index[group], channel_index[channel], *values])
        for key in totals:
            totals[key] += result["counts"][key]
        by_dataset[dataset.stem] = prf(result["counts"])
        counts = result["counts"]
        facts.append({
            "key": dataset.stem, "label": info.label, "about": info.about, "group_label": info.group_label,
            "groups": groups, **result["facts"],
            "gold": counts["exact"] + counts["over"] + counts["partial"] + counts["missed"],
            "edits": counts["edits_tp"] + counts["edits_over"] + counts["edits_fp"],
            "lines": result["lines_total"],
            "sessions_sha256": dataset.sessions_sha256, "gold_sha256": dataset.gold_sha256,
        })
        write_json(out_dir / "examples" / f"{dataset.stem}.json",
                   {"dataset": dataset.stem, "examples": result["examples"]})
        chosen = set(result["overview"])
        overview += [{**example, "dataset": dataset.stem} for example in result["examples"] if example["id"] in chosen]
    write_json(out_dir / "examples" / "_all.json", {"dataset": None, "examples": overview})

    headline = {**prf(totals), "datasets": by_dataset}
    evaluated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(out_dir / "summary.json", {
        "version": SUMMARY_VERSION,
        "evaluated_at": evaluated_at,
        "wall_seconds": round(wall_seconds, 1),
        "commit": commit,
        "system": {"fingerprint": system_fingerprint, **system},
        "benchmark": {"fingerprint": bench["fingerprint"], "code": bench["code"], "gitleaks": bench["gitleaks"]},
        "datasets": facts,
        "channels": [{"key": channel, "label": CHANNEL_LABELS[channel]} for channel in CHANNELS],
        "types": [{"key": type_, "label": TYPE_LABELS[type_]} for type_ in TYPES],
        "statuses": list(STATUSES),
        "edit_classes": list(EDIT_CLASSES),
        "cells": cells,
        "items": items,
        "totals": {**headline, "counts": totals},
    })
    write_json(out_dir / "meta.json", {"commit": commit, "system_fingerprint": system_fingerprint,
                                       "ensemble": system.get("ensemble"),
                                       "benchmark_fingerprint": bench["fingerprint"], "evaluated_at": evaluated_at,
                                       "wall_seconds": round(wall_seconds, 1), "headline": headline,
                                       "python": sys.version.split()[0]}, pretty=True)
    return headline
