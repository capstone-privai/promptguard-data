"""Offline tests of trajectory annotations and explicit API configuration; no paid requests."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock

import convert_trajectory as C
import creddata_rollout as R


class CredDataRolloutTest(unittest.TestCase):
    def data(self):
        task = {"task_id": "test_writing-01", "family": "test_writing", "split": "train",
                "component_id": "component-fixture", "source_repo_id": "repo-fixture",
                "source_session_id": "source-fixture", "source_item_id": 0, "source_license": "fixture-only",
                "slots": {"s_01": {"type": "PASSWORD", "generator_kind": "password_random"}}}
        return task, {"values": {"s_01": "nZ7vQ2mJ6pR9sK4x"}}

    def test_commands_and_tool_outputs_both_receive_labels(self):
        task, registry = self.data()
        value = registry["values"]["s_01"]
        items = [C.Item("t0", "prompt", "Inspect the configuration."),
                 C.Item("t0", "tool_output", f'password="{value}"\n'),
                 C.Item("t1", "tool_input", json.dumps({"command": f"client --password '{value}'"}))]
        session, gold, labels, stats = R.label_items(task, registry, items, "fixture-run")
        self.assertEqual(stats["gold_tool_output"], 1)
        self.assertEqual(stats["gold_tool_input"], 1)
        self.assertEqual(len(gold), 2)
        self.assertIsNone(session["meta"]["success_grading"])
        for row in gold:
            text = session["items"][row["item_id"]]["text"]
            span = row["span"]
            self.assertEqual(text[span["start"]:span["end"]], value)

    def test_unknown_credential_is_queued_for_review(self):
        task, registry = self.data()
        item = C.Item("t0", "tool_output", 'password="sU8tR5vW2xY7zP4q"\n')
        _, gold, labels, stats = R.label_items(task, registry, [item], "fixture-run")
        self.assertEqual(gold, [])
        self.assertTrue(any(r.get("review") and r.get("kind") == "undeclared" for r in labels))
        self.assertGreater(stats["review_candidates"], 0)

    def test_subscriber_login_never_substitutes_for_an_api_key(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "fixture-not-a-real-token"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ANTHROPIC_API_KEY is not configured"):
                R.api_environment()

    def test_env_file_is_read_as_data_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            path = Path(tmp) / "pilot.env"
            path.write_text("export ANTHROPIC_API_KEY='literal-$(never-run)'\nUNRELATED=ignored\n")
            env = R.api_environment(path)
            self.assertEqual(env["ANTHROPIC_API_KEY"], "literal-$(never-run)")
            self.assertNotIn("UNRELATED", env)

    def test_subscription_mode_selects_existing_login_and_removes_api_overrides(self):
        auth = {"loggedIn": True, "authMethod": "claude.ai"}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture-only", "ANTHROPIC_BASE_URL": "http://fixture",
                                     "CLAUDE_CODE_SIMPLE": "1"}, clear=True), \
                patch.object(R.subprocess, "run", return_value=Mock(stdout=json.dumps(auth))):
            env = R.subscription_environment()
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("ANTHROPIC_BASE_URL", env)
        self.assertNotIn("CLAUDE_CODE_SIMPLE", env)

    def test_model_guard_blocks_non_haiku_before_upstream_call(self):
        connection = Mock()
        guarded = R.ModelGuardConnection(connection)
        with self.assertRaisesRegex(ValueError, "non-Haiku"):
            guarded.request("POST", "/v1/messages", body=json.dumps({"model": "claude-sonnet-fixture"}))
        connection.request.assert_not_called()
        guarded.request("POST", "/v1/messages", body=json.dumps({"model": "claude-haiku-fixture"}))
        connection.request.assert_called_once()

    def test_one_per_family_accepts_automatically_generated_task_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for family in R.T.FAMILIES:
                for n in (1, 2):
                    path = root / f"{family}-auto-{n:04}"
                    path.mkdir()
                    (path / "task.json").write_text(json.dumps({"family": family}))
            selected = R.select_instances(root, "one-per-family")
            self.assertEqual([p.name for p in selected], [f"{family}-auto-0001" for family in R.T.FAMILIES])


class SourceGoldTest(unittest.TestCase):
    def test_slot_without_gold_source_span_is_not_labeled(self):
        import creddata_export as E
        task = {"task_id": "t", "source_session_id": "src",
                "occurrences": [{"secret_id": "s_01", "source_start": 10, "source_end": 18},
                                {"secret_id": "s_02", "source_start": 30, "source_end": 43},
                                {"secret_id": "s_03", "source_start": 50, "source_end": 62},
                                {"secret_id": "s_03", "source_start": 66, "source_end": 78}]}
        registry = {"seed": "x", "values": {"s_01": "a", "s_02": "b", "s_03": "c"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold_category_test.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in [
                {"session_id": "src", "start": 10, "end": 18}, {"session_id": "src", "start": 66, "end": 78},
                {"session_id": "src", "start": 30, "end": 43, "dropped": "unsure"}]))
            kept, rejected = E.without_rejected_slots(task, registry, E.source_gold_spans(path))
        self.assertEqual(rejected, ["s_02"])  # s_03 keeps one gold source span: the rules judge its occurrences
        self.assertEqual(kept["values"], {"s_01": "a", "s_03": "c"})
        self.assertEqual(registry["values"]["s_02"], "b")  # the input is not changed


class ExcludedOccurrencesTest(unittest.TestCase):
    def data(self):
        task = {"slots": {"s_01": {"type": "Password", "structure": None}, "s_02": {"type": "Token", "structure": None},
                          "s_03": {"type": "Password", "structure": None}},
                "occurrences": [{"secret_id": name, "codec": "raw"} for name in ("s_01", "s_02", "s_03")]}
        return task, {"values": {"s_01": "nZ7vQ2mJ6pR9sK4x", "s_02": "x7k2q9", "s_03": "x7k2q9"}}

    def test_every_occurrence_of_a_rejected_value_is_excluded(self):
        import creddata_export as E
        task, registry = self.data()
        items = [C.Item("t0", "prompt", "Check the port."),
                 C.Item("t0", "tool_output", "     1\tpassword=nZ7vQ2mJ6pR9sK4x\n     2\turl=db://u:p@host:x7k2q9\n"),
                 C.Item("t1", "tool_input", json.dumps({"command": "grep x7k2q9 conf; echo x7k2q9x"})),
                 C.Item("t1", "tool_output", "port x7k2q9 is used; ax7k2q9 is another word")]
        rows, still_gold = E.excluded_occurrences(task, registry, ["s_02"], items, [])
        found = [(r["item_id"], r["channel"], items[r["item_id"]].text[r["start"]:r["end"]]) for r in rows]
        # every channel, line-numbered output included; not inside another word
        self.assertEqual(found, [(1, "tool_output", "x7k2q9"), (2, "tool_input", "x7k2q9"), (3, "tool_output", "x7k2q9")])
        self.assertEqual({(r["entry"], r["type"], r["reason"]) for r in rows}, {("s_02", "Token", "slot_no_longer_gold")})
        self.assertEqual(still_gold, [])
        self.assertNotIn("x7k2q9", json.dumps(rows))  # rows carry the hash, never the value

    def test_an_occurrence_that_is_still_gold_through_another_slot_stays_gold(self):
        import creddata_export as E
        task, registry = self.data()
        text = "a: x7k2q9\nb: x7k2q9\n"
        gold = [{"item_id": 0, "span": {"start": 3, "end": 9, "type": "Password"}}]  # s_03 is gold at the first place
        rows, still_gold = E.excluded_occurrences(task, registry, ["s_02"], [C.Item("t0", "tool_output", text)], gold)
        self.assertEqual([(r["start"], r["end"]) for r in rows], [(13, 19)])
        self.assertEqual([(r["start"], r["end"]) for r in still_gold], [(3, 9)])


class EvalSetExcludedTest(unittest.TestCase):
    def test_excluded_rows_follow_the_gold_rows_with_later_span_ids(self):
        import creddata_eval_set as S
        with tempfile.TemporaryDirectory() as tmp:
            handoff, out = Path(tmp) / "handoff", Path(tmp) / "out"
            handoff.mkdir()
            (handoff / "manifest.json").write_text(json.dumps({"split": "test", "variants_per_session": 0, "sessions": 1}))
            (handoff / "sessions_test.jsonl").write_text(json.dumps({"session_id": "s", "items": [], "meta": {}}) + "\n")
            (handoff / "gold_test.jsonl").write_text(json.dumps(
                {"session_id": "s", "item_id": 1, "span_id": 0, "span": {"start": 3, "end": 9, "type": "Password"}}) + "\n")
            (handoff / "excluded_test.jsonl").write_text("".join(json.dumps(
                {"session_id": "s", "item_id": item, "channel": "tool_output", "start": start, "end": start + 6,
                 "type": "Token", "entry": "s_02", "value_sha256": "0" * 16, "reason": "slot_no_longer_gold"}) + "\n"
                for item, start in ((1, 13), (2, 0))))
            with patch("sys.argv", ["x", "--handoff", str(handoff), "--out", str(out)]), patch("builtins.print"):
                S.main()
            rows = [json.loads(line) for line in
                    (out / "data_answer/gold_from_CredData-trajectory.jsonl").read_text().splitlines()]
        self.assertEqual([(r["item_id"], r["span_id"], r.get("excluded")) for r in rows],
                         [(1, 0, None), (1, 1, "slot_no_longer_gold"), (2, 0, "slot_no_longer_gold")])
        self.assertEqual(rows[1]["span"], {"start": 13, "end": 19, "type": "TOKEN", "category": "Token"})


if __name__ == "__main__":
    unittest.main()
