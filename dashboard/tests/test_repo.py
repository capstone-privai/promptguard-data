"""Commit listing, fingerprints and export on a small throwaway repository."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import repo  # noqa: E402
from pipeline.service import display_url  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, env=ENV, check=True, capture_output=True)


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "src_repo"
        self.src.mkdir()
        run("git", "init", "-q", "-b", "main", cwd=self.src)
        write(self.src, "README.md", "demo\n")
        run("git", "add", "-A", cwd=self.src)
        run("git", "commit", "-q", "-m", "Start without a detector", cwd=self.src)
        for name, text in {"src/detector/pgdetector/__init__.py": "", "src/detector/worker.py": "# v1\n",
                           "src/detector/detector.json": "{}\n", "requirements.txt": "credsweeper==1.19.0\n",
                           "src/native-mod/hooks/register.mjs": "// mod\n", "docs/notes.md": "a\n"}.items():
            write(self.src, name, text)
        run("git", "add", "-A", cwd=self.src)
        run("git", "commit", "-q", "-m", "Add the detector", cwd=self.src)
        write(self.src, "docs/notes.md", "b\n")
        run("git", "commit", "-q", "-am", "Edit docs only", cwd=self.src)
        run("git", "checkout", "-q", "-b", "feature", cwd=self.src)
        write(self.src, "src/detector/worker.py", "# v2\n")
        run("git", "commit", "-q", "-am", "Faster worker", cwd=self.src)
        run("git", "checkout", "-q", "main", cwd=self.src)
        run("git", "merge", "-q", "--no-ff", "-m", "Merge pull request #5 from team/feature", "-m", "Faster worker",
            "feature", cwd=self.src)
        self.bare = self.root / "data" / "repo.git"
        repo.sync(str(self.src), self.bare, "main")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_evaluable_commits_oldest_first(self):
        commits = repo.commits(self.bare, "main")
        self.assertEqual([commit.subject for commit in commits],
                         ["Add the detector", "Edit docs only", "Faster worker", "Merge pull request #5 from team/feature"])
        add, docs, feature, merge = commits
        self.assertEqual(add.fingerprint, docs.fingerprint)  # docs do not touch the detector
        self.assertNotEqual(docs.fingerprint, feature.fingerprint)
        self.assertEqual(feature.fingerprint, merge.fingerprint)
        self.assertEqual(merge.title, "Faster worker")  # a PR merge is titled by the PR
        self.assertEqual(add.title, "Add the detector")

    def test_fetch_sees_new_commits(self):
        write(self.src, "src/detector/worker.py", "# v3\n")
        run("git", "commit", "-q", "-am", "Even faster", cwd=self.src)
        repo.sync(str(self.src), self.bare, "main")
        self.assertEqual(repo.commits(self.bare, "main")[-1].subject, "Even faster")

    def test_export_holds_only_what_the_evaluators_read(self):
        merge = repo.commits(self.bare, "main")[-1]
        out = repo.export(self.bare, merge.sha, self.root / "checkout")
        files = sorted(path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file())
        self.assertEqual(files, ["requirements.txt", "src/detector/detector.json", "src/detector/pgdetector/__init__.py",
                                 "src/detector/worker.py", "src/native-mod/hooks/register.mjs"])
        self.assertEqual((out / "src/detector/worker.py").read_text(), "# v2\n")
        self.assertEqual(repo.pinned_credsweeper(out), "1.19.0")

    def test_urls(self):
        self.assertEqual(repo.github_web_url("https://github.com/capstone-privai/promptguard-claude-demoV0.git"),
                         "https://github.com/capstone-privai/promptguard-claude-demoV0")
        self.assertEqual(repo.github_web_url("git@github.com:org/name.git"), "https://github.com/org/name")
        self.assertIsNone(repo.github_web_url("/srv/repos/promptguard"))
        self.assertEqual(display_url("https://user:token@github.com/org/name.git"), "https://github.com/org/name.git")


if __name__ == "__main__":
    unittest.main()
