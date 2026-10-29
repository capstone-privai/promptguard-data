#!/usr/bin/env python3
"""중간발표용 탐지 지연 평가: 측정부터 report/latency/ 파일 3개까지 한 번에 한다.

중간발표/오늘밤_지연평가_프롬프트_WSL.md 의 요구를 그대로 따른다.

  1. 사전 점검   다른 무거운 작업이 없는지, gitleaks가 있는지, 탐지기 설정에서 켜진 어댑터가 무엇인지
  2. 단위 테스트 평가기(metric-latency/tests)가 통과하는지. 실패하면 측정하지 않는다
  3. 측정       탐지기마다 m4.py run 을 두 번 부른다
                  합성 입력  --synth, 반복을 많이 (p99가 나오도록)
                  기록 재생  --guard / --recorded, 반복은 적게 (호출 수 자체가 많다)
                탐지기
                  시스템 앙상블  체크아웃 설정 그대로 (m4 --detector promptguard)
                  어댑터별       켜진 어댑터마다 그 하나만. 나머지는 PG_DETECTOR_DISABLE로 끈다.
                                 후보 전용(candidate_only) 어댑터는 혼자서는 투표자가 0명이라 worker가
                                 시작을 거부하므로, 그 어댑터 하나만 든 임시 설정 파일로 띄운다
                  바닥값         m4의 null 탐지기 (로컬 HTTP와 JSON 비용만)
                ML 어댑터는 뺀다(기본 설정에서 꺼져 있다. 켜져 있으면 끄고 잰다)
  4. 기록 검증   각 실행에서 실제로 뜬 어댑터가 기대와 같은지. gitleaks가 빠진 결과는 쓰지 않는다
  5. 결과물     report/latency/README.md, latency.md, slide_numbers.md

시스템 코드와 m4.py는 고치지 않는다(import만 한다). 텍스트는 어디에도 남지 않는다: m4가 숫자만 기록한다.

반복 횟수를 왜 이렇게 잡나
  전체 데이터를 다 돌릴 필요는 없다. 지연은 "분포 모양"만 잡으면 된다.
  합성 입력은 셀(예: 1KB 텍스트 1개)마다 plain·secrets 두 종류 × --synth-repeat 번이 표본이다.
  기본 50번이면 셀마다 100표본이라 p99를 낼 수 있다(100개 중 가장 느린 1개 수준).
  재생은 Guard 기록만 해도 호출이 150개쯤이라 --replay-repeat 5면 750표본이다.

실행 (promptguard-data 루트에서. WSL이면 리눅스 쪽 폴더에서)
  python3 metric-latency/scripts/midterm_latency.py              # 본 측정 (PC에서 20~40분)
  python3 metric-latency/scripts/midterm_latency.py --quick      # 몇 분짜리 점검. 숫자를 발표에 쓰지 않는다
  python3 metric-latency/scripts/midterm_latency.py --report-only runs/metric-latency/midterm_<시간>
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import m4  # noqa: E402  quantile, fit, guard_summary, load_run: 평가기 보고서와 같은 집계 함수를 쓴다

DATA_ROOT = HERE.parents[1]
SYSTEM_ENV = "PROMPTGUARD_CLAUDE_ROOT"
WORKER = Path("src", "detector", "worker.py")
DETECTOR_CONFIG = Path("src", "detector", "detector.json")
SYSTEM_CONFIG = "promptguard.config.json"
KB1, KB64 = 1024, 65536
GUARD_DEFAULT = Path("runs", "metric-task", "capture_trial")
RECORDED_SEARCH = Path("runs", "metric-task")

# 같은 기기에서 돌면 숫자를 오염시키는 작업. 명령줄 전체는 출력하지 않는다(비밀이 들어 있을 수 있다).
HEAVY = re.compile(r"(\bm2\.py|\bm4\.py|metric-detection|metric-task|evaluate|pytest|unittest|jest|vitest|"
                   r"npm (?:run|test|ci|install)|\byarn\b|\bpnpm\b|\btsc\b|\bcargo\b|\bmake\b|cmake|gradle|\bmvn\b|"
                   r"docker (?:build|compose)|credsweeper|gitleaks|jupyter|ipykernel|ffmpeg|pip install|uv pip)", re.I)

NOTE_ENSEMBLE = "앙상블은 어댑터를 병렬로 돌리므로, 앙상블 시간은 대략 가장 느린 어댑터 시간에 투표 시간을 더한 값이다."
NOTE_SCOPE = "훅의 치환·기록 비용과 MCP bridge 비용은 들어가지 않는다."


def say(*parts):
    print(*parts, flush=True)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---- 환경 ---------------------------------------------------------------------------------------------------

def run_text(argv, **kw) -> str | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30, **kw).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower() or bool(os.environ.get("WSL_DISTRO_NAME"))


def machine_info() -> dict:
    cpu = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    if not cpu:
        lscpu = run_text(["lscpu"]) or ""
        match = re.search(r"Model name:\s*(.+)", lscpu)
        cpu = match.group(1).strip() if match else (run_text(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor() or "unknown")
    mem = None
    try:
        kb = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
        mem = f"{kb / 1024 / 1024:.1f} GiB"
    except (OSError, AttributeError):
        raw = run_text(["sysctl", "-n", "hw.memsize"])
        mem = f"{int(raw) / 1024 ** 3:.1f} GiB" if raw and raw.isdigit() else "unknown"
    wsl = f"WSL ({os.environ.get('WSL_DISTRO_NAME', 'distro unknown')}, kernel {platform.release()})" if is_wsl() else "WSL 아님"
    return {"cpu": cpu, "cpu_count": os.cpu_count(), "memory": mem, "os": platform.platform(), "wsl": wsl, "is_wsl": is_wsl()}


def git_state(root: Path) -> dict:
    head = run_text(["git", "-C", str(root), "rev-parse", "HEAD"])
    dirty = run_text(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"])
    return {"commit": head, "dirty": bool(dirty)}


def processes() -> list[tuple[int, int, str]]:
    out = run_text(["ps", "-eo", "pid=,ppid=,args="]) or ""
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


def other_heavy() -> list[str]:
    """이 스크립트와 그 자식(m4, worker, gitleaks) 말고 도는 무거운 작업. 프로그램 이름과 걸린 단어만 돌려준다."""
    rows = processes()
    children = defaultdict(list)
    for pid, ppid, _ in rows:
        children[ppid].append(pid)
    mine, stack = set(), [os.getpid()]
    while stack:
        pid = stack.pop()
        if pid not in mine:
            mine.add(pid)
            stack += children[pid]
    found = []
    for pid, _, args in rows:
        if pid in mine or "midterm_latency.py" in args:
            continue
        match = HEAVY.search(args)
        if match:
            program = Path(args.split()[0]).name if args.split() else "?"
            found.append(f"pid {pid} {program} ('{match.group(1).strip()}')")
    return found


def load_sample(stage: str) -> dict:
    try:
        load1 = round(os.getloadavg()[0], 2)
    except OSError:
        load1 = None
    return {"at": now(), "stage": stage, "load1": load1, "others": other_heavy()}


# ---- 사전 점검 -----------------------------------------------------------------------------------------------

def is_ml(entry: dict) -> bool:
    return str(entry.get("type", "")).startswith("ml") or str(entry.get("name", "")).startswith("ml")


def worker_python(system: Path, arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    for candidate in (system / ".venv" / "bin" / "python", system / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    raise SystemExit(f"[중단] {system}/.venv 가 없다. 시스템의 설치 스크립트를 먼저 돌리거나 --python 을 줘.")


def preflight(args) -> dict:
    data = Path(args.data_root).resolve()
    system = Path(args.system_root or os.environ.get(SYSTEM_ENV) or data.parent / "promptguard-claude-demoV0").expanduser().resolve()
    if not (system / WORKER).is_file():
        raise SystemExit(f"[중단] {system} 에 {WORKER.as_posix()} 가 없다. --system-root 를 줘.")
    python = worker_python(system, args.python)
    config_path = system / DETECTOR_CONFIG
    config = json.loads(config_path.read_text(encoding="utf-8"))
    entries = config.get("adapters", [])
    names_all = [e["name"] for e in entries]
    on = [e for e in entries if e.get("enabled", True) and not is_ml(e)]
    ml_on = [e["name"] for e in entries if e.get("enabled", True) and is_ml(e)]
    ml_all = [e["name"] for e in entries if is_ml(e)]
    if not on:
        raise SystemExit("[중단] 탐지기 설정에 켜진 (ML 아닌) 어댑터가 없다.")

    # gitleaks 어댑터가 쓸 실행 파일. 없으면 required:false라 조용히 빠지므로 여기서 막는다.
    gitleaks_version = None
    for entry in on:
        if entry.get("type") == "gitleaks":
            binary = (entry.get("options") or {}).get("binary") or "gitleaks"
            path = shutil.which(binary)
            if not path:
                raise SystemExit(f"[중단] gitleaks 실행 파일({binary})을 PATH에서 찾지 못했다. gitleaks가 빠진 결과는 쓰지 않으므로 설치 후 다시 돌려.")
            gitleaks_version = run_text([path, "version"])

    timeout_ms = 5000
    try:
        timeout_ms = int(json.loads((system / SYSTEM_CONFIG).read_text(encoding="utf-8")).get("detectorTimeoutMs", 5000))
    except (OSError, ValueError):
        pass

    credsweeper_version = run_text([str(python), "-c", "import credsweeper; print(credsweeper.__version__)"])
    return {
        "data_root": str(data), "system_root": str(system), "worker_python": str(python),
        "worker_python_version": run_text([str(python), "-c", "import platform; print(platform.python_version())"]),
        "evaluator_python_version": platform.python_version(),
        "config_path": str(config_path), "config": config, "adapters_all": names_all,
        "adapters_on": [e["name"] for e in on], "candidate_only": [e["name"] for e in on if e.get("candidate_only")],
        "ml_on_by_default": ml_on, "ml_all": ml_all, "timeout_ms": timeout_ms,
        "credsweeper_version": credsweeper_version, "gitleaks_version": gitleaks_version,
        "system_git": git_state(system), "data_git": git_state(data), "machine": machine_info(),
    }


def wait_until_quiet(args) -> dict:
    sample = load_sample("preflight")
    deadline = time.time() + max(0, args.wait) * 60
    while sample["others"] and not args.force:
        if time.time() >= deadline:
            say("[중단] 같은 기기에서 다른 무거운 작업이 돌고 있다. 끝난 뒤 다시 돌리거나, 기다리려면 --wait 분, 무시하려면 --force.")
            for item in sample["others"]:
                say("   -", item)
            raise SystemExit(2)
        say(f"   다른 작업이 끝나길 기다리는 중: {', '.join(sample['others'])}")
        time.sleep(30)
        sample = load_sample("preflight")
    return sample


# ---- 측정 계획 -----------------------------------------------------------------------------------------------

def absolutize(value, base: Path):
    if isinstance(value, str) and value and not Path(value).is_absolute() and (base / value).exists():
        return str((base / value).resolve())
    if isinstance(value, list):
        return [absolutize(v, base) for v in value]
    if isinstance(value, dict):
        return {k: absolutize(v, base) for k, v in value.items()}
    return value


def plan_detectors(env: dict, batch: Path) -> list[dict]:
    system = Path(env["system_root"])
    worker = str(system / WORKER)
    python = env["worker_python"]
    config = env["config"]
    plan = []

    if env["ml_on_by_default"]:
        # 기본 설정에 ML이 켜져 있으면 ML만 끈 앙상블을 cmd:로 띄운다(m4의 promptguard는 PG_*를 지운다).
        argv = ["env", "PG_DETECTOR_MODE=normal", "PG_DETECTOR_DISABLE=" + ",".join(env["ml_on_by_default"]), python, worker]
        ensemble_spec = "cmd:" + shlex.join(argv)
    else:
        ensemble_spec = "promptguard"
    plan.append({"label": "ensemble", "display": "시스템 앙상블", "spec": ensemble_spec, "expected": env["adapters_on"]})

    configs = batch / "configs"
    for name in env["adapters_on"]:
        if name in env["candidate_only"]:
            entry = next(e for e in config["adapters"] if e["name"] == name)
            solo = {k: v for k, v in config.items() if k != "adapters"}
            solo["adapters"] = [{**{k: v for k, v in entry.items() if k != "options"},
                                 "options": absolutize(entry.get("options", {}), system / DETECTOR_CONFIG.parent),
                                 "enabled": True, "required": True, "candidate_only": False}]
            configs.mkdir(parents=True, exist_ok=True)
            path = configs / f"{name}.json"
            path.write_text(json.dumps(solo, ensure_ascii=False, indent=2), encoding="utf-8")
            argv = ["env", "PG_DETECTOR_MODE=normal", f"PG_DETECTOR_CONFIG={path}", python, worker]
            how = "그 어댑터 하나만 든 임시 설정 파일 (후보 전용이라 혼자서는 시작이 거부돼서, 투표자로 등록)"
        else:
            others = [n for n in env["adapters_all"] if n != name]
            argv = ["env", "PG_DETECTOR_MODE=normal", "PG_DETECTOR_DISABLE=" + ",".join(others), python, worker]
            how = "시스템 설정 파일 그대로, 나머지 어댑터는 PG_DETECTOR_DISABLE로 끔"
        plan.append({"label": name, "display": f"어댑터: {name}", "spec": "cmd:" + shlex.join(argv),
                     "expected": [name], "how": how})

    plan.append({"label": "null", "display": "바닥값 (null)", "spec": "null", "expected": None})
    return plan


def replay_inputs(args, data: Path) -> tuple[list[str], list[str], list[str]]:
    """Guard 재생 경로, Native Mod 재생 경로, 하지 못한 이유."""
    reasons, guard, recorded = [], [], []
    if args.skip_guard:
        reasons.append("Final Guard 재생: --skip-guard로 건너뜀")
    else:
        paths = [Path(p) for p in (args.guard or [str(data / GUARD_DEFAULT)])]
        paths = [p if p.is_absolute() else (Path.cwd() / p) for p in paths]
        found = [p for p in paths if p.exists() and (p.is_file() or any(p.rglob(m4.wl.CAPTURE_FILE)))]
        if found:
            guard = [str(p) for p in found]
        else:
            reasons.append(f"Final Guard 재생: 실행 기록({m4.wl.CAPTURE_FILE})이 없음 — "
                           + ", ".join(str(p) for p in paths) + " 에 기록을 복사해 두면 잰다")
    if args.skip_recorded:
        reasons.append("Native Mod 재생: --skip-recorded로 건너뜀")
    else:
        if args.recorded:
            paths = [Path(p) if Path(p).is_absolute() else Path.cwd() / p for p in args.recorded]
            found = [p for p in paths if p.exists() and (p.is_file() or any(p.rglob(m4.wl.RECORDED_FILE)))]
        else:
            root = data / RECORDED_SEARCH
            found = sorted({f.parent for f in root.rglob(m4.wl.RECORDED_FILE)}) if root.is_dir() else []
        if found:
            recorded = [str(p) for p in found]
        else:
            reasons.append(f"Native Mod 재생: 훅 호출 기록({m4.wl.RECORDED_FILE})이 없음 — "
                           "metric-task를 --detector-capture로 돌려야 생긴다")
    return guard, recorded, reasons


# ---- 측정 ----------------------------------------------------------------------------------------------------

def run_m4(meta: dict, det: dict, kind: str, workload: list[str], repeat: int, warmup: int) -> dict:
    env, batch = meta["env"], Path(meta["batch"])
    out = batch / f"{det['label']}__{kind}"
    argv = [sys.executable, str(HERE / "m4.py"), "run", "--out", str(out), "--detector", det["spec"],
            "--repeat", str(repeat), "--warmup", str(warmup), "--timeout-ms", str(env["timeout_ms"])]
    if det["spec"].startswith("cmd:"):
        argv += ["--label", det["label"]]
    if det["spec"] == "promptguard":
        argv += ["--system-root", env["system_root"], "--python", env["worker_python"]]
    argv += workload
    (batch / "logs").mkdir(exist_ok=True)
    before = load_sample(f"{det['label']}/{kind} 전")
    started = time.perf_counter()
    with open(batch / "logs" / f"{det['label']}__{kind}.log", "w", encoding="utf-8") as log:
        code = subprocess.run(argv, cwd=env["data_root"], stdout=log, stderr=subprocess.STDOUT).returncode
    seconds = round(time.perf_counter() - started, 1)
    after = load_sample(f"{det['label']}/{kind} 후")
    meta["load"] += [before, after]
    result = {"dir": str(out), "code": code, "seconds": seconds, "repeat": repeat, "warmup": warmup}
    if code != 0:
        tail = (batch / "logs" / f"{det['label']}__{kind}.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()
        result["error"] = (tail[-1] if tail else f"exit {code}")[:200]
    return result


def check_run(path: Path, expected: list[str] | None) -> str | None:
    """실제로 뜬 어댑터가 기대와 다르면 그 이유를 돌려준다."""
    if not (path / "run.json").is_file():
        return "run.json이 없음 (실행이 끝나지 않음)"
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if not run.get("detectors") or "counts" not in run["detectors"][0]:
        return "측정이 끝까지 가지 않음"
    if expected is None:
        return None
    desc = run["detectors"][0].get("describe") or {}
    names = [a.get("name") for a in desc.get("adapters", [])]
    if desc.get("skipped"):
        return "빠진 어댑터가 있음: " + ", ".join(f"{s.get('name')}" for s in desc["skipped"])
    if sorted(names) != sorted(expected):
        return f"뜬 어댑터 {names}가 기대한 {expected}와 다름"
    return None


def measure_all(meta: dict, args):
    plan, s = meta["plan"], meta["settings"]
    replay = (["--guard", *meta["guard"]] if meta["guard"] else []) + (["--recorded", *meta["recorded"]] if meta["recorded"] else [])
    total = len(plan) * (2 if replay else 1)
    step = 0
    for det in plan:
        for kind, workload, repeat, warmup in (("synth", ["--synth"], s["synth_repeat"], s["synth_warmup"]),
                                               ("replay", replay, s["replay_repeat"], s["replay_warmup"])):
            if not workload:
                continue
            step += 1
            what = "합성 입력" if kind == "synth" else "기록 재생"
            say(f"[측정 {step}/{total}] {det['display']} — {what} (반복 {repeat}, warmup {warmup})")
            result = run_m4(meta, det, kind, workload, repeat, warmup)
            problem = result.get("error") or check_run(Path(result["dir"]), det["expected"])
            result["invalid"] = problem
            det[kind] = result
            say(f"   {result['seconds']}초" + (f" — 쓰지 않음: {problem}" if problem else ""))
            save_meta(meta)


def save_meta(meta: dict):
    Path(meta["batch"], "midterm.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- 집계 ----------------------------------------------------------------------------------------------------

def q(values: list[float]) -> dict:
    return {"n": len(values), "p50": m4.quantile(values, .5), "p95": m4.quantile(values, .95),
            "p99": m4.quantile(values, .99), "max": max(values) if values else None}


def timing(row) -> bool:
    return bool(row.get("ok")) and isinstance(row.get("detector_ms"), (int, float))


def synth_stats(path: Path) -> dict:
    run, calls, _ = m4.load_run(path)
    rows = [r for r in calls if r.get("source") == "synth"]
    ok = [r for r in rows if timing(r)]
    cell = lambda size, batch=1: [r["detector_ms"] for r in ok if r.get("size") == size and r.get("batch") == batch]  # noqa: E731
    by_items = m4.fit([(r["n_items"], r["detector_ms"]) for r in ok if r.get("size") == m4.wl.SYNTH_BATCH_ITEM])
    by_kb = m4.fit([(r["bytes"] / 1024, r["detector_ms"]) for r in ok if r.get("batch") == 1])
    det = run["detectors"][0]
    return {"1k": q(cell(KB1)), "64k": q(cell(KB64)),
            "per_item": by_items[1] if by_items else None, "per_kb": by_kb[1] if by_kb else None,
            "cold_call": (det.get("cold") or {}).get("call_ms"), "cold_detector": (det.get("cold") or {}).get("detector_ms"),
            "startup": det.get("startup_ms"), "samples": len(rows), "failed": sum(1 for r in rows if not r.get("ok")),
            "over": sum(1 for r in rows if r.get("over_timeout")),
            "curve": {size: m4.quantile(cell(size), .5) for size in sorted({r["size"] for r in ok if r.get("batch") == 1})},
            "describe": det.get("describe") or {}}


def request_totals(calls: list[dict], requests: list[dict]) -> list[tuple[int, float]]:
    """m4.guard_summary와 같은 규칙으로 요청마다 시간을 낸다(세션 첫 요청을 나누려고)."""
    per_call = defaultdict(list)
    for row in calls:
        t = row.get("detector_ms")
        if row.get("source") == "guard" and timing(row) and t >= 0:
            per_call[(row["detector"], row["session"], row["request"], row["batch"])].append(t)
    out = []
    for req in requests:
        count = req.get("calls")
        if req.get("failed") or type(count) is not int or count < 0 or (count == 0 and req.get("unique", 0) > 0):
            continue
        medians = [m4.quantile(per_call[(req["detector"], req["session"], req["request"], b)], .5) for b in range(count)]
        if any(v is None for v in medians):
            continue
        out.append((req["request"], sum(medians)))
    return out


def replay_stats(path: Path) -> dict:
    _, calls, requests = m4.load_run(path)
    out = {}
    if requests:
        summary = m4.guard_summary(calls, requests)
        totals = request_totals(calls, requests)
        guard_rows = [r for r in calls if r.get("source") == "guard"]
        out["guard"] = {**summary, "first": q([t for i, t in totals if i == 0]), "rest": q([t for i, t in totals if i > 0]),
                        "samples": len(guard_rows), "over": sum(1 for r in guard_rows if r.get("over_timeout"))}
    rec = [r for r in calls if r.get("source") == "recorded"]
    if rec:
        out["recorded"] = {**q([r["detector_ms"] for r in rec if timing(r)]), "calls": sum(1 for r in rec if r.get("rep") == 0),
                           "samples": len(rec), "over": sum(1 for r in rec if r.get("over_timeout")),
                           "failed": sum(1 for r in rec if not r.get("ok"))}
    return out


def collect(meta: dict) -> dict:
    stats = {}
    for det in meta["plan"]:
        entry = {"display": det["display"], "synth": None, "guard": None, "recorded": None, "why": {}}
        for kind in ("synth", "replay"):
            result = det.get(kind)
            if not result:
                continue
            if result.get("invalid"):
                entry["why"][kind] = result["invalid"]
                continue
            if kind == "synth":
                entry["synth"] = synth_stats(Path(result["dir"]))
            else:
                replay = replay_stats(Path(result["dir"]))
                entry["guard"], entry["recorded"] = replay.get("guard"), replay.get("recorded")
        stats[det["label"]] = entry
    return stats


# ---- 쓰기 ----------------------------------------------------------------------------------------------------

def ms(v) -> str:
    if v is None:
        return "—"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def slope(v) -> str:
    return "—" if v is None else ("+" if v >= 0 else "") + ms(v)


def notes(meta: dict) -> list[str]:
    machine = meta["env"]["machine"]
    first = ("WSL에서 잰 값이라 이전 맥 측정과 직접 비교하지 않는다." if machine["is_wsl"]
             else f"WSL이 아닌 환경({machine['os']})에서 잰 값이다. 이전 맥 측정과 직접 비교하지 않는다.")
    return [f"- {first}", f"- {NOTE_ENSEMBLE}", f"- {NOTE_SCOPE}"]


def adapters_ranked(stats: dict) -> list[tuple[str, float]]:
    ranked = [(label, e["synth"]["1k"]["p50"]) for label, e in stats.items()
              if label not in ("ensemble", "null") and e["synth"] and e["synth"]["1k"]["p50"] is not None]
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def missing_lines(stats: dict, kind: str, title: str) -> list[str]:
    lines = []
    for e in stats.values():
        why = e["why"].get(kind)
        if why:
            lines.append(f"- {e['display']} {title}: — ({why})")
    return lines


def write_latency_md(meta: dict, stats: dict, path: Path):
    s = meta["settings"]
    md = ["# 탐지 지연 표", "", f"측정 기기: {device_line(meta)}. 단위는 ms.", ""]
    md += ["## 합성 입력", "",
           "| 탐지기 | 1KB p50 | 1KB p95 | 64KB p50 | 64KB p95 | 문자열 1개당 증가 | 1KB당 증가 | cold 호출 | worker 시작 | 5초 초과 수 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for e in stats.values():
        x = e["synth"]
        if not x:
            md.append(f"| {e['display']} |" + " — |" * 9)
            continue
        md.append(f"| {e['display']} | {ms(x['1k']['p50'])} | {ms(x['1k']['p95'])} | {ms(x['64k']['p50'])} | {ms(x['64k']['p95'])} "
                  f"| {slope(x['per_item'])} | {slope(x['per_kb'])} | {ms(x['cold_call'])} | {ms(x['startup'])} | {x['over']} |")
    md += ["", f"- 1KB·64KB는 텍스트 1개짜리 호출(1,024자·65,536자). 셀마다 표본은 plain·secrets 2종 × 반복 {s['synth_repeat']}번"
               f" = {2 * s['synth_repeat']}개, warmup {s['synth_warmup']}번은 뺐다. p50·p95는 탐지기가 보고한 batch 시간(`detector_ms`).",
           "- 문자열 1개당 증가: 1,024자 텍스트를 batch 1·4·16·64·256개로 늘릴 때의 기울기(ms/문자열). "
           "1KB당 증가: 텍스트 1개를 128자~256K자로 늘릴 때의 기울기(ms/KB). 둘 다 최소제곱 직선.",
           "- cold 호출: worker가 뜬 뒤 첫 호출(1,024자)의 HTTP 왕복 시간. worker 시작: 프로세스 시작부터 `/health`가 200이 될 때까지.",
           f"- 5초 초과 수: 합성 입력 표본 중 HTTP 왕복이 {meta['env']['timeout_ms']:,}ms(시스템의 `detectorTimeoutMs`)를 넘은 수."]
    md += missing_lines(stats, "synth", "합성 입력")
    md += notes(meta) + [""]

    # p99: 표의 열은 프롬프트대로 두고, 꼬리는 따로 적는다.
    md += ["### 참고: 꼬리 지연 (p99, max)", "", "| 탐지기 | 1KB p99 | 1KB max | 64KB p99 | 64KB max | 셀당 표본 |", "|---|---|---|---|---|---|"]
    for e in stats.values():
        x = e["synth"]
        if x:
            md.append(f"| {e['display']} | {ms(x['1k']['p99'])} | {ms(x['1k']['max'])} | {ms(x['64k']['p99'])} | {ms(x['64k']['max'])} | {x['1k']['n']} |")
    md += [""]

    ranked = adapters_ranked(stats)
    slow = ranked[0][0] if ranked else None
    md += ["## 크기별 곡선", "", f"텍스트 1개짜리 호출의 p50. 가장 느린 어댑터는 1KB p50 기준으로 골랐다({stats[slow]['display'] if slow else '—'}).", "",
           "| 텍스트 크기 | 시스템 앙상블 p50 | 가장 느린 어댑터 p50 |", "|---|---|---|"]
    ens = (stats.get("ensemble") or {}).get("synth")
    slow_curve = stats[slow]["synth"]["curve"] if slow else {}
    sizes = sorted(set((ens or {}).get("curve", {})) | set(slow_curve))
    for size in sizes:
        md.append(f"| {size:,}자 | {ms((ens or {}).get('curve', {}).get(size))} | {ms(slow_curve.get(size))} |")
    if not ens:
        md.append("- 시스템 앙상블: — (" + stats["ensemble"]["why"].get("synth", "측정 없음") + ")")
    md += notes(meta) + [""]

    md += ["## Final Guard 재생", ""]
    guard_any = any(e["guard"] for e in stats.values())
    if guard_any:
        md += ["metric-task 실행에서 기록한 실제 API 요청을, Final Guard가 보냈을 탐지기 호출(캐시에 없는 문자열만 256개씩)로 재생했다. "
               f"요청 시간은 그 요청의 모든 호출 시간(반복 {s['replay_repeat']}번의 중앙값) 합이다.", "",
               "| 탐지기 | 요청 수 | 요청당 p50 | p95 | max | 캐시 통과 요청 수 | 실패·미측정 요청 수 |", "|---|---|---|---|---|---|---|"]
        for e in stats.values():
            g = e["guard"]
            md.append(f"| {e['display']} | {g['requests']} | {ms(g['p50'])} | {ms(g['p95'])} | {ms(g['max'])} | {g['cache_only']} | {g['failed']} / {g['unmeasured']} |"
                      if g else f"| {e['display']} | — | — | — | — | — | — |")
        md += ["", "세션 첫 요청과 나머지 요청:", "", "| 탐지기 | 세션 첫 요청 p50 (요청 수) | 나머지 요청 p50 (요청 수) |", "|---|---|---|"]
        for e in stats.values():
            g = e["guard"]
            if g:
                md.append(f"| {e['display']} | {ms(g['first']['p50'])} ({g['first']['n']}) | {ms(g['rest']['p50'])} ({g['rest']['n']}) |")
        md += ["", "- 실패·미측정은 `실패 / 미측정` 순서. 캐시 통과는 문자열이 있지만 전부 캐시에 있어 탐지기를 부르지 않은 요청."]
        md += missing_lines(stats, "replay", "재생")
        md += notes(meta)
    else:
        md += ["- 하지 못함: " + guard_reason(meta)]
    md += [""]

    md += ["## Native Mod 재생", ""]
    if any(e["recorded"] for e in stats.values()):
        md += ["| 탐지기 | 호출 수 | p50 | p95 | max | 5초 초과 수 |", "|---|---|---|---|---|---|"]
        for e in stats.values():
            r = e["recorded"]
            md.append(f"| {e['display']} | {r['calls']} | {ms(r['p50'])} | {ms(r['p95'])} | {ms(r['max'])} | {r['over']} |"
                      if r else f"| {e['display']} | — | — | — | — | — |")
        md += ["", f"- 실제 훅이 보낸 호출을 순서대로 재생. 호출마다 {s['replay_repeat']}번 반복. p50·p95·max는 `detector_ms`."]
        md += missing_lines(stats, "replay", "재생")
        md += notes(meta)
    else:
        md += ["- 하지 못함: " + recorded_reason(meta)]
    md += [""]
    path.write_text("\n".join(md), encoding="utf-8")


def guard_reason(meta) -> str:
    return next((r for r in meta["skipped"] if r.startswith("Final Guard")), "기록 없음").split(": ", 1)[-1]


def recorded_reason(meta) -> str:
    return next((r for r in meta["skipped"] if r.startswith("Native Mod")), "기록 없음").split(": ", 1)[-1]


def device_line(meta) -> str:
    m = meta["env"]["machine"]
    return f"{m['cpu']} ({m['cpu_count']}스레드), 메모리 {m['memory']}, {m['wsl']}"


def ensemble_timeouts(stats: dict) -> tuple[int | None, int, int]:
    e = stats.get("ensemble") or {}
    parts = [x for x in (e.get("synth"), e.get("guard"), e.get("recorded")) if x]
    if not parts:
        return None, 0, 0
    over = sum(x["over"] for x in parts)
    samples = sum(x["samples"] for x in parts)
    everything = sum(x["over"] for v in stats.values() for x in (v.get("synth"), v.get("guard"), v.get("recorded")) if x)
    return over, samples, everything


def write_readme(meta: dict, stats: dict, path: Path):
    env, s = meta["env"], meta["settings"]
    ens = (stats.get("ensemble") or {}).get("synth")
    ranked = adapters_ranked(stats)
    slow = ranked[0] if ranked else None
    over, samples, everything = ensemble_timeouts(stats)
    md = ["# 탐지 지연 평가 (중간발표)", ""]
    if s["quick"]:
        md += ["> **--quick 점검 실행이다. 반복이 적어 p95·p99가 믿을 만하지 않으니 이 숫자를 발표에 쓰지 않는다.**", ""]
    md += [f"- \"탐지기 호출 한 번에 1KB 텍스트 기준 {ms(ens['1k']['p50']) if ens else '—'}ms(p50), "
           f"64KB 기준 {ms(ens['64k']['p50']) if ens else '—'}ms가 걸리고, 가장 느린 어댑터는 "
           f"{slow[0] if slow else '—'}(1KB {ms(slow[1]) if slow else '—'}ms)이다.\"",
           f"- \"5초 timeout을 넘은 호출은 {over if over is not None else '—'}개다.\"",
           f"  - 시스템 앙상블의 모든 측정 표본 {samples:,}개 기준. 어댑터별·바닥값까지 모든 탐지기를 합치면 {everything}개."]
    g = (stats.get("ensemble") or {}).get("guard")
    if g:
        first, rest = g["first"]["p50"], g["rest"]["p50"]
        if first is not None and rest is not None and first >= rest:
            md.append(f"- \"실제 요청 기준으로 요청 하나당 p50 {ms(g['p50'])}ms, p95 {ms(g['p95'])}ms이고, 세션 첫 요청이 가장 오래 걸린다({ms(first)}ms).\"")
        else:
            md.append(f"- \"실제 요청 기준으로 요청 하나당 p50 {ms(g['p50'])}ms, p95 {ms(g['p95'])}ms이다.\" "
                      f"(세션 첫 요청 p50 {ms(first)}ms가 나머지 {ms(rest)}ms보다 길지 않아 '첫 요청이 가장 오래 걸린다'는 문장은 뺐다.)")
        md.append(f"  - 세션 첫 요청 p50은 {g['first']['n']}개 세션의 첫 요청, 나머지는 {g['rest']['n']}개 요청 기준.")
    md += [""]

    sysgit, datagit = env["system_git"], env["data_git"]
    commit = lambda g_: (f"`{g_['commit'][:7]}`" + (" (커밋 안 된 수정 있음)" if g_["dirty"] else "")) if g_.get("commit") else "—"  # noqa: E731
    cfg = env["config"]
    adapters_desc = []
    for name in env["adapters_on"]:
        tag = " (후보 전용)" if name in env["candidate_only"] else ""
        adapters_desc.append(name + tag)
    others = [l for l in meta["load"] if l["others"]]
    load_line = ("없음 (측정 전후 매번 프로세스를 확인했고, 다른 무거운 작업은 보이지 않았다)" if not others else
                 "있음 — " + "; ".join(f"{l['stage']}: {', '.join(l['others'])}" for l in others))
    if meta.get("forced"):
        load_line += " (--force로 사전 점검을 무시하고 돌렸다)"
    loads = [l["load1"] for l in meta["load"] if l["load1"] is not None]
    seconds = sum(d[k]["seconds"] for d in meta["plan"] for k in ("synth", "replay") if d.get(k))
    versions = {}
    for e in stats.values():
        for a in ((e.get("synth") or {}).get("describe") or {}).get("adapters", []):
            versions.setdefault(a.get("name"), a.get("version"))
    md += ["## 측정 환경", "", "| 항목 | 값 |", "|---|---|",
           f"| 기기 | CPU {env['machine']['cpu']} ({env['machine']['cpu_count']}스레드), 메모리 {env['machine']['memory']} |",
           f"| OS / WSL | {env['machine']['os']} / {env['machine']['wsl']} |",
           f"| 평가한 시스템 커밋 | promptguard-claude-demoV0 {commit(sysgit)} |",
           f"| 평가기 커밋 | promptguard-data {commit(datagit)} |",
           f"| CredSweeper | {versions.get('credsweeper') or env['credsweeper_version'] or '—'} |",
           f"| gitleaks | {env['gitleaks_version'] or versions.get('gitleaks') or '—'} |",
           f"| Python | 탐지기 worker {env['worker_python_version']}, 평가기 {env['evaluator_python_version']} |",
           f"| 탐지기 설정 | `src/detector/detector.json`: 합의 {json.dumps(cfg.get('consensus'), ensure_ascii=False)}, "
           f"candidate_policy {cfg.get('candidate_policy')}, 켜진 어댑터 {', '.join(adapters_desc)}. "
           f"ML 어댑터({', '.join(env['ml_all']) or '없음'})는 뺐다" + (" (기본 설정에서 켜져 있어 끄고 잼)" if env["ml_on_by_default"] else " (기본 설정에서 꺼져 있음)") + " |",
           f"| timeout 기준 | {env['timeout_ms']:,}ms (`promptguard.config.json`의 `detectorTimeoutMs`) |",
           f"| 반복·warmup | 합성 입력: 호출마다 {s['synth_repeat']}번, warmup {s['synth_warmup']}번 (첫 warmup이 cold). "
           f"기록 재생: 호출마다 {s['replay_repeat']}번, warmup {s['replay_warmup']}번 |",
           f"| 측정 중 다른 부하 | {load_line} |",
           f"| 1분 평균 부하 (측정 전후 표본) | 최소 {min(loads) if loads else '—'}, 최대 {max(loads) if loads else '—'} (이 스크립트가 띄운 탐지기 자체의 부하 포함) |",
           f"| 평가기 단위 테스트 | {meta['tests']} |",
           f"| 측정 시간 | {meta['started_at']} ~ {meta.get('finished_at', '—')}, 탐지기 실행 합계 {seconds / 60:.1f}분 |",
           f"| 원본 기록 | `{meta['batch']}` (탐지기별 `calls.jsonl`, `run.json`; 텍스트는 없음) |",
           ""]
    md += ["어댑터별 탐지기를 띄운 방법:", ""]
    for d in meta["plan"]:
        if d.get("how"):
            md.append(f"- {d['display']}: {d['how']}")
    md += ["", "## 하지 못한 측정과 이유", ""]
    missing = list(meta["skipped"])
    for e in stats.values():
        for kind, why in e["why"].items():
            missing.append(f"{e['display']} {'합성 입력' if kind == 'synth' else '기록 재생'}: {why}")
    md += [f"- {m}" for m in missing] if missing else ["- 없음"]
    md += ["", "## 파일", "", "- [latency.md](latency.md): 지연 표", "- [slide_numbers.md](slide_numbers.md): 발표 문서에 넣을 숫자", ""]
    path.write_text("\n".join(md), encoding="utf-8")


def write_slides(meta: dict, stats: dict, path: Path):
    ens = (stats.get("ensemble") or {}).get("synth")
    ranked = adapters_ranked(stats)
    over, samples, _ = ensemble_timeouts(stats)
    g = (stats.get("ensemble") or {}).get("guard")
    guard_cell = f"{ms(g['p50'])}ms / {ms(g['p95'])}ms" if g else "—"
    md = ["# 발표 문서에 넣을 숫자", ""]
    if meta["settings"]["quick"]:
        md += ["> **--quick 점검 실행이다. 발표에 쓰지 않는다.**", ""]
    md += ["| 항목 | 값 |", "|---|---|",
           f"| 탐지기 1KB p50 | {ms(ens['1k']['p50']) + 'ms' if ens else '—'} |",
           f"| 탐지기 64KB p50 | {ms(ens['64k']['p50']) + 'ms' if ens else '—'} |",
           f"| 가장 느린 어댑터와 그 1KB p50 | {f'{ranked[0][0]}, {ms(ranked[0][1])}ms' if ranked else '—'} |",
           f"| 가장 빠른 어댑터와 그 1KB p50 | {f'{ranked[-1][0]}, {ms(ranked[-1][1])}ms' if ranked else '—'} |",
           f"| 5초 timeout 초과 수 | {f'{over}개 (시스템 앙상블, 표본 {samples:,}개 중)' if over is not None else '—'} |",
           f"| Guard 재생 요청당 p50 / p95 | {guard_cell} |",
           f"| 측정 기기 | {device_line(meta)} |", ""]
    md += ["- 탐지기 = 시스템 앙상블(기본 설정). p50은 텍스트 1개짜리 호출의 탐지기 처리 시간."]
    if not ens:
        md.append("- 탐지기 1KB·64KB: — (" + (stats.get("ensemble") or {}).get("why", {}).get("synth", "측정 없음") + ")")
    if not g:
        md.append("- Guard 재생: — (" + ((stats.get("ensemble") or {}).get("why", {}).get("replay") or guard_reason(meta)) + ")")
    md += [""]
    path.write_text("\n".join(md), encoding="utf-8")


def write_reports(meta: dict, out: Path):
    stats = collect(meta)
    out.mkdir(parents=True, exist_ok=True)
    write_readme(meta, stats, out / "README.md")
    write_latency_md(meta, stats, out / "latency.md")
    write_slides(meta, stats, out / "slide_numbers.md")
    Path(meta["batch"], "midterm_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    # 평가기 자체 보고서(전체 표)도 원본 기록 폴더에 남긴다.
    runs = [d[k]["dir"] for d in meta["plan"] for k in ("synth", "replay") if d.get(k) and not d[k].get("invalid")]
    if runs:
        subprocess.run([sys.executable, str(HERE / "m4.py"), "report", *runs, "--out", str(Path(meta["batch"], "m4_report"))],
                       cwd=meta["env"]["data_root"], capture_output=True)
    return stats


# ---- main ----------------------------------------------------------------------------------------------------

def run_tests(data: Path) -> str:
    say("[2] 평가기 단위 테스트")
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "metric-latency/tests"],
                          cwd=data, capture_output=True, text=True)
    tail = (proc.stderr or proc.stdout).strip().splitlines()
    summary = next((line for line in reversed(tail) if line.startswith("Ran ")), "")
    if proc.returncode != 0:
        say("\n".join(tail[-15:]))
        raise SystemExit("[중단] 평가기 단위 테스트가 실패했다. 측정하지 않는다.")
    say(f"   통과 ({summary})")
    return f"통과 ({summary})"


def main(argv=None):
    p = argparse.ArgumentParser(description="중간발표용 탐지 지연 평가를 한 번에 돌리고 report/latency/를 만든다")
    p.add_argument("--data-root", default=str(DATA_ROOT), help="promptguard-data 체크아웃 (기본: 이 스크립트가 든 저장소)")
    p.add_argument("--system-root", help=f"promptguard-claude-demoV0 체크아웃 (기본 ${SYSTEM_ENV}, 없으면 promptguard-data 옆)")
    p.add_argument("--python", help="탐지기 worker를 돌릴 Python (기본: 시스템 체크아웃의 .venv)")
    p.add_argument("--out", default="report/latency", help="결과물 폴더 (기본: 지금 폴더 아래 report/latency)")
    p.add_argument("--runs-dir", help="원본 기록을 둘 폴더 (기본: promptguard-data/runs/metric-latency)")
    p.add_argument("--guard", nargs="+", metavar="PATH", help=f"Final Guard 재생 기록 (기본: promptguard-data/{GUARD_DEFAULT.as_posix()})")
    p.add_argument("--recorded", nargs="+", metavar="PATH", help=f"Native Mod 재생 기록 (기본: promptguard-data/{RECORDED_SEARCH.as_posix()} 아래에서 찾음)")
    p.add_argument("--skip-guard", action="store_true")
    p.add_argument("--skip-recorded", action="store_true")
    p.add_argument("--synth-repeat", type=int, default=50, help="합성 입력 호출마다 반복 (기본 50 → 셀당 100표본)")
    p.add_argument("--synth-warmup", type=int, default=10, help="합성 입력 측정 전 버리는 호출 (기본 10, 첫 호출은 cold로 따로 기록)")
    p.add_argument("--replay-repeat", type=int, default=5, help="기록 재생 호출마다 반복 (기본 5)")
    p.add_argument("--replay-warmup", type=int, default=3)
    p.add_argument("--quick", action="store_true", help="반복을 줄인 점검 실행 (발표용 숫자 아님)")
    p.add_argument("--wait", type=float, default=0, help="다른 무거운 작업이 끝나길 최대 몇 분 기다릴지 (기본 0: 바로 중단)")
    p.add_argument("--force", action="store_true", help="다른 작업이 보여도 측정한다 (README에 남는다)")
    p.add_argument("--report-only", metavar="BATCH", help="이미 측정한 기록 폴더로 결과물만 다시 만든다")
    args = p.parse_args(argv)
    out = Path(args.out).resolve()

    if args.report_only:
        meta = json.loads(Path(args.report_only, "midterm.json").read_text(encoding="utf-8"))
        write_reports(meta, out)
        say(f"결과물: {out}")
        return

    if args.quick:
        args.synth_repeat, args.synth_warmup, args.replay_repeat, args.replay_warmup = 2, 2, 1, 1

    say("[1] 사전 점검")
    env = preflight(args)
    first_load = wait_until_quiet(args)
    say(f"   기기: {env['machine']['cpu']}, {env['machine']['memory']}, {env['machine']['wsl']}")
    say(f"   시스템 {env['system_git'].get('commit', '?')[:7]}, 켜진 어댑터: {', '.join(env['adapters_on'])}"
        + (f" (ML {', '.join(env['ml_on_by_default'])}는 끄고 잼)" if env["ml_on_by_default"] else ""))
    say(f"   CredSweeper {env['credsweeper_version']}, gitleaks {env['gitleaks_version']}, worker Python {env['worker_python_version']}")

    data = Path(env["data_root"])
    tests = run_tests(data)
    runs_dir = Path(args.runs_dir).resolve() if args.runs_dir else data / "runs" / "metric-latency"
    batch = runs_dir / ("midterm_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ("_quick" if args.quick else ""))
    batch.mkdir(parents=True)
    guard, recorded, skipped = replay_inputs(args, data)
    for reason in skipped:
        say("   건너뜀:", reason)
    meta = {"started_at": now(), "batch": str(batch), "out": str(out), "env": env, "tests": tests,
            "forced": bool(args.force and first_load["others"]), "load": [first_load],
            "settings": {"synth_repeat": args.synth_repeat, "synth_warmup": args.synth_warmup,
                         "replay_repeat": args.replay_repeat, "replay_warmup": args.replay_warmup, "quick": args.quick},
            "guard": guard, "recorded": recorded, "skipped": skipped}
    meta["plan"] = plan_detectors(env, batch)
    save_meta(meta)

    say(f"[3] 측정 — 탐지기 {len(meta['plan'])}개: {', '.join(d['display'] for d in meta['plan'])}")
    measure_all(meta, args)
    meta["finished_at"] = now()
    save_meta(meta)

    say("[4] 결과물 작성")
    stats = write_reports(meta, out)
    ens = (stats.get("ensemble") or {}).get("synth")
    if ens:
        say(f"   시스템 앙상블 1KB p50 {ms(ens['1k']['p50'])}ms, 64KB p50 {ms(ens['64k']['p50'])}ms")
    say(f"결과물: {out}")
    say(f"원본 기록: {batch}")


if __name__ == "__main__":
    main()
