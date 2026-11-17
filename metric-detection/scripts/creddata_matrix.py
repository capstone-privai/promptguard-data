"""Score selected PromptGuard main-branch commits combined with ML span models on the CredData-trajectory test set.

The matrix is fixed here: COMMITS are the systems, MODELS the span models with their publish times. A commit gets
`base` (the commit as shipped, ML adapters off) and every model published before the next selected commit; the last
commit (current main) gets every model. A commit without ML adapters gets `base` only.

Each commit is unpacked once (git archive, no worktree). For a model, a copy of the commit gets a detector.json in
which exactly one ML adapter is enabled (`required: true`, so a model that fails to load stops the run) and pointed at
the model: ml-span, or ml-v9 before ml-span existed. Its other options are the commit's defaults; `--device` overrides
the device of that adapter only. Each copy is scored by the dashboard's shard runner (same scorer, shared gitleaks
cache). The CredData-trajectory token classifiers are ml-span bundles built from their training output; they are
looked up under $MATRIX_BUNDLES (default runs/creddata-traj-eval/bundles).

  python3 metric-detection/scripts/creddata_matrix.py plan
  python3 metric-detection/scripts/creddata_matrix.py run --jobs 3 [--models base v10] [--commits e9089c2] [--device cuda]
  python3 metric-detection/scripts/creddata_matrix.py report

Work files and results are under runs/creddata-traj-eval (git-ignored); report writes
metric-detection/results/creddata-trajectory/summary.{csv,md}, with the CredSweeper-only prototype
(`evaluate.py run --system credsweeper --ml off --out runs/creddata-traj-eval/results/credsweeper-mloff`) as first row.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "runs/creddata-traj-eval"
SYSTEM_REPO = ROOT.parent / "promptguard-claude-demoV0"
MODEL_REPO = ROOT.parent / "promptguard-model"
BUNDLES = Path(os.environ.get("MATRIX_BUNDLES") or WORK / "bundles")
STEM = "sessions_from_CredData-trajectory"
DATA = ROOT / "metric-detection/data_test"
OUT = ROOT / "metric-detection/results/creddata-trajectory"
# torch, transformers and the pinned credsweeper
PYTHON = Path(os.environ.get("MATRIX_PYTHON") or ROOT / "runs/e2e-20261106/env/bin/python")
COMMITS = ["424df6a", "d7072b4", "ca858be", "ff87b4c", "f07bbfb", "9e80dc4", "e9089c2", "668c2c1"]
# name -> (model folder, published). A relative folder is in the model repository.
MODELS = {
    "v10": ("models/span-detector-v10", "2026-11-02T16:10+09:00"),
    "pilot-b-seed110": ("models/span-pilot-step0-b-seed110", "2026-11-10T22:38+09:00"),
    "pilot-b-seed112": ("models/span-pilot-step0-b-seed112", "2026-11-10T22:53+09:00"),
    "pilot-bv10-seed112": ("models/span-pilot-step0-bv10-seed112", "2026-11-10T22:53+09:00"),
    "mmbert-traj": (str(BUNDLES / "token-span-creddata-mmbert"), "2026-11-16T23:01+09:00"),
    "qwen-traj": (str(BUNDLES / "token-span-creddata-qwen"), "2026-11-16T23:01+09:00"),
}
PROTOTYPE = "credsweeper-mloff"

sys.path.insert(0, str(ROOT / "dashboard"))


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def ml_adapters(sha: str) -> list[str]:
    config = json.loads(git(SYSTEM_REPO, "show", f"{sha}:src/detector/detector.json"))
    return [a["name"] for a in config.get("adapters", []) if str(a.get("name", "")).startswith("ml-")]


def commits() -> list[dict]:
    """COMMITS oldest first, each with its ML adapters and the configurations the matrix gives it."""
    found = []
    for prefix in COMMITS:
        sha, when, subject = git(SYSTEM_REPO, "log", "-1", "--format=%H %cI %s", prefix).decode().strip().split(" ", 2)
        found.append({"sha": sha, "time": datetime.fromisoformat(when), "date": when[:10], "subject": subject,
                      "ml_adapters": ml_adapters(sha)})
    found.sort(key=lambda c: c["time"])
    for index, commit in enumerate(found):
        later = found[index + 1]["time"] if index + 1 < len(found) else None
        models = [name for name, (_, published) in MODELS.items()
                  if later is None or datetime.fromisoformat(published) < later] if commit["ml_adapters"] else []
        commit["models"] = ["base", *models]
    return found


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def model_folder(name: str) -> Path:
    return MODEL_REPO / MODELS[name][0]  # an absolute folder stays as it is


def model_identity(name: str) -> dict:
    folder = model_folder(name)
    identity = {"model": name, "path": str(folder), "weights_sha256": digest(folder / "model.safetensors")}
    if folder.is_relative_to(MODEL_REPO):
        identity["model_repo_commit"] = git(MODEL_REPO, "rev-parse", "HEAD").decode().strip()
    return identity


def checkout(commit: dict, model: str, device: str | None) -> tuple[Path, str | None]:
    """A copy of the commit configured for the model; returns it and the ML adapter that must run (None for base)."""
    if model not in commit["models"]:
        raise ValueError(f"{model} is not in the matrix for {commit['sha'][:7]}")
    wanted = None if model == "base" else ("ml-span" if "ml-span" in commit["ml_adapters"] else "ml-v9")
    root = WORK / "systems" / commit["sha"][:7] / (model if device is None or wanted is None else f"{model}-{device}")
    target = root / "src/detector/detector.json"
    if not target.is_file():
        root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(git(SYSTEM_REPO, "archive", commit["sha"]))) as archive:
            archive.extractall(root, filter="data")
    shipped = git(SYSTEM_REPO, "show", f"{commit['sha']}:src/detector/detector.json")
    if wanted is None:
        target.write_bytes(shipped)
        return root, None
    config = json.loads(shipped)
    for adapter in config["adapters"]:
        if adapter["name"] == wanted:
            adapter["enabled"] = True
            adapter["required"] = True
            adapter["options"]["repository"] = str(MODEL_REPO)
            adapter["options"]["checkpoint"] = str(model_folder(model))
            if device:
                adapter["options"]["device"] = device
        elif adapter["name"].startswith("ml-"):
            adapter["enabled"] = False
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return root, wanted


PROBE = """
import json, sys
sys.path.insert(0, sys.argv[1])
from evaluation.adapters.system_root import load_worker
detector = load_worker(sys.argv[2]).load_detector()
info = detector.describe()
out = {"adapters": [a["name"] for a in info["adapters"]], "skipped": info.get("skipped")}
for adapter in detector.adapters:
    if adapter.name.startswith("ml-"):
        model = getattr(adapter, "model", None)
        out["ml"] = {"name": adapter.name, "model_id": getattr(adapter, "model_id", None),
                     "threshold": getattr(model, "threshold", None), "timeout": getattr(adapter, "timeout", None),
                     "device": str(getattr(model, "device", None))}
