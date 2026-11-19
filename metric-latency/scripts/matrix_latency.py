"""Latency of one PromptGuard detector call on a 4 KB text, for every cell of the CredData-trajectory matrix.

The matrix (commits, models, publish rule, configured copies) is metric-detection/scripts/creddata_matrix.py; this
script imports it, so the two cannot drift. Each cell is one subprocess: it loads the checkout's detector the way the
scorer does (`system_root.load_worker(root).load_detector()`), warms it up, then times `detector.scan(text, source)`
alone, once per text. The prototype row is the scorer's CredSweeper adapter with ML off (`CredSweeperAdapter(ml=False)
.detect(text)`). No Mod, no HTTP, no gitleaks cache: gitleaks runs per call, as in the system.

  python metric-latency/scripts/matrix_latency.py setup [--venv DIR --torch cpu|cuda|default]
  python metric-latency/scripts/matrix_latency.py bundles --drive-runs DIR --out DIR
  python metric-latency/scripts/matrix_latency.py run [--out DIR] [--cells 668c2c1/v10 prototype] [--calls 1000]
                                                       [--device cpu|cuda|mps|auto] [--token-bundles DIR] [--dry-run]
  python metric-latency/scripts/matrix_latency.py report OUT_DIR

Output (default metric-latency/results/creddata-matrix-<timestamp>/): cells/<cell>.json per cell (every timing,
no text), run.json (settings, hardware), summary.md and summary.csv. Only the two summaries go into git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "metric-detection"))
sys.path.insert(0, str(ROOT / "metric-detection" / "scripts"))

import m4  # noqa: E402  (nearest-rank quantile, the metric-latency convention)
import m4_workloads as wl  # noqa: E402  (synthetic log/code/secret texts)
from evaluation.adapters.promptguard_adapter import CHANNEL_MAP, _WARMUP_TEXT  # noqa: E402

TEXT_BYTES = 4096
PERCENTILES = (50, 90, 95, 99)
PROTOTYPE = "prototype"
PROTOTYPE_LABEL = "프로토타입: CredSweeper만, ML 꺼짐"
EVAL_SET = ROOT / "metric-detection/data_test/sessions_from_CredData-trajectory.jsonl"
EVAL_SET_SHA256 = "2c856d91c0aa8cde7dde7964865db0697e2f319c8ac0f89539e447f91ac60e3c"  # RUN_NOTES.md
DEFAULT_WORK = ROOT / "runs/metric-latency/creddata-matrix-work"
SYSTEM_URL = "https://github.com/capstone-privai/promptguard-claude-demoV0"
MODEL_URL = "https://github.com/capstone-privai/promptguard-model"
MODEL_COMMIT = "1619e76bd9cfb62cd1f81628add8b35e359e9675"
GITLEAKS_VERSION = "8.30.1"
CREDSWEEPER_VERSION = "1.19.0"
# model.safetensors sha256 per matrix model: repository models at MODEL_COMMIT, token bundles from RUN_NOTES.md
WEIGHTS_SHA256 = {
    "v10": "027fd9f24ed72643d76a804d9be50d0448b8da2bed085f61ccbd5400d15b6aa0",
    "pilot-b-seed110": "bd7835235d8988bdbc3e369f959074ccf52b689c9ec8f1d8292826fe6f2e744b",
    "pilot-b-seed112": "a6600fb69f8d5ab01b7a8f005410c406911675eeafbcfbed9a2c585e042e1cc5",
    "pilot-bv10-seed112": "e3e4b9f8bf10c78e5c273d4f04a5965e51f830c0329fa906b5e8e4cd0890d681",
    "mmbert-traj": "75373e30b8cba90a76a7b219147e04d625488e3e40b3e2f42c053d4cd67f80e9",
    "qwen-traj": "e2400a76d5d01cfb26b63e83bc75d3350af5b1beeb6a2c490472067786a91e84",
}
TOKEN_BUNDLES = ("mmbert-traj", "qwen-traj")
# The Drive training output the two bundles are built from (runs/creddata-traj-colab/build_bundles.py on Colab):
# name -> (Drive folder, epoch, cutoff, bundle folder, sha256 of the epoch folder's files)
BUNDLE_SOURCES = {
    "mmbert-traj": ("token-span-creddata-mmbert", 1, 0.720, "token-span-creddata-mmbert", {
        "config.json": "5556abda07a42e7425228ca15c0ca342e8da3e4e00dfab58ebaf6bc93aaaa032",
        "model.safetensors": "75373e30b8cba90a76a7b219147e04d625488e3e40b3e2f42c053d4cd67f80e9",
        "special_tokens_map.json": "6e3204c5a4004719c185007a745d1940471a6fb02521cfa0a00306dbb6bc5903",
        "tokenizer.json": "ac6fc8196d1db9ef82e68f6088e8d77d711b8c6f07589cec7d9d59c4adfc9a1e",
        "tokenizer_config.json": "3b66ca84514d9aacf4b90c65a61e561127c6c21d81bbf4e8ba9d46a4c15ac82d"}),
    "qwen-traj": ("token-span-creddata-qwen", 3, 0.914, "token-span-creddata-qwen", {
        "adapter_config.json": "51b8d3f81f9a9e86851fd9828f506cf924dd7985a49fc9af4e7c583b0edd2a37",
        "adapter_model.safetensors": "51541b055492d9b0a16e4954f3ec25fed0471182a3e4904dad2036afe9645f93",
        "added_tokens.json": "58b54bbe36fc752f79a24a271ef66a0a0830054b4dfad94bde757d851968060b",
        "chat_template.jinja": "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f",
        "merges.txt": "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
        "special_tokens_map.json": "76862e765266b85aa9459767e33cbaf13970f327a0e88d1c65846c2ddd3a1ecd",
        "tokenizer.json": "79b47f69e24c09858c3fc2abf46de8496aeabc866e2933a3bee21b75d7ccddcb",
        "tokenizer_config.json": "60bf17d6543b028dbd97ac7f4847418c96502006b80b4b1c57427c241c818224",
        "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"}),
}
REQUIREMENTS = ["credsweeper==1.19.0", "transformers==4.57.6", "peft==0.21.2", "tokenizers==0.22.2",
                "safetensors==0.8.0", "huggingface_hub==0.36.2", "numpy==2.5.4", "PyYAML==6.0.3",
                "scikit-learn==1.9.1", "psutil"]
TORCH = "torch==2.14.1"
TORCH_INDEX = {"cpu": "https://download.pytorch.org/whl/cpu", "cuda": "https://download.pytorch.org/whl/cu130"}


def say(*args):
    print(*args, file=sys.stderr, flush=True)


def matrix_module(token_bundles: str | None = None):
    """creddata_matrix, with its token-bundle folder taken from --token-bundles ($MATRIX_BUNDLES otherwise)."""
    if token_bundles:
        os.environ["MATRIX_BUNDLES"] = str(Path(token_bundles).resolve())
    import creddata_matrix
    return creddata_matrix


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---- workload (pure) ---------------------------------------------------------------------------------------

def cut_utf8(data: bytes, size: int = TEXT_BYTES) -> str:
    """The first `size` bytes as text: a code point cut at the end is dropped and replaced by spaces, so the
    result is exactly `size` bytes of UTF-8."""
    text = data[:size].decode("utf-8", errors="ignore")
    return text + " " * (size - len(text.encode("utf-8")))


def eval_windows(path: Path, count: int, seed: int = 0, size: int = TEXT_BYTES) -> tuple[list[tuple[str, str]], dict]:
    """`count` windows of `size` bytes from the scored channels (prompt, instructions, tool_output) of a session
    file, each starting at a line start of an item at least `size` bytes long. Seeded; the same arguments give the
    same windows in the same order. Returns [(text, source)], where source is what the mod scans the channel as."""
    items = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            for item in json.loads(line).get("items", []):
                if item.get("channel") in CHANNEL_MAP:
                    data = item["text"].encode("utf-8")
                    if len(data) >= size:
                        starts = [0] + [m.end() for m in re.finditer(b"\n", data) if len(data) - m.end() >= size]
                        items.append((data, CHANNEL_MAP[item["channel"]], starts))
    if not items:
        raise ValueError(f"no scored-channel item of {size} bytes or more in {path}")
    rng = random.Random(f"matrix-latency:{seed}")
    used, out = set(), []
    for _ in range(count):
        for _attempt in range(50):
            index = rng.randrange(len(items))
            data, source, starts = items[index]
            start = rng.choice(starts)
            if (index, start) not in used:
                break
        used.add((index, start))
        out.append((cut_utf8(data[start:], size), source))
    return out, {"kind": "creddata-trajectory", "file": path.name, "eligible_items": len(items),
                 "distinct_windows": len(used)}


def synthetic_texts(count: int, seed: int = 0, size: int = TEXT_BYTES, prefix: str = "") -> list[tuple[str, str]]:
    """m4's synthetic log/code text with about one secret-like line per 20 lines (ASCII, so `size` chars = bytes),
    scanned as tool output."""
    return [(wl.synth_text(size, "secrets", f"{prefix}{seed}:{i}"), "tool_result") for i in range(count)]


def fingerprint(texts: list[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for text, source in texts:
        h.update(source.encode() + b"\0" + text.encode("utf-8") + b"\0")
    return h.hexdigest()


def build_workload(kind: str, count: int, seed: int, eval_set: Path = EVAL_SET) -> tuple[list[tuple[str, str]], dict]:
    if kind == "auto":
        kind = "creddata" if eval_set.is_file() else "synthetic"
    if kind == "creddata":
        texts, info = eval_windows(eval_set, count, seed)
        info["file_sha256"] = sha256_file(eval_set)
        info["file_sha256_matches_run_notes"] = info["file_sha256"] == EVAL_SET_SHA256
    else:
        texts, info = synthetic_texts(count, seed), {"kind": "synthetic", "generator": "m4_workloads.synth_text secrets"}
    info.update(count=count, seed=seed, bytes_per_text=TEXT_BYTES, fingerprint=fingerprint(texts))
    return texts, info


def percentiles(values: list[float]) -> dict:
    return {f"p{p}": m4.quantile(values, p / 100) for p in PERCENTILES}


# ---- cells and table (pure) --------------------------------------------------------------------------------

def cell_key(commit: str, model: str) -> str:
    return PROTOTYPE if commit == PROTOTYPE else f"{commit}/{model}"


def matrix_cells(found: list[dict]) -> list[dict]:
    """Prototype first, then every commit (oldest first) with each configuration the matrix gives it."""
    cells = [{"key": PROTOTYPE, "commit": PROTOTYPE, "model": "base", "sha": None}]
    for commit in found:
        for model in commit["models"]:
            cells.append({"key": cell_key(commit["sha"][:7], model), "commit": commit["sha"][:7], "model": model,
                          "sha": commit["sha"]})
    return cells


def select_cells(cells: list[dict], tokens: list[str] | None) -> list[dict]:
    """Tokens: `prototype`, a commit prefix (all its cells), `COMMIT/MODEL`, or `*/MODEL` (that model everywhere)."""
    if not tokens:
        return cells

    def match(cell, token):
        if token == PROTOTYPE:
            return cell["commit"] == PROTOTYPE
        commit, _, model = token.partition("/")
        if cell["commit"] == PROTOTYPE:
            return False
        return (commit == "*" or cell["sha"].startswith(commit)) and (not model or model == cell["model"])

    unknown = [t for t in tokens if not any(match(c, t) for c in cells)]
    if unknown:
        raise ValueError(f"not in the matrix: {', '.join(unknown)}")
    return [c for c in cells if any(match(c, t) for t in tokens)]


def cell_file(key: str) -> str:
    return key.replace("/", "__") + ".json"


def fmt_ms(value) -> str:
    if value is None:
        return "?"
    return f"{value:.1f}" if value >= 10 else f"{value:.2f}"


def cell_text(record: dict | None) -> str:
    if record is None:
        return "(not run)"
    if record.get("status") != "ok":
        return f"({record.get('status', '?')})"
    p = record["latency_ms"]
    return " / ".join(fmt_ms(p[f"p{q}"]) for q in PERCENTILES)


def table(found: list[dict], models: list[str], records: dict[str, dict], meta: dict | None = None) -> str:
    """summary.md: rows are the prototype and the systems in date order, columns base + models; a cell is
    p50 / p90 / p95 / p99 in ms, `-` where the matrix has no such combination."""
    lines = ["# CredData-trajectory 행렬: 탐지기 호출 1회 지연 (4 KB 입력)", "",
             "칸마다 p50 / p90 / p95 / p99, 단위 ms(nearest rank). 호출 하나는 `detector.scan(text, source)` 한 번이다"
             "(프로토타입은 채점기의 CredSweeper 어댑터 `detect`). `-`는 행렬에 없는 조합, `(skipped)`는 모델이 없어 건너뛴 칸, "
             "`(failed)`는 실패한 칸이다.", ""]
    if meta:
        hw = meta.get("hardware", {})
        work = meta.get("workload", {})
        lines += [f"- 기기: {hw.get('cpu_model')}, 코어 {hw.get('physical_cores')}개(논리 {hw.get('logical_cpus')}개), "
                  f"RAM {hw.get('ram_gb')} GB, GPU {hw.get('gpu') or '없음'}, {hw.get('os')}",
                  f"- Python {hw.get('python')}, torch {hw.get('torch')}, transformers {hw.get('transformers')}, "
                  f"credsweeper {hw.get('credsweeper')}, gitleaks {hw.get('gitleaks')}",
                  f"- 입력: {work.get('kind')} {work.get('count')}개 × {work.get('bytes_per_text')} bytes, seed "
                  f"{work.get('seed')}, 지문 `{str(work.get('fingerprint'))[:12]}`; warmup {meta.get('warmup')}회; "
                  f"ML 장치 {meta.get('device')}", ""]
    lines += ["| 시스템 | 날짜 | " + " | ".join(models) + " |", "|---|---|" + "---:|" * len(models)]
    rows = [(PROTOTYPE, "", PROTOTYPE_LABEL, ["base"])] + [
        (c["sha"][:7], c["date"], c["subject"].split(" from ")[0].replace("Merge pull request ", ""), c["models"])
        for c in found]
    for commit, date, label, present in rows:
        cells = [cell_text(records.get(cell_key(commit, m))) if m in present else "-" for m in models]
        lines.append(f"| {commit} {label} | {date} | " + " | ".join(cells) + " |")
    failed_calls = [f"{key} {r['failed_calls']}/{r['calls']}" for key, r in records.items()
                    if r.get("status") == "ok" and r.get("failed_calls")]
    notes = [f"{key}: {r.get('reason')}" for key, r in records.items() if r.get("status") in ("skipped", "failed")]
    lines.append("")
    if failed_calls:
        lines += ["탐지기가 실패를 돌려준 호출(시스템이라면 막혔을 것, 시간은 표에 포함): " + ", ".join(failed_calls), ""]
    if notes:
        lines += ["건너뛰거나 실패한 칸:", "", *[f"- {n}" for n in notes], ""]
    return "\n".join(lines)


CSV_FIELDS = ["cell", "commit", "date", "model", "ml_adapter", "device", "status", "reason", "calls", "failed_calls",
              "p50_ms", "p90_ms", "p95_ms", "p99_ms", "mean_ms", "min_ms", "max_ms", "load_seconds", "workload"]


def csv_rows(found: list[dict], records: dict[str, dict]) -> list[dict]:
    dates = {c["sha"][:7]: c["date"] for c in found}
    rows = []
    for cell in matrix_cells(found):
        r = records.get(cell["key"])
        if r is None:
            continue
        lat = r.get("latency_ms") or {}
        rows.append({"cell": cell["key"], "commit": cell["commit"], "date": dates.get(cell["commit"], ""),
                     "model": cell["model"], "ml_adapter": r.get("ml_adapter") or "", "device": r.get("device") or "",
                     "status": r.get("status"), "reason": r.get("reason") or "", "calls": r.get("calls"),
                     "failed_calls": r.get("failed_calls"),
                     **{f"p{q}_ms": lat.get(f"p{q}") for q in PERCENTILES},
                     **{f"{k}_ms": lat.get(k) for k in ("mean", "min", "max")},
                     "load_seconds": r.get("load_seconds"), "workload": (r.get("workload") or {}).get("kind")})
    return rows


# ---- hardware ------------------------------------------------------------------------------------------------

def _run(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def gitleaks_version() -> str | None:
    if not shutil.which("gitleaks"):
        return None
    return _run("gitleaks", "version").lstrip("v") or "unknown"


def hardware() -> dict:
    info = {"os": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "logical_cpus": os.cpu_count(), "physical_cores": None, "cpu_model": None, "ram_gb": None, "gpu": None}
    system = platform.system()
    if system == "Linux":
        cpuinfo = Path("/proc/cpuinfo").read_text(errors="ignore") if Path("/proc/cpuinfo").is_file() else ""
        found = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.M)
        info["cpu_model"] = found.group(1).strip() if found else (
            re.search(r"Model name:\s*(.+)", _run("lscpu")) or [None, None])[1]
        mem = re.search(r"MemTotal:\s*(\d+)", Path("/proc/meminfo").read_text()) if Path("/proc/meminfo").is_file() else None
        if mem:
            info["ram_gb"] = round(int(mem.group(1)) / 2**20, 1)
    elif system == "Darwin":
        info["cpu_model"] = _run("sysctl", "-n", "machdep.cpu.brand_string") or None
        mem = _run("sysctl", "-n", "hw.memsize")
        info["ram_gb"] = round(int(mem) / 2**30, 1) if mem.isdigit() else None
        cores = _run("sysctl", "-n", "hw.physicalcpu")
        info["physical_cores"] = int(cores) if cores.isdigit() else None
    elif system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            info["cpu_model"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            info["cpu_model"] = platform.processor() or None
        try:
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            status = Status()
            status.length = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            info["ram_gb"] = round(status.total / 2**30, 1)
        except (OSError, AttributeError):
            pass
    try:
        import psutil
        info["physical_cores"] = info["physical_cores"] or psutil.cpu_count(logical=False)
        info["ram_gb"] = info["ram_gb"] or round(psutil.virtual_memory().total / 2**30, 1)
    except ImportError:
        pass
    if info["physical_cores"] is None and system == "Linux":
        pairs = set(re.findall(r"physical id\s*:\s*(\d+)\n(?:.*\n)*?core id\s*:\s*(\d+)", cpuinfo))
        info["physical_cores"] = len(pairs) or None
    for name in ("torch", "transformers", "credsweeper", "peft"):
        try:
            module = __import__(name)
            info[name] = getattr(module, "__version__", "?")
        except ImportError:
            info[name] = None
    try:
        import torch
        info["torch_threads"] = torch.get_num_threads()
        info["torch_cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            info["gpu"] = ", ".join(torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count()))
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["gpu"] = "Apple MPS"
    except ImportError:
        pass
    if not info["gpu"] and shutil.which("nvidia-smi"):
        info["gpu"] = _run("nvidia-smi", "--query-gpu=name", "--format=csv,noheader").replace("\n", ", ") or None
        info["gpu_note"] = "torch does not see this GPU"
    info["gitleaks"] = gitleaks_version()
    return info


# ---- one cell, in its own process ----------------------------------------------------------------------------

def measure_cell(spec: dict) -> dict:
    """Load the detector, warm it up, time one call per workload text. Runs in the cell's subprocess."""
    texts, workload = build_workload(spec["workload"], spec["calls"], spec["seed"])
    if workload["fingerprint"] != spec["fingerprint"]:
        raise RuntimeError("the workload differs from the parent's")
    warmup = synthetic_texts(spec["warmup"], spec["seed"], prefix="warmup:")
    started = time.perf_counter()
    out = {"device": spec.get("device"), "ml_adapter": spec.get("ml_adapter")}
    if spec["kind"] == PROTOTYPE:
        import credsweeper
        if credsweeper.__version__ != CREDSWEEPER_VERSION:
            raise RuntimeError(f"credsweeper {credsweeper.__version__} is installed, not {CREDSWEEPER_VERSION}")
        from evaluation.adapters.credsweeper_adapter import CredSweeperAdapter
        adapter = CredSweeperAdapter(ml=False)  # its constructor scans a warmup text, as in the scorer
        out["detector"] = adapter.describe()

        def call(text, _source):
            return {"ok": True, "findings": adapter.detect(text)}
    else:
        if os.environ.get("PG_DETECTOR_MODE", "normal") != "normal":
            raise RuntimeError("unset PG_DETECTOR_MODE; the worker would inject faults")
        from evaluation.adapters.system_root import load_worker
        detector = load_worker(spec["root"]).load_detector()
        info = detector.describe()
        running = [a["name"] for a in info["adapters"]]
        ml = [name for name in running if name.startswith("ml-")]
        expected = [spec["ml_adapter"]] if spec["ml_adapter"] else []
        if ml != expected:
            raise RuntimeError(f"ML adapters running: {ml}, expected {expected}; skipped: {info.get('skipped')}")
        if "gitleaks" in spec["configured"] and "gitleaks" not in running:
            raise RuntimeError(f"gitleaks is configured but not running: {info.get('skipped')}")
        for adapter in detector.adapters:
            if adapter.name.startswith("ml-"):
                model = getattr(adapter, "model", None)
                out["ml"] = {"name": adapter.name, "model_id": getattr(adapter, "model_id", None),
                             "timeout": getattr(adapter, "timeout", None), "device": str(getattr(model, "device", None))}
                if spec["device"] not in (None, "auto") and not out["ml"]["device"].startswith(spec["device"]):
                    raise RuntimeError(f"{adapter.name} runs on {out['ml']['device']}, not {spec['device']}")
        out["detector"] = {"adapters": running, "skipped": info.get("skipped"),
                           "versions": {a["name"]: a.get("version") for a in info["adapters"]}}
        detector.scan(_WARMUP_TEXT, "warmup")  # as the scorer's adapter does
        call = detector.scan
    for text, source in warmup:
        call(text, source)
    out["load_seconds"] = round(time.perf_counter() - started, 3)
    timings, failed, findings, errors = [], 0, [], {}
    clock = time.perf_counter_ns
    for text, source in texts:
        error = None
        begin = clock()
        try:
            result = call(text, source)
        except Exception as exc:  # noqa: BLE001 - the worker answers any exception with HTTP 500: a failed call
            result, error = None, type(exc).__name__
        end = clock()
        timings.append((end - begin) / 1e6)
        if error is None:
            ok = isinstance(result, dict) and result.get("ok") is True and not result.get("errors")
            if not ok:
                error = ";".join(str(e)[:60] for e in (result or {}).get("errors") or []) or "not ok"
        if error:
            failed += 1
            errors[error] = errors.get(error, 0) + 1
        findings.append(len((result or {}).get("findings") or []))
    out.update(status="ok", calls=len(timings), failed_calls=failed, errors=errors,
               latency_ms={**percentiles(timings), "mean": sum(timings) / len(timings), "min": min(timings),
                           "max": max(timings)},
               findings_per_call={"mean": sum(findings) / len(findings), "max": max(findings)},
               timings_ms=[round(t, 4) for t in timings])
    return out


