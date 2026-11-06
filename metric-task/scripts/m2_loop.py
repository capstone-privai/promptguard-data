#!/usr/bin/env python3
"""Keeps one m2.py batch going across subscription usage limits.

A limit fails every remaining run, and it can take hours to lift. So this runs the batch with --retries 0, waits, and
resumes until every run is valid. It stops on its own when waiting will not help:

  - m2.py run exits non-zero (for example a resume refused because the code or the Claude Code version changed);
  - a round makes no progress and some invalid run reached the model (a timeout, a budget cap, a Mod failure): running
    it again spends usage, so this stops after --max-hard-stalls such rounds;
  - only refused runs are left and nothing has passed for --max-wait-hours.

The Claude Code auto-updater is turned off for the runs, because a version change refuses the resume.

    CLAUDE_CONFIG_DIR=~/.claude-trajectory M2_RUNS_DIR=<dir> python3 metric-task/scripts/m2_loop.py --name NAME \
        -- --tasks family:ingress --conditions none --reps 1 --model sonnet --jobs 1 --budget 2
"""
import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2  # noqa: E402

BUDGET_SUBTYPE = "error_max_budget_usd"


@dataclass
class Progress:
    expected: int
    valid: int
    refused: int  # the model was never reached (usage limit, overload); trying again costs nothing
    hard: int  # invalid for another reason; the run spent usage, and trying again spends it again


@dataclass
class State:
    best_valid: int = -1
    hard_stalls: int = 0
    last_progress: float = 0.0


def is_refused(result: dict) -> bool:
    return m2.api_failed(result) and (result.get("claude") or {}).get("subtype") != BUDGET_SUBTYPE


def batch_progress(batch: Path) -> Progress:
    meta = json.loads((batch / "batch.json").read_text(encoding="utf-8"))
    expected = len(meta["tasks"]) * len(meta["conditions"]) * meta["reps"]
    valid = refused = hard = 0
    for path in batch.glob("*/*/result.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("valid"):
            valid += 1
        elif is_refused(result):
            refused += 1
        else:
            hard += 1
    return Progress(expected, valid, refused, hard)


def decide(progress: Progress, state: State, now: float, max_hard_stalls: int, max_wait: float) -> str | None:
    """Updates state after a round. None means wait and resume; anything else is why to stop."""
    if progress.valid >= progress.expected:
        return "done"
    if progress.valid > state.best_valid:
        state.best_valid, state.hard_stalls, state.last_progress = progress.valid, 0, now
        return None
    if progress.hard:
        state.hard_stalls += 1
        if state.hard_stalls >= max_hard_stalls:
            return f"no progress in {state.hard_stalls} rounds with {progress.hard} run(s) failing after reaching the model"
        return None
    if now - state.last_progress >= max_wait:
        return f"only refused runs left and nothing passed for {(now - state.last_progress) / 3600:.1f} hours"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="batch folder name under M2_RUNS_DIR")
    parser.add_argument("--wait-minutes", type=float, default=30)
    parser.add_argument("--max-hard-stalls", type=int, default=2)
    parser.add_argument("--max-wait-hours", type=float, default=6, help="longer than one usage limit window")
    parser.add_argument("run_args", nargs="*", help="after --: passed to m2.py run")
    args = parser.parse_args()

    batch = m2.RUNS_DIR / args.name
    command = [sys.executable, str(Path(m2.__file__).resolve()), "run", "--name", args.name, "--resume", "--retries", "0",
               *args.run_args]
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1"}
    state = State()
    while True:
        print(f"[{datetime.now():%H:%M:%S}] round: {' '.join(command[2:])}", flush=True)
        code = subprocess.run(command, env=env).returncode
        if code:
            print(f"stopping: m2.py run exited with {code}", flush=True)
            return 1
        progress = batch_progress(batch)
        print(f"[{datetime.now():%H:%M:%S}] {progress.valid}/{progress.expected} valid, {progress.refused} refused, "
              f"{progress.hard} failed after reaching the model", flush=True)
        reason = decide(progress, state, time.time(), args.max_hard_stalls, args.max_wait_hours * 3600)
        if reason == "done":
            return 0
        if reason:
            print(f"stopping: {reason}", flush=True)
            return 1
        time.sleep(args.wait_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
