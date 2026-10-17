"""The PromptGuard repository (promptguard-claude-demoV0): fetch its branch, list the commits worth evaluating, and
export the files the evaluators need from one commit.

The commits are the branch's first-parent history: the states the branch itself went through, a merged pull request
being one merge commit. Commits inside a merged branch are left out; that branch started from an older state of
the branch, so between the branch's own commits they would show changes it never had.

A commit can be evaluated once it has the detector package (src/detector/pgdetector), the code both the
metric-detection scorer and the metric-latency worker load. Commits whose src/detector tree and requirements.txt are
the same share a system fingerprint and detection results. Latency results also depend on each commit's timeout.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

DETECTOR_PACKAGE = "src/detector/pgdetector/__init__.py"
# What the evaluators read from a checkout: the detector (worker.py, pgdetector, detector.json), the mod's
# register.mjs (the scorer checks it exists; its substitution rules are re-implemented there), the pinned
# requirements, and promptguard.config.json for metric-latency's timeout.
EXPORT_PATHS = ("src/detector", "src/native-mod/hooks/register.mjs", "requirements.txt", "promptguard.config.json")
PR_MERGE = re.compile(r"Merge pull request #\d+ ")  # GitHub's merge commit: the PR title is the first body line
DEFAULT_TIMEOUT_MS = 5000  # same fallback as metric-latency/scripts/m4.py


class RepoError(Exception):
    pass


def git(*args: str, cwd: Path, binary: bool = False) -> str | bytes:
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RepoError(f"git {' '.join(args[:3])}: {completed.stderr.decode(errors='replace').strip()}")
    return completed.stdout if binary else completed.stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str  # ISO 8601 author date
    author: str
    subject: str
    title: str  # the PR title for a merge commit (first body line), else the subject
    fingerprint: str  # src/detector tree + requirements.txt blob
    timeout_ms: int = DEFAULT_TIMEOUT_MS  # only latency results depend on promptguard.config.json

    @property
    def short(self) -> str:
        return self.sha[:7]

    def as_json(self) -> dict[str, str]:
        return {"sha": self.sha, "short": self.short, "date": self.date, "author": self.author,
                "subject": self.subject, "title": self.title}


def remote_identity(url: str, *, base: Path | None = None) -> str:
    """Normalize local paths the way Git stores clone origins; leave URL/scp remotes exact."""
    if "://" in url or re.match(r"^[^/]+:", url):
        return url
    local = Path(url).expanduser()
    return str(((base or Path.cwd()) / local).resolve())


def sync(url: str, path: Path, branch: str) -> None:
    """Clone (bare) on first use, then fetch only if origin still matches the requested repository."""
    url = remote_identity(url)
    if not (path / "HEAD").is_file():
        shutil.rmtree(path, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "--bare", "--single-branch", "--branch", branch, url, str(path), cwd=path.parent)
    origin = git("remote", "get-url", "origin", cwd=path).strip()
    if remote_identity(origin, base=path) != url:
        # Do not publish the old project's commits under a new configured URL. Keep the old clone/results intact.
        # Avoid including either URL here: authenticated remotes may contain credentials.
        raise RepoError("the data directory belongs to a different repository; use a separate --data-dir")
    git("fetch", "--prune", "origin", f"+refs/heads/{branch}:refs/heads/{branch}", cwd=path)


def detector_timeout(config: str) -> int:
    """The configured detector timeout, or the measurement default if no positive integer was provided."""
    try:
        value = json.loads(config)
    except json.JSONDecodeError:
        return DEFAULT_TIMEOUT_MS
    timeout = value.get("detectorTimeoutMs") if isinstance(value, dict) else None
    return timeout if type(timeout) is int and timeout > 0 else DEFAULT_TIMEOUT_MS


def commits(path: Path, branch: str) -> list[Commit]:
    """Evaluable commits of the branch's first-parent history, oldest first."""
    log = git("log", "--first-parent", "--reverse", "--format=%H%x1f%aI%x1f%an%x1f%s%x1f%b%x1e",
              f"refs/heads/{branch}", cwd=path)
    entries = [entry.strip("\n").split("\x1f") for entry in log.split("\x1e") if entry.strip()]
    found = []
    for sha, date, author, subject, body in entries:
        if not git("ls-tree", "--name-only", sha, "--", DETECTOR_PACKAGE, cwd=path).strip():
            continue
        trees = git("rev-parse", f"{sha}:src/detector", f"{sha}:requirements.txt", cwd=path).split()
        fingerprint = hashlib.sha256(" ".join(trees).encode()).hexdigest()
        first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
        title = first_line if PR_MERGE.match(subject) and first_line else subject
        try:
            config = git("show", f"{sha}:promptguard.config.json", cwd=path)
        except RepoError:  # older commits may not have a config file
            config = "{}"
        found.append(Commit(sha, date, author, subject, title, fingerprint, detector_timeout(config)))
    return found


