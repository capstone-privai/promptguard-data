"""metric-latency: how long the detector takes on the text it is handed at that moment.

The PromptGuard Native Mod sends each hook's new text to a detector, and the Final Guard sends only the
string leaves it has not yet seen clean. So the unit measured here is one detector call (one POST
/scan-batch): the batch the detector got, and how long it took. Each call is timed twice:

  detector_ms  the detector's own wall time for the batch, as it reports it (items[].latency_ms; the
               system's worker gives every item of a batch the batch time)
  call_ms      the evaluator's wall time around the HTTP call on loopback: detector_ms plus HTTP and JSON

The evaluator treats the detector as a black box that speaks the worker's HTTP protocol (GET /health,
POST /scan-batch). It can start the system's worker (--detector promptguard, optionally once per adapter
with --adapters each), a built-in null detector that finds nothing (--detector null: the transport floor),
any command (--detector "cmd:... {port}") or use a running one (--detector url:http://127.0.0.1:18771).
It imports nothing from the system or from metric-detection and metric-task. What it needs to know about the system is
listed in metric-latency/README.md.

Commands, from the repository root:
  python3 metric-latency/scripts/m4.py run --name pg --detector promptguard --adapters each --synth \\
      --guard runs/metric-task/capture_trial
  python3 metric-latency/scripts/m4.py run --name null --detector null --synth --guard runs/metric-task/capture_trial
  python3 metric-latency/scripts/m4.py report runs/metric-latency/pg runs/metric-latency/null --out metric-latency/results/<name>
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import math
import os
import platform
import shlex
import socket
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_workloads as wl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "runs" / "metric-latency"
SYSTEM_ENV = "PROMPTGUARD_CLAUDE_ROOT"
# The system's worker and its config, relative to a promptguard-claude-demoV0 checkout.
WORKER = Path("src", "detector", "worker.py")
DETECTOR_CONFIG = Path("src", "detector", "detector.json")
# The system's detector timeout (detectorTimeoutMs in promptguard.config.json): a slower call fails closed.
DEFAULT_TIMEOUT_MS = 5000
WARMUP_TEXT_SIZE = 1024


def say(*args):
    print(*args, flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- talking to a detector ---------------------------------------------------------------------------------

def http_json(url: str, method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    """One request on a fresh connection, as the system's clients make. Returns (status, json or None, ms)."""
    parts = urlsplit(url)
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if body is not None else None
    started = time.perf_counter()
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        headers = {"content-type": "application/json", "content-length": str(len(payload))} if payload else {}
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        ms = (time.perf_counter() - started) * 1000
        try:
            value = json.loads(raw)
        except ValueError:
            value = None
        return response.status, value, ms
    finally:
        conn.close()


class Detector:
    """One detector under measurement: a process this evaluator started, or a URL it was given."""

    def __init__(self, label: str, kind: str, argv: list[str] | None = None, env: dict | None = None,
                 cwd: Path | None = None, url: str | None = None, config: Path | None = None,
                 system_root: Path | None = None):
        self.label, self.kind, self.argv, self.env, self.cwd = label, kind, argv, env, cwd
        self.url, self.config, self.system_root = url, config, system_root
        self.proc = None
        self.log = None
        self.startup_ms = None

    def start(self, run_dir: Path, ready_timeout: float = 180.0):
        if self.argv is None:
            self._wait(time.perf_counter(), ready_timeout)
            return
        port = free_port()
        argv = [a.replace("{port}", str(port)) for a in self.argv]
        env = {**(self.env or {}), "PG_DETECTOR_PORT": str(port)}
        self.url = f"http://127.0.0.1:{port}"
        self.log = open(run_dir / f"detector-{self.label}.log", "w", encoding="utf-8")
        started = time.perf_counter()
        self.proc = subprocess.Popen(argv, cwd=self.cwd, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self._wait(started, ready_timeout)
        self.startup_ms = round((time.perf_counter() - started) * 1000, 1)

    def _wait(self, started: float, timeout: float):
        while time.perf_counter() - started < timeout:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"detector {self.label} exited with {self.proc.returncode}; see its log")
            try:
                status, _, _ = http_json(self.url, "GET", "/health", timeout=2)
                if status == 200:
                    return
            except OSError:
                pass
            time.sleep(0.05)
        raise RuntimeError(f"detector {self.label} at {self.url} not healthy within {timeout:.0f}s")

    def describe(self) -> dict:
        for path in ("/status", "/health"):
            try:
                status, value, _ = http_json(self.url, "GET", path, timeout=5)
            except OSError:
                continue
            if status == 200 and isinstance(value, dict):
                # Process facts (pid, uptime, counters) change per run and say nothing about the detector.
                return {k: v for k, v in value.items() if k not in {"pid", "uptime_ms", "rss_bytes", "scan_count",
                                                                   "error_count", "in_flight", "last_latency_ms"}}
        return {}

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log:
            self.log.close()


