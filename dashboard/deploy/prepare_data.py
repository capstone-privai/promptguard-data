"""Rebuild the nine documented datasets into a staging directory.

Run with the dashboard stopped, then restart it after this command succeeds.
Downloads and checkpoints live under git-ignored runs/deploy. Existing input
files are preserved unless their content matches the rebuilt files exactly.
"""

from __future__ import annotations

import concurrent.futures
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "runs" / "deploy"
SOURCES = WORK / "sources"
STAGE = WORK / "datasets"
SCRIPTS = ROOT / "metric-detection" / "scripts"
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def run(*args: object, cwd: Path = ROOT) -> None:
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=ENV, check=True)


def download(url: str, target: Path, size: int | None = None) -> None:
    if target.is_file() and (size is None or target.stat().st_size == size):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PromptGuard-dataset-setup/1"})
            with urllib.request.urlopen(request, timeout=120) as source, temp.open("wb") as out:
                shutil.copyfileobj(source, out)
            if size is not None and temp.stat().st_size != size:
                raise ValueError(f"incomplete download: {target.name}")
            temp.replace(target)
            return
        except Exception:
            temp.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def checkout(name: str, repo: str, revision: str) -> Path:
    path = SOURCES / name
    if not (path / ".git").is_dir():
        path.mkdir(parents=True, exist_ok=True)
        run("git", "init", "--quiet", path)
        run("git", "remote", "add", "origin", f"https://github.com/{repo}.git", cwd=path)
    actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True)
    if actual.stdout.strip() != revision:
        run("git", "fetch", "--depth", "1", "origin", revision, cwd=path)
        run("git", "checkout", "--quiet", "--detach", revision, cwd=path)
    return path


def hf_snapshot(name: str, repo: str, revision: str, patterns: list[str]) -> Path:
    path = SOURCES / name
    manifest = WORK / "manifests" / f"{name}.json"
    url = f"https://huggingface.co/api/datasets/{repo}/tree/{revision}?recursive=true&limit=1000"
    # Follow pagination so a larger source cannot silently produce a partial snapshot.
    pages = []
    while url:
        request = urllib.request.Request(url, headers={"User-Agent": "PromptGuard-dataset-setup/1"})
        with urllib.request.urlopen(request, timeout=120) as response:
            pages.extend(json.load(response))
            link = response.headers.get("Link", "")
        url = next((part.split("<", 1)[1].split(">", 1)[0]
                    for part in link.split(",") if 'rel="next"' in part), "")
    selected = [entry for entry in pages if entry["type"] == "file"
                and any(fnmatch.fnmatch(entry["path"], pattern) for pattern in patterns)]
    if not selected:
        raise ValueError(f"no source files: {name}")
    for entry in selected:
        relative = entry["path"]
        target = (path / relative).resolve()
        if not target.is_relative_to(path.resolve()):
            raise ValueError("unsafe dataset path")
        file_url = (f"https://huggingface.co/datasets/{repo}/resolve/{revision}/"
                    f"{urllib.parse.quote(relative, safe='/')}?download=true")
        download(file_url, target, entry["size"])
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"repo": repo, "revision": revision, "files": selected}, indent=2))
    print(f"Downloaded {name}: {len(selected)} files", flush=True)
    return path


def external(name: str, converter: str, option: str, loader, expected: tuple[int, int]) -> None:
    source = loader()
    run(sys.executable, SCRIPTS / converter, option, source, "--out", STAGE)
    sessions = STAGE / "data_test" / f"sessions_from_{name}.jsonl"
    gold = STAGE / "data_answer" / f"gold_from_{name}.jsonl"
    counts = tuple(sum(1 for _ in p.open()) for p in (sessions, gold))
    if counts != expected:
        raise ValueError(f"{name} differs from documented sessions/gold counts: {counts} != {expected}")
    run(sys.executable, SCRIPTS / "dataset_verify.py", sessions, option, source)
    print(f"Validated {name}: {counts}", flush=True)