print(json.dumps(out))
"""


def probe(root: Path) -> dict:
    result = subprocess.run([str(PYTHON), "-c", PROBE, str(ROOT / "metric-detection"), str(root)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "probe failed")
    return json.loads(result.stdout.strip().splitlines()[-1])


def result_dir(commit: dict, model: str) -> Path:
    return WORK / "results" / commit["sha"][:7] / model


def run_one(commit: dict, model: str, jobs: int, datasets, bench, device: str | None) -> dict:
    from pipeline import runner
    out = result_dir(commit, model)
    if (out / "meta.json").is_file():
        return json.loads((out / "meta.json").read_text())["headline"]
    root, required = checkout(commit, model, device)
    info = probe(root)
    ml = [name for name in info["adapters"] if name.startswith("ml-")]
    if ml != ([required] if required else []):
        raise RuntimeError(f"ML adapters running: {ml}, expected {required}; skipped: {info['skipped']}")
    if required and device and not info["ml"]["device"].startswith(device):
        raise RuntimeError(f"{required} runs on {info['ml']['device']}, not {device}")
    identity = {"model": "base"} if model == "base" else {**model_identity(model), "adapter": info["ml"]}
    config_hash = digest(root / "src/detector/detector.json")
    fingerprint = f"{commit['sha'][:12]}:{model}:{config_hash[:12]}:{identity.get('weights_sha256', '')[:12]}"
    return runner.evaluate(
        root, datasets, out, python=str(PYTHON), jobs=jobs, cache_dir=WORK / "validated",
        commit={"sha": commit["sha"], "date": commit["date"], "subject": commit["subject"], "config": model,
                "detector_json_sha256": config_hash, "detector_adapters": info["adapters"], **identity},
        system_fingerprint=fingerprint, bench=bench, resume_dir=WORK / "resume" / commit["sha"][:7] / model,
        gitleaks_cache=WORK / "gitleaks-cache.sqlite")


def f2(precision, recall):
    if precision is None or recall is None:
        return None
    return 0.0 if precision + recall == 0 else 5 * precision * recall / (4 * precision + recall)


def prototype_row() -> dict | None:
    runs = sorted((WORK / "results" / PROTOTYPE).glob("*/metrics.json"))
    if not runs:
        return None
    metrics = json.loads(runs[-1].read_text())
    counts = metrics.get("counts", {})
    return {"commit": "prototype", "date": "", "model": "base", "ml_adapter": "",
            "recall": metrics["recall"], "precision": metrics["precision"], "f2": metrics["f2"],
            "exact_recall": metrics["exact_recall"], "edit_precision": metrics["edit_precision"],
            "exact_f2": metrics["exact_f2"],
            **{k: counts.get(k) for k in ("exact", "over", "partial", "missed", "edits_fp", "masked_chars",
                                          "masked_gold_chars")},
            "gold": counts.get("gold_total"), "edits": counts.get("edits_total"), "items": metrics.get("items"),
            "result": str(runs[-1].parent.relative_to(WORK))}


def report(found: list[dict]):
    models = ["base", *MODELS]
    rows, missing = [], []
    prototype = prototype_row()
    if prototype:
        rows.append(prototype)
    for commit in found:
        for model in commit["models"]:
            meta_path = result_dir(commit, model) / "meta.json"
            if not meta_path.is_file():
                missing.append(f"{commit['sha'][:7]}/{model}")
                continue
            meta = json.loads(meta_path.read_text())
            summary = json.loads((meta_path.parent / "summary.json").read_text())
            fact = next(f for f in summary["datasets"] if f["key"] == STEM)
            counts = summary["totals"]["counts"]  # the only dataset, so the totals are its counts
            head = meta["headline"]["datasets"][STEM]
            rows.append({"commit": commit["sha"][:7], "date": commit["date"], "model": model,
                         "ml_adapter": (meta["commit"].get("adapter") or {}).get("name", ""),
                         "recall": head["recall"], "precision": head["precision"],
                         "f2": f2(head["precision"], head["recall"]),
                         "exact_recall": head["exact_recall"], "edit_precision": head["edit_precision"],
                         "exact_f2": f2(head["edit_precision"], head["exact_recall"]),
                         **{k: counts.get(k) for k in ("exact", "over", "partial", "missed", "edits_fp", "masked_chars",
                                                       "masked_gold_chars")},
                         **{k: fact.get(k) for k in ("gold", "edits", "items", "blocked", "failed_open", "seconds")},
                         "result": str(meta_path.parent.relative_to(WORK))})
    OUT.mkdir(parents=True, exist_ok=True)
    if not rows:
        print("no results yet")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    labels = [("prototype", "", "프로토타입: CredSweeper만, ML 꺼짐")] + [
        (c["sha"][:7], c["date"], c["subject"].split(" from ")[0].replace("Merge pull request ", "")) for c in found]
    lines = ["# CredData-trajectory test: 시스템 커밋 × ML 모델", "",
             "지표 정의 (채점 채널 prompt, instructions, tool_output만 센다):", "",
             "- **recall** = 다 가려진 정답 span / 정답 span. 정답 span의 글자가 모두 가려졌으면 찾은 것으로 센다"
             "(채점기의 exact와 over). 일부만 가려졌거나(partial) 하나도 안 가려졌으면(missed) 못 찾은 것이다.",
             "- **precision** = 가린 글자 가운데 정답 글자의 비율. item마다 원문 좌표에서 "
             "가린 글자 = edit가 바꾼 글자의 합집합, 가린 정답 글자 = 그 가운데 정답 span 안에 있는 글자를 세고, "
             "Σ 가린 정답 글자 / Σ 가린 글자로 계산한다. fail-closed로 차단된 item은 item 글자 전체를 가린 것으로 센다.",
             "- **F2** = 5PR / (4P + R). recall에 precision보다 4배 무게를 둔다.",
             "- 예전 지표는 summary.csv에 남겼다: exact_recall = 정확히 가린 정답 / 정답, edit_precision = 정답 span "
             "하나 안에 든 edit / 전체 edit, exact_f2 = 그 둘의 F2.", "",
             "`base`는 ML 어댑터를 끈 커밋 그대로다. `-`는 그 조합이 행렬에 없거나 결과가 없다는 뜻이다. "
             "조건은 RUN_NOTES.md.", ""]
    for metric, fmt in (("f2", "{:.3f}"), ("recall", "{:.3f}"), ("precision", "{:.3f}"), ("blocked", "{}")):
        title = metric if metric != "blocked" else "blocked (fail-closed로 item 전체를 가린 수)"
        lines += [f"## {title}", "", "| 시스템 | 날짜 | " + " | ".join(models) + " |", "|---|---|" + "---:|" * len(models)]
        for key, date, name in labels:
            cells = {r["model"]: r.get(metric) for r in rows if r["commit"] == key}
            show = lambda m: "-" if cells.get(m) is None else fmt.format(cells[m])
            lines.append(f"| {key} {name} | {date} | " + " | ".join(show(m) for m in models) + " |")
        lines.append("")
    if missing:
        lines += ["결과가 없는 조합: " + ", ".join(missing), ""]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} results -> {OUT}" + (f"; missing {', '.join(missing)}" if missing else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("plan", "run", "report"))
    parser.add_argument("--models", nargs="*", help="only these configurations of the matrix")
    parser.add_argument("--commits", nargs="*", help="only these commits of the matrix (sha prefixes)")
    parser.add_argument("--device", help="device of the enabled ML adapter (e.g. cuda); default the commit's own")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    found = commits()
    if args.command == "report":
        report(found)
        return
    if args.commits:
        found = [c for c in found if any(c["sha"].startswith(prefix) for prefix in args.commits)]
    for commit in found:
        commit["run"] = [m for m in commit["models"] if not args.models or m in args.models]
    if args.command == "plan":
        for commit in found:
            print(commit["sha"][:7], commit["time"].isoformat(timespec="minutes"), ",".join(commit["ml_adapters"]) or "-",
                  " ".join(commit["run"]))
        print(f"{sum(len(c['run']) for c in found)} combinations ({sum(len(c['run']) - ('base' in c['run']) for c in found)} with ML)")
        return
    from pipeline import runner
    from pipeline.gitleaks_cache import GitleaksCache
    datasets = [d for d in runner.discover(DATA) if d.stem == STEM]
    if len(datasets) != 1:
        parser.error(f"{STEM}.jsonl and its gold file are not in {DATA}; run creddata_eval_set.py first")
    bench = runner.benchmark(datasets)
    WORK.mkdir(parents=True, exist_ok=True)
    GitleaksCache(WORK / "gitleaks-cache.sqlite").close()  # switch the file to WAL before shards open it
    log = (WORK / "matrix.log").open("a", encoding="utf-8")
    for model in ["base", *MODELS]:  # model by model, so the first pass over the commits fills the gitleaks cache
        for commit in [c for c in found if model in c["run"]]:
            started = time.time()
            record = {"at": time.strftime("%FT%TZ", time.gmtime()), "commit": commit["sha"][:7], "model": model,
                      "device": args.device}
            try:
                headline = run_one(commit, model, args.jobs, datasets, bench, args.device)
                record.update(status="ok", seconds=round(time.time() - started), **headline["datasets"][STEM])
            except Exception as error:  # one failed combination must not stop the rest; it is listed in the log
                record.update(status="failed", error=f"{type(error).__name__}: {error}"[:500])
            log.write(json.dumps(record) + "\n")
            log.flush()
            print(json.dumps(record), flush=True)
    report(commits())


if __name__ == "__main__":
    main()