def child_env() -> dict:
    """The parent environment without PG_* settings, so no inherited override changes the detector."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PG_")}


def system_root(arg: str | None) -> Path:
    root = Path(arg or os.environ.get(SYSTEM_ENV) or REPO_ROOT.parent / "promptguard-claude-demoV0").expanduser()
    if not (root / WORKER).is_file():
        raise SystemExit(f"no {WORKER.as_posix()} under {root}; pass --system-root or set {SYSTEM_ENV}")
    return root.resolve()


def system_python(root: Path, arg: str | None) -> str:
    if arg:
        return arg
    for candidate in (root / ".venv" / "bin" / "python", root / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return str(candidate)
    raise SystemExit(f"no .venv under {root} (run its install script) and no --python given")


def single_adapter_config(config_path: Path, entry: dict, out_dir: Path) -> Path:
    """detector.json with one adapter and consensus "any". Option values that name a file next to the original
    config are made absolute, because the system resolves them against the config's folder."""
    def absolute(value):
        if isinstance(value, str) and value and (config_path.parent / value).exists():
            return str((config_path.parent / value).resolve())
        if isinstance(value, list):
            return [absolute(v) for v in value]
        return value
    entry = {**entry, "required": True, "options": {k: absolute(v) for k, v in entry.get("options", {}).items()}}
    out = out_dir / f"detector-{entry['name']}.json"
    out.write_text(json.dumps({"consensus": "any", "adapters": [entry]}, indent=2), encoding="utf-8")
    return out


def detectors_from_args(args, run_dir: Path) -> list[Detector]:
    spec = args.detector
    if spec == "null":
        return [Detector("null", "null", [sys.executable, str(Path(__file__).resolve()), "null-detector"], child_env())]
    if spec.startswith("url:"):
        return [Detector(args.label or "url", "url", url=spec[4:].rstrip("/"))]
    if spec.startswith("cmd:"):
        return [Detector(args.label or "cmd", "cmd", shlex.split(spec[4:]), child_env())]
    if spec != "promptguard":
        raise SystemExit(f"unknown --detector {spec!r}")
    root = system_root(args.system_root)
    python = system_python(root, args.python)
    config = root / DETECTOR_CONFIG
    base = {**child_env(), "PG_DETECTOR_MODE": "normal"}
    argv = [python, str(root / WORKER)]
    out = [Detector("ensemble", "promptguard", argv, base, cwd=root, config=config, system_root=root)]
    if args.adapters == "each":
        entries = [e for e in json.loads(config.read_text(encoding="utf-8")).get("adapters", []) if e.get("enabled", True)]
        for entry in entries:
            path = single_adapter_config(config, entry, run_dir)
            out.append(Detector(entry["name"], "promptguard", argv, {**base, "PG_DETECTOR_CONFIG": str(path)},
                                cwd=root, config=path, system_root=root))
    return out


def git_state(root: Path | None) -> dict | None:
    if root is None:
        return None
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return {"commit": head, "dirty": bool(dirty)}
    except (OSError, subprocess.CalledProcessError):
        return None


