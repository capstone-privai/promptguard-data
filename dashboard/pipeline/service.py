"""The dashboard service: keep the PromptGuard branch evaluated and index.json current.

Each cycle fetches the branch, lists the evaluable commits, writes index.json, then runs the most urgent missing job
(newest commit first; detection before latency) and writes index.json again. A result is keyed by the commit's
system fingerprint and what else the numbers depend on (the benchmark for detection, the measuring environment for
latency), so commits that did not touch the detector share results, and a new dataset or scorer version makes every
commit due again. Jobs run one at a time: latency is never measured while the detection shards load the machine.

Keys are computed from the code files on disk, but a running process keeps the code it started with. When a pull
changes that code, the service stops before its next cycle instead of keying results by code it does not run; the
supervisor (or the next --once) starts the new code.

One process evaluates per data directory: two would delete each other's work folders and checkouts. The one holding
.lock evaluates; another --once does nothing, and another server keeps serving and evaluates once the lock is free.

Data directory:
  .lock                           held by the process that evaluates here (its pid inside)
  repo.git/                       bare clone of the PromptGuard repository
  checkouts/, venvs/, validated/  exported commits, Pythons with the pinned CredSweeper, dataset validation cache
  results/detection/<key>/        runner.py output
  results/latency/<key>/          latency.py output
  index.json                      what the UI loads first
  failures.json                   jobs that failed, not retried until a refresh asks for it
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import fcntl
except ImportError:  # Windows: no lock; run one evaluator per data directory by hand
    fcntl = None

from pipeline import catalog, latency, repo, runner, task
from pipeline.paths import DASHBOARD_ROOT, DATA_TEST, METRIC_DETECTION, REPO_ROOT

TRACKS = ("detection", "latency")
KEY = re.compile(r"[0-9a-f]{16}")


class DataDirBusy(Exception):
    """Another process holds the data directory's lock and evaluates there."""

    def __init__(self, holder: str):
        super().__init__(f"another dashboard process (pid {holder}) is evaluating in this data directory")
        self.holder = holder


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"{now()} {message}", flush=True)


