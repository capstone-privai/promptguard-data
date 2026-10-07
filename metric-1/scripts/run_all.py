"""Run every metric 1 evaluation combination and collect the results in one batch folder.

Run from the repository root:
  python metric-1/scripts/run_all.py                      # every combination (see below)
  python metric-1/scripts/run_all.py --dry-run            # list the combinations without running them
  python metric-1/scripts/run_all.py --systems credsweeper gitleaks --no-sweep --jobs 4

Axes (each defaults to every value):
  dataset       every metric-1/data_test/sessions*.jsonl that has a gold file (--datasets)
  system        promptguard, credsweeper, gitleaks, oracle, identity (--systems)
  ml            credsweeper only: off, on (--ml)
  predictor     promptguard only: every predictor in promptguard.decision.registry (--predictors)
  threshold     promptguard only: none, plus each --thresholds value and each --sweeps range (default 0:1:0.1;
                --no-sweep drops the sweeps)

CredSweeper and gitleaks always scan all four channels (`--channels all`); recall_by_channel in each run
breaks the result down per channel. PromptGuard processes the channels its pipeline handles.

A combination is skipped, with the reason recorded, when the dataset's meta.allowed_use does not include the
purpose the run needs (ml_eval for credsweeper --ml on or a non-mock predictor, else rule_eval), or when a
dependency is missing (credsweeper package, gitleaks executable, PromptGuard checkout). Gitleaks is scanned
once per dataset with run_gitleaks.py before it is scored.

Writes runs/all_<YYYYmmdd-HHMMSS>/ (or --out):
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

from evaluation.adapters.system_root import SystemRootError, resolve_system_root  # noqa: E402
from evaluation.dataset.io import gold_path_for  # noqa: E402

SYSTEMS = ("promptguard", "credsweeper", "gitleaks", "oracle", "identity")
DEFAULT_SWEEPS = ["0:1:0.1"]


@dataclass
class Combo:
    dataset: Path
    system: str
    ml: str | None = None
    predictor: str | None = None
    threshold: float | None = None
    sweep: str | None = None
    skip: str | None = None
    # filled in after running
    status: str = "pending"
    run_dir: str = ""
    seconds: float | None = None
    metrics: dict = field(default_factory=dict)
    note: str = ""

    @property
    def config(self) -> str:
        parts = []
        if self.ml:
            parts.append(f"ml={self.ml}")
        if self.predictor:
            parts.append(f"predictor={self.predictor}")
        if self.threshold is not None:
            parts.append(f"threshold={self.threshold:g}")
        if self.sweep:
            parts.append(f"sweep={self.sweep}")
        return " ".join(parts)

    @property
    def slug(self) -> str:
        text = f"{self.dataset.stem}__{self.system}__{self.config}" if self.config else f"{self.dataset.stem}__{self.system}"
        return re.sub(r"[^A-Za-z0-9._+-]+", "_", text)

    def use(self) -> str:
        if self.system == "credsweeper" and self.ml == "on":
            return "ml_eval"
        if self.system == "promptguard" and self.predictor not in (None, "mock"):
            return "ml_eval"
        return "rule_eval"


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


def discover_predictors(system_root: Path) -> list[str]:
    sys.path.insert(0, str(system_root))
    try:
        from promptguard.decision.registry import available_predictors

        return available_predictors()
    except Exception as exc:  # noqa: BLE001 - fall back to the default rather than abort the batch
        print(f"warning: could not list predictors ({exc}); using mock", file=sys.stderr)
        return ["mock"]


def build_combos(args: argparse.Namespace) -> list[Combo]:
    datasets = discover_datasets(args.datasets)

    have_credsweeper = importlib.util.find_spec("credsweeper") is not None
    have_gitleaks = shutil.which(args.gitleaks) is not None
    system_root, root_error = None, None
    if "promptguard" in args.systems:
        try:
            system_root = resolve_system_root(args.system_root)
        except SystemRootError as exc:
            root_error = str(exc)
    predictors = args.predictors or (discover_predictors(system_root) if system_root else ["mock"])

    missing = {
        "credsweeper": None if have_credsweeper else f"credsweeper is not installed for {sys.executable}",
        "gitleaks": None if have_gitleaks else f"gitleaks executable {args.gitleaks!r} not found",
        "promptguard": root_error or (None if have_credsweeper else f"credsweeper is not installed for {sys.executable}"),
    }

    combos: list[Combo] = []
    for dataset in datasets:
        gold = gold_path_for(dataset)
        dataset_skip = None if Path(gold).is_file() else f"no gold file {gold}"
        uses = allowed_uses(dataset) if dataset_skip is None else set()
        for system in args.systems:
            if system == "credsweeper":
                variants = [Combo(dataset, system, ml=ml) for ml in args.ml]
            elif system == "promptguard":
                variants = []
                for predictor in predictors:
                    variants.append(Combo(dataset, system, predictor=predictor))
                    variants += [Combo(dataset, system, predictor=predictor, threshold=t) for t in args.thresholds]
                    variants += [Combo(dataset, system, predictor=predictor, sweep=s) for s in args.sweeps]
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
        cmd += ["--predictor", combo.predictor, "--system-root", str(args.resolved_system_root)]
        if combo.threshold is not None:
            cmd += ["--threshold", repr(combo.threshold)]
        if combo.sweep:
            cmd += ["--sweep", combo.sweep]
    return cmd


def run_logged(cmd: list[str], log) -> int:
    log.write("$ " + " ".join(cmd) + "\n")
    log.flush()
    return subprocess.run(cmd, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy()).returncode


def read_metrics(run_dir: Path) -> dict:
    data = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    if "summary" not in data:
        return {key: data.get(key) for key in ("recall", "precision", "f2", "fp_per_1k_lines")}
    summary = data["summary"]
    at = summary.get("precision_at_recall") or {}
    best = max((p for p in data["points"] if p.get("f2") is not None), key=lambda p: p["f2"], default=None)
    return {
        "pr_auc": summary.get("pr_auc"),
        "precision_at_recall_0.95": (at.get("0.95") or {}).get("precision"),
        "precision_at_recall_0.99": (at.get("0.99") or {}).get("precision"),
        "best_f2": None if best is None else best["f2"],
        "best_f2_threshold": None if best is None else best["threshold"],
        "recall": None if best is None else best["recall"],
        "precision": None if best is None else best["precision"],
        "f2": None if best is None else best["f2"],
        "fp_per_1k_lines": None if best is None else best["fp_per_1k_lines"],
    }


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

COLUMNS = ["dataset", "system", "config", "status", "recall", "precision", "f2", "fp_per_1k_lines", "pr_auc",
           "precision_at_recall_0.95", "precision_at_recall_0.99", "best_f2_threshold", "seconds", "run_dir", "note"]


def fmt(value, digits: int = 4) -> str:
    if value is None or value == "":
        return ""
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def row(combo: Combo) -> dict:
    return {"dataset": combo.dataset.name, "system": combo.system, "config": combo.config, "status": combo.status,
            **{key: fmt(combo.metrics.get(key)) for key in COLUMNS[4:12]},
            "seconds": fmt(combo.seconds, 1), "run_dir": combo.run_dir, "note": combo.skip or combo.note}


def write_summary(combos: list[Combo], batch: Path) -> None:
    with (batch / "summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(row(c) for c in combos)
    lines = ["# 지표 1 전체 평가", "",
             "sweep 행의 recall, precision, f2, fp_per_1k_lines는 F2가 가장 높은 임계값(`best_f2_threshold`)의 값이다.", ""]
    for dataset in dict.fromkeys(c.dataset.name for c in combos):
        md_cols = ["system", "config", "status", "recall", "precision", "f2", "fp_per_1k_lines", "pr_auc", "run_dir", "note"]
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
    parser.add_argument("--predictors", nargs="+", help="promptguard predictors (default: every registered predictor)")
    parser.add_argument("--thresholds", nargs="*", type=float, default=[], help="extra fixed-threshold promptguard runs")
    parser.add_argument("--sweeps", nargs="*", default=DEFAULT_SWEEPS,
                        help="promptguard sweep ranges START:STOP:STEP (default: 0:1:0.1)")
    parser.add_argument("--no-sweep", action="store_true", help="skip the promptguard sweeps")
    parser.add_argument("--system-root", help="PromptGuard checkout (default: $PROMPTGUARD_ROOT, else ../promptguard-demo-v0)")
    parser.add_argument("--gitleaks", default="gitleaks", help="gitleaks executable")
    parser.add_argument("--jobs", type=int, default=1, help="combinations to run in parallel (default: 1)")
    parser.add_argument("--out", type=Path, help="batch folder (default: runs/all_<timestamp>)")
    parser.add_argument("--dry-run", action="store_true", help="list the combinations and exit")
    args = parser.parse_args()
    if args.no_sweep:
        args.sweeps = []

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

    batch = (args.out or REPO_ROOT / "runs" / f"all_{datetime.now():%Y%m%d-%H%M%S}").resolve()
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
            headline = " ".join(f"{k}={fmt(combo.metrics.get(k))}" for k in ("recall", "precision", "f2", "pr_auc")
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