# ---- measuring ---------------------------------------------------------------------------------------------

class Recorder:
    """Times calls to one detector and writes one row per sample."""

    def __init__(self, detector: Detector, out, repeat: int, timeout_ms: int, client_timeout: float):
        self.detector, self.out, self.repeat = detector, out, repeat
        self.timeout_ms, self.client_timeout = timeout_ms, client_timeout

    def call(self, items: list[dict], row: dict) -> list[int] | None:
        """`repeat` samples of one call. Returns the finding count per item from the first, or None if it failed."""
        texts = [item["text"] for item in items]
        base = {"detector": self.detector.label, **row, "n_items": len(items), "chars": sum(map(len, texts)),
                "bytes": sum(len(t.encode("utf-8")) for t in texts), "max_item_chars": max(map(len, texts), default=0),
                "item_sources": "+".join(sorted({str(item.get("source", "unknown")) for item in items}))}
        first = None
        for rep in range(self.repeat):
            sample, counts = self.sample(items)
            first = counts if rep == 0 else first
            self.out.write(json.dumps({**base, "rep": rep, **sample}) + "\n")
        self.out.flush()  # outside the timed region; keeps what was measured if a long run is stopped
        return first

    def sample(self, items: list[dict]) -> tuple[dict, list[int] | None]:
        """One timed call: its row fields, and the finding count per item (None if the call failed)."""
        body = {"request_id": str(uuid.uuid4()), "items": items}
        try:
            status, value, call_ms = http_json(self.detector.url, "POST", "/scan-batch", body, self.client_timeout)
        except OSError as exc:
            return {"ok": False, "status": None, "error": type(exc).__name__, "call_ms": None, "detector_ms": None,
                    "over_timeout": False, "findings": None}, None
        results = value.get("items") if isinstance(value, dict) else None
        ok = status == 200 and value.get("ok") is True and isinstance(results, list) and len(results) == len(items)
        counts, reported = None, None
        if ok:
            counts = [len(r.get("findings") or []) for r in results]
            latencies = [r.get("latency_ms") for r in results if isinstance(r.get("latency_ms"), (int, float))]
            reported = max(latencies) if latencies else None
        return {"ok": ok, "status": status, "error": None if ok else f"HTTP {status}", "call_ms": round(call_ms, 3),
                "detector_ms": reported, "over_timeout": call_ms > self.timeout_ms,
                "findings": sum(counts) if counts is not None else None}, counts


def measure(detector: Detector, args, run_dir: Path, sessions_for) -> dict:
    """Start the detector, warm it up (the first call is reported as cold), then run every session."""
    say(f"[{detector.label}] starting")
    detector.start(run_dir)
    info = {"label": detector.label, "kind": detector.kind, "startup_ms": detector.startup_ms,
            "describe": detector.describe(), "config": json.loads(detector.config.read_text()) if detector.config else None,
            "system": git_state(detector.system_root)}
    rows = open(run_dir / "calls.jsonl", "a", encoding="utf-8")
    requests = open(run_dir / "requests.jsonl", "a", encoding="utf-8")
    try:
        rec = Recorder(detector, rows, 1, args.timeout_ms, args.client_timeout)
        warm = []
        for i in range(max(1, args.warmup)):
            item = {"id": 0, "text": wl.synth_text(WARMUP_TEXT_SIZE, "secrets", f"warmup{i}"), "source": "warmup"}
            warm.append(rec.sample([item])[0])
        info["cold"] = {k: warm[0][k] for k in ("ok", "call_ms", "detector_ms")}
        rec.repeat = args.repeat
        counts = Counter()
        for session in sessions_for():
            if session.source == "guard":
                def scan(items, meta, session=session):
                    return rec.call(items, {"source": "guard", "workload": "guard", "session": session.name, **meta})
                for summary in wl.guard_session(session.requests, scan):
                    requests.write(json.dumps({"detector": detector.label, "session": session.name, **summary}) + "\n")
                    counts["guard requests"] += 1
                    counts["calls"] += summary["calls"]
            else:
                for call in session.calls:
                    rec.call(call.items, {"source": session.source, "workload": call.workload, "session": session.name,
                                          **call.meta})
                    counts["calls"] += 1
        info["counts"] = dict(counts)
        say(f"[{detector.label}] {dict(counts)}")
    finally:
        rows.close()
        requests.close()
        detector.stop()
    return info