def describe(path: Path, sha: str) -> dict[str, str] | None:
    """sha, short, date, author, subject and title of any commit the clone has, else None."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        return None
    try:
        out = git("log", "-1", "--format=%H%x1f%aI%x1f%an%x1f%s%x1f%b", sha, "--", cwd=path)
    except RepoError:
        return None
    full, date, author, subject, body = (out.strip("\n").split("\x1f") + [""] * 5)[:5]
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return {"sha": full, "short": full[:7], "date": date, "author": author, "subject": subject,
            "title": first_line if PR_MERGE.match(subject) and first_line else subject}


def export(path: Path, sha: str, dest: Path) -> Path:
    """Write the files the evaluators read from `sha` into dest (replaced) and return it."""
    present = [item for item in EXPORT_PATHS
               if git("ls-tree", "--name-only", sha, "--", item, cwd=path).strip()]
    archive = git("archive", "--format=tar", sha, *present, cwd=path, binary=True)
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not target.is_relative_to(dest.resolve()) or member.issym() or member.islnk():
                raise RepoError(f"refusing archive member {member.name!r}")
        tar.extractall(dest)
    return dest


def pinned_credsweeper(root: Path) -> str | None:
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name, separator, version = line.split("#", 1)[0].partition("==")
        if separator and name.strip().lower() == "credsweeper":
            return version.strip()
    return None


def installed_credsweeper(python: str) -> str | None:
    completed = subprocess.run(
        [python, "-c", "import importlib.metadata as m; print(m.version('credsweeper'))"],
        capture_output=True, text=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def python_for(root: Path, base_python: str, venv_root: Path, auto_venv: bool) -> str:
    """A Python that has the CredSweeper version the checkout pins: `base_python` if it does, else (with auto_venv)
    a virtual environment per requirements.txt content, created on first use."""
    pinned = pinned_credsweeper(root)
    if pinned is None or installed_credsweeper(base_python) == pinned:
        return base_python
    if not auto_venv:
        raise RepoError(f"the checkout pins credsweeper=={pinned}, but {base_python} has "
                        f"{installed_credsweeper(base_python) or 'none'}")
    requirements = (root / "requirements.txt").read_bytes()
    venv = venv_root / hashlib.sha256(requirements).hexdigest()[:12]
    python = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if not Path(python).is_file() or installed_credsweeper(python) != pinned:
        shutil.rmtree(venv, ignore_errors=True)
        for command in ([base_python, "-m", "venv", str(venv)],
                        [python, "-m", "pip", "install", "--quiet", "-r", str(root / "requirements.txt")]):
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0:
                tail = (completed.stderr or completed.stdout).strip().splitlines()
                raise RepoError(f"{' '.join(command[1:3])} failed: {tail[-1] if tail else completed.returncode}")
    return python


def github_web_url(url: str) -> str | None:
    """https://github.com/<owner>/<repo> for a GitHub remote, so the UI can link commits."""
    found = re.match(r"(?:https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return f"https://github.com/{found.group(1)}" if found else None
