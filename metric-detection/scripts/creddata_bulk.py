"""Run every not-yet-run instance of a catalog, on the subscription account while it has room, else on the API key.

Before each run the account's 5-hour and weekly utilization is read; at or above --switch-at percent (or after a
run that died on a usage limit) runs go to the API key until the window resets, then back to the account. API
spending is capped by --api-cap (sum of the CLI's reported cost of API runs). A run that does not finish is kept
under attempts/ and tried once more. Resumable: instances with a run.json are skipped. Create <instances>/STOP to
stop after the runs in flight. Tokens and keys are never logged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.request

import creddata_tasks as T
import creddata_rollout as R

LIMIT = re.compile(r"usage limit|rate.?limit|limit reached|\b429\b|out of extra usage", re.I)
ORDER = re.compile(r"-(\d+)__(ko|en)$")


class Chooser:
    def __init__(self, config_dir: Path, switch_at: float, api_cap: float, spent: float, slack: float):
        self.credentials, self.switch_at, self.api_cap, self.slack = config_dir / ".credentials.json", switch_at, api_cap, slack
        self.lock, self.spent, self.checked, self.usage, self.blocked_until = threading.Lock(), spent, 0.0, None, 0.0

    def read_usage(self):
        try:
            token = json.loads(self.credentials.read_text())["claudeAiOauth"]["accessToken"]
            request = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
                "Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-cli"})
            data = json.load(urllib.request.urlopen(request, timeout=20))
            return {name: (data[name]["utilization"], data[name]["resets_at"]) for name in ("five_hour", "seven_day")
                    if data.get(name)}
        except Exception:  # the endpoint is advisory; a run that hits the limit is caught separately
            return None

    def mode(self) -> str | None:
        """subscription, api, or None when neither is available right now."""
        with self.lock:
            now = time.time()
            if now - self.checked > 120:
                self.usage, self.checked = self.read_usage(), now
            full = [reset for used, reset in (self.usage or {}).values() if used >= self.switch_at]
            if now >= self.blocked_until and not full:
                return "subscription"
            if self.spent + self.slack < self.api_cap:
                return "api"
            return None

    def account_limited(self):
        with self.lock:
            resets = (self.usage or {}).get("five_hour", (0, None))[1]
            until = datetime.fromisoformat(resets).timestamp() if resets else 0
            self.blocked_until = until if until > time.time() else time.time() + 1800
            self.checked = 0.0

    def add(self, cost):
        with self.lock:
            self.spent += cost or 0.0


def archive(instance: Path):
    """Keep a failed attempt and free the instance for another run."""
    attempts = instance / "attempts"
    target = attempts / str(len(list(attempts.iterdir())) + 1 if attempts.exists() else 1)
    target.mkdir(parents=True)
    for name in ("run.json", "capture", "labeled", "workspace_after"):
        if (instance / name).exists():
            shutil.move(str(instance / name), str(target / name))


def hit_limit(instance: Path) -> bool:
    text = ""
    for name in ("capture/stderr.txt", "capture/stream.jsonl"):
        path = instance / name
        if path.exists():
            text += path.read_text(errors="replace")[-20000:]
    return bool(LIMIT.search(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=T.ROOT / ".env")
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".claude-trajectory")
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--budget", type=float, default=1.0, help="per-run CLI budget in API mode, USD")
    parser.add_argument("--api-cap", type=float, required=True, help="stop using the API key at this total, USD")
    parser.add_argument("--switch-at", type=float, default=95.0, help="account utilization percent that sends runs to the API")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, help="run at most this many instances")
    args = parser.parse_args()
    os.environ["CLAUDE_CONFIG_DIR"] = str(args.config_dir)
    environments = {"subscription": R.subscription_environment(), "api": R.api_environment(args.env_file)}
    done, todo, spent = 0, [], 0.0
    for path in sorted(p for p in args.instances.iterdir() if (p / "task.json").is_file()):
        for record in [path / "run.json", *path.glob("attempts/*/run.json")]:
            if record.exists():
                run = json.loads(record.read_text())
                spent += (run.get("cost_usd") or 0.0) if run.get("auth_mode") == "api" else 0.0
        if (path / "run.json").exists():
            done += 1
        else:
            todo.append(path)
    # Interleave families and languages so a partial run stays balanced.
    todo.sort(key=lambda p: (int(ORDER.search(p.name)[1]), p.name))
    todo = todo[:args.limit]
    chooser = Chooser(args.config_dir, args.switch_at, args.api_cap, spent, args.budget * args.workers)
    log_lock, failures, stop = threading.Lock(), [0], threading.Event()

    def log(row):
        with log_lock:
            with (args.instances / "bulk.log").open("a") as stream:
                stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}) + "\n")

    def work(instance: Path):
        for attempt in (1, 2):
            while True:
                if stop.is_set() or (args.instances / "STOP").exists():
                    return
                mode = chooser.mode()
                if mode:
                    break
                log({"event": "waiting", "reason": "account limited and API cap reached", "api_spent": round(chooser.spent, 2)})
                time.sleep(600)
            try:
                summary = R.run_one(instance, environments[mode], args.model, args.budget, args.timeout, mode, False, args.effort)
            except Exception as error:  # the run record, if any, stays for inspection
                log({"event": "error", "task": instance.name, "mode": mode, "error": f"{type(error).__name__}: {error}"[:300]})
                with log_lock:
                    failures[0] += 1
                return
            if mode == "api":
                chooser.add(summary.get("cost_usd"))
            limited = summary["status"] != "finished" and mode == "subscription" and hit_limit(instance)
            if limited:
                chooser.account_limited()
            log({"event": "run", "task": instance.name, "attempt": attempt, "mode": mode, "status": summary["status"],
                 "cost_usd": summary.get("cost_usd"), "turns": summary.get("num_turns"), "elapsed_s": summary.get("elapsed_s"),
                 "gold_spans": (summary.get("annotation") or {}).get("gold_spans"), "account_limited": limited,
                 "api_spent": round(chooser.spent, 2), "usage": chooser.usage})
            if summary["status"] == "finished":
                with log_lock:
                    failures[0] = 0
                return
            with log_lock:
                failures[0] += 0 if limited else 1
                if failures[0] >= 8:
                    stop.set()
            if stop.is_set():
                log({"event": "abort", "reason": "8 consecutive runs did not finish"})
                return
            if attempt == 1:
                archive(instance)

    log({"event": "start", "already_done": done, "todo": len(todo), "api_spent_before": round(spent, 2),
         "model": args.model, "effort": args.effort, "workers": args.workers, "api_cap": args.api_cap})
    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, todo))
    finished = sum((p / "run.json").exists() for p in args.instances.iterdir() if (p / "task.json").is_file())
    log({"event": "end", "with_run_record": finished, "api_spent": round(chooser.spent, 2), "aborted": stop.is_set()})
    print(json.dumps({"with_run_record": finished, "api_spent": round(chooser.spent, 2), "aborted": stop.is_set()}))


if __name__ == "__main__":
    main()