def cmd_run(args):
    name = args.name or (Path(args.out).name if args.out else datetime.now().strftime("batch_%Y%m%d-%H%M%S"))
    run_dir = Path(args.out) if args.out else RUNS_DIR / name
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"{run_dir} is not empty; pick another --name")
    run_dir.mkdir(parents=True, exist_ok=True)
    if not (args.synth or args.guard or args.recorded):
        args.synth = True

    def sessions_for():
        out = []
        if args.synth:
            out += wl.synth_sessions()
        if args.guard:
            out += wl.guard_sessions(args.guard)
        if args.recorded:
            out += wl.recorded_sessions(args.recorded)
        return out

    meta = {"name": name, "started_at": datetime.now().isoformat(timespec="seconds"),
            "argv": sys.argv[1:], "repeat": args.repeat, "warmup": args.warmup, "timeout_ms": args.timeout_ms,
            "machine": {"platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
                        "python": platform.python_version()},
            "workloads": {"synth": bool(args.synth), "guard": args.guard or [], "recorded": args.recorded or []},
            "detectors": []}
    for detector in detectors_from_args(args, run_dir):
        meta["detectors"].append(measure(detector, args, run_dir, sessions_for))
        (run_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    (run_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"run folder: {run_dir}")


# ---- report ------------------------------------------------------------------------------------------------

def quantile(values: list[float], p: float) -> float | None:
    """Nearest rank: the smallest value with at least p of the samples at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def fit(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Least squares ms = a + b * KB. Returns (a, b), or None with fewer than two distinct sizes."""
    if len({x for x, _ in points}) < 2:
        return None
    n = len(points)
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    b = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x, _ in points)
    return my - b * mx, b


def fmt(value, digits=1) -> str:
    return "-" if value is None else f"{value:,.{digits}f}"


def load_run(path: Path) -> tuple[dict, list[dict], list[dict]]:
    meta = json.loads((path / "run.json").read_text(encoding="utf-8"))
    read = lambda name: [json.loads(line) for line in (path / name).read_text(encoding="utf-8").splitlines() if line.strip()] \
        if (path / name).is_file() else []  # noqa: E731
    return meta, read("calls.jsonl"), read("requests.jsonl")


