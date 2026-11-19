"""Values the evaluation side spells out on its own must match the data scripts and the system."""

from __future__ import annotations

import argparse
import inspect
import sys
import unittest
from pathlib import Path
from typing import Any

from evaluation.adapters.node_mod import NodeMod
from evaluation.adapters.promptguard_adapter import CHANNEL_MAP
from evaluation.adapters.system_root import MOD, load_worker
from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import CHANNELS, GOLD_TYPES, SCORED_CHANNELS, TRAINING_SPLITS, USES
from evaluation.tests.mod_port import ModFailure, ModSession
from evaluation.tests.support import (CREDSWEEPER_REASON, GOLD, HAS_CREDSWEEPER, HAS_NODE, HAS_PROMPTGUARD,
                                      NODE_REASON, SESSIONS, SYSTEM_ROOT, finding, found, mod_at)

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _script(name: str):
    sys.path.insert(0, str(SCRIPTS))
    try:
        return __import__(name)
    finally:
        sys.path.remove(str(SCRIPTS))


class DataContractTests(unittest.TestCase):
    def test_channels_and_types_match_dataset_build(self) -> None:
        dataset_build = _script("dataset_build")
        self.assertEqual(set(CHANNELS), dataset_build.CHANNELS)
        self.assertEqual(set(GOLD_TYPES), dataset_build.TYPES)

    def test_scored_channels(self) -> None:
        # tool_input is what the model wrote: placeholders there are restored before execution, not masked.
        self.assertEqual(set(SCORED_CHANNELS), set(CHANNELS) - {"tool_input"})
        self.assertEqual(SCORED_CHANNELS, tuple(channel for channel in CHANNELS if channel in SCORED_CHANNELS))

    def test_systems_process_the_scored_channels(self) -> None:
        self.assertEqual(tuple(CHANNEL_MAP), SCORED_CHANNELS)  # PromptGuard
        run_gitleaks = _script("run_gitleaks")
        self.assertEqual(run_gitleaks.CHANNELS, CHANNELS)
        self.assertEqual(tuple(run_gitleaks.SCORED_CHANNELS.split(",")), SCORED_CHANNELS)

    @unittest.skipUnless(HAS_CREDSWEEPER, CREDSWEEPER_REASON)
    def test_credsweeper_scans_the_scored_channels_by_default(self) -> None:
        from evaluation.adapters.credsweeper_adapter import CredSweeperAdapter

        default = inspect.signature(CredSweeperAdapter).parameters["channels"].default
        self.assertEqual(default, SCORED_CHANNELS)

    def test_run_all_scans_only_the_scored_channels(self) -> None:
        run_all = _script("run_all")
        args = argparse.Namespace(gitleaks="gitleaks", resolved_system_root=Path("checkout"))
        dataset = Path("sessions.jsonl")
        commands = [run_all.gitleaks_command(dataset, args, Path("findings.jsonl"))]
        commands += [run_all.evaluate_command(run_all.Combo(dataset, system, ml=ml), args, Path("batch"),
                                              Path("findings.jsonl"))
                     for system, ml in (("credsweeper", "off"), ("credsweeper", "on"), ("gitleaks", None))]
        for command in commands:
            self.assertNotIn("--channels", command)

    def test_evaluation_uses_match_dataset_policy(self) -> None:
        dataset_policy = _script("dataset_policy")
        self.assertEqual(set(USES), set(dataset_policy.USES) - {"ml_train"})
        self.assertEqual(set(dataset_policy.USES), {"rule_eval", "ml_eval", "ml_train"})
        self.assertEqual(TRAINING_SPLITS, dataset_policy.TRAIN_SPLITS)
        for origin in ("authored", "recorded", "external"):
            dataset_policy.require_use([{"session_id": origin, "meta": {
                "allowed_use": dataset_policy.ALLOWED_USE[origin]}}], "ml_eval")
        with self.assertRaises(PermissionError):
            dataset_policy.require_use([{"session_id": "injected", "meta": {
                "allowed_use": dataset_policy.ALLOWED_USE["injected"]}}], "ml_eval")


Step = tuple[str | None, list[tuple[int, int, str]]]  # output text (None: blocked or failed) and its edits


def _port_steps(steps: list[dict[str, Any]]) -> list[Step]:
    mod, out = ModSession(), []
    for step in steps:
        try:
            text, edits = mod.redact(step["text"], step["result"])
            out.append((text, sorted((e.start, e.end, e.replacement) for e in edits)))
        except ModFailure:
            out.append((None, []))
    return out


