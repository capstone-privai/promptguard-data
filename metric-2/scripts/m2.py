"""Metric 2: does masking change whether a coding agent gets its task done?

Runs Claude Code on the tasks in metric-2/tasks under a masking condition and checks what it left behind.

  none         the PromptGuard mod is attached, but its detector finds nothing: nothing is masked
  gold         the PromptGuard mod is attached, and its detector returns exactly the task's gold secrets
  promptguard  the PromptGuard mod with its own CredSweeper detector: the system under test
  plain        Claude Code without the mod (optional sanity baseline)

none, gold and promptguard all run the unchanged mod and MCP bridge from promptguard-claude-demoV0; only the
detector process behind the bridge differs (scripts/detector_worker.py for none and gold, the demo's
CredSweeper worker for promptguard). So the conditions differ in what gets masked and nothing else.

Commands, from the repository root:
  python3 metric-2/scripts/m2.py list
  python3 metric-2/scripts/m2.py selftest
  python3 metric-2/scripts/m2.py build t01 --out /tmp/t01
  python3 metric-2/scripts/m2.py check t01 /tmp/t01                         after working in it yourself
  python3 metric-2/scripts/m2.py play t01 --condition promptguard          interactive Claude Code session
  python3 metric-2/scripts/m2.py run --tasks all --conditions none,gold,promptguard --reps 1 --jobs 3
  python3 metric-2/scripts/m2.py report runs/metric-2/<batch> [...] --out metric-2/results
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_tasks as mt  # noqa: E402

REPO_ROOT = mt.REPO_ROOT
RUNS_DIR = REPO_ROOT / "runs" / "metric-2"
WORK_ROOT = Path(tempfile.gettempdir()) / "promptguard-m2"
DETECTOR = Path(__file__).resolve().parent / "detector_worker.py"
CONDITIONS = ("none", "gold", "promptguard", "plain")
DEFAULT_CONDITIONS = "none,gold,promptguard"
# Bash for commands, the file tools for reading and editing, and the mod's own detector transport: without that
# permission the mod's call to its detector is refused, the hook is skipped and the text reaches the model
# unmasked (seen with claude -p).
ALLOWED_TOOLS = "Bash,Read,Edit,Write,Glob,Grep,mcp__pgdetector__scan_batch"
# Set when this script runs inside another Claude Code session; a child session must not inherit them.
PARENT_SESSION_ENV = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET",
                      "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION",
                      "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION",
                      "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING",
                      "CLAUDE_CODE_EMIT_STARTUP_TIMING", "CLAUDE_CODE_QUESTION_PREVIEW_FORMAT", "PG_MOD_FAILURE_MODE")
PRINT_LOCK = threading.Lock()


def say(*args):
    with PRINT_LOCK:
        print(*args, flush=True)


def system_root(arg: str | None) -> Path:
    root = Path(arg or os.environ.get("PROMPTGUARD_CLAUDE_ROOT") or REPO_ROOT.parent / "promptguard-claude-demoV0")
    if not (root / "src" / "native-mod" / "hooks" / "register.mjs").is_file():
        raise SystemExit(f"PromptGuard Claude Code demo not found at {root}; pass --system-root or set PROMPTGUARD_CLAUDE_ROOT")
    return root.resolve()


def clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in PARENT_SESSION_ENV}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- one run -----------------------------------------------------------------------------------------------

class Detector:
    """The detector process behind the mod's MCP bridge, for one run."""

    def __init__(self, condition: str, task: mt.Task, run_dir: Path, pg_root: Path):
        self.proc = None
        self.url = None
        if condition == "plain":
            return
        port = free_port()
        env = {**clean_env(), "PG_DETECTOR_PORT": str(port), "PG_DETECTOR_MODE": "normal"}
        gold_file = None
        if condition == "promptguard":
            python = pg_root / ".venv" / "bin" / "python"
            if not python.is_file():
                raise RuntimeError(f"{python} missing; run install.sh in {pg_root} first")
            argv, cwd = [str(python), str(pg_root / "src" / "credsweeper-adapter" / "worker.py")], pg_root
        else:
            argv, cwd = [sys.executable, str(DETECTOR), "--mode", condition], run_dir
            if condition == "gold":
                # Outside the workspace, and deleted as soon as the worker has read it.
                fd, name = tempfile.mkstemp(prefix="m2-gold-", suffix=".json")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"secrets": mt.gold_rows(task.secrets)}, f)
                gold_file = Path(name)
                argv += ["--gold", str(gold_file)]
        self.log = open(run_dir / "detector.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self.url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 90
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"detector exited with {self.proc.returncode}; see {run_dir / 'detector.log'}")
                try:
                    with urllib.request.urlopen(self.url + "/health", timeout=1) as r:
                        if r.status == 200:
                            return
                except OSError:
                    time.sleep(0.2)
            raise RuntimeError("detector did not become healthy within 90s")
        finally:
            if gold_file:
                gold_file.unlink(missing_ok=True)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.proc:
            self.log.close()