def cmd_report(args):
    runs = [load_run(Path(p)) for p in args.runs]
    labels = Counter(d["label"] for meta, _, _ in runs for d in meta["detectors"])
    detectors, rows, requests = [], [], []
    for meta, calls, reqs in runs:
        rename = {d["label"]: (f"{meta['name']}:{d['label']}" if labels[d["label"]] > 1 else d["label"]) for d in meta["detectors"]}
        detectors += [{**d, "label": rename[d["label"]], "run": meta["name"], "meta": meta} for d in meta["detectors"]]
        rows += [{**r, "detector": rename.get(r["detector"], r["detector"])} for r in calls]
        requests += [{**r, "detector": rename.get(r["detector"], r["detector"])} for r in reqs]
    names = [d["label"] for d in detectors]
    ok_rows = [r for r in rows if r["ok"]]

    def series(pred, key="detector_ms"):
        return [r[key] for r in ok_rows if pred(r) and r.get(key) is not None]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = ["# metric-latency: 탐지기 호출 지연", ""]
    md += ["실행: " + ", ".join(f"`{m['name']}` ({m['started_at']}, 반복 {m['repeat']}회, warmup {m['warmup']}회)" for m, _, _ in runs), ""]
    machine = runs[0][0]["machine"]
    md += [f"기기: {machine['platform']}, {machine['machine']}, CPU {machine['cpu_count']}개, Python {machine['python']}", ""]

    md += ["## 탐지기", "", "| 탐지기 | 어댑터 (버전) | 합의 | 시작 시간 | 첫 호출 (cold) call / detector | 시스템 커밋 |", "|---|---|---|---|---|---|"]
    for d in detectors:
        desc = d.get("describe") or {}
        adapters = ", ".join(f"{a.get('name')} ({a.get('version')})" for a in desc.get("adapters", [])) or desc.get("detector", "-")
        system = d.get("system") or {}
        commit = f"`{system['commit'][:7]}`" + (" (수정됨)" if system.get("dirty") else "") if system.get("commit") else "-"
        cold = d.get("cold") or {}
        md.append(f"| {d['label']} | {adapters} | {desc.get('consensus', '-')} | {fmt(d.get('startup_ms'), 0)} ms "
                  f"| {fmt(cold.get('call_ms'))} / {fmt(cold.get('detector_ms'))} ms | {commit} |")
    md.append("")

    timeout_ms = runs[0][0]["timeout_ms"]
    sources = [s for s in ("synth", "guard", "recorded") if any(r["source"] == s for r in rows)]
    md += ["## 호출 지연 (warm, 모든 반복)", "",
           f"detector는 탐지기가 보고한 batch 시간, call은 평가기가 잰 HTTP 왕복 시간이다. 백분위수는 nearest rank. "
           f"timeout 초과는 call이 {timeout_ms:,}ms(시스템의 `detectorTimeoutMs`)를 넘은 표본 수다.", "",
           "| 탐지기 | 워크로드 | 호출 | 표본 | detector p50 | p95 | p99 | max | call p50 | call p95 | call − detector p50 | timeout 초과 | 실패 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    csv_rows = []
    for name in names:
        for source in sources:
            mine = [r for r in rows if r["detector"] == name and r["source"] == source]
            if not mine:
                continue
            det = series(lambda r: r["detector"] == name and r["source"] == source)
            call = series(lambda r: r["detector"] == name and r["source"] == source, "call_ms")
            gap = [r["call_ms"] - r["detector_ms"] for r in ok_rows if r["detector"] == name and r["source"] == source
                   and r.get("detector_ms") is not None]
            n_calls = sum(1 for r in mine if r["rep"] == 0)
            over = sum(1 for r in mine if r.get("over_timeout"))
            failed = sum(1 for r in mine if not r["ok"])
            md.append(f"| {name} | {source} | {n_calls:,} | {len(mine):,} | {fmt(quantile(det, .5))} | {fmt(quantile(det, .95))} "
                      f"| {fmt(quantile(det, .99))} | {fmt(max(det) if det else None)} | {fmt(quantile(call, .5))} "
                      f"| {fmt(quantile(call, .95))} | {fmt(quantile(gap, .5), 2)} | {over} | {failed} |")
        for workload in sorted({r["workload"] for r in rows if r["detector"] == name}):
            det = series(lambda r: r["detector"] == name and r["workload"] == workload)
            call = series(lambda r: r["detector"] == name and r["workload"] == workload, "call_ms")
            csv_rows.append({"detector": name, "workload": workload,
                             "samples": sum(1 for r in rows if r["detector"] == name and r["workload"] == workload),
                             **{f"detector_{k}": quantile(det, p) for k, p in (("p50", .5), ("p95", .95), ("p99", .99))},
                             "detector_max": max(det) if det else None,
                             **{f"call_{k}": quantile(call, p) for k, p in (("p50", .5), ("p95", .95), ("p99", .99))},
                             "call_max": max(call) if call else None})
    md.append("")

    if "synth" in sources:
        for title, key, fixed in (("크기별 (텍스트 1개짜리 호출)", "size", {"batch": 1}),
                                  (f"batch 크기별 ({wl.SYNTH_BATCH_ITEM:,}자 텍스트)", "batch", {"size": wl.SYNTH_BATCH_ITEM})):
            md += [f"## 합성 입력: {title}", "", "detector_ms의 p50 (p95). plain은 비밀이 없는 로그·코드, secrets는 약 20줄마다 비밀 한 줄.", ""]
            values = sorted({r[key] for r in rows if r["source"] == "synth" and all(r.get(k) == v for k, v in fixed.items())})
            md += ["| " + key + " | " + " | ".join(f"{n} {kind}" for n in names for kind in ("plain", "secrets")) + " |",
                   "|---" * (1 + 2 * len(names)) + "|"]
            for value in values:
                cells = []
                for n in names:
                    for kind in ("plain", "secrets"):
                        s = series(lambda r: r["detector"] == n and r["source"] == "synth" and r.get("kind") == kind
                                   and r.get(key) == value and all(r.get(k) == v for k, v in fixed.items()))
                        cells.append(f"{fmt(quantile(s, .5))} ({fmt(quantile(s, .95))})" if s else "-")
                md.append(f"| {value:,} | " + " | ".join(cells) + " |")
            md.append("")

    if "synth" in sources:
        md += ["## 기울기", "", "합성 입력의 warm 표본에 최소제곱으로 맞춘 직선. 크기: 텍스트 1개짜리 호출로 `detector_ms = 고정 + 기울기 × KB`"
               f"(UTF-8 1,024바이트). 문자열 수: {wl.SYNTH_BATCH_ITEM:,}자 텍스트의 batch로 `detector_ms = 고정 + 기울기 × 문자열 수`.", "",
               "| 탐지기 | 크기: 고정 (ms) | ms/KB | 문자열 수: 고정 (ms) | ms/문자열 |", "|---|---|---|---|---|"]
        for name in names:
            synth = [r for r in ok_rows if r["detector"] == name and r["source"] == "synth" and r.get("detector_ms") is not None]
            by_size = fit([(r["bytes"] / 1024, r["detector_ms"]) for r in synth if r.get("batch") == 1])
            by_items = fit([(r["n_items"], r["detector_ms"]) for r in synth if r.get("size") == wl.SYNTH_BATCH_ITEM])
            cells = [fmt(v, d) for line in (by_size, by_items) for v, d in ((line[0], 2), (line[1], 3)) if line] if by_size and by_items else ["-"] * 4
            md.append(f"| {name} | " + " | ".join(cells) + " |")
        md.append("")

    if requests:
        md += ["## Final Guard 재생: 요청 1개당", "",
               "요청마다 본문의 문자열 중 캐시에 없는 것만 256개씩 보낸다. 요청 시간은 그 요청의 호출들의 detector_ms(반복 중앙값) 합이다.", "",
               "| 탐지기 | 세션 | 요청 | 문자열 (중앙값) | 보낸 문자열 비율 | 보낸 문자열 p50 | p95 | 요청당 호출 p95 | 요청 시간 p50 | p95 | max | 막힌 요청 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        per_call = defaultdict(list)
        for r in ok_rows:
            if r["source"] == "guard" and r.get("detector_ms") is not None:
                per_call[(r["detector"], r["session"], r["request"], r["batch"])].append(r["detector_ms"])
        for name in names:
            mine = [q for q in requests if q["detector"] == name]
            if not mine:
                continue
            totals = [sum(quantile(per_call[(name, q["session"], q["request"], b)], .5) or 0 for b in range(q["calls"])) for q in mine]
            sent = sum(q["unique"] for q in mine) / max(1, sum(q["leaves"] for q in mine))
            md.append(f"| {name} | {len({q['session'] for q in mine})} | {len(mine)} | {fmt(quantile([q['leaves'] for q in mine], .5), 0)} "
                      f"| {sent:.1%} | {fmt(quantile([q['unique'] for q in mine], .5), 0)} | {fmt(quantile([q['unique'] for q in mine], .95), 0)} "
                      f"| {fmt(quantile([q['calls'] for q in mine], .95), 0)} | {fmt(quantile(totals, .5))} | {fmt(quantile(totals, .95))} "
                      f"| {fmt(max(totals))} | {sum(1 for q in mine if q['findings'] or q['failed'])} |")
        md.append("")

    if "recorded" in sources:
        md += ["## Native Mod 기록 재생: item source별", "", "| 탐지기 | source | 호출 | detector p50 | p95 | max |", "|---|---|---|---|---|---|"]
        for name in names:
            for workload in sorted({r["workload"] for r in rows if r["detector"] == name and r["source"] == "recorded"}):
                s = series(lambda r: r["detector"] == name and r["workload"] == workload)
                md.append(f"| {name} | {workload.split('/', 1)[1]} | {sum(1 for r in rows if r['detector'] == name and r['workload'] == workload and r['rep'] == 0)} "
                          f"| {fmt(quantile(s, .5))} | {fmt(quantile(s, .95))} | {fmt(max(s) if s else None)} |")
        md.append("")

    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0]) if csv_rows else ["detector"])
        writer.writeheader()
        writer.writerows(csv_rows)
    say(f"wrote {out_dir / 'summary.md'} and summary.csv")


