"""Unit tests for git ceiling isolation in check_task and git-dependent verdict retention in recheck."""
import argparse
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2  # noqa: E402
import m2_tasks as mt  # noqa: E402


def _make_fake_batch(batch_dir: Path, task: mt.Task, ws: Path, check_result: dict) -> Path:
    run_dir = batch_dir / task.id / "none-r1"
    run_dir.mkdir(parents=True, exist_ok=True)
    m2.save_workspace(ws, run_dir)
    (run_dir / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": "ok"}}) + "\n",
        encoding="utf-8",
    )
    result = {
        "task": task.id,
        "suite": task.suite,
        "category": task.category,
        "needs_secret_value": task.spec["needs_secret_value"],
        "family": task.meta.get("family"),
        "channels": task.meta.get("channels", ["file"]),
        "meta": task.meta,
        "formats": task.meta.get("formats", []),
        "language": task.meta.get("language"),
        "project": task.meta.get("project"),
        "secret_requirement": task.meta.get("secret_requirement"),
        "length": task.meta.get("length"),
        "secrets_fingerprint": task.fingerprint,
        "condition": "none",
        "rep": 1,
        "model": "sonnet",
        "session_id": "00000000-0000-0000-0000-000000000000",
        "started_at": "2026-11-09T00:00:00",
        "error": None,
        "capture": False,
        "detector_capture": False,
        "claude": {"exit_code": 0, "num_turns": 1, "cost_usd": 0.01, "models": ["sonnet"]},
        "elapsed_s": 1.0,
        **copy.deepcopy(check_result),
        "transcript": {
            "secrets_seen": [],
            "seen_occurrences": 0,
            "secrets_written": [],
            "written_occurrences": 0,
            "tool_calls": {},
            "failed_tool_calls": {},
            "tool_inputs_with_placeholder": 0,
        },
        "server": None,
        "mod": {"rows": 1, "findings": 0, "failures": 0, "failure_reasons": []},
        "valid": True,
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


class RecheckGitTests(unittest.TestCase):
    def test_git_isolation_from_outer_repository(self):
        with tempfile.TemporaryDirectory() as d:
            outer = Path(d) / "outer"
            outer.mkdir()
            mt.git(outer, "init", "-q", "-b", "main")
            (outer / "README.md").write_text("outer\n", encoding="utf-8")
            mt.git(outer, "add", "-A")
            mt.git(outer, "commit", "-qm", "outer init", date=mt.GIT_DATE)
            mt.git(outer, "remote", "add", "origin", "https://git.example.invalid/outer/repo.git")

            ws = outer / "workspace_after"
            ws.mkdir()
            self.assertFalse((ws / ".git").exists())

            # git_remotes on a .git-less workspace must not leak the outer repository's remote.
            self.assertEqual(mt.git_remotes(ws), {})

            task_dir = Path(d) / "fake-task"
            task_dir.mkdir()
            (task_dir / "check.py").write_text(
                "import os, subprocess\n"
                "def check_git_in_python(ws, secrets):\n"
                "    p = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ws, capture_output=True, text=True)\n"
                "    return p.returncode == 0, p.stdout.strip() or p.stderr.strip()\n"
                "def raise_in_python(ws, secrets):\n"
                "    raise RuntimeError('boom')\n",
                encoding="utf-8",
            )
            spec = {
                "id": "fake-task",
                "title": "fake",
                "category": "diagnose",
                "needs_secret_value": False,
                "prompt": "fake",
                "checks": [
                    {"name": "cmd_git", "kind": "command", "run": ["git", "rev-parse", "--show-toplevel"]},
                    {"name": "py_git", "kind": "python", "func": "check_git_in_python"},
                ],
                "solution": [],
            }
            task = mt.Task("fake-task", task_dir, spec)

            sentinel = "/sentinel/ceiling"
            prev = os.environ.get("GIT_CEILING_DIRECTORIES")
            os.environ["GIT_CEILING_DIRECTORIES"] = sentinel
            try:
                res = mt.check_task(task, ws, {})
                self.assertEqual(os.environ.get("GIT_CEILING_DIRECTORIES"), sentinel)
            finally:
                if prev is None:
                    os.environ.pop("GIT_CEILING_DIRECTORIES", None)
                else:
                    os.environ["GIT_CEILING_DIRECTORIES"] = prev

            self.assertFalse(res["checks"][0]["ok"], res["checks"][0])
            self.assertFalse(res["checks"][1]["ok"], res["checks"][1])
            self.assertEqual(os.environ.get("GIT_CEILING_DIRECTORIES"), prev)

            # Even if a python check raises an exception, GIT_CEILING_DIRECTORIES is restored.
            task_err = mt.Task(
                "fake-task",
                task_dir,
                {**spec, "checks": [{"name": "py_err", "kind": "python", "func": "raise_in_python"}]},
            )
            res_err = mt.check_task(task_err, ws, {})
            self.assertFalse(res_err["checks"][0]["ok"])
            self.assertEqual(os.environ.get("GIT_CEILING_DIRECTORIES"), prev)

    def test_recheck_keeps_git_dependent_verdict_and_is_idempotent(self):
        task = mt.load_tasks(["n17"])[0]
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "ws"
            built = mt.build(task, ws)
            mt.apply_solution(task, ws)
            solved = mt.check_task(task, ws, built)
            self.assertTrue(solved["success"], solved)

            batch = Path(d) / "batch"
            run_dir = _make_fake_batch(batch, task, ws, solved)
            self.assertFalse((run_dir / "workspace_after" / ".git").exists())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                m2.cmd_recheck(argparse.Namespace(batches=[str(batch)]))
            out1 = buf.getvalue()

            r1 = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertTrue(r1["success"])
            self.assertTrue(r1["task_ok"])
            self.assertEqual(len(r1["checks"]), 1)
            self.assertTrue(r1["checks"][0]["ok"])
            expected_detail = f"breaking commits identified {m2.GIT_KEPT_NOTE}"
            self.assertEqual(r1["checks"][0]["detail"], expected_detail)
            self.assertEqual(set(r1["checks"][0].keys()), {"check", "ok", "detail"})
            self.assertIn("kept git-dependent verdict: n17-release-review none r1: breaking commits", out1)
            self.assertIn("0 verdict(s) changed", out1)

            # Running recheck a second time must not append the kept note again.
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                m2.cmd_recheck(argparse.Namespace(batches=[str(batch)]))
            r2 = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(r2["checks"][0]["detail"], expected_detail)

            # If old result.json lacks the check name, recheck cannot keep it: warns and leaves it failed.
            r2["checks"] = []
            (run_dir / "result.json").write_text(json.dumps(r2), encoding="utf-8")
            buf3 = io.StringIO()
            with contextlib.redirect_stdout(buf3):
                m2.cmd_recheck(argparse.Namespace(batches=[str(batch)]))
            r3 = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertFalse(r3["task_ok"])
            self.assertFalse(r3["success"])
            self.assertIn("warning:", buf3.getvalue())

    def test_recheck_still_regrades_non_git_checks(self):
        task = mt.load_tasks(["n17"])[0]
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "ws"
            built = mt.build(task, ws)
            mt.apply_solution(task, ws)
            solved = mt.check_task(task, ws, built)
            self.assertTrue(solved["success"])

            # 1) Unmodified n17 task: corrupt workspace_after with a placeholder so integrity check fails
            # while the git-dependent check is kept.
            batch1 = Path(d) / "batch1"
            run_dir1 = _make_fake_batch(batch1, task, ws, solved)
            (run_dir1 / "workspace_after" / "README.md").write_text("[PASSWORD_1]\n", encoding="utf-8")
            buf1 = io.StringIO()
            with contextlib.redirect_stdout(buf1):
                m2.cmd_recheck(argparse.Namespace(batches=[str(batch1)]))
            r_int = json.loads((run_dir1 / "result.json").read_text(encoding="utf-8"))
            self.assertTrue(r_int["checks"][0]["ok"])
            self.assertTrue(r_int["checks"][0]["detail"].endswith(m2.GIT_KEPT_NOTE))
            self.assertTrue(r_int["task_ok"])
            self.assertFalse(r_int["integrity_ok"])
            self.assertFalse(r_int["success"])
            self.assertIn("1 verdict(s) changed", buf1.getvalue())

            # 2) Non-git check in checks list fails while git-dependent check is kept.
            batch = Path(d) / "batch"
            run_dir = _make_fake_batch(batch, task, ws, solved)

            extra_check = {"name": "readme unchanged", "kind": "unchanged", "path": "README.md"}
            orig_checks = list(task.spec["checks"])
            r_init = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            r_init["checks"].append({"check": "readme unchanged", "ok": True, "detail": "README.md unchanged"})
            (run_dir / "result.json").write_text(json.dumps(r_init), encoding="utf-8")
            (run_dir / "workspace_after" / "README.md").write_text("tampered\n", encoding="utf-8")

            with unittest.mock.patch.object(
                mt,
                "load_tasks",
                return_value=[mt.Task(task.id, task.dir, {**task.spec, "checks": orig_checks + [extra_check]},
                                      task.secrets, task.decoys)],
            ):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    m2.cmd_recheck(argparse.Namespace(batches=[str(batch)]))
                out = buf.getvalue()

            r_after = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            by_name = {c["check"]: c for c in r_after["checks"]}
            self.assertTrue(by_name["breaking commits"]["ok"])
            self.assertTrue(by_name["breaking commits"]["detail"].endswith(m2.GIT_KEPT_NOTE))
            self.assertFalse(by_name["readme unchanged"]["ok"])
            self.assertFalse(r_after["task_ok"])
            self.assertFalse(r_after["success"])
            self.assertIn("1 verdict(s) changed", out)

    def test_check_task_default_output_unchanged(self):
        task = mt.load_tasks(["n17"])[0]
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "ws"
            built = mt.build(task, ws)
            mt.apply_solution(task, ws)

            path_before = os.environ.get("PATH")
            res_default = mt.check_task(task, ws, built)
            self.assertEqual(os.environ.get("PATH"), path_before)
            self.assertEqual(set(res_default.keys()), {"success", "task_ok", "integrity_ok", "integrity", "checks"})
            for c in res_default["checks"]:
                self.assertEqual(set(c.keys()), {"check", "ok", "detail"})

            res_recorded = mt.check_task(task, ws, built, record_git=True)
            self.assertEqual(os.environ.get("PATH"), path_before)
            self.assertEqual(set(res_recorded.keys()), {"success", "task_ok", "integrity_ok", "integrity", "checks"})
            self.assertTrue(res_recorded["checks"][0]["used_git"])

    def test_concurrent_python_checks_on_gitless_workspaces_are_thread_safe(self):
        with tempfile.TemporaryDirectory() as d:
            workspaces = []
            for name in ("a", "b"):
                outer = Path(d) / f"outer_{name}"
                outer.mkdir()
                mt.git(outer, "init", "-q", "-b", "main")
                (outer / "README.md").write_text(f"{name}\n", encoding="utf-8")
                mt.git(outer, "add", "-A")
                mt.git(outer, "commit", "-qm", "init", date=mt.GIT_DATE)
                ws = outer / "workspace_after"
                ws.mkdir()
                workspaces.append(ws)

            ws_with_git = Path(d) / "with_git"
            ws_with_git.mkdir()
            mt.git(ws_with_git, "init", "-q", "-b", "main")

            task_dir = Path(d) / "concurrent-task"
            task_dir.mkdir()
            (task_dir / "check.py").write_text(
                "import os, subprocess, time\n"
                "def check_git_isolated(ws, secrets):\n"
                "    time.sleep(0.005)\n"
                "    p = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ws, capture_output=True, text=True)\n"
                "    return p.returncode == 0, p.stdout.strip() or p.stderr.strip()\n"
                "def check_env_untouched(ws, secrets):\n"
                "    return os.environ.get('GIT_CEILING_DIRECTORIES') == '/keep/me', str(os.environ.get('GIT_CEILING_DIRECTORIES'))\n",
                encoding="utf-8",
            )
            task = mt.Task(
                "concurrent-task",
                task_dir,
                {
                    "id": "concurrent-task",
                    "title": "concurrent",
                    "category": "diagnose",
                    "needs_secret_value": False,
                    "prompt": "concurrent",
                    "checks": [{"name": "py_git", "kind": "python", "func": "check_git_isolated"}],
                    "solution": [],
                },
            )

            prev = os.environ.get("GIT_CEILING_DIRECTORIES")
            try:
                for initial in (None, "/initial/ceiling"):
                    if initial is None:
                        os.environ.pop("GIT_CEILING_DIRECTORIES", None)
                    else:
                        os.environ["GIT_CEILING_DIRECTORIES"] = initial
                    jobs = [workspaces[i % 2] for i in range(24)]
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(lambda w: mt.check_task(task, w, {}), jobs))
                    self.assertEqual(os.environ.get("GIT_CEILING_DIRECTORIES"), initial)
                    for r in results:
                        self.assertFalse(r["checks"][0]["ok"], r["checks"][0])

                # When ws has .git, python check does not touch GIT_CEILING_DIRECTORIES.
                os.environ["GIT_CEILING_DIRECTORIES"] = "/keep/me"
                task_env = mt.Task(
                    "concurrent-task",
                    task_dir,
                    {**task.spec, "checks": [{"name": "env_check", "kind": "python", "func": "check_env_untouched"}]},
                )
                r_git = mt.check_task(task_env, ws_with_git, {})
                self.assertTrue(r_git["checks"][0]["ok"], r_git["checks"][0])
                self.assertEqual(os.environ.get("GIT_CEILING_DIRECTORIES"), "/keep/me")
            finally:
                if prev is None:
                    os.environ.pop("GIT_CEILING_DIRECTORIES", None)
                else:
                    os.environ["GIT_CEILING_DIRECTORIES"] = prev


if __name__ == "__main__":
    unittest.main()