def claude_command(task: mt.Task, condition: str, run_dir: Path, session_id: str, pg_root: Path,
                   model: str | None, headless: bool, budget: float, detector: Detector) -> tuple[list[str], dict]:
    argv = ["claude"]
    argv += ["-p", task.prompt, "--output-format", "json", "--max-budget-usd", str(budget)] if headless else [task.prompt]
    argv += ["--session-id", session_id, "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS,
             "--setting-sources", "project", "--strict-mcp-config"]
    if model:
        argv += ["--model", model]
    env = clean_env()
    if condition != "plain":
        mcp = run_dir / "mcp.json"
        bridge = pg_root / "src" / "credsweeper-adapter" / "mcp-bridge.cjs"
        mcp.write_text(json.dumps({"mcpServers": {"pgdetector": {
            "command": "node", "args": [str(bridge)], "env": {"PG_DETECTOR_URL": detector.url}}}}), encoding="utf-8")
        argv += ["--plugin-dir", str(pg_root / "src" / "native-mod"), "--mcp-config", str(mcp)]
        env.update({"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1", "PG_DETECTOR_URL": detector.url,
                    "PG_MOD_AUDIT": str(run_dir / "audit.json"), "PG_SESSION_HASH": secrets.token_hex(32)})
    return argv, env


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def collect_transcript(session_id: str, run_dir: Path) -> list[dict]:
    """Moves the session transcript into the run folder and removes what the session left under ~/.claude
    (its project folder, which only this run's workspace path maps to, and its file-history backups, which hold
    the raw files)."""
    home = claude_home()
    found = sorted(home.glob(f"projects/*/{session_id}.jsonl"))
    rows = []
    if found:
        dest = run_dir / "transcript.jsonl"
        shutil.move(str(found[0]), dest)
        rows = [json.loads(line) for line in dest.read_text(encoding="utf-8").split("\n") if line.strip()]
        project = found[0].parent
        if "promptguard-m2" in project.name:  # a folder only our temporary workspaces map to
            shutil.rmtree(project, ignore_errors=True)
    for leftover in (home / "file-history" / session_id, home / "session-env" / session_id):
        shutil.rmtree(leftover, ignore_errors=True)
    for todo in home.glob(f"todos/{session_id}*"):
        todo.unlink(missing_ok=True)
    return rows