def cmd_cell(args):
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    result = measure_cell(spec)
    Path(args.result).write_text(json.dumps(result), encoding="utf-8")


def cmd_hardware(_args):
    print(json.dumps(hardware()))


# ---- run -------------------------------------------------------------------------------------------------------

def child_env() -> dict:
    """The parent environment without PG_* variables, so nothing outside detector.json changes the detector."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PG_")}


def configured_adapters(cm, sha: str) -> list[str]:
    config = json.loads(cm.git(cm.SYSTEM_REPO, "show", f"{sha}:src/detector/detector.json"))
    return [a["name"] for a in config.get("adapters", []) if a.get("enabled", True) is not False]


def model_check(cm, model: str, check: bool, cache: dict) -> tuple[str | None, dict]:
    """None if the cell's model is usable, else why not. Token bundles that are missing or differ are skipped."""
    folder = cm.model_folder(model)
    weights = folder / "model.safetensors"
    bundle = model in TOKEN_BUNDLES
    if not weights.is_file() or (bundle and not (folder / "span_bundle.json").is_file()):
        hint = "see metric-latency/README.md (토큰 분류기 bundle)" if bundle else "run setup (git lfs pull)"
        return ("skipped" if bundle else "failed", {"reason": f"model missing: {folder}; {hint}"})
    if str(weights) not in cache:
        cache[str(weights)] = sha256_file(weights)
    identity = {"path": str(folder), "weights_sha256": cache[str(weights)]}
    if check and identity["weights_sha256"] != WEIGHTS_SHA256[model]:
        return ("skipped" if bundle else "failed",
                {"reason": f"model.safetensors sha256 {identity['weights_sha256'][:12]} is not the expected "
                           f"{WEIGHTS_SHA256[model][:12]} ({'rebuild the bundle' if bundle else 'git lfs pull at ' + MODEL_COMMIT[:7]})",
                 **identity})
    return None, identity


