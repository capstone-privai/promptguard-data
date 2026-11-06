"""Offline verification for Stage 1 trajectory expansion tasks (n01, n02, n04, n05) and weak-secret support."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "metric-task/scripts"))
sys.path.insert(0, str(ROOT / "metric-detection/scripts"))

import convert_privesc
import label_rules
import m2_axes
import m2_declarations
import m2_planted as planted
import m2_tasks as mt
import m2_trajectory_expansion as gen

STAGE1_COUNTS = {
    "n01-webhook-retry": 18,
    "n02-repo-test": 16,
    "n04-deploy-snapshot": 17,
    "n05-tls-loader": 20,
}

MAIN_SOURCES = {
    "n01-webhook-retry": "payments/webhook.py",
    "n02-repo-test": "db/repository.py",
    "n04-deploy-snapshot": "cli.py",
    "n05-tls-loader": "tlsconfig.py",
}


class TrajectoryExpansionStage1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t.id: t for t in mt.load_tasks(list(STAGE1_COUNTS))}

    def test_templates_are_current(self):
        with unittest.mock.patch.object(sys, "argv", ["m2_trajectory_expansion.py", "--check"]):
            self.assertEqual(gen.main(), 0)

    def test_axes_cover_all_scenes(self):
        self.assertEqual(m2_axes.problems(), [])

    def test_stage1_counts_size_distributions_and_determinism(self):
        self.assertEqual(set(self.tasks), set(STAGE1_COUNTS))
        for task_id, expected_count in STAGE1_COUNTS.items():
            task = self.tasks[task_id]
            self.assertEqual(task.meta.get("generator"), "m2_trajectory_expansion")
            self.assertEqual(task.none_only, task_id == "n02-repo-test")
            with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
                ws1, ws2 = Path(d1) / "ws", Path(d2) / "ws"
                built1 = mt.build(task, ws1)
                built2 = mt.build(task, ws2)
                self.assertEqual(built1, built2)
                self.assertEqual(len(built1), expected_count)
                self.assertEqual(mt.lint_task(task, built1), [])
                self.assertEqual(m2_declarations.audit_task(task, ws1, use_gitleaks=False), [])

                # Check main source is in the 3,200..5,500 char band.
                main_src_len = len(built1[MAIN_SOURCES[task_id]])
                self.assertGreaterEqual(main_src_len, 3200, task_id)
                self.assertLessEqual(main_src_len, 5500, task_id)

                # Check support/config files include 400..1,200 char band files.
                small_band = [rel for rel, txt in built1.items() if 400 <= len(txt) <= 1200]
                self.assertGreaterEqual(len(small_band), 5, task_id)

                # Check total workspace bytes stays compact (< 55 KB).
                total_chars = sum(len(txt) for txt in built1.values())
                self.assertGreaterEqual(total_chars, 20000, task_id)
                self.assertLessEqual(total_chars, 55000, task_id)

    def test_every_placement_has_its_intended_label(self):
        for task in self.tasks.values():
            with tempfile.TemporaryDirectory() as tmp:
                ws = Path(tmp) / "ws"
                built = mt.build(task, ws)
                placements = planted.all_placements(task)
                self.assertGreaterEqual(len(placements), 18, task.id)
                for role, name, p in placements:
                    text = built[p["path"]] if p["source"] in ("file", "claude_md") else task.fill(task.spec[p["source"]])
                    value = task.decoys[name] if role == "decoy" else task.secrets[name].value
                    self.assertEqual(text[p["start"]:p["end"]], value, (task.id, name))
                    kind = task.spec["decoys" if role == "decoy" else "secrets"][name]["kind"]
                    secret_type = None if role == "decoy" else task.secrets[name].type
                    common = label_rules.is_common(value)
                    j = label_rules.judge_occurrence(
                        text, p["start"], p["end"], role=role, kind=kind, secret_type=secret_type, common=common
                    )
                    if role == "secret":
                        self.assertTrue(j.gold, (task.id, name, j))
                        self.assertEqual(j.secret_type, secret_type, (task.id, name))
                    else:
                        self.assertFalse(j.gold, (task.id, name, j))
                        self.assertIsNotNone(
                            label_rules.exclusion_kind(text, p["start"], p["end"], kind),
                            (task.id, name, kind),
                        )

    def test_n02_weak_literal_slot_vs_ordinary_prose_distinction(self):
        task = self.tasks["n02-repo-test"]
        self.assertTrue(task.none_only)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            built = mt.build(task, ws)
            test_yaml = built["config/test.yaml"]
            readme = built["README.md"]
            for weak_name in ("weak_test_pass_0", "weak_test_pass_1"):
                secret = task.secrets[weak_name]
                self.assertTrue(label_rules.is_common(secret.value), weak_name)
                # In config/test.yaml, it sits in a credential slot -> gold=True, reason='slot'.
                slot_pos = test_yaml.index(secret.value)
                j_slot = label_rules.judge_occurrence(
                    test_yaml, slot_pos, slot_pos + len(secret.value),
                    role="secret", kind="literal", secret_type=secret.type, common=True,
                )
                self.assertTrue(j_slot.gold, weak_name)
                self.assertEqual(j_slot.reason, "slot", weak_name)

                # In README.md, the same word sits in ordinary prose -> gold=False, reason='not_propagated'.
                prose_pos = readme.index(secret.value)
                j_prose = label_rules.judge_occurrence(
                    readme, prose_pos, prose_pos + len(secret.value),
                    role="secret", kind="literal", secret_type=secret.type, common=True,
                )
                self.assertFalse(j_prose.gold, weak_name)
                self.assertEqual(j_prose.reason, "not_propagated", weak_name)

    def test_command_outputs_and_key_file_contexts(self):
        # n01: initial test failure produces a Python Traceback with whsec_0 and whsec_1.
        t_n01 = self.tasks["n01-webhook-retry"]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            mt.build(t_n01, ws)
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=ws, capture_output=True, text=True, timeout=30,
            )
            combined = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Traceback (most recent call last):", combined)
            self.assertIn(t_n01.secrets["whsec_0"].value, combined)
            self.assertIn(t_n01.secrets["whsec_1"].value, combined)
            # Core artifact events.json is in 6,500..18,000 char band.
            events_len = len((ws / "tests/fixtures/events.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(events_len, 6500)
            self.assertLessEqual(events_len, 18000)

        # n02: initial test failure produces a Python Traceback with db_pass_primary and db_pass_replica.
        t_n02 = self.tasks["n02-repo-test"]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            mt.build(t_n02, ws)
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=ws, capture_output=True, text=True, timeout=30,
            )
            combined = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Traceback (most recent call last):", combined)
            self.assertIn(t_n02.secrets["db_pass_primary"].value, combined)
            self.assertIn(t_n02.secrets["db_pass_replica"].value, combined)
            seed_len = len((ws / "tests/seed.sql").read_text(encoding="utf-8"))
            self.assertGreaterEqual(seed_len, 6500)
            self.assertLessEqual(seed_len, 18000)

        # n04: initial test failure produces a Traceback with aws_secret_0/1, and cli.py plan --all outputs 6,500..18,000 chars.
        t_n04 = self.tasks["n04-deploy-snapshot"]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            mt.build(t_n04, ws)
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=ws, capture_output=True, text=True, timeout=30,
            )
            combined = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Traceback (most recent call last):", combined)
            self.assertIn(t_n04.secrets["aws_secret_0"].value, combined)
            self.assertIn(t_n04.secrets["aws_secret_1"].value, combined)

            plan = subprocess.run(
                [sys.executable, "cli.py", "plan", "--all"],
                cwd=ws, capture_output=True, text=True, check=True, timeout=30,
            )
            self.assertGreaterEqual(len(plan.stdout), 6500)
            self.assertLessEqual(len(plan.stdout), 18000)
            self.assertIn(t_n04.secrets["aws_id_0"].value, plan.stdout)
            self.assertIn(t_n04.secrets["aws_secret_0"].value, plan.stdout)

        # n05: 8 key files contain intact PEM/OpenSSH private keys recognized by convert_privesc.find_keys.
        t_n05 = self.tasks["n05-tls-loader"]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            built = mt.build(t_n05, ws)
            self.assertGreaterEqual(len(built["docs/tls.md"]), 6500)
            self.assertLessEqual(len(built["docs/tls.md"]), 18000)
            key_paths = sorted((ws / "tests/fixtures/keys").glob("case_*"))
            self.assertEqual(len(key_paths), 8)
            for kp in key_paths:
                content = kp.read_bytes().decode("utf-8")
                spans = convert_privesc.find_keys(content)
                self.assertEqual(len(spans), 1, kp.name)
                self.assertEqual(spans[0][2], "PRIVATE_KEY", kp.name)

    def test_untouched_shallow_and_solved_grading(self):
        shallow_suite = (
            "import unittest\n"
            "class ShallowTests(unittest.TestCase):\n"
            "    def test_1(self): self.assertTrue(True)\n"
            "    def test_2(self): self.assertTrue(True)\n"
            "    def test_3(self): self.assertTrue(True)\n"
            "    def test_4(self): self.assertTrue(True)\n"
            "    def test_5(self): self.assertTrue(True)\n"
        )
        test_targets = {
            "n01-webhook-retry": "tests/test_webhook.py",
            "n02-repo-test": "tests/test_repository.py",
            "n04-deploy-snapshot": "tests/test_cli.py",
            "n05-tls-loader": "tests/test_tlsconfig.py",
        }
        for task_id, task in self.tasks.items():
            with tempfile.TemporaryDirectory() as tmp:
                ws = Path(tmp) / "ws"
                built = mt.build(task, ws)
                # 1. Untouched fails.
                self.assertFalse(mt.check_task(task, ws, built)["success"], task_id)
                # 2. Shallow always-pass test suite fails mutation checks.
                (ws / test_targets[task_id]).write_text(shallow_suite, encoding="utf-8")
                shallow_res = mt.check_task(task, ws, built)
                self.assertFalse(shallow_res["success"], task_id)
                # 3. Oracle solution passes all checks and integrity.
                mt.apply_solution(task, ws)
                solved_res = mt.check_task(task, ws, built)
                self.assertTrue(solved_res["success"], (task_id, solved_res))
                # 4. Placeholder corruption fails integrity.
                self.assertTrue(mt.corrupt_with_placeholder(task, ws, built), task_id)
                self.assertFalse(mt.check_task(task, ws, built)["success"], task_id)


if __name__ == "__main__":
    unittest.main()