def _node_steps(mod: NodeMod, steps: list[dict[str, Any]]) -> list[Step]:
    session, out = mod.session(), []
    for step in steps:
        output = session.process(step["text"], step["result"])
        ok = output.status == "ok"
        out.append((output.text if ok else None, sorted((e.start, e.end, e.replacement) for e in output.edits) if ok else []))
    return out


def _scripted_sessions() -> list[list[dict[str, Any]]]:
    overlap, after = "key=abcdefgh\n", "other=zzzzzzzz\n"
    emoji = "😀 token=abcdefgh and 🔐 again abcdefgh\n"
    repeated = "A=Qw3rTy9uIo B=Zx8cVb7nMm\n"
    return [
        [{"text": overlap, "result": found(finding(overlap, "abcdef", value_hash="a"), finding(overlap, "efgh"))},
         {"text": after, "result": found(finding(after, "zzzzzzzz"))}],
        [{"text": emoji, "result": found(finding(emoji, "abcdefgh", "TOKEN"), finding(emoji, "abcdefgh", "TOKEN", nth=1))},
         {"text": repeated, "result": found(finding(repeated, "Zx8cVb7nMm"), finding(repeated, "Qw3rTy9uIo"),
                                            finding(repeated, "A", "api key"))}],
        [{"text": overlap, "result": found(finding(overlap, "abcd", offset_unit="code_points"))},
         {"text": overlap, "result": found(finding(overlap, "abcd", end=99))},
         {"text": overlap, "result": {"ok": False, "findings": [], "errors": ["SPAN_TOO_LARGE"]}},
         {"text": overlap, "result": {"ok": True, "findings": [], "errors": ["INVALID_OFFSET_RANGE"]}},
         {"text": overlap, "result": found(finding(overlap, "abcd"))}],
        # A value masked once is re-masked where the detector misses it later, and inside a longer value.
        [{"text": repeated, "result": found(finding(repeated, "Qw3rTy9uIo"))},
         {"text": "echo Qw3rTy9uIo; B=Zx8cVb7nMm\n", "result": found(finding("echo Qw3rTy9uIo; B=Zx8cVb7nMm\n", "Zx8cVb7nMm"))},
         {"text": "x=Qw3rTy9uIoQw3rTy9uIo y=Zx8cVb7nMm\n", "result": found()}],
        # A run of a known value's characters is masked as a part, unless it is only words or too short.
        [{"text": "P=Qw3rTy9uIo7Hg2Lk5Z S=password-of-mine\n",
          "result": found(finding("P=Qw3rTy9uIo7Hg2Lk5Z S=password-of-mine\n", "Qw3rTy9uIo7Hg2Lk5Z"),
                          finding("P=Qw3rTy9uIo7Hg2Lk5Z S=password-of-mine\n", "password-of-mine"))},
         {"text": "cut: Qw3rTy9uIo7, short Qw3rTy9, word password-of, joined [Qw3rTy9uIo7Hg2Lk5Z]\n", "result": found()}],
        # One placeholder per value hash, whatever type a later finding names; numbered top to bottom.
        [{"text": "A=aaaaaaaa1 B=bbbbbbbb2\n",
          "result": found(finding("A=aaaaaaaa1 B=bbbbbbbb2\n", "bbbbbbbb2", "TOKEN", value_hash="b"),
                          finding("A=aaaaaaaa1 B=bbbbbbbb2\n", "aaaaaaaa1", "TOKEN", value_hash="a"))},
         {"text": "C=aaaaaaaa1\n", "result": found(finding("C=aaaaaaaa1\n", "aaaaaaaa1", "API_KEY", value_hash="a"))}],
    ]


def _worker_sessions() -> list[list[dict[str, Any]]]:
    detector = load_worker(SYSTEM_ROOT).load_detector()
    sessions = [[{"text": item.text, "result": detector.scan(item.text, CHANNEL_MAP[item.channel])}
                 for item in session.items if item.channel in CHANNEL_MAP]
                for session in load_sessions(SESSIONS, GOLD)]
    extra = ["🔐 DB_PASSWORD=mysecret123\n", "A_PASSWORD=Qw3rTy9uIo\nB_PASSWORD=Zx8cVb7nMm\nA_PASSWORD=Qw3rTy9uIo\n"]
    return sessions + [[{"text": text, "result": detector.scan(text, "tool_result")} for text in extra]]


