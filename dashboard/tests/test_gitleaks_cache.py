"""The gitleaks cache: a fake gitleaks that logs each run checks what is reused, what is keyed and what passes through."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


# Reports the value after PASSWORD= or "password " as [[start, end], ...].
SCANNER = """#!{python}
import json, re, sys
from pathlib import Path
with open(Path(__file__).with_name("runs.log"), "a") as log:
    log.write("run\\n")
text = sys.stdin.buffer.read().decode()
print(json.dumps([m.span(1) for m in re.finditer(r"(?:PASSWORD=|password )(\\S+)", text)]))
"""


class GitleaksSystem:
    """A system under test whose only detector is a gitleaks binary run per text, the way PromptGuard runs it."""

    name = "gitleaks-only"

    def __init__(self, binary: Path):
        self.binary = binary

    def describe(self):
        return {"system": self.name}

    def run_session(self, session):
        from evaluation.adapters.base import ItemOutput
        from evaluation.scorer.edits import Edit, apply_edits

        outputs = {}
        for item in session.items:
            completed = subprocess.run([str(self.binary), "stdin"], input=item.text.encode(), capture_output=True,
                                       check=True)
            edits = [Edit(start, end, "[PASSWORD_1]") for start, end in json.loads(completed.stdout)]
            outputs[item.item_id] = ItemOutput(item.item_id, apply_edits(item.text, edits), edits)
        return outputs


class GoldChangeTest(unittest.TestCase):
    """The cache holds detector output only; scoring against the gold labels is redone on every evaluation."""

    def test_changed_gold_scores_the_same_with_a_warm_cache_as_without_one(self):
        from pipeline.shard import load_range
        from tests.test_collect import FIXTURES, payload_for

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "gitleaks"
            binary.write_text(SCANNER.format(python=sys.executable))
            binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
            runs = root / "runs.log"
            gold = FIXTURES / "gold.jsonl"
            changed = root / "gold_changed.jsonl"
            changed.write_text("".join(gold.read_text().splitlines(keepends=True)[::2]))  # drop every other label
            system = GitleaksSystem(binary)

            def score(gold_path: Path, cache_path: Path | None):
                sessions = load_range(FIXTURES / "sessions.jsonl", gold_path, 0, sys.maxsize)
                if cache_path is None:
                    return payload_for(sessions, system)[0]
                cache = GitleaksCache(cache_path, subprocess.run)
                try:
                    with patch.object(subprocess, "run", cache):
                        return payload_for(sessions, system)[0]
                finally:
                    cache.close()

            original = score(gold, root / "cache.sqlite")
            scanned = len(runs.read_text().splitlines())
            uncached = score(changed, None)
            runs.write_text("")
            warm = score(changed, root / "cache.sqlite")

            self.assertGreater(original["counts"]["edits_tp"], 0)  # the scanner finds some gold
            self.assertNotEqual(warm["counts"], original["counts"])
            self.assertEqual(warm, uncached)
            self.assertEqual(runs.read_text(), "")  # every text came from the cache
            self.assertGreater(scanned, 0)


if __name__ == "__main__":
    unittest.main()