def strings_in(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in strings_in(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings_in(v)]
    return []


def transcript_stats(rows: list[dict], task: mt.Task) -> dict:
    """What the model received and wrote, read from the transcript (which stores each row as the mod left it).
    seen: gold secrets inside user-role rows (the prompt and tool results); written: inside the model's own
    text and tool calls. Text the engine sends outside these rows (the system prompt, CLAUDE.md) is not here."""
    forms = [(g["name"], g["value"]) for g in mt.gold_rows(task.secrets) if len(g["value"]) >= 8]
    seen, written = Counter(), Counter()
    tools, failed_tools, placeholder_inputs = Counter(), Counter(), 0
    names = {}
    for row in rows:
        message = row.get("message") or {}
        if row.get("type") not in ("user", "assistant") or not isinstance(message, dict):
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            texts = strings_in(block.get("content") if block.get("type") == "tool_result" else
                               block.get("input") if block.get("type") == "tool_use" else block.get("text"))
            target = seen if row["type"] == "user" else written
            for text in texts:
                for name, value in forms:
                    if value in text:
                        target[name] += text.count(value)
            if block.get("type") == "tool_use":
                tools[block.get("name")] += 1
                names[block.get("id")] = block.get("name")
                if any(mt.PLACEHOLDER.search(t) for t in texts):
                    placeholder_inputs += 1
            if block.get("type") == "tool_result" and block.get("is_error"):
                failed_tools[names.get(block.get("tool_use_id"), "?")] += 1
    return {"secrets_seen": sorted(seen), "seen_occurrences": sum(seen.values()),
            "secrets_written": sorted(written), "written_occurrences": sum(written.values()),
            "tool_calls": dict(tools), "failed_tool_calls": dict(failed_tools),
            "tool_inputs_with_placeholder": placeholder_inputs}


def audit_stats(run_dir: Path) -> dict:
    path = run_dir / "audit.json"
    if not path.is_file():
        return {"rows": 0, "findings": 0, "failures": 0, "failure_reasons": []}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"rows": 0, "findings": 0, "failures": 1, "failure_reasons": ["audit file unreadable"]}
    failures = [r for r in rows if r.get("blocked")]
    by_source = Counter()
    for r in rows:
        by_source[r.get("source", "?")] += r.get("finding_count", 0)
    return {"rows": len(rows), "findings": sum(by_source.values()), "findings_by_source": dict(by_source),
            "failures": len(failures), "failure_reasons": sorted({str(r.get("reason"))[:160] for r in failures})}


def save_workspace(ws: Path, run_dir: Path):
    # Remotes live in .git, which is not kept; recheck reads them from here.
    (run_dir / "git_remotes.json").write_text(json.dumps(mt.git_remotes(ws)), encoding="utf-8")
    mt.git(ws, "add", "-A", check=False)
    diff = mt.git(ws, "diff", "--cached", "--binary", check=False).stdout
    (run_dir / "diff.patch").write_text(diff, encoding="utf-8")
    if (ws / "answer.json").is_file():
        shutil.copyfile(ws / "answer.json", run_dir / "answer.json")
    shutil.copytree(ws, run_dir / "workspace_after", ignore=shutil.ignore_patterns(".git"), dirs_exist_ok=True)


def run_one(task: mt.Task, condition: str, rep: int, run_dir: Path, pg_root: Path, model: str | None,
            headless: bool = True, budget: float = 2.0, timeout: int = 900) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{task.id[:3]}-{condition}-", dir=_work_root()))
    ws = work / "workspace"
    built = mt.build(task, ws)
    session_id = str(uuid.uuid4())
    result = {"task": task.id, "category": task.category, "needs_secret_value": task.spec["needs_secret_value"],
              "condition": condition, "rep": rep, "model": model, "session_id": session_id,
              "started_at": datetime.now().isoformat(timespec="seconds"), "error": None}
    detector = None
    started = time.time()
    try:
        detector = Detector(condition, task, run_dir, pg_root)
        argv, env = claude_command(task, condition, run_dir, session_id, pg_root, model, headless, budget, detector)
        if headless:
            proc = subprocess.run(argv, cwd=ws, env=env, capture_output=True, text=True, timeout=timeout,
                                  stdin=subprocess.DEVNULL)
            (run_dir / "claude.stderr.txt").write_text(proc.stderr, encoding="utf-8")
            try:
                out = json.loads(proc.stdout)
            except json.JSONDecodeError:
                out = {"raw_stdout": proc.stdout[-2000:]}
            (run_dir / "claude.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            result["claude"] = {"exit_code": proc.returncode, "subtype": out.get("subtype"),
                                "is_error": out.get("is_error"), "api_error_status": out.get("api_error_status"),
                                "terminal_reason": out.get("terminal_reason"), "num_turns": out.get("num_turns"),
                                "cost_usd": out.get("total_cost_usd"), "duration_ms": out.get("duration_ms"),
                                "models": sorted((out.get("modelUsage") or {}).keys())}
        else:
            proc = subprocess.run(argv, cwd=ws, env=env)
            result["claude"] = {"exit_code": proc.returncode}
    except subprocess.TimeoutExpired:
        result["error"] = f"timeout after {timeout}s"
    except Exception as e:  # keep the batch going; the run is reported as an error
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if detector:
            detector.stop()
    result["elapsed_s"] = round(time.time() - started, 1)
    rows = collect_transcript(session_id, run_dir)
    result.update(mt.check_task(task, ws, built))
    result["transcript"] = transcript_stats(rows, task)
    result["mod"] = audit_stats(run_dir) if condition != "plain" else None
    result["valid"] = is_valid(result, bool(rows))
    save_workspace(ws, run_dir)
    shutil.rmtree(work, ignore_errors=True)
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def api_failed(result: dict) -> bool:
    """The model was never reached or the request failed (usage limit, overload): not the agent's doing."""
    claude = result.get("claude") or {}
    return bool(claude.get("is_error")) or claude.get("terminal_reason") == "api_error" or \
        claude.get("api_error_status") is not None


