"""Cache `gitleaks stdin` runs of a shard process on disk, shared by every shard and commit.

PromptGuard's gitleaks voter pipes each text to a new `gitleaks stdin` process. Starting gitleaks and compiling its
rules costs about 20 ms, ten times the rest of the ensemble, and the datasets have about 190k scored items. The run's
output depends only on the binary, its arguments, the config files they name, the ignore and config files in its
working directory, the GITLEAKS_* environment and the input bytes, so the cache key is made of exactly those. A new
commit whose detector change leaves gitleaks alone then reuses every report.

The cache sits at the process boundary (subprocess.run), not in the checkout's adapter, so it does not depend on how
a commit's adapter is written: a call it does not recognise runs as usual. Only calls that capture bytes output and
exit 0 are stored. Never install it for latency measurements.

Reports quote the secrets they found, so the database stays in the data directory, which is not served.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any

IGNORE_FILES = (".gitleaks.toml", ".gitleaksignore")
FLUSH_EVERY = 256
_TEXT_OPTIONS = ("text", "universal_newlines", "encoding", "errors")


def file_digest(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class GitleaksCache:
    def __init__(self, path: Path, run: Any = subprocess.run):
        self.run = run
        self.lock = threading.Lock()
        self.memory: dict[bytes, tuple[bytes, bytes]] = {}
        self.unsaved: list[tuple[bytes, bytes, bytes]] = []
        self.binaries: dict[tuple, str] = {}
        self.hits = self.misses = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        # The shards of one evaluation write side by side; WAL lets them read while another writes.
        self.db = sqlite3.connect(path, timeout=120, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS runs (key BLOB PRIMARY KEY, stdout BLOB NOT NULL, "
                        "stderr BLOB NOT NULL)")

    def _binary(self, program: str) -> str:
        stat = os.stat(program)
        identity = (os.path.realpath(program), stat.st_size, stat.st_mtime_ns)
        if identity not in self.binaries:
            self.binaries[identity] = file_digest(program)
        return self.binaries[identity]

    def key(self, args: list[str], data: bytes, cwd: Any, env: Any) -> bytes:
        digest = hashlib.sha256()

        def part(value: str | bytes) -> None:
            value = value.encode() if isinstance(value, str) else value
            digest.update(len(value).to_bytes(8, "big") + value)

        directory = Path(cwd if cwd is not None else os.getcwd())
        part(self._binary(args[0]))
        for arg in args[1:]:
            part(arg)
            # A path argument (--config, --baseline-path, ...) stands for its content.
            part(file_digest(directory / arg) if (directory / arg).is_file() else "")
        for name in IGNORE_FILES:
            part(file_digest(directory / name) if (directory / name).is_file() else "")
        environment = os.environ if env is None else env
        for name in sorted(name for name in environment if name.startswith("GITLEAKS_")):
            part(name)
            part(environment[name])
        part(data)
        return digest.digest()

    @staticmethod
    def handles(args: Any, kwargs: dict[str, Any]) -> bool:
        return (isinstance(args, (list, tuple)) and len(args) > 1 and all(isinstance(arg, str) for arg in args)
                and os.path.basename(args[0]).startswith("gitleaks") and args[1] == "stdin"
                and isinstance(kwargs.get("input"), bytes) and kwargs.get("capture_output") is True
                and not any(kwargs.get(option) for option in _TEXT_OPTIONS)
                and not kwargs.get("shell") and "stdout" not in kwargs and "stderr" not in kwargs)

    def __call__(self, args: Any, *rest: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        if rest or not self.handles(args, kwargs):
            return self.run(args, *rest, **kwargs)
        args = list(args)
        try:
            key = self.key(args, kwargs["input"], kwargs.get("cwd"), kwargs.get("env"))
        except OSError:  # e.g. a program name not resolved to a file: nothing to fingerprint it by
            return self.run(args, **kwargs)
        found = self.lookup(key)
        if found is not None:
            self.hits += 1
            return subprocess.CompletedProcess(args, 0, *found)
        completed = self.run(args, **kwargs)
        self.misses += 1
        if completed.returncode == 0:
            self.store(key, completed.stdout, completed.stderr)
        return completed

    def lookup(self, key: bytes) -> tuple[bytes, bytes] | None:
        with self.lock:
            if key in self.memory:
                return self.memory[key]
            row = self.db.execute("SELECT stdout, stderr FROM runs WHERE key = ?", (key,)).fetchone()
            if row is not None:
                self.memory[key] = (bytes(row[0]), bytes(row[1]))
                return self.memory[key]
        return None

    def store(self, key: bytes, stdout: bytes, stderr: bytes) -> None:
        with self.lock:
            self.memory[key] = (stdout, stderr)
            self.unsaved.append((key, stdout, stderr))
            if len(self.unsaved) >= FLUSH_EVERY:
                self._flush()

    def _flush(self) -> None:
        if self.unsaved:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.executemany("INSERT OR IGNORE INTO runs VALUES (?, ?, ?)", self.unsaved)
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")
            self.unsaved.clear()

    def close(self) -> None:
        with self.lock:
            self._flush()
            self.db.close()


def install(path: Path) -> GitleaksCache:
    """Route this process's subprocess.run through a cache at path. Call close() before exiting to save new runs."""
    cache = GitleaksCache(path, subprocess.run)
    subprocess.run = cache
    return cache
