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


if __name__ == "__main__":
    unittest.main()
