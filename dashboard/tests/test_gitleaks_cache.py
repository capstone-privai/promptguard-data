"""The gitleaks cache: a fake gitleaks that logs each run checks what is reused, what is keyed and what passes through."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.gitleaks_cache import GitleaksCache  # noqa: E402

FAKE = """#!/bin/sh
echo run >> "$(dirname "$0")/runs.log"
input=$(cat)
case "$input" in *fail*) exit 1 ;; esac
printf '[{"Secret":"%s","Config":"%s"}]' "$input" "${GITLEAKS_CONFIG:-}"
"""


class GitleaksCacheTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.binary = self.root / "gitleaks"
        self.binary.write_text(FAKE)
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IEXEC)
        self.work = self.root / "work"
        self.work.mkdir()
        self.db = self.root / "cache.sqlite"
        self.cache = self.open()

    def open(self) -> GitleaksCache:
        cache = GitleaksCache(self.db, subprocess.run)
        self.addCleanup(cache.db.close)
        return cache

    def runs(self) -> int:
        log = self.root / "runs.log"
        return len(log.read_text().splitlines()) if log.exists() else 0

    def scan(self, cache: GitleaksCache, text: str, *extra: str, env=None) -> subprocess.CompletedProcess:
        return cache([str(self.binary), "stdin", "--report-format", "json", *extra], input=text.encode(),
                     capture_output=True, timeout=10, cwd=self.work, env=env, check=False)

    def test_same_input_runs_once_and_returns_the_same_output(self):
        first = self.scan(self.cache, "AKIA123")
        second = self.scan(self.cache, "AKIA123")
        self.assertEqual(self.runs(), 1)
        self.assertEqual((second.returncode, second.stdout, second.stderr), (0, first.stdout, first.stderr))
        self.assertEqual((self.cache.hits, self.cache.misses), (1, 1))

    def test_other_processes_and_later_commits_reuse_saved_runs(self):
        self.scan(self.cache, "AKIA123")
        self.cache.close()
        again = self.open()
        self.assertEqual(self.scan(again, "AKIA123").stdout, b'[{"Secret":"AKIA123","Config":""}]')
        self.assertEqual(self.runs(), 1)

    def test_key_covers_input_arguments_config_ignore_files_environment_and_binary(self):
        self.scan(self.cache, "a")
        self.scan(self.cache, "b")
        self.scan(self.cache, "a", "--max-decode-depth", "0")
        config = self.work / "rules.toml"
        config.write_text("one")
        self.scan(self.cache, "a", "--config", "rules.toml")
        config.write_text("two")
        self.scan(self.cache, "a", "--config", "rules.toml")
        (self.work / ".gitleaksignore").write_text("fingerprint")
        self.scan(self.cache, "a")
        self.assertEqual(self.scan(self.cache, "a", env={**os.environ, "GITLEAKS_CONFIG": "x"}).stdout,
                         b'[{"Secret":"a","Config":"x"}]')
        self.binary.write_text(FAKE + "# new version\n")
        self.scan(self.cache, "a")
        self.assertEqual(self.runs(), 8)

    def test_failed_runs_are_not_saved(self):
        self.assertEqual(self.scan(self.cache, "fail").returncode, 1)
        self.assertEqual(self.scan(self.cache, "fail").returncode, 1)
        self.assertEqual(self.runs(), 2)

    def test_other_calls_pass_through(self):
        self.cache([str(self.binary), "stdin"], input=b"a", capture_output=True)
        self.cache([str(self.binary), "stdin"], input=b"a", capture_output=True)
        self.cache([str(self.binary), "stdin"], input="a", capture_output=True, text=True)
        self.cache([str(self.binary), "stdin"], input="a", capture_output=True, text=True)
        self.cache([str(self.binary), "version"], input=b"", capture_output=True)
        self.cache([str(self.binary), "version"], input=b"", capture_output=True)
        self.assertEqual(self.runs(), 5)  # only the bytes stdin scan was cached


if __name__ == "__main__":
    unittest.main()