# ---- null detector -----------------------------------------------------------------------------------------

class NullHandler(BaseHTTPRequestHandler):
    """Speaks the worker protocol and finds nothing: what is left of call_ms is HTTP and JSON."""

    def log_message(self, _format, *_args):
        return

    def send_json(self, status: int, value):
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in {"/health", "/ready", "/status"}:
            return self.send_json(404, {"ok": False})
        self.send_json(200, {"ok": True, "ready": True, "detector": "null"})

    def do_POST(self):
        started = time.perf_counter()
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))).decode("utf-8"))
            items = payload["items"]
        except (ValueError, KeyError, TypeError):
            return self.send_json(400, {"ok": False, "error": "INVALID_BATCH"})
        latency = round((time.perf_counter() - started) * 1000, 3)
        self.send_json(200, {"ok": True, "request_id": payload.get("request_id"), "items": [
            {"id": item.get("id"), "ok": True, "findings": [], "errors": [], "finding_count": 0, "latency_ms": latency}
            for item in items]})


def cmd_null_detector(_args):
    server = ThreadingHTTPServer(("127.0.0.1", int(os.environ["PG_DETECTOR_PORT"])), NullHandler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="measure detector calls over workloads")
    p.add_argument("--name", help="run folder name under runs/metric-latency (default batch_<time>)")
    p.add_argument("--out", help="run folder (default runs/metric-latency/<name>)")
    p.add_argument("--detector", default="promptguard",
                   help="promptguard (the system's worker), null, cmd:<command with {port}>, url:<base url>")
    p.add_argument("--label", help="name for a cmd: or url: detector in the report")
    p.add_argument("--adapters", choices=["ensemble", "each"], default="ensemble",
                   help="promptguard: also measure each adapter alone (one worker per adapter, consensus any)")
    p.add_argument("--system-root", help=f"promptguard-claude-demoV0 checkout (default ${SYSTEM_ENV}, else ../promptguard-claude-demoV0)")
    p.add_argument("--python", help="Python for the system's worker (default the checkout's .venv)")
    p.add_argument("--synth", action="store_true", help="generated size and batch sweeps (the default workload)")
    p.add_argument("--guard", nargs="+", metavar="PATH", help="metric-task run folders or api_requests.jsonl.xz files to replay as Final Guard calls")
    p.add_argument("--recorded", nargs="+", metavar="PATH", help="metric-task run folders or detector_calls.jsonl.xz files to replay as Native Mod calls")
    p.add_argument("--repeat", type=int, default=5, help="samples per call (default 5)")
    p.add_argument("--warmup", type=int, default=3, help="calls before measuring; the first is reported as cold (default 3)")
    p.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS, help="count samples slower than this (default 5000)")
    p.add_argument("--client-timeout", type=float, default=120.0, help="seconds before a call is abandoned (default 120)")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("report", help="summary.md and summary.csv from run folders")
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("null-detector", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_null_detector)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