def is_valid(result: dict, has_transcript: bool = True) -> bool:
    mod_ok = result["condition"] == "plain" or (
        (result.get("mod") or {}).get("rows", 0) > 0 and (result.get("mod") or {}).get("failures", 0) == 0)
    return result.get("error") is None and has_transcript and not api_failed(result) and mod_ok


def _work_root() -> Path:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    return WORK_ROOT


# ---- commands ----------------------------------------------------------------------------------------------

def cmd_list(args):
    for t in mt.load_tasks(args.tasks):
        flag = "값 필요" if t.spec["needs_secret_value"] else ""
        print(f"{t.id:30s} {t.category:9s} {flag:6s} {t.spec['title']}")


def cmd_build(args):
    task = mt.load_tasks([args.task])[0]
    out = Path(args.out)
    mt.build(task, out)
    print(f"built {task.id} into {out}")
    print(f"prompt: {task.prompt}")


def cmd_check(args):
    """Checks a workspace you worked in with your own Claude Code session (built with `build`)."""
    task = mt.load_tasks([args.task])[0]
    with tempfile.TemporaryDirectory() as d:
        built = mt.build(task, Path(d) / "ws")
    r = mt.check_task(task, Path(args.workspace), built)
    for c in r["checks"]:
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['check']}: {c['detail']}")
    print(f"  {'ok  ' if r['integrity_ok'] else 'FAIL'} integrity: {r['integrity']}")
    print("PASS" if r["success"] else "FAIL")
    sys.exit(0 if r["success"] else 1)


def cmd_selftest(args):
    problems = 0
    for task in mt.load_tasks(args.tasks):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "ws"
            built = mt.build(task, ws)
            untouched = mt.check_task(task, ws, built)["success"]
            mt.apply_solution(task, ws)
            solved = mt.check_task(task, ws, built)
            corrupted = mt.corrupt_with_placeholder(task, ws, built)
            broken = mt.check_task(task, ws, built)["success"] if corrupted else False
            ok = not untouched and solved["success"] and not broken
            problems += not ok
            print(f"{'ok ' if ok else 'BAD'} {task.id:30s} untouched={untouched!s:5} solved={solved['success']!s:5} "
                  f"placeholder_written={'n/a' if not corrupted else broken}")
            if not solved["success"]:
                print("    ", json.dumps(solved, ensure_ascii=False))
    print(f"{problems} problem(s)")
    sys.exit(1 if problems else 0)


def print_result(r: dict, run_dir: Path):
    mark = "PASS" if r["success"] else "FAIL"
    t = r["transcript"]
    cost = (r.get("claude") or {}).get("cost_usd")
    extra = f" cost=${cost:.3f}" if cost else ""
    say(f"[{mark}] {r['task']} {r['condition']} r{r['rep']}: task_ok={r['task_ok']} integrity={r['integrity_ok']} "
        f"seen={len(t['secrets_seen'])} masked={(r.get('mod') or {}).get('findings', '-')}{extra}"
        f"{'' if r['valid'] else ' INVALID'}{' error=' + r['error'] if r['error'] else ''}  -> {run_dir}")


def cmd_play(args):
    pg_root = system_root(args.system_root)
    task = mt.load_tasks([args.task])[0]
    run_dir = RUNS_DIR / "play" / f"{datetime.now():%Y%m%d-%H%M%S}_{task.id}_{args.condition}"
    print(f"task:      {task.id} ({task.spec['title']})")
    print(f"condition: {args.condition}")
    print(f"prompt:    {task.prompt}\n")
    print("Claude Code starts with this prompt already sent. Exit it (/exit or Ctrl+D) when done; the result is checked then.\n")
    r = run_one(task, args.condition, 1, run_dir, pg_root, args.model, headless=False)
    print()
    for c in r["checks"]:
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['check']}: {c['detail']}")
    print(f"  {'ok  ' if r['integrity_ok'] else 'FAIL'} integrity: {r['integrity']}")
    print_result(r, run_dir)


