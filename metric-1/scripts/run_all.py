"""Run every metric 1 evaluation combination and collect the results in one batch folder.

Run from the repository root:
  python metric-1/scripts/run_all.py                      # every combination (see below)
  python metric-1/scripts/run_all.py --dry-run            # list the combinations without running them
  python metric-1/scripts/run_all.py --systems credsweeper gitleaks --jobs 4

Axes (each defaults to every value):
  dataset       every metric-1/data_test/sessions*.jsonl that has a gold file (--datasets)
  system        promptguard, credsweeper, gitleaks, oracle, identity (--systems)
  ml            credsweeper only: off, on (--ml)

CredSweeper and gitleaks always scan all four channels (`--channels all`); recall_by_channel in each run
breaks the result down per channel. PromptGuard processes the channels its Claude Code mod rewrites.

A combination is skipped, with the reason recorded, when the dataset's meta.allowed_use does not include the
purpose the run needs (ml_eval for credsweeper --ml on, else rule_eval), or when a dependency is missing
(credsweeper package, gitleaks executable, promptguard-claude-demoV0 checkout and its pinned credsweeper).
Gitleaks is scanned once per dataset with run_gitleaks.py before it is scored.

Writes metric-1/results/all_<YYYYmmdd-HHMMSS>/ (or --out):
  <system>_.../     one evaluate.py run folder per combination
  gitleaks/         findings files from run_gitleaks.py
  logs/             each combination's evaluate.py (and run_gitleaks.py) output
  summary.csv, summary.md   one row per combination: status, headline metrics, run folder

Exit code 0 if every combination ran, 1 if any failed or was skipped.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from dataclasses import dataclass, field
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

METRIC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = METRIC_ROOT.parent
SCRIPTS = METRIC_ROOT / "scripts"
sys.path.insert(0, str(METRIC_ROOT))

from evaluation.adapters.system_root import SystemRootError, check_credsweeper, resolve_system_root  # noqa: E402
from evaluation.dataset.io import gold_path_for  # noqa: E402

SYSTEMS = ("promptguard", "credsweeper", "gitleaks", "oracle", "identity")


@dataclass
class Combo:
    dataset: Path
    system: str
    ml: str | None = None
    skip: str | None = None
    # filled in after running
    status: str = "pending"
    run_dir: str = ""
    seconds: float | None = None
    metrics: dict = field(default_factory=dict)
    note: str = ""

    @property
    def config(self) -> str:
        return f"ml={self.ml}" if self.ml else ""

    @property
    def slug(self) -> str:
        text = f"{self.dataset.stem}__{self.system}__{self.config}" if self.config else f"{self.dataset.stem}__{self.system}"
        return re.sub(r"[^A-Za-z0-9._+-]+", "_", text)

    def use(self) -> str:
        return "ml_eval" if self.system == "credsweeper" and self.ml == "on" else "rule_eval"


# ---------------------------------------------------------------- axes

def discover_datasets(selected: list[str] | None) -> list[Path]:
    found = sorted((METRIC_ROOT / "data_test").glob("sessions*.jsonl"))
    if not selected:
        return found
    out = []
    for name in selected:
        path = Path(name)
        if path.is_file():
            out.append(path.resolve())
            continue
        matches = [p for p in found if name in (p.name, p.stem, p.stem.removeprefix("sessions").lstrip("_"))]
        if not matches:
            raise SystemExit(f"no dataset {name!r}; available: {[p.name for p in found]}")
        out += matches
    return list(dict.fromkeys(out))


def allowed_uses(path: Path) -> set[str]:
    """Purposes every session in the file allows (the evaluator refuses a run otherwise)."""
    uses: set[str] | None = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                session_uses = set(json.loads(line).get("meta", {}).get("allowed_use", []))
                uses = session_uses if uses is None else uses & session_uses
    return uses or set()


def build_combos(args: argparse.Namespace) -> list[Combo]:
    datasets = discover_datasets(args.datasets)

    have_credsweeper = importlib.util.find_spec("credsweeper") is not None
    have_gitleaks = shutil.which(args.gitleaks) is not None
    system_root, root_error = None, None
    if "promptguard" in args.systems:
        try:
            system_root = resolve_system_root(args.system_root)
            check_credsweeper(system_root)
        except SystemRootError as exc:
            root_error = str(exc)

    missing = {
        "credsweeper": None if have_credsweeper else f"credsweeper is not installed for {sys.executable}",
        "gitleaks": None if have_gitleaks else f"gitleaks executable {args.gitleaks!r} not found",
        "promptguard": root_error,
    }

    combos: list[Combo] = []
    for dataset in datasets:
        gold = gold_path_for(dataset)
        dataset_skip = None if Path(gold).is_file() else f"no gold file {gold}"
        uses = allowed_uses(dataset) if dataset_skip is None else set()
        for system in args.systems:
            if system == "credsweeper":
                variants = [Combo(dataset, system, ml=ml) for ml in args.ml]
            else:
                variants = [Combo(dataset, system)]
            for combo in variants:
                combo.skip = (dataset_skip or missing.get(system)
                              or (None if combo.use() in uses else f"dataset does not allow {combo.use()}"))
            combos += variants
    args.resolved_system_root = system_root
    return combos


# ---------------------------------------------------------------- running

def evaluate_command(combo: Combo, args: argparse.Namespace, batch: Path, findings: Path | None) -> list[str]:
    cmd = [sys.executable, str(SCRIPTS / "evaluate.py"), "run", "--system", combo.system,
           "--sessions", str(combo.dataset), "--out", str(batch)]
    if combo.system == "credsweeper":
        cmd += ["--ml", combo.ml]
        cmd += ["--channels", "all"]
    elif combo.system == "gitleaks":
        cmd += ["--findings", str(findings)]
    elif combo.system == "promptguard":
        cmd += ["--system-root", str(args.resolved_system_root)]
    return cmd


def run_logged(cmd: list[str], log) -> int:
    log.write("$ " + " ".join(cmd) + "\n")
    log.flush()
    return subprocess.run(cmd, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy()).returncode


def read_metrics(run_dir: Path) -> dict:
    data = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    return {key: data.get(key) for key in ("recall", "precision", "f2", "fp_per_1k_lines")}


def run_combo(combo: Combo, args: argparse.Namespace, batch: Path) -> None:
    log_path = batch / "logs" / f"{combo.slug}.log"
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        findings = None
        if combo.system == "gitleaks":
            findings = batch / "gitleaks" / f"{combo.dataset.stem}.jsonl"
            code = run_logged([sys.executable, str(SCRIPTS / "run_gitleaks.py"), "--sessions", str(combo.dataset),
                               "--channels", "all", "--out", str(findings), "--gitleaks", args.gitleaks], log)
            if code != 0:
                combo.status, combo.note = "failed", f"run_gitleaks.py exit {code}"
                combo.seconds = time.perf_counter() - started
                return
        code = run_logged(evaluate_command(combo, args, batch, findings), log)
    combo.seconds = time.perf_counter() - started
    output = log_path.read_text(encoding="utf-8")
    if match := re.search(r"^results: (.+)$", output, re.MULTILINE):
        combo.run_dir = match.group(1).strip()
    if code == 0 and combo.run_dir:
        combo.status = "ok"
        combo.metrics = read_metrics(Path(combo.run_dir) if Path(combo.run_dir).is_absolute() else REPO_ROOT / combo.run_dir)
    else:
        combo.status = "failed"
        last = [line for line in output.splitlines() if line.strip()][-1:] or [""]
        combo.note = f"exit {code}: {last[0][:200]}"


# ---------------------------------------------------------------- reporting

COLUMNS = ["dataset", "system", "config", "status", "recall", "precision", "f2", "fp_per_1k_lines", "seconds",
           "run_dir", "note"]


def fmt(value, digits: int = 4) -> str:
    if value is None or value == "":
        return ""
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def row(combo: Combo) -> dict:
    return {"dataset": combo.dataset.name, "system": combo.system, "config": combo.config, "status": combo.status,
            **{key: fmt(combo.metrics.get(key)) for key in COLUMNS[4:8]},
            "seconds": fmt(combo.seconds, 1), "run_dir": combo.run_dir, "note": combo.skip or combo.note}


def write_summary(combos: list[Combo], batch: Path) -> None:
    with (batch / "summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(row(c) for c in combos)
    lines = ["# 지표 1 전체 평가", ""]
    for dataset in dict.fromkeys(c.dataset.name for c in combos):
        md_cols = ["system", "config", "status", "recall", "precision", "f2", "fp_per_1k_lines", "run_dir", "note"]
        lines += [f"## {dataset}", "", "| " + " | ".join(md_cols) + " |", "|" + "---|" * len(md_cols)]
        for c in combos:
            if c.dataset.name == dataset:
                r = row(c)
                r["run_dir"] = Path(r["run_dir"]).name if r["run_dir"] else ""
                lines.append("| " + " | ".join(str(r[k]).replace("|", "\\|") for k in md_cols) + " |")
        lines.append("")
    (batch / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description="Run every metric 1 evaluation combination")
    parser.add_argument("--datasets", nargs="+", help="sessions files or names (e.g. sessions_2, from_CredData); default: all")
    parser.add_argument("--systems", nargs="+", choices=SYSTEMS, default=list(SYSTEMS))
    parser.add_argument("--ml", nargs="+", choices=("off", "on"), default=["off", "on"], help="credsweeper ML settings")
    parser.add_argument("--system-root", help="promptguard-claude-demoV0 checkout "
                                              "(default: $PROMPTGUARD_CLAUDE_ROOT, else ../promptguard-claude-demoV0)")
    parser.add_argument("--gitleaks", default="gitleaks", help="gitleaks executable")
    parser.add_argument("--jobs", type=int, default=1, help="combinations to run in parallel (default: 1)")
    parser.add_argument("--out", type=Path, help="batch folder (default: metric-1/results/all_<timestamp>)")
    parser.add_argument("--dry-run", action="store_true", help="list the combinations and exit")
    args = parser.parse_args()

    combos = build_combos(args)
    runnable = [c for c in combos if not c.skip]
    skipped = [c for c in combos if c.skip]
    for c in combos:
        c.status = "skipped" if c.skip else c.status
    print(f"{len(combos)} combinations: {len(runnable)} to run, {len(skipped)} skipped")
    if args.dry_run:
        for c in combos:
            print(f"  {'SKIP' if c.skip else 'RUN '} {c.dataset.name:42} {c.system:12} {c.config}"
                  + (f"  ({c.skip})" if c.skip else ""))
        return 0

    batch = (args.out or METRIC_ROOT / "results" / f"all_{datetime.now():%Y%m%d-%H%M%S}").resolve()
    (batch / "logs").mkdir(parents=True, exist_ok=True)
    (batch / "gitleaks").mkdir(exist_ok=True)
    print(f"batch: {batch}")
    for c in skipped:
        print(f"  skip {c.dataset.name} {c.system} {c.config}: {c.skip}")

    print_lock = threading.Lock()
    done = 0

    def task(combo: Combo) -> None:
        nonlocal done
        try:
            run_combo(combo, args, batch)
        except Exception as exc:  # noqa: BLE001 - one broken combination must not stop the batch
            combo.status, combo.note = "failed", f"{type(exc).__name__}: {exc}"
        with print_lock:
            done += 1
            headline = " ".join(f"{k}={fmt(combo.metrics.get(k))}" for k in ("recall", "precision", "f2")
                                if combo.metrics.get(k) is not None)
            print(f"[{done}/{len(runnable)}] {combo.status:6} {combo.dataset.name} {combo.system} {combo.config} "
                  f"({fmt(combo.seconds, 1)}s) {headline or combo.note}", flush=True)
            write_summary(combos, batch)

    write_summary(combos, batch)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        list(pool.map(task, runnable))
    write_summary(combos, batch)

    failed = [c for c in combos if c.status == "failed"]
    print(f"\nsummary: {batch / 'summary.md'}")
    print(f"ok {len(runnable) - len(failed)}, failed {len(failed)}, skipped {len(skipped)}")
    for c in failed:
        print(f"  failed {c.dataset.name} {c.system} {c.config}: {c.note} (log: logs/{c.slug}.log)")
    return 1 if failed or skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