def write_json(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load_records(out: Path) -> dict[str, dict]:
    records = {}
    for path in sorted((out / "cells").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        records[record["cell"]] = record
    return records


def write_report(cm, out: Path):
    found = cm.commits()
    records = load_records(out)
    meta = json.loads((out / "run.json").read_text(encoding="utf-8")) if (out / "run.json").is_file() else None
    (out / "summary.md").write_text(table(found, ["base", *cm.MODELS], records, meta), encoding="utf-8")
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows(found, records))
    say(f"{len(records)} cells -> {out / 'summary.md'}")


def apply_repos(cm, args):
    if args.system_repo:
        cm.SYSTEM_REPO = Path(args.system_repo).resolve()
    if args.model_repo:
        cm.MODEL_REPO = Path(args.model_repo).resolve()
    cm.WORK = Path(args.work).resolve()  # configured copies go here, not into the matrix's work folder


def cmd_run(args):
    cm = matrix_module(args.token_bundles)
    apply_repos(cm, args)
    out = Path(args.out) if args.out else ROOT / "metric-latency/results" / datetime.now().strftime("creddata-matrix-%Y%m%d-%H%M%S")
    found = cm.commits()
    cells = select_cells(matrix_cells(found), args.cells)
    texts, workload = build_workload(args.workload, args.calls, args.seed)
    del texts
    gitleaks = gitleaks_version()
    needs_pg = any(c["commit"] != PROTOTYPE for c in cells)
    gitleaks_problem = None
    if needs_pg and gitleaks is None:
        gitleaks_problem = f"gitleaks is not on PATH; install gitleaks {GITLEAKS_VERSION}"
    elif needs_pg and gitleaks != GITLEAKS_VERSION:
        gitleaks_problem = f"gitleaks {gitleaks} is on PATH, not {GITLEAKS_VERSION}"
    done = load_records(out) if (out / "cells").is_dir() else {}
    if args.dry_run:
        print(f"out: {out}\nworkload: {workload['kind']} x{workload['count']} ({workload['fingerprint'][:12]})"
              f"\ngitleaks: {gitleaks or 'MISSING'}  ML device: {args.device}  token bundles: {cm.BUNDLES}")
        if gitleaks_problem:
            print(f"PROBLEM: {gitleaks_problem}")
        cache = {}
        for cell in cells:
            state = "done" if done.get(cell["key"], {}).get("status") == "ok" else "run"
            if state == "run" and cell["model"] in TOKEN_BUNDLES:
                problem, identity = model_check(cm, cell["model"], not args.no_model_check, cache)
                state = f"{problem}: {identity['reason']}" if problem else state
            print(f"{cell['key']:<28} {state}")
        print(f"{len(cells)} cells")
        return
    if gitleaks_problem:
        raise SystemExit(gitleaks_problem)
    (out / "cells").mkdir(parents=True, exist_ok=True)
    settings = {"calls": args.calls, "warmup": args.warmup, "seed": args.seed, "device": args.device,
                "workload": workload}
    if (out / "run.json").is_file():
        previous = json.loads((out / "run.json").read_text(encoding="utf-8"))
        if {k: previous.get(k) for k in settings} != settings:
            raise SystemExit(f"{out} was started with other settings (calls, warmup, seed, device or workload); "
                             "use another --out")
    hw = json.loads(subprocess.run([args.python, __file__, "_hardware"], capture_output=True, text=True, check=True,
                                   env=child_env()).stdout)
    meta = {**settings, "python_executable": args.python, "hardware": hw, "system_repo": str(cm.SYSTEM_REPO),
            "model_repo": str(cm.MODEL_REPO), "model_repo_commit": cm.git(cm.MODEL_REPO, "rev-parse", "HEAD").decode().strip(),
            "token_bundles": str(cm.BUNDLES), "started_at": datetime.now().isoformat(timespec="seconds"),
            "argv": sys.argv[1:]}
    write_json(out / "run.json", meta)
    if meta["model_repo_commit"] != MODEL_COMMIT:
        say(f"warning: the model repository is at {meta['model_repo_commit'][:7]}, not {MODEL_COMMIT[:7]}")
    logs = Path(args.work) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    dates = {c["sha"][:7]: c for c in found}
    cache = {}
    for cell in cells:
        target = out / "cells" / cell_file(cell["key"])
        if done.get(cell["key"], {}).get("status") == "ok":
            say(f"{cell['key']}: done")
            continue
        record = {"cell": cell["key"], "commit": cell["commit"], "sha": cell["sha"], "model": cell["model"],
                  "date": dates[cell["commit"]]["date"] if cell["sha"] else None, "workload": workload,
                  "warmup": args.warmup, "gitleaks": gitleaks}
        spec = {"kind": PROTOTYPE if cell["commit"] == PROTOTYPE else "promptguard", "calls": args.calls,
                "warmup": args.warmup, "seed": args.seed, "workload": workload["kind"].replace("creddata-trajectory", "creddata"),
                "fingerprint": workload["fingerprint"], "device": None, "ml_adapter": None}
        try:
            if spec["kind"] != PROTOTYPE:
                if cell["model"] != "base":
                    problem, identity = model_check(cm, cell["model"], not args.no_model_check, cache)
                    record["model_identity"] = identity
                    if problem:
                        record.update(status=problem, reason=identity["reason"])
                        write_json(target, record)
                        say(f"{cell['key']}: {problem}: {identity['reason']}")
                        continue
                commit = dates[cell["commit"]]
                root, wanted = cm.checkout(commit, cell["model"], args.device if cell["model"] != "base" else None)
                spec.update(root=str(root), ml_adapter=wanted, device=args.device if wanted else None,
                            configured=configured_adapters(cm, commit["sha"]))
                record["detector_json_sha256"] = sha256_file(root / "src/detector/detector.json")
            spec_path = Path(args.work) / "logs" / (cell_file(cell["key"])[:-5] + ".spec.json")
            result_path = spec_path.with_name(spec_path.name.replace(".spec.", ".result."))
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            result_path.unlink(missing_ok=True)
            say(f"{cell['key']}: measuring {args.calls} calls")
            started = time.time()
            with (logs / (cell_file(cell["key"])[:-5] + ".log")).open("w", encoding="utf-8") as log:
                proc = subprocess.run([args.python, __file__, "_cell", str(spec_path), str(result_path)],
                                      stdout=log, stderr=subprocess.STDOUT, env=child_env(), cwd=str(ROOT))
            if proc.returncode or not result_path.is_file():
                tail = (logs / (cell_file(cell["key"])[:-5] + ".log")).read_text(encoding="utf-8", errors="replace").strip()
                raise RuntimeError(tail.splitlines()[-1][:300] if tail else f"exit {proc.returncode}")
            record.update(json.loads(result_path.read_text(encoding="utf-8")), wall_seconds=round(time.time() - started, 1),
                          finished_at=datetime.now().isoformat(timespec="seconds"))
            result_path.unlink()
            lat = record["latency_ms"]
            say(f"{cell['key']}: p50 {fmt_ms(lat['p50'])} p99 {fmt_ms(lat['p99'])} ms, failed {record['failed_calls']}")
        except Exception as error:  # one failed cell must not stop the rest
            record.update(status="failed", reason=f"{type(error).__name__}: {error}"[:400])
            say(f"{cell['key']}: failed: {record['reason']}")
        write_json(target, record)
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(out / "run.json", meta)
    write_report(cm, out)


def cmd_report(args):
    cm = matrix_module(args.token_bundles)
    apply_repos(cm, args)
    write_report(cm, Path(args.out_dir))


# ---- setup and token bundles ---------------------------------------------------------------------------------

def git_run(*args: str, cwd: Path | None = None):
    say("$ git " + " ".join(args))
    subprocess.run(["git", *args], cwd=cwd, check=True)


def cmd_setup(args):
    """Clone or update the system and model repositories next to this one, pin the model repository, pull the
    matrix models through git LFS and check them; optionally make a venv with the pinned packages."""
    cm = matrix_module(args.token_bundles)
    system = Path(args.system_repo or cm.SYSTEM_REPO).resolve()
    models = Path(args.model_repo or cm.MODEL_REPO).resolve()
    if not system.is_dir():
        git_run("clone", SYSTEM_URL, str(system))
    else:
        git_run("fetch", "origin", cwd=system)
    for prefix in cm.COMMITS:
        git_run("cat-file", "-e", f"{prefix}^{{commit}}", cwd=system)
    if not models.is_dir():
        env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}  # only the matrix models are pulled below
        say(f"$ git clone {MODEL_URL} {models}")
        subprocess.run(["git", "clone", MODEL_URL, str(models)], check=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=models, capture_output=True, text=True).stdout.strip()
    if head != MODEL_COMMIT:
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=models,
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            raise SystemExit(f"{models} has local changes; commit or stash them, then run setup again")
        git_run("fetch", "origin", cwd=models)
        subprocess.run(["git", "-c", "advice.detachedHead=false", "checkout", MODEL_COMMIT], cwd=models, check=True,
                       env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
    git_run("lfs", "install", "--local", cwd=models)
    folders = [cm.MODELS[m][0] for m in WEIGHTS_SHA256 if m not in TOKEN_BUNDLES]
    git_run("lfs", "pull", "--include", ",".join(f"{f}/**" for f in folders), cwd=models)
    cm.MODEL_REPO = models
    bad = []
    for model in WEIGHTS_SHA256:
        if model in TOKEN_BUNDLES:
            continue
        digest = sha256_file(cm.model_folder(model) / "model.safetensors")
        say(f"{model}: {'ok' if digest == WEIGHTS_SHA256[model] else 'MISMATCH ' + digest[:12]}")
        bad += [model] if digest != WEIGHTS_SHA256[model] else []
    for model in TOKEN_BUNDLES:
        weights = cm.model_folder(model) / "model.safetensors"
        say(f"{model}: " + ("found" if weights.is_file() else f"missing ({weights.parent}); see the README"))
    if args.venv:
        venv = Path(args.venv).resolve()
        if not venv.is_dir():
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        torch_cmd = [str(python), "-m", "pip", "install", TORCH]
        if args.torch in TORCH_INDEX:
            torch_cmd += ["--index-url", TORCH_INDEX[args.torch]]
        subprocess.run(torch_cmd, check=True)
        subprocess.run([str(python), "-m", "pip", "install", *REQUIREMENTS], check=True)
        say(f"venv ready: {python}")
    gitleaks = gitleaks_version()
    say(f"gitleaks: {gitleaks or 'MISSING'}" + ("" if gitleaks == GITLEAKS_VERSION else f" (need {GITLEAKS_VERSION} on PATH)"))
    if bad:
        raise SystemExit(f"weights differ: {', '.join(bad)}")


def cmd_bundles(args):
    """runs/creddata-traj-colab/build_bundles.py, on any device: the two token-classifier bundles from the Drive
    training output (promptguard-runs/token-span-creddata-{mmbert,qwen}), checked against the Colab hashes."""
    cm = matrix_module(None)
    models = Path(args.model_repo or cm.MODEL_REPO).resolve()
    sys.path.insert(0, str(models / "src"))
    from privai_model.ml_span.bio import LABELS
    from privai_model.ml_span.runtime import MLSpanDetector
    from privai_model.token_span.train import load_model
    runs, out = Path(args.drive_runs).resolve(), Path(args.out).resolve()
    failed = []
    for name, (folder, epoch, cutoff, target, files) in BUNDLE_SOURCES.items():
        run, source = runs / folder, runs / folder / f"epoch-{epoch}"
        wrong = [f for f, digest in files.items() if not (source / f).is_file() or sha256_file(source / f) != digest]
        if wrong:
            raise SystemExit(f"{source}: missing or different files: {', '.join(wrong)}")
        selected = json.loads((run / "selection.json").read_text())["selected"]
        config = json.loads((run / "config.json").read_text())
        assert selected["epoch"] == epoch and abs(selected["threshold"] - cutoff) < 5e-4, (name, selected)
        assert (config["max_length"], config["stride"]) == (512, 128), config
        dst = out / target
        if dst.exists():
            shutil.rmtree(dst)
        if config.get("lora"):
            model = load_model(config, adapter=str(source)).merge_and_unload()
            model.save_pretrained(dst, safe_serialization=True)
            from transformers import AutoTokenizer
            AutoTokenizer.from_pretrained(source).save_pretrained(dst)
        else:
            shutil.copytree(source, dst)
        meta = {"schema_version": "ml-span-bundle-v1", "max_length": 512, "stride": 128,
                "threshold": selected["threshold"],
                "threshold_source": f"{folder}/selection.json (validation exact-span F2, epoch {epoch})",
                "backbone": config["model_name"] + (" (LoRA merged into the token-classification model)" if config.get("lora") else ""),
                "revision": config.get("revision"), "label_mapping": {str(k): v for k, v in LABELS.items()},
                "source": f"Drive promptguard-runs/{folder}/epoch-{epoch}", "production_ready": False}
        (dst / "span_bundle.json").write_text(json.dumps(meta, indent=2) + "\n")
        detector = MLSpanDetector(dst, device=args.device)
        assert detector.model.config.id2label == LABELS, detector.model.config.id2label
        detector.scan_text("password = hunter2-example-value")
        digest = sha256_file(dst / "model.safetensors")
        ok = digest == WEIGHTS_SHA256[name]
        say(f"{name}: {dst} sha256 {digest[:12]} {'ok' if ok else 'MISMATCH, expected ' + WEIGHTS_SHA256[name][:12]}")
        failed += [] if ok else [name]
    if failed:
        raise SystemExit(f"bundles differ from the Colab build: {', '.join(failed)}")
    say(f"pass --token-bundles {out} to run")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def repos(p):
        p.add_argument("--system-repo", help="promptguard-claude-demoV0 clone (default: next to this repository)")
        p.add_argument("--model-repo", help="promptguard-model clone (default: next to this repository)")
        p.add_argument("--token-bundles", help="folder with token-span-creddata-{mmbert,qwen} "
                                               "(default $MATRIX_BUNDLES or runs/creddata-traj-eval/bundles)")
        p.add_argument("--work", default=str(DEFAULT_WORK), help="configured copies and cell logs (git-ignored)")

    p = sub.add_parser("run", help="measure the matrix cells")
    repos(p)
    p.add_argument("--out", help="output folder (default metric-latency/results/creddata-matrix-<timestamp>)")
    p.add_argument("--cells", nargs="*", help="prototype, COMMIT, COMMIT/MODEL or */MODEL (default: all 27)")
    p.add_argument("--calls", type=int, default=1000, help="timed calls per cell, one per text (default 1000)")
    p.add_argument("--warmup", type=int, default=20, help="untimed calls before timing (default 20)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workload", choices=("auto", "creddata", "synthetic"), default="auto",
                   help="auto: CredData-trajectory windows if the eval set is present, else synthetic")
    p.add_argument("--device", choices=("cpu", "cuda", "mps", "auto"), default="cpu", help="device of the ML adapter")
    p.add_argument("--python", default=sys.executable, help="interpreter for the cell processes (torch etc.)")
    p.add_argument("--no-model-check", action="store_true", help="measure even if model.safetensors sha256 differs")
    p.add_argument("--dry-run", action="store_true", help="print the plan and stop")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("report", help="rewrite summary.md/csv from an output folder")
    repos(p)
    p.add_argument("out_dir")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("setup", help="clone/pin the repositories, pull the models, optionally make a venv")
    repos(p)
    p.add_argument("--venv", help="create this venv and install the pinned packages")
    p.add_argument("--torch", choices=("cpu", "cuda", "default"), default="cpu",
                   help="torch wheel: cpu, cuda (cu130) or default (PyPI; use on macOS)")
    p.set_defaults(func=cmd_setup)
    p = sub.add_parser("bundles", help="build the two token-classifier bundles from the Drive training output")
    p.add_argument("--drive-runs", required=True, help="folder holding token-span-creddata-mmbert and -qwen")
    p.add_argument("--out", required=True)
    p.add_argument("--model-repo")
    p.add_argument("--device", default="cpu")
    p.set_defaults(func=cmd_bundles)
    p = sub.add_parser("_cell")
    p.add_argument("spec")
    p.add_argument("result")
    p.set_defaults(func=cmd_cell)
    sub.add_parser("_hardware").set_defaults(func=cmd_hardware)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