def cmd_run(args):
    pg_root = system_root(args.system_root)
    tasks = mt.load_tasks(args.tasks)
    conditions = args.conditions.split(",")
    unknown = set(conditions) - set(CONDITIONS)
    if unknown:
        raise SystemExit(f"unknown condition(s) {sorted(unknown)}; choose from {CONDITIONS}")
    batch = RUNS_DIR / (args.name or f"batch_{datetime.now():%Y%m%d-%H%M%S}")
    batch.mkdir(parents=True, exist_ok=True)
    jobs = [(t, c, rep) for rep in range(1, args.reps + 1) for t in tasks for c in conditions]
    if args.resume:
        jobs = [(t, c, rep) for t, c, rep in jobs if not finished(batch / t.id / f"{c}-r{rep}")]
    (batch / "batch.json").write_text(json.dumps({
        "started_at": datetime.now().isoformat(timespec="seconds"), "model": args.model, "reps": args.reps,
        "conditions": conditions, "tasks": [t.id for t in tasks], "system_root": str(pg_root),
        "system_commit": mt.git(pg_root, "rev-parse", "HEAD", check=False).stdout.strip(),
        "data_commit": mt.git(REPO_ROOT, "rev-parse", "HEAD", check=False).stdout.strip(),
        "claude_version": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
    }, indent=2), encoding="utf-8")
    say(f"{len(jobs)} run(s) -> {batch}")

    def job(spec):
        task, condition, rep = spec
        run_dir = batch / task.id / f"{condition}-r{rep}"
        for attempt in range(args.retries + 1):
            if run_dir.exists():
                shutil.rmtree(run_dir)
            r = run_one(task, condition, rep, run_dir, pg_root, args.model, budget=args.budget, timeout=args.timeout)
            print_result(r, run_dir)
            if not api_failed(r) or attempt == args.retries:
                return r
            wait = 120 * (attempt + 1)
            say(f"    API error {(r.get('claude') or {}).get('api_error_status')}; retrying in {wait}s")
            time.sleep(wait)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(job, jobs))
    rows = load_results([batch])
    write_report(rows, batch)
    say(f"summary: {batch / 'summary.md'}")


# ---- report ------------------------------------------------------------------------------------------------

def finished(run_dir: Path) -> bool:
    path = run_dir / "result.json"
    return path.is_file() and bool(json.loads(path.read_text(encoding="utf-8")).get("valid"))


def load_results(dirs: list[Path]) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for d in dirs for p in sorted(Path(d).glob("*/*/result.json"))]


def rate(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.0%})" if d else "-"


CATEGORY_KO = {
    "diagnose": "진단 (비밀과 무관)", "edit": "비밀이 든 파일 수정", "identity": "같은 비밀인지 비교",
    "overmask": "비밀 아닌 값 필요", "property": "비밀 값의 속성 필요", "use": "비밀을 명령에 사용",
    "transport": "비밀 옮기기",
}


