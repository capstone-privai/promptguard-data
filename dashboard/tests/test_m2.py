"""Batch provenance and resume checks use throwaway Git repos and never invoke Claude."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "metric-task/scripts"))
import m2


class BatchProvenanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.system = self.root / "system"
        self.data = self.root / "data"
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        for folder in (self.system, self.data):
            folder.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=folder, env=env, check=True)
            (folder / "code.py").write_text("# original\n")
            subprocess.run(["git", "add", "."], cwd=folder, env=env, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=folder, env=env, check=True)
        self.args = SimpleNamespace(system_root=str(self.system), tasks=["t01"], conditions="promptguard",
                                    name="batch", resume=False, reps=1, model="sonnet", jobs=1,
                                    budget=2.0, timeout=900, no_capture=False, detector_capture=False, retries=0)
        self.tasks = [SimpleNamespace(id="t01")]
        self.batch = self.root / "runs/batch"

    def metadata(self):
        with patch.object(m2, "REPO_ROOT", self.data), patch.object(m2, "claude_version", return_value="test-cli"):
            return m2.batch_metadata(self.args, self.system, self.tasks)

    def test_clean_and_dirty_provenance_includes_untracked_content(self):
        clean = m2.checkout_provenance(self.system)
        self.assertIs(clean["dirty"], False)
        (self.system / "code.py").write_text("# modified\n")
        self.assertIs(m2.checkout_provenance(self.system)["dirty"], True)
        (self.system / "code.py").write_text("# original\n")
        untracked = self.system / "extra.py"
        untracked.write_text("# v1\n")
        dirty = m2.checkout_provenance(self.system)
        self.assertIs(dirty["dirty"], True)
        untracked.write_text("# v2\n")
        self.assertNotEqual(m2.checkout_provenance(self.system)["fingerprint"], dirty["fingerprint"])

    def test_resume_preserves_the_original_metadata(self):
        original = self.metadata()
        m2.prepare_batch(self.batch, original, resume=False)
        saved = (self.batch / "batch.json").read_bytes()
        resumed = {**self.metadata(), "started_at": "a later time"}
        m2.prepare_batch(self.batch, resumed, resume=True)
        self.assertEqual((self.batch / "batch.json").read_bytes(), saved)

    def test_resume_rejects_changed_settings_without_overwriting_metadata(self):
        original = self.metadata()
        m2.prepare_batch(self.batch, original, resume=False)
        saved = (self.batch / "batch.json").read_bytes()
        for field, value in (("model", "other"), ("budget", 3), ("timeout", 10), ("capture", False),
                             ("reps", 2), ("conditions", ["gold"]), ("tasks", ["t02"]),
                             ("detector_capture", True), ("claude_version", "new-cli")):
            with self.subTest(field=field):
                with self.assertRaisesRegex(SystemExit, "cannot resume"):
                    m2.prepare_batch(self.batch, {**original, field: value}, resume=True)
                self.assertEqual((self.batch / "batch.json").read_bytes(), saved)

    def test_resume_rejects_changed_system_or_evaluator_sources(self):
        original = self.metadata()
        m2.prepare_batch(self.batch, original, resume=False)
        for folder in (self.system, self.data):
            with self.subTest(folder=folder.name):
                (folder / "code.py").write_text("# changed\n")
                with self.assertRaisesRegex(SystemExit, "cannot resume"):
                    m2.prepare_batch(self.batch, self.metadata(), resume=True)
                (folder / "code.py").write_text("# original\n")
        changed_commit = {**original["system_provenance"], "commit": "f" * 40}
        with self.assertRaisesRegex(SystemExit, "cannot resume"):
            m2.prepare_batch(self.batch, {**original, "system_provenance": changed_commit}, resume=True)

    def test_dirty_resume_requires_the_same_uncommitted_contents(self):
        extra = self.system / "extra.py"
        extra.write_text("# first dirty version\n")
        original = self.metadata()
        m2.prepare_batch(self.batch, original, resume=False)
        m2.prepare_batch(self.batch, self.metadata(), resume=True)
        extra.write_text("# another dirty version\n")
        with self.assertRaisesRegex(SystemExit, "cannot resume"):
            m2.prepare_batch(self.batch, self.metadata(), resume=True)

    def test_legacy_and_non_resume_reuse_are_rejected(self):
        self.batch.mkdir(parents=True)
        path = self.batch / "batch.json"
        path.write_text('{"system_commit":"old","started_at":"keep"}')
        saved = path.read_bytes()
        for resume in (True, False):
            with self.subTest(resume=resume), self.assertRaises(SystemExit):
                m2.prepare_batch(self.batch, self.metadata(), resume=resume)
            self.assertEqual(path.read_bytes(), saved)

    def test_cmd_run_checks_resume_before_starting_jobs(self):
        with patch.object(m2, "REPO_ROOT", self.data), patch.object(m2, "RUNS_DIR", self.root / "runs"), \
                patch.object(m2, "system_root", return_value=self.system), \
                patch.object(m2.mt, "load_tasks", return_value=self.tasks), \
                patch.object(m2, "claude_version", return_value="test-cli"), \
                patch.object(m2, "run_one") as run, patch.object(m2, "write_report"), \
                patch.object(m2, "print_result"), patch.object(m2, "say"):
            def fake_run(task, condition, rep, run_dir, *args, **kwargs):
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text('{"valid":true}')
                return {"valid": True}

            run.side_effect = fake_run
            m2.cmd_run(self.args)
            self.assertEqual(run.call_count, 1)
            saved = (self.batch / "batch.json").read_bytes()
            self.args.resume = True
            m2.cmd_run(self.args)
            self.assertEqual(run.call_count, 1)  # the existing valid result is kept
            self.assertEqual((self.batch / "batch.json").read_bytes(), saved)
            self.args.model = "another model"
            with self.assertRaisesRegex(SystemExit, "cannot resume"):
                m2.cmd_run(self.args)
            self.assertEqual(run.call_count, 1)
            self.assertEqual((self.batch / "batch.json").read_bytes(), saved)
