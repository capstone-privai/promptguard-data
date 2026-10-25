"""Tests of ml_train_export.py on small templates built with ml_train_build.py.

Run from the repository root:
  python -m unittest discover -s metric-detection/scripts -p "test_ml_train_export.py"
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from dataset_build import write_jsonl
import dataset_verify as V
import ml_train_build as B
import ml_train_export as E

SCRIPTS = Path(__file__).resolve().parent
# A long tool_output shared by two templates: the same context, other values (a near duplicate)
LOG = "".join(f"2026-10-0{i} INFO {worker} started job {job} on queue={queue} pid=4421{i} region=eu-west-1\n"
              for i, (worker, job, queue) in enumerate([("ingest", "nightly-sync", "default"),
                                                       ("billing", "invoice-export", "slow"),
                                                       ("mailer", "digest", "default"),
                                                       ("search", "reindex", "bulk"),
                                                       ("reports", "monthly-close", "slow")], 1))


def tpl(sid: str, split: str, text: str, prompt: str = "설정 파일을 확인해 줘", **meta) -> dict:
    return {"session_id": sid, "meta": {"split": split, **meta},
            "items": [{"turn_id": "t0", "channel": "prompt", "text": prompt},
                      {"turn_id": "t0", "channel": "tool_output", "text": text}]}


CLEAN = [
    tpl("c0001", "train", "DB_PASSWORD={{password:db}}\nDB_HOST=db.internal\n", variants=2),
    tpl("c0002", "train", "API_KEY={{api_key:k}}\nAPI_URL=${API_BASE}/v1\n"),
    tpl("c0003", "val", "REDIS_PASSWORD={{password:r}}\nCACHE_TTL=300\n"),
    tpl("c0004", "test", "SECRET_KEY={{hex_secret:s}}\nDEBUG=false\n"),
    tpl("o0001", "test_ood", "HF_TOKEN={{huggingface_token:s1}}\n", card={"context": "jupyter_output"},
        source_id="SRC-032"),
]


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.handoff = self.root / "handoff"
        self.eval_out = self.root / "eval"

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, name: str, templates: list[dict], out: Path | None = None) -> Path:
        path = self.root / "templates" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in templates), encoding="utf-8")
        paths = B.paths(out or self.root / "built", name)
        for p, rows in zip(paths, B.build(path)):
            p.parent.mkdir(parents=True, exist_ok=True)
            write_jsonl(p, rows)
        return paths[0]

    def export(self, *inputs: Path) -> dict:
        return E.export(list(inputs), self.handoff, self.eval_out)

    def failure(self, *inputs: Path) -> str:
        with self.assertRaises(ValueError) as caught:
            self.export(*inputs)
        self.assertFalse(self.handoff.exists(), "a failed export wrote the handoff folder")
        self.assertEqual(E.old_eval_outputs(self.eval_out), [], "a failed export wrote evaluation files")
        return str(caught.exception)

    def outputs(self) -> dict[str, bytes]:
        files = [*self.handoff.iterdir(), *E.old_eval_outputs(self.eval_out)]
        return {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(files)}

    @staticmethod
    def edit(path: Path, change):
        rows = V.read_jsonl(path, [])
        change(rows)
        write_jsonl(path, rows)

    # ---- the export itself

    def test_splits_go_to_their_folders_byte_for_byte(self):
        report = self.export(self.build("clean", CLEAN))
        self.assertEqual(report["sessions"], {"train": 3, "val": 1, "clean/test": 1, "clean/test_ood": 1})
        self.assertEqual(sorted(p.name for p in self.handoff.iterdir()),
                         ["README.md", "gold_train.jsonl", "gold_val.jsonl", "labels_train.jsonl", "labels_val.jsonl",
                          "manifest.json", "sessions_train.jsonl", "sessions_val.jsonl"])
        splits = {s["meta"]["split"] for s in V.read_jsonl(self.handoff / "sessions_train.jsonl", [])}
        self.assertEqual(splits, {"train"})
        test = V.read_jsonl(self.eval_out / "data_test" / "sessions_mleval_clean_test.jsonl", [])
        self.assertEqual([s["session_id"] for s in test], ["c0004"])
        manifest = json.loads((self.handoff / "manifest.json").read_text())
        self.assertEqual(manifest["counts"]["train"]["sessions"], 3)
        self.assertEqual(manifest["versions"]["cards"], "cards-v0.1")
        for name, digest in manifest["files"].items():
            self.assertEqual(E.sha256(self.handoff / name), digest)
        eval_manifest = json.loads((self.eval_out / "manifest_mleval.json").read_text())
        self.assertEqual(eval_manifest["training_side_groups"], ["c0001", "c0002", "c0003"])
        first = self.outputs()
        self.export(self.root / "built" / "data_test" / "sessions_ml_clean.jsonl")
        self.assertEqual(self.outputs(), first)

    def test_evaluation_files_pass_dataset_verify_and_evaluate(self):
        self.export(self.build("clean", CLEAN))
        for split in ("test", "test_ood"):
            sessions = self.eval_out / "data_test" / f"sessions_mleval_clean_{split}.jsonl"
            done = subprocess.run([sys.executable, str(SCRIPTS / "dataset_verify.py"), str(sessions)],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            done = subprocess.run([sys.executable, str(SCRIPTS / "evaluate.py"), "run", "--system", "oracle",
                                   "--sessions", str(sessions), "--out", str(self.root / "results")],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("recall=1.0000", done.stdout)

    def test_evaluation_refuses_the_training_side(self):
        self.export(self.build("clean", CLEAN))
        for split in ("train", "val"):
            sessions = self.handoff / f"sessions_{split}.jsonl"
            self.assertEqual({tuple(s["meta"]["allowed_use"]) for s in V.read_jsonl(sessions, [])}, {("ml_train",)})
            done = subprocess.run([sys.executable, str(SCRIPTS / "evaluate.py"), "run", "--system", "oracle",
                                   "--sessions", str(sessions), "--out", str(self.root / "results")],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn(f"meta.split '{split}' is ML training data", done.stdout + done.stderr)
        self.assertFalse((self.root / "results").exists())
        test = V.read_jsonl(self.eval_out / "data_test" / "sessions_mleval_clean_test.jsonl", [])
        self.assertEqual(test[0]["meta"]["allowed_use"], ["rule_eval", "ml_eval"])

    def test_rerun_replaces_earlier_outputs(self):
        clean, other = self.build("clean", CLEAN), self.build("other", [tpl("x0001", "test", "PASS={{password:p}}\n")])
        self.export(clean, other)
        self.assertTrue((self.eval_out / "data_test" / "sessions_mleval_other_test.jsonl").is_file())
        self.export(clean)
        self.assertFalse((self.eval_out / "data_test" / "sessions_mleval_other_test.jsonl").exists())

    def test_failed_export_keeps_earlier_outputs(self):
        clean = self.build("clean", CLEAN)
        self.export(clean)
        before = self.outputs()
        with self.assertRaises(ValueError):
            self.export(clean, self.build("again", [tpl("c0001", "test", "PASS={{password:p}}\n")]))
        self.assertEqual(self.outputs(), before)

    def test_refuses_a_folder_it_did_not_write(self):
        self.handoff.mkdir()
        (self.handoff / "notes.txt").write_text("mine")
        with self.assertRaises(ValueError) as caught:
            self.export(self.build("clean", CLEAN))
        self.assertIn("did not write", str(caught.exception))
        self.assertTrue((self.handoff / "notes.txt").is_file())

    def test_warns_about_training_groups_left_in_data_test(self):
        report = self.export(self.build("clean", CLEAN, out=self.eval_out))
        # the build holds its test and test_ood sessions too
        self.assertEqual(len(report["warnings"]), 2)
        self.assertIn("sessions_ml_clean.jsonl holds 3 training-side group(s)", report["warnings"][0])
        self.assertIn("sessions_ml_clean.jsonl holds 2 session(s) of the evaluation files", report["warnings"][1])

    def test_warns_about_evaluation_sessions_kept_twice_in_data_test(self):
        clean = self.build("clean", CLEAN)
        self.export(clean)
        # what the full privesc conversion is to the privesc test_ood: the same sessions under the same ids
        first = self.eval_out / "data_test" / "sessions_mleval_clean_test.jsonl"
        shutil.copy(first, self.eval_out / "data_test" / "sessions_from_full.jsonl")
        report = self.export(clean)
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("sessions_from_full.jsonl holds 1 session(s) of the evaluation files", report["warnings"][0])

    # ---- checks that stop the export

    def test_group_id_in_two_files(self):
        message = self.failure(self.build("clean", CLEAN), self.build("again", [tpl("c0001", "train", "X=1\n")]))
        self.assertIn("group c0001 is in again and clean", message)

    def test_group_in_two_splits(self):
        clean = self.build("clean", CLEAN)
        self.edit(clean, lambda rows: rows[1]["meta"].update(split="test"))  # c0001~1
        self.assertIn("group c0001 is in splits ['test', 'train']", self.failure(clean))

    def test_value_on_both_sides(self):
        leak = self.build("leak", [tpl("v0001", "train", "DB_PASSWORD={{PASSWORD=Kq7#vPz2xW}}\n"),
                                   tpl("v0002", "test", "DB_PASSWORD={{PASSWORD=Kq7#vPz2xW}}\n"),
                                   tpl("v0003", "train", "DB_PASSWORD={{PASSWORD=admin}}\n"),
                                   tpl("v0004", "test", "DB_PASSWORD={{PASSWORD=admin}}\n")])
        message = self.failure(leak)
        self.assertIn("'Kq7#vPz2xW'... is on both sides: v0001 and v0002", message)
        self.assertNotIn("'admin'", message)  # a common value is shared on purpose

    def test_value_only_recorded_sessions_share_is_reported(self):
        guesses = self.build("rec", [tpl("privesc-a", "train", "trying {{PASSWORD=letmein}}\nPASS={{PASSWORD=Qv4!toor}}\n"),
                                     tpl("privesc-b", "test_ood", "PASS={{PASSWORD=Qv4!toor}}\n")])
        self.edit(guesses, lambda rows: [r["meta"].update(origin="recorded") for r in rows])
        report = self.export(guesses)
        self.assertEqual(report["recorded_values_on_both_sides"], 1)
        shared = json.loads((self.handoff / "manifest.json").read_text())["recorded_values_on_both_sides"]
        self.assertEqual(shared[0]["example"], ["privesc-a", "privesc-b"])
        self.assertNotIn("Qv4!toor", (self.handoff / "manifest.json").read_text())
        authored = self.build("syn", [tpl("s0001", "test", "PASS={{PASSWORD=Qv4!toor}}\n")])
        with self.assertRaises(ValueError) as caught:
            self.export(guesses, authored)
        self.assertIn("'Qv4!toor'... is on both sides", str(caught.exception))

    def test_gold_in_tool_input(self):
        clean = self.build("clean", [*CLEAN, {"session_id": "c0005", "meta": {"split": "train"}, "items": [
            {"channel": "tool_output", "text": "TOKEN={{token:t}}\n"},
            {"channel": "tool_input", "text": "curl -H 'Authorization: Bearer {{mask:t}}' https://api.internal"}]}])
        gold = B.paths_of(clean)[1]
        sessions = V.read_jsonl(clean, [])
        text = next(s for s in sessions if s["session_id"] == "c0005")["items"][1]["text"]
        start = text.index("[TOKEN_1]")

        def add(rows):
            rows.append({"session_id": "c0005", "item_id": 1, "span_id": 0,
                         "span": {"start": start, "end": start + 9, "type": "TOKEN"}})
            rows.sort(key=lambda g: [s["session_id"] for s in sessions].index(g["session_id"]))
        self.edit(gold, add)
        self.assertIn("gold in tool_input c0005/1", self.failure(clean))

    def test_shifted_test_features_on_the_training_side(self):
        ood = self.build("ood", [
            tpl("d0001", "train", "HF_TOKEN={{huggingface_token:s1}}\n"),
            tpl("d0002", "val", "X=1\n", card={"context": "terraform_state"}),
            tpl("d0003", "train", "X=1\n", card={"tool_output_format": "mcp_result"}),
            tpl("d0004", "train", "TWILIO_AUTH_TOKEN={{secret:s}}\n", source_id="SRC-192"),
            tpl("d0005", "train", "KEY={{neg:prefix_example|of=twilio_api_key}}\n"),
            tpl("d0006", "test_ood", "HF_TOKEN={{huggingface_token:s1}}\n", card={"context": "jupyter_output"})])
        message = self.failure(ood)
        for expected in ("d0001 (train) has the shifted test's kind huggingface_token",
                         "d0002 (val) has the shifted test's context terraform_state",
                         "d0003 (train) has the shifted test's tool output format mcp_result",
                         "d0004 (train) has the shifted test's catalog row SRC-192",
                         "d0005 (train) has the shifted test's kind twilio_api_key"):
            self.assertIn(expected, message)
        self.assertNotIn("d0006", message)

    def test_build_from_before_the_split_rule(self):
        clean = self.build("clean", CLEAN)
        self.edit(clean, lambda rows: [r["meta"].update(allowed_use=["rule_eval", "ml_eval", "ml_train"]) for r in rows])
        self.assertIn("6 session(s) whose meta.allowed_use is not dataset_policy's", self.failure(clean))

    def test_origin_not_for_training(self):
        clean = self.build("clean", CLEAN)
        self.edit(clean, lambda rows: [r["meta"].update(origin="injected", allowed_use=["rule_eval"]) for r in rows])
        message = self.failure(clean)
        self.assertIn("origin ['injected']", message)
        self.assertIn("not allowed for ml_train", message)

    # ---- near duplicates

    def test_near_duplicates_move_test_drop_test_ood_and_report_recorded(self):
        near = self.build("near", [
            tpl("n0001", "train", LOG + "DB_PASSWORD={{password:a}}\n"),
            tpl("n0002", "test", LOG + "DB_PASSWORD={{password:b}}\n"),
            tpl("n0003", "test_ood", LOG + "API_TOKEN={{token:c}}\n"),
            tpl("n0004", "test", "SECRET_KEY={{hex_secret:d}}\n")])
        # one environment: the same machine output in two scenarios. Not the synthetic LOG, which would make
        # privesc-b a near duplicate of n0001 too, and an authored partner drops it
        shell = LOG.replace("INFO", "sshd").replace("worker", "session")
        recorded = self.build("rec", [tpl("privesc-a", "train", shell + "PASS={{password:e}}\n"),
                                      tpl("privesc-b", "test_ood", shell + "PASS={{password:f}}\n")])
        self.edit(recorded, lambda rows: [r["meta"].update(origin="recorded") for r in rows])
        report = self.export(near, recorded)
        self.assertEqual(report["sessions"], {"train": 3, "val": 0, "near/test": 1, "rec/test_ood": 1})
        moved = next(s for s in V.read_jsonl(self.handoff / "sessions_train.jsonl", []) if s["session_id"] == "n0002")
        self.assertEqual((moved["meta"]["split"], moved["meta"]["split_moved_from"]), ("train", "test"))
        self.assertEqual(moved["meta"]["allowed_use"], ["ml_train"])
        pairs = json.loads((self.handoff / "manifest.json").read_text())["near_duplicates"]["pairs"]
        rules = {(p["group"], p["partner"]): p["rule"] for p in pairs}
        self.assertEqual(rules[("n0002", "n0001")], "moved_to_train")
        self.assertEqual(rules[("n0003", "n0001")], "dropped")
        self.assertEqual(rules[("privesc-b", "privesc-a")], "reported")
        self.assertNotIn("n0004", {p["group"] for p in pairs})
        self.assertFalse((self.eval_out / "data_test" / "sessions_mleval_near_test_ood.jsonl").exists())

    def test_values_and_digits_do_not_hide_a_near_duplicate(self):
        a = E.context_text("job 1234 failed with password hunter2!", [(30, 38)])
        b = E.context_text("job 9876 failed with  password Zx9#kq2", [(31, 38)])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