def write_report(rows: list[dict], out: Path):
    out.mkdir(parents=True, exist_ok=True)
    valid = [r for r in rows if r.get("valid")]
    conditions = [c for c in CONDITIONS if any(r["condition"] == c for r in rows)]
    lines = ["# 지표 2 결과 요약", ""]
    models = sorted({m for r in rows for m in (r.get("claude") or {}).get("models") or [r.get("model") or "default"]})
    lines += [f"- 실행: {len(rows)}회 (유효 {len(valid)}회), 과제 {len({r['task'] for r in rows})}개, "
              f"조건 {', '.join(conditions)}, 모델 {', '.join(models)}",
              "- 유효하지 않은 실행(Mod 실패, 오류, transcript 없음)은 아래 표에서 뺀다.", ""]

    def table(title, key_fn, keys, label=lambda k: k):
        lines.extend([f"## {title}", "", "| 구분 | " + " | ".join(conditions) + " |",
                      "|---|" + "---|" * len(conditions)])
        for k in keys:
            cells = []
            for c in conditions:
                sel = [r for r in valid if r["condition"] == c and key_fn(r) == k]
                cells.append(rate(sum(r["success"] for r in sel), len(sel)))
            lines.append(f"| {label(k)} | " + " | ".join(cells) + " |")
        lines.append("")

    table("과제 성공률 (전체)", lambda r: "전체", ["전체"])
    table("비밀 값이 필요한 과제인가", lambda r: r["needs_secret_value"], [False, True],
          lambda k: "필요 (property, use, transport)" if k else "불필요 (그 밖)")
    cats = [c for c in CATEGORY_KO if any(r["category"] == c for r in rows)]
    table("과제 유형별", lambda r: r["category"], cats, lambda k: f"{k}: {CATEGORY_KO[k]}")

    lines += ["## 실패의 종류와 노출", "",
              "| 조건 | 과제 실패 | 비밀 훼손 (placeholder 기록 등) | 비밀이 모델에 보인 실행 | 모델이 본 비밀(실행당) | placeholder를 도구 입력에 쓴 실행 | 평균 비용 |",
              "|---|---|---|---|---|---|---|"]
    for c in conditions:
        sel = [r for r in valid if r["condition"] == c]
        if not sel:
            continue
        costs = [(r.get("claude") or {}).get("cost_usd") or 0 for r in sel]
        lines.append(f"| {c} | {sum(not r['task_ok'] for r in sel)} | {sum(not r['integrity_ok'] for r in sel)} | "
                     f"{rate(sum(bool(r['transcript']['secrets_seen']) for r in sel), len(sel))} | "
                     f"{sum(len(r['transcript']['secrets_seen']) for r in sel) / len(sel):.2f} | "
                     f"{sum(r['transcript']['tool_inputs_with_placeholder'] > 0 for r in sel)} | "
                     f"${sum(costs) / len(sel):.3f} |")
    lines.append("")

    lines += ["## 과제별 결과", "", "| 과제 | 유형 | " + " | ".join(conditions) + " |",
              "|---|---|" + "---|" * len(conditions)]
    by_task = defaultdict(list)
    for r in valid:
        by_task[r["task"]].append(r)
    for task_id in sorted(by_task):
        cells = []
        for c in conditions:
            sel = [r for r in by_task[task_id] if r["condition"] == c]
            marks = "".join("O" if r["success"] else ("x" if r["task_ok"] else "X") for r in sorted(sel, key=lambda r: r["rep"]))
            cells.append(marks or "-")
        lines.append(f"| {task_id} | {by_task[task_id][0]['category']} | " + " | ".join(cells) + " |")
    lines += ["", "O 성공, X 과제 실패, x 과제는 했지만 비밀 훼손(placeholder를 파일에 씀 등). 반복 실행은 글자를 이어 적는다.", ""]
    invalid = [r for r in rows if not r.get("valid")]
    if invalid:
        lines += ["## 유효하지 않은 실행", ""]
        lines += [f"- {r['task']} {r['condition']} r{r['rep']}: {r.get('error') or (r.get('mod') or {}).get('failure_reasons') or 'no transcript'}"
                  for r in invalid]
        lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    fields = ["task", "category", "needs_secret_value", "condition", "rep", "valid", "success", "task_ok",
              "integrity_ok", "secrets_seen", "secrets_written", "tool_inputs_with_placeholder", "masked_findings",
              "mod_failures", "num_turns", "cost_usd", "elapsed_s", "model", "error"]
    with (out / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            claude = r.get("claude") or {}
            w.writerow({"task": r["task"], "category": r["category"], "needs_secret_value": r["needs_secret_value"],
                        "condition": r["condition"], "rep": r["rep"], "valid": r.get("valid"), "success": r["success"],
                        "task_ok": r["task_ok"], "integrity_ok": r["integrity_ok"],
                        "secrets_seen": len(r["transcript"]["secrets_seen"]),
                        "secrets_written": len(r["transcript"]["secrets_written"]),
                        "tool_inputs_with_placeholder": r["transcript"]["tool_inputs_with_placeholder"],
                        "masked_findings": (r.get("mod") or {}).get("findings"),
                        "mod_failures": (r.get("mod") or {}).get("failures"),
                        "num_turns": claude.get("num_turns"), "cost_usd": claude.get("cost_usd"),
                        "elapsed_s": r.get("elapsed_s"),
                        "model": ",".join(claude.get("models") or []) or r.get("model"), "error": r.get("error")})


def cmd_recheck(args):
    """Re-runs the checks against each run's saved workspace_after, e.g. after a checker fix. The agent's work is
    not repeated; transcript and mod statistics stay as recorded."""
    tasks = {t.id: t for t in mt.load_tasks()}
    built_cache: dict[str, dict] = {}
    changed = 0
    for batch in args.batches:
        for path in sorted(Path(batch).glob("*/*/result.json")):
            r = json.loads(path.read_text(encoding="utf-8"))
            task = tasks[r["task"]]
            if task.id not in built_cache:
                with tempfile.TemporaryDirectory() as d:
                    built_cache[task.id] = mt.build(task, Path(d) / "ws")
            remotes_file = path.parent / "git_remotes.json"
            remotes = json.loads(remotes_file.read_text()) if remotes_file.is_file() else None
            fresh = mt.check_task(task, path.parent / "workspace_after", built_cache[task.id], remotes or {})
            if remotes is None:  # older runs did not save remotes: keep their git_remote verdicts
                kinds = {c.get("name") or f"{c['kind']}#{i}": c["kind"] for i, c in enumerate(task.spec["checks"])}
                old = {c["check"]: c for c in r["checks"]}
                fresh["checks"] = [old.get(c["check"], c) if kinds.get(c["check"]) == "git_remote" else c
                                   for c in fresh["checks"]]
                fresh["task_ok"] = all(c["ok"] for c in fresh["checks"])
                fresh["success"] = fresh["task_ok"] and fresh["integrity_ok"]
            if fresh["success"] != r["success"]:
                changed += 1
                say(f"{r['task']} {r['condition']} r{r['rep']}: success {r['success']} -> {fresh['success']}")
            r.update(fresh)
            r["valid"] = is_valid(r, (path.parent / "transcript.jsonl").is_file())
            path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(load_results([Path(batch)]), Path(batch))
    say(f"{changed} verdict(s) changed")


def cmd_report(args):
    rows = load_results([Path(d) for d in args.batches])
    if not rows:
        raise SystemExit("no result.json under the given folders")
    write_report(rows, Path(args.out))
    print(f"{len(rows)} run(s) -> {Path(args.out) / 'summary.md'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="list the tasks")
    p.add_argument("--tasks", nargs="*")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("build", help="write one task's workspace to a folder")
    p.add_argument("task")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build)
    p = sub.add_parser("check", help="check a workspace built with `build` after working in it yourself")
    p.add_argument("task")
    p.add_argument("workspace")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("selftest", help="check every task's checks against its oracle solution, without Claude")
    p.add_argument("--tasks", nargs="*")
    p.set_defaults(func=cmd_selftest)
    p = sub.add_parser("play", help="open an interactive Claude Code session on one task")
    p.add_argument("task")
    p.add_argument("--condition", choices=CONDITIONS, default="promptguard")
    p.add_argument("--model", help="default: your Claude Code default model")
    p.add_argument("--system-root", help="promptguard-claude-demoV0 checkout (default ../promptguard-claude-demoV0)")
    p.set_defaults(func=cmd_play)
    p = sub.add_parser("run", help="run tasks headless (claude -p) under each condition")
    p.add_argument("--tasks", nargs="*", default=["all"])
    p.add_argument("--conditions", default=DEFAULT_CONDITIONS)
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--budget", type=float, default=2.0, help="--max-budget-usd per run")
    p.add_argument("--timeout", type=int, default=900, help="seconds per run")
    p.add_argument("--name", help="batch folder name under runs/metric-2 (default batch_<time>)")
    p.add_argument("--resume", action="store_true", help="with --name: skip runs that already have a valid result")
    p.add_argument("--retries", type=int, default=2, help="retries of a run the API refused (usage limit, overload)")
    p.add_argument("--system-root")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("recheck", help="re-run the checks on saved runs (after fixing a checker)")
    p.add_argument("batches", nargs="+")
    p.set_defaults(func=cmd_recheck)
    p = sub.add_parser("report", help="summarize one or more batch folders")
    p.add_argument("batches", nargs="+")
    p.add_argument("--out", default=str(REPO_ROOT / "metric-2" / "results"))
    p.set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
