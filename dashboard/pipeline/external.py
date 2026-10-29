"""Read-only dashboard views of registered evaluations running outside the service queue."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
import re

from pipeline import catalog, latency

ID = re.compile(r"[A-Za-z0-9_-]+")
RESULT = re.compile(r"results/(detection|latency)/([0-9a-f]{16})/"
                    r"(summary\.json|latency\.json|examples/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.json)")
RESULT_FILES = {"detection": re.compile(r"summary\.json|examples/.+"), "latency": re.compile(r"latency\.json")}


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def records(path):
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def count(value):
    return value if type(value) is int and value >= 0 else 0


def timestamp(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


def result_key(run, launch, track="detection"):
    prefix = "" if track == "detection" else track + "|"
    return hashlib.sha256(f'{prefix}{run["key"]}|{launch["started_at"]}|{launch["pid"]}'.encode()).hexdigest()[:16]


def completed_summary(result, launch):
    summary = read(result / "summary.json")
    if not isinstance(summary, dict) or not isinstance(summary.get("totals"), dict) or not isinstance(summary.get("benchmark"), dict):
        return None
    return summary if finished_at(summary, result / "summary.json") >= timestamp(launch["started_at"]) else None


def completed_latency(result, launch):
    data = read(result / "latency.json")
    if not isinstance(data, dict) or not isinstance(data.get("detectors"), list) or not data["detectors"]:
        return None
    return data if finished_at(data, result / "latency.json") >= timestamp(launch["started_at"]) else None


def finished_at(data, path):
    finished = timestamp(data.get("evaluated_at"))
    if not finished:
        try:
            finished = path.stat().st_mtime
        except OSError:
            return 0
    return finished


def process_state(launch):
    """running while the launched process (same pid and start time) is alive, else failed."""
    try:
        stat = Path(f'/proc/{launch["pid"]}/stat').read_text().rsplit(") ", 1)[1].split()
        matches = "pid_start_ticks" not in launch or int(stat[19]) == launch["pid_start_ticks"]
        return "running" if stat[0] != "Z" and matches else "failed"
    except (OSError, IndexError):
        return "failed"


def latency_view(run):
    """The registered latency measurement of a run: (launch, result dir, key, state, latency.json or None)."""
    launch = read(run["latency"]["launch"]) if isinstance(run.get("latency"), dict) else None
    if not isinstance(launch, dict):
        return None
    result = Path(launch["result"])
    data = completed_latency(result, launch)
    return launch, result, result_key(run, launch, "latency"), "done" if data else process_state(launch), data


class Evaluations:
    def __init__(self, data_dir):
        self.registry = read(Path(data_dir) / "evaluations.json") or {}

    def catalog(self):
        return {"default": self.registry.get("default"), "runs": [
            {"id": r["id"], "label": r["label"]} for r in self.registry.get("runs", [])]}

    def run(self, id):
        if not ID.fullmatch(id):
            return None
        return next((r for r in self.registry.get("runs", []) if r["id"] == id), None)

    def snapshot(self, id):
        run = self.run(id)
        if not run:
            return None
        launch = read(run["launch"])
        if not launch:
            return None
        result = Path(launch["result"])
        summary = completed_summary(result, launch)
        done, total = 0, launch["scored_items"]
        if summary:
            state, done = "done", total
        else:
            for row in records(launch["log"]):
                if row.get("event") == "progress":
                    done = max(done, count(row.get("done")))
            works = []
            for path in result.parent.glob(result.name + ".work-*"):
                try:
                    modified = path.stat().st_mtime
                except OSError:
                    continue
                if modified >= timestamp(launch["started_at"]) - 1:
                    works.append((modified, path))
            # A previous interrupted run can leave a work directory behind. Never add its counts.
            if works:
                work = max(works)[1]
                finished_items, active_items = 0, 0
                for shard in (work / "shards").glob("*.json"):
                    payload = read(shard)
                    if isinstance(payload, dict):
                        finished_items += sum(count(row[2]) for row in payload.get("items", [])
                                              if isinstance(row, list) and len(row) >= 3)
                for log in (work / "logs").glob("*.log"):
                    if (work / "shards" / log.with_suffix(".json").name).exists():
                        continue
                    processed = 0
                    for row in records(log):
                        if row.get("event") == "ml_progress":
                            processed = max(processed, count(row.get("requests_processed")))
                    active_items += processed
                # Shard publication precedes the parent's progress line. Use the larger completed count.
                done = max(done, finished_items) + active_items
            state = process_state(launch)
        done = min(done, total)
        key = result_key(run, launch)
        lat = latency_view(run)
        revision = hashlib.sha256(f'{key}|{state}|{done}|{total}|{lat and lat[2]}|{lat and lat[3]}'
                                  .encode()).hexdigest()[:16]
        message = f'{run["label"]} · {done:,}/{total:,}개 · job {launch["jobs"]}'
        if lat and lat[3] != "done" and state == "done":
            # The detection run finished; what still runs (or died) is the latency measurement.
            state_now, message = lat[3], f'{run["label"]} · 탐지 지연 측정' + (" 중" if lat[3] == "running" else "")
        else:
            state_now = state
        status = {"state": "evaluating" if state_now == "running" else "error" if state_now == "failed" else "idle",
                  "message": message if state_now != "failed" else message + " · 프로세스 종료, 서버 로그 확인 필요",
                  "progress": {"done": done, "total": total}, "index_at": revision}
        commit = dict(run["commit"])
        commit["detection"] = {"key": key, "state": state}
        if summary:
            commit["detection"]["headline"] = summary["totals"]
        elif state == "failed":
            commit["detection"]["error"] = "평가 프로세스가 종료됐어요. 서버 로그를 확인해 주세요."
        if lat:
            commit["latency"] = {"key": lat[2], "state": lat[3]}
            if lat[4]:
                commit["latency"]["headline"] = latency.headline(lat[4])
            elif lat[3] == "failed":
                commit["latency"]["error"] = "지연 측정 프로세스가 종료됐어요. 서버 로그를 확인해 주세요."
        index = {"version": 1, "generated_at": revision, "repo": {"branch": run["label"], "web": run.get("repo_web")},
                 "benchmark": summary["benchmark"] if summary else {"second_stage": run["model"]},
                 "tracks": ["detection", "latency"] if lat else ["detection"], "commits": [commit], "latest": commit["sha"], "status": status,
                 "catalog": catalog.as_json(), "task_batches": None,
                 "evaluation": {"label": run["label"], "items": total, "sessions": launch["sessions"],
                                "jobs": launch["jobs"], "state": state, "started_at": launch["started_at"]}}
        return {"index": index, "status": status, "result": result, "key": key}

    def file(self, id, relative):
        match = RESULT.fullmatch(relative)
        run = self.run(id)
        if not match or not run or not RESULT_FILES[match[1]].fullmatch(match[3]):
            return None
        if match[1] == "latency":
            lat = latency_view(run)
            if not lat or lat[3] != "done" or match[2] != lat[2]:
                return None
            result = lat[1].resolve()
        else:
            launch = read(run["launch"])
            if not launch:
                return None
            result = Path(launch["result"]).resolve()
            if match[2] != result_key(run, launch) or not completed_summary(result, launch):
                return None
        path = result / match[3]
        if not path.resolve().is_relative_to(result):
            return None
        return path