def creddata() -> Path:
    path = checkout("CredData", "Samsung/CredData", "0b1940e171725ad8937311120b191602608a4801")
    marker = path / ".promptguard-download-complete"
    if not marker.is_file():
        run(sys.executable, path / "download_data.py", "--jobs", 4, "--clean_data", cwd=path)
        marker.touch()
    return path


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    status = WORK / "data-status.json"
    status.write_text(json.dumps({"state": "preparing", "started_at": time.time()}))
    run(sys.executable, SCRIPTS / "dataset_build.py", "--out", STAGE)
    for template, extra in (("example.jsonl", []), ("agent_sessions_2.jsonl", ["--name", "2"])):
        run(sys.executable, SCRIPTS / "dataset_build.py", "--out", STAGE,
            "--template", ROOT / "metric-detection" / "templates" / template, "--origin", "authored", *extra)
    jobs = [
        ("CredData", "convert_creddata.py", "--creddata", creddata, (11030, 15596)),
        ("privesc-llm-data", "convert_privesc.py", "--privesc",
         lambda: hf_snapshot("privesc-llm-data", "sailab-vienna/privesc-llm-data",
                             "39a9d2ff37222184fcaf2a6d9a124906e8bb49ad", ["paper_sft_dataset/*/traces.jsonl", "README.md"]),
         (2200, 10624)),
        ("Nemotron-PII", "convert_nemotron_pii.py", "--nemotron",
         lambda: hf_snapshot("Nemotron-PII", "nvidia/Nemotron-PII", "b70ffaf5ff39e079776134c5bf4381f00a9fd1ed",
                             ["data/test-*", "README.md"]), (6000, 3866)),
        ("openhands-feedback", "convert_openhands_feedback.py", "--openhands",
         lambda: hf_snapshot("openhands-feedback", "all-hands/openhands-feedback", "facf45600d625510b98222ec584a8c9ac59272a2",
                             ["*.parquet", "README.md"]), (275, 47)),
        ("SWE-Gym", "convert_swe_gym.py", "--swe-gym",
         lambda: hf_snapshot("SWE-Gym-OpenHands-SFT-Trajectories", "SWE-Gym/OpenHands-SFT-Trajectories",
                             "4aaa5a4a4b5861f4799d2336908760c190ac3b17", ["*.parquet", "README.md"]), (491, 2)),
        ("noseyparker", "convert_noseyparker.py", "--noseyparker",
         lambda: checkout("noseyparker", "praetorian-inc/noseyparker", "2e6e7f36ce36619852532bbe698d8cb7a26d2da7"),
         (573, 351)),
    ]
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(external, *job): job[0] for job in jobs}
        for future in concurrent.futures.as_completed(tasks):
            try:
                future.result()
            except Exception as error:
                errors.append(f"{tasks[future]}: {error}")
                print(errors[-1], flush=True)
    if errors:
        status.write_text(json.dumps({"state": "failed", "errors": errors}, ensure_ascii=False, indent=2))
        raise RuntimeError("dataset preparation failed; see runs/deploy/data-status.json")
    for sessions in sorted((STAGE / "data_test").glob("sessions*.jsonl")):
        run(sys.executable, SCRIPTS / "dataset_verify.py", sessions, "--skip-rebuild")
    files = [path for folder in ("data_test", "data_answer") for path in (STAGE / folder).glob("*.jsonl")]
    if len(files) != 18:
        raise ValueError(f"expected nine input/answer pairs, got {len(files)} files")
    manifest = {}
    for source in files:
        relative = source.relative_to(STAGE)
        target = ROOT / "metric-detection" / relative
        content = source.read_bytes()
        if target.is_file() and target.read_bytes() != content:
            raise FileExistsError(f"preserving existing different dataset: {target}")
        manifest[str(relative)] = hashlib.sha256(content).hexdigest()
    for source in files:
        target = ROOT / "metric-detection" / source.relative_to(STAGE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(".jsonl.part")
            shutil.copy2(source, temporary)
            temporary.replace(target)
    status.write_text(json.dumps({"state": "ready", "completed_at": time.time(), "sha256": manifest}, indent=2))
    print("All nine datasets are ready. Start/restart pg-dashboard.", flush=True)


if __name__ == "__main__":
    main()