# The Mod generations of the scored commits. The port (tests/mod_port.py) has the rules of cca44c4 .. e9089c2; 668c2c1
# differs only by a public-prefix option that is off unless PG_PLACEHOLDER_PUBLIC_PREFIX=on.
PORT_GENERATION = ("cca44c4", "9e80dc4", "e9089c2", "668c2c1")
FAIL_CLOSED = {"424df6a": False, "d7072b4": False, "ca858be": True, "ff87b4c": True, "f07bbfb": True,
               "cca44c4": True, "9e80dc4": True, "e9089c2": True, "668c2c1": True}


def _mod(commit: str) -> NodeMod:
    path = mod_at(commit)
    if path is None:
        raise unittest.SkipTest(f"no {commit} in the checkout's history")
    return NodeMod(path)


@unittest.skipIf(SYSTEM_ROOT is None, "no promptguard-claude-demoV0 checkout")
class ModContractTests(unittest.TestCase):
    def test_channel_map_uses_the_mods_sources(self) -> None:
        mod = (SYSTEM_ROOT / MOD).read_text(encoding="utf-8")
        self.assertLessEqual(set(CHANNEL_MAP), set(CHANNELS))
        for source in CHANNEL_MAP.values():
            self.assertIn(f"'{source}'", mod)

    @unittest.skipUnless(HAS_NODE, NODE_REASON)
    def test_node_path_matches_the_port_for_its_generation(self) -> None:
        """Text and edits from register.mjs under Node equal the port's, for every Mod with the port's rules."""
        sessions = _scripted_sessions() + (_worker_sessions() if HAS_PROMPTGUARD else [])
        expected = [_port_steps(steps) for steps in sessions]
        self.assertNotIn(None, [text for text, _ in expected[1]])  # valid findings were substituted
        self.assertIn(None, [text for text, _ in expected[2]])  # the failure cases did fail
        for commit in PORT_GENERATION:
            with self.subTest(commit=commit):
                mod = _mod(commit)
                self.assertEqual([_node_steps(mod, steps) for steps in sessions], expected)
                mod.close()

    @unittest.skipUnless(HAS_NODE, NODE_REASON)
    def test_checkout_mod_matches_the_port(self) -> None:
        mod = NodeMod(SYSTEM_ROOT / MOD)
        self.assertEqual([_node_steps(mod, steps) for steps in _scripted_sessions()],
                         [_port_steps(steps) for steps in _scripted_sessions()])

    @unittest.skipUnless(HAS_NODE, NODE_REASON)
    def test_each_generation_drives(self) -> None:
        """Every scored commit's Mod runs under the driver, with its own failure handling and remask passes."""
        repeated, again = "A_PASSWORD=Qw3rTy9uIo\n", "echo Qw3rTy9uIo\n"
        part_text = "P=Qw3rTy9uIo7Hg2Lk5Z S=password-of-mine\n"
        cut = "cut: uIo7Hg2Lk5, word password-of\n"
        steps = [{"text": repeated, "result": found(finding(repeated, "Qw3rTy9uIo"))},
                 {"text": again, "result": found()},
                 {"text": part_text, "result": found(finding(part_text, "Qw3rTy9uIo7Hg2Lk5Z"),
                                                     finding(part_text, "password-of-mine"))},
                 {"text": cut, "result": found()},
                 {"text": repeated, "result": {"ok": False, "findings": [], "errors": ["ADAPTER_FAILURE:x"]}}]
        for commit, closed in FAIL_CLOSED.items():
            with self.subTest(commit=commit):
                mod = _mod(commit)
                self.assertEqual(mod.fail_closed, closed)
                session = mod.session()
                outputs = [session.process(step["text"], step["result"]) for step in steps]
                self.assertEqual(outputs[1].text, "echo [PASSWORD_1]\n")  # remaskText: every generation
                partial = commit not in ("424df6a", "d7072b4", "ca858be")  # remaskPartial since ff87b4c
                self.assertEqual("uIo7Hg2Lk5" not in outputs[3].text, partial)
                # cca44c4: a run of a value that is only words is not masked as a part
                self.assertEqual("password-of" in outputs[3].text, commit not in ("ff87b4c", "f07bbfb") or not partial)
                self.assertEqual(outputs[4].status, "blocked" if closed else "failed_open")
                mod.close()


if __name__ == "__main__":
    unittest.main()