def result_key(track: str, system_fingerprint: str, context_fingerprint: str, *,
               timeout_ms: int = repo.DEFAULT_TIMEOUT_MS) -> str:
    identity = f"{track}|{system_fingerprint}|{context_fingerprint}"
    if track == "latency":
        identity += f"|timeout_ms={timeout_ms}"
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def code_hash() -> str:
    """The code a service process imports: the dashboard, the scorer and m4."""
    digest = hashlib.sha256()
    for path in sorted({*DASHBOARD_ROOT.glob("*.py"), *DASHBOARD_ROOT.glob("pipeline/*.py"),
                        *(METRIC_DETECTION / "evaluation").rglob("*.py"), *latency.SCRIPTS.glob("*.py")}):
        digest.update(f"{path}\0".encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def display_url(url: str) -> str:
    """The repository URL without credentials."""
    parts = urlsplit(url)
    if parts.username or parts.password:
        return urlunsplit((parts.scheme, parts.hostname + (f":{parts.port}" if parts.port else ""), parts.path,
                           parts.query, parts.fragment))
    return url


@dataclass
class Config:
    data_dir: Path
    repo_url: str
    branch: str = "main"
    jobs: int = 4
    python: str = "python3"
    auto_venv: bool = True
    latency: bool = True
    latency_adapters: str = "each"
    latency_guard: list[str] = field(default_factory=list)
    latency_repeat: int = 5
    latency_warmup: int = 3
    task: bool = True  # read metric-task batches people ran; never run it (it costs API money)
    task_runs: list[str] = field(default_factory=lambda: [str(REPO_ROOT / "runs" / "metric-task")])


class Service:
    def __init__(self, config: Config):
        self.config = config
        self.data = config.data_dir
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.status: dict[str, Any] = {"state": "starting", "updated_at": now()}
        self.failures: dict[str, dict[str, Any]] = self._read("failures.json") or {}
        self.retry = False
        self._meta_cache: dict[Path, dict[str, Any]] = {}
        self.code = code_hash()
        self.code_changed = False
        self._lock_file = None  # open while this process holds the data directory

    # ------------------------------------------------------------------ data directory lock

    def acquire(self) -> bool:
        """Hold <data>/.lock, so that this process alone evaluates here. False while another process holds it; the
        lock goes with the process."""
        if self._lock_file is not None or fcntl is None:
            return True
        self.data.mkdir(parents=True, exist_ok=True)
        handle = (self.data / ".lock").open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._lock_file = handle
        self.failures = self._read("failures.json") or {}  # the previous holder may have recorded some
        return True

    def release(self) -> None:
        if self._lock_file is not None:
            self._lock_file.close()  # closing the file drops the lock
            self._lock_file = None

    def lock_holder(self) -> str:
        try:
            return (self.data / ".lock").read_text(encoding="utf-8").strip() or "?"
        except OSError:
            return "?"

    # ------------------------------------------------------------------ status

    def set_status(self, **fields: Any) -> None:
        with self.lock:
            kept = {name: self.status[name] for name in ("last_sync", "index_at") if name in self.status}
            self.status = {**kept, **fields, "updated_at": now()}

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.status)

    def _read(self, name: str) -> Any:
        try:
            return json.loads((self.data / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def request_refresh(self, retry: bool = False) -> None:
        self.retry = self.retry or retry
        self.wake.set()

    # ------------------------------------------------------------------ results

    def result_dir(self, track: str, key: str) -> Path:
        return self.data / "results" / track / key

    def meta(self, track: str, key: str) -> dict[str, Any] | None:
        path = self.result_dir(track, key) / "meta.json"
        if path not in self._meta_cache:
            try:
                self._meta_cache[path] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return self._meta_cache[path]

    def latest_by_system(self, track: str) -> dict[str, tuple[str, str]]:
        """system fingerprint → (evaluated_at, key) of its newest result under any benchmark or environment."""
        found: dict[str, tuple[str, str]] = {}
        root = self.data / "results" / track
        for folder in root.iterdir() if root.is_dir() else []:
            if KEY.fullmatch(folder.name) and (meta := self.meta(track, folder.name)):
                entry = (meta["evaluated_at"], folder.name)
                found[meta["system_fingerprint"]] = max(found.get(meta["system_fingerprint"], entry), entry)
        return found

    # ------------------------------------------------------------------ cycle

    def plan(self) -> dict[str, Any]:
        self.set_status(state="syncing", message="PromptGuard 저장소를 받는 중")
        repo.sync(self.config.repo_url, self.data / "repo.git", self.config.branch)
        commits = repo.commits(self.data / "repo.git", self.config.branch)
        datasets = runner.discover(DATA_TEST)
        if not datasets:
            raise runner.EvaluationError(f"no datasets under {DATA_TEST}; build them first (metric-detection/README.md)")
        bench = runner.benchmark(datasets)
        contexts = {"detection": bench["fingerprint"]}
        env = None
        if self.config.latency:
            env = latency.environment(self.config.latency_adapters, self.config.latency_guard,
                                      self.config.latency_repeat, self.config.latency_warmup)
            contexts["latency"] = env["fingerprint"]
        if self.retry:
            self.failures, self.retry = {}, False
            self._save_failures()
        batches = None
        if self.config.task:
            batches = task.collect(self.config.task_runs, self.data / "results" / "task")
            for batch in batches:
                batch["commit"] = repo.describe(self.data / "repo.git", batch.get("system_commit") or "")
        self.set_status(state="idle", message="", last_sync=now())
        return {"commits": commits, "datasets": datasets, "bench": bench, "env": env, "contexts": contexts,
                "task_batches": batches}

    def jobs(self, plan: dict[str, Any]) -> list[tuple[str, repo.Commit, str]]:
        """Missing results, most urgent first, one per (track, key)."""
        seen, out = set(), []
        for commit in reversed(plan["commits"]):
            for track, context in plan["contexts"].items():
                key = result_key(track, commit.fingerprint, context, timeout_ms=commit.timeout_ms)
                if (track, key) in seen:
                    continue
                seen.add((track, key))
                if not self.meta(track, key) and f"{track}:{key}" not in self.failures:
                    out.append((track, commit, key))
        return out

    def cycle(self) -> bool:
        """Plan, index, run one job, index again. True if a job ran."""
        if code_hash() != self.code:
            log("the dashboard or scorer code changed on disk; stopping so that the new code is started")
            self.code_changed = True
            self.stop()
            return False
        if not self.acquire():
            raise DataDirBusy(self.lock_holder())
        plan = self.plan()
        pending = self.jobs(plan)
        self.write_index(plan, pending, running=None)
        if not pending:
            return False
        track, commit, key = pending[0]
        self.run_job(plan, track, commit, key, pending)
        self.write_index(plan, self.jobs(plan), running=None)
        return True

    def run_job(self, plan: dict[str, Any], track: str, commit: repo.Commit, key: str,
                pending: list[tuple[str, repo.Commit, str]]) -> None:
        label = {"detection": "탐지 성능", "latency": "탐지 지연"}[track]
        started = now()

        def progress(done: int, total: int) -> None:
            self.set_status(state="evaluating", track=track, commit=commit.sha, short=commit.short, key=key,
                            started_at=started, progress={"done": done, "total": total},
                            message=f"{commit.short} {label} 평가 중")

        progress(0, 1)
        self.write_index(plan, pending, running=(track, key))
        checkout = self.data / "checkouts" / commit.fingerprint[:12]
        name = f"{track} {commit.short} ({key})"
        log(f"{name}: started, {len(pending) - 1} more queued")
        began = time.monotonic()
        try:
            repo.export(self.data / "repo.git", commit.sha, checkout)
            python = repo.python_for(checkout, self.config.python, self.data / "venvs", self.config.auto_venv)
            if track == "detection":
                runner.evaluate(checkout, plan["datasets"], self.result_dir(track, key), python=python,
                                jobs=self.config.jobs, cache_dir=self.data / "validated", commit=commit.as_json(),
                                system_fingerprint=commit.fingerprint, bench=plan["bench"], progress=progress,
                                cancelled=self.stopping.is_set)
            else:
                latency.evaluate(checkout, self.result_dir(track, key), python=python,
                                 adapters=self.config.latency_adapters, guard=self.config.latency_guard,
                                 repeat=self.config.latency_repeat, warmup=self.config.latency_warmup,
                                 commit=commit.as_json(), system_fingerprint=commit.fingerprint, env=plan["env"],
                                 cancelled=self.stopping.is_set)
        except runner.InputsChanged as exc:
            # A stale plan is not a detector failure. The next cycle discovers the current inputs and can retry.
            log(f"{name}: discarded: {exc}")
            if code_hash() != self.code:
                self.code_changed = True
                self.stop()
        except Exception as exc:  # noqa: BLE001 - any failure is recorded, so the job is not retried every cycle
            if self.stopping.is_set():
                log(f"{name}: stopped")
                return
            log(f"{name}: failed: {str(exc)[:200]}")
            self.failures[f"{track}:{key}"] = {"error": str(exc)[:500], "at": now(), "commit": commit.sha}
            self._save_failures()
            (self.data / "logs").mkdir(parents=True, exist_ok=True)
            with (self.data / "logs" / "failures.log").open("a", encoding="utf-8") as out:
                out.write(f"{now()} {track} {commit.sha} {key}\n{traceback.format_exc()}\n")
        else:
            log(f"{name}: done in {time.monotonic() - began:.0f} s")
        finally:
            shutil.rmtree(checkout, ignore_errors=True)
            self.set_status(state="idle", message="")

    def _save_failures(self) -> None:
        runner.write_json(self.data / "failures.json", self.failures, pretty=True)

    # ------------------------------------------------------------------ index

    def write_index(self, plan: dict[str, Any], pending: list[tuple[str, repo.Commit, str]],
                    running: tuple[str, str] | None) -> None:
        queued = {(track, key) for track, _commit, key in pending}
        fallback = {track: self.latest_by_system(track) for track in plan["contexts"]}
        entries = []
        for commit in plan["commits"]:
            entry = commit.as_json()
            entry["fingerprint"] = commit.fingerprint[:12]
            for track, context in plan["contexts"].items():
                key = result_key(track, commit.fingerprint, context, timeout_ms=commit.timeout_ms)
                meta = self.meta(track, key)
                if meta:
                    state = "done"
                elif running == (track, key):
                    state = "running"
                elif f"{track}:{key}" in self.failures:
                    state = "failed"
                else:
                    state = "queued" if (track, key) in queued else "missing"
                record: dict[str, Any] = {"key": key, "state": state}
                if meta:
                    record["headline"] = meta["headline"]
                elif state == "failed":
                    record["error"] = self.failures[f"{track}:{key}"]["error"]
                old = fallback[track].get(commit.fingerprint)
                if not meta and old:  # a result for the same detector under an older benchmark or environment
                    record["stale"] = {"key": old[1], "headline": self.meta(track, old[1])["headline"],
                                       "evaluated_at": old[0]}
                entry[track] = record
            if plan.get("task_batches") is not None:
                entry["task"] = [batch["key"] for batch in plan["task_batches"]
                                 if (batch.get("system_commit") or "") == commit.sha]
            entries.append(entry)
        index = {
            "version": 1,
            "generated_at": now(),
            "repo": {"url": display_url(self.config.repo_url), "web": repo.github_web_url(self.config.repo_url),
                     "branch": self.config.branch},
            "benchmark": plan["bench"],
            "latency_environment": plan["env"],
            "catalog": catalog.as_json(),  # current display names; results keep the ones of their evaluation
            "tracks": list(plan["contexts"]),
            "commits": entries,
            "task_batches": plan.get("task_batches"),
            "latest": plan["commits"][-1].sha if plan["commits"] else None,
            "status": self.snapshot(),
        }
        runner.write_json(self.data / "index.json", index)
        with self.lock:
            self.status["index_at"] = index["generated_at"]

    # ------------------------------------------------------------------ loop

    def run_forever(self, poll_seconds: float) -> None:
        waiting = False
        try:
            while not self.stopping.is_set():
                ran, pause = False, poll_seconds
                try:
                    ran = self.cycle()
                    waiting = False
                except DataDirBusy as busy:  # keep serving; evaluate once the other process is done
                    if not waiting:
                        log(f"{busy}; waiting for it")
                    waiting = True
                    self.set_status(state="waiting", message=f"다른 프로세스(pid {busy.holder})가 이 데이터 폴더에서 평가하는 중")
                    pause = min(poll_seconds, 30)
                except Exception as exc:  # noqa: BLE001 - keep serving; the UI shows the error
                    log(f"cycle failed: {str(exc)[:200]}")
                    self.set_status(state="error", message=str(exc)[:500])
                    (self.data / "logs").mkdir(parents=True, exist_ok=True)
                    with (self.data / "logs" / "service.log").open("a", encoding="utf-8") as out:
                        out.write(f"{now()}\n{traceback.format_exc()}\n")
                if not ran and not self.stopping.is_set():
                    self.wake.wait(pause)
                    self.wake.clear()
        finally:
            self.release()

    def run_until_done(self) -> None:
        try:
            while not self.stopping.is_set() and self.cycle():
                pass
        finally:
            self.release()

    def stop(self) -> None:
        self.stopping.set()
        self.wake.set()


def sleep_forever() -> None:  # pragma: no cover - used by serve.py --serve-only
    while True:
        time.sleep(3600)
