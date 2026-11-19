"""Rule eligibility and balanced sampling, without LLMs or agent execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import creddata_tasks as T
import creddata_tasks_auto as A


INSTRUCTIONS = {f: "공통 지시문: " + f for f in T.FAMILIES}


def sample(number, language="python", **kwargs):
    secret = "synthetic-source-fixture"
    if language == "python":
        text = ("# A source excerpt with enough nonsecret context to explain its inputs and returned data.\n"
                f"PASSWORD = '{secret}'\ndef process_{number}(value):\n    return value + {number}\n")
    else:
        text = json.dumps({"password": secret, "port": 8000 + number,
                           "description": "A configuration with ordinary runtime metadata and enough readable context.", **kwargs})
    start = text.index(secret)
    session = {"session_id": f"creddata-repo{number:02}-file{number:02}",
               "meta": {"creddata_file": f"data/repo{number:02}/src/file{number:02}." + ("py" if language == "python" else "json")}}
    item = {"item_id": 0, "text": text}
    spans = [{"start": start, "end": start + len(secret), "type": "PASSWORD"}]
    repo = {"repo_id": f"repo{number:02}", "component_id": f"component{number:02}"}
    return session, item, spans, repo


class AutoTasksTest(unittest.TestCase):
    def candidates(self, count=12):
        return [A.inspect_item(*sample(i)) for i in range(count)]

    def test_one_source_can_qualify_for_all_four_families(self):
        candidate = A.inspect_item(*sample(1))
        self.assertEqual(set(candidate["eligible_families"]), set(T.FAMILIES))
        self.assertEqual(candidate["facts"]["testable_top_level_functions"], ["process_1"])

    def test_config_tests_and_conversion_have_different_eligibility(self):
        candidate = A.inspect_item(*sample(1, "json", nullable=None))
        self.assertIn("test_writing", candidate["eligible_families"])
        self.assertNotIn("refactoring", candidate["eligible_families"])

    def test_duplicates_and_broken_json_are_rejected(self):
        session, item, spans, repo = sample(1, "json")
        item["text"] = item["text"].replace('"port": 8001', '"port": 8001, "port": 8002')
        with self.assertRaisesRegex(A.Ineligible, "duplicate_json_key"):
            A.inspect_item(session, item, spans, repo)
        item["text"] = "{" + item["text"]
        with self.assertRaisesRegex(A.Ineligible, "invalid_json_syntax"):
            A.inspect_item(session, item, spans, repo)

    def test_partial_literal_is_not_rendered_as_arbitrary_text(self):
        session, item, spans, repo = sample(1)
        spans[0]["start"] += 2
        with self.assertRaisesRegex(A.Ineligible, "whole_supported_string"):
            A.inspect_item(session, item, spans, repo)

    def test_noop_functions_and_factory_fragments_are_not_test_targets(self):
        tree = __import__("ast").parse(
            'def empty():\n    "doc"\n    pass\n'
            'def factory():\n    def inner(x):\n        return x\n'
            'def main():\n    launch()\n'
            'def test_existing():\n    assert True\n'
            'def useful(x):\n    return x + 1\n')
        self.assertEqual(A.testable_functions(tree), ["useful"])

    def test_sampler_uses_four_shared_instructions_and_equal_counts(self):
        tasks = A.select_tasks(self.candidates(), 3, "seed", 2, INSTRUCTIONS)
        self.assertEqual(len(tasks), 12)
        for family in T.FAMILIES:
            selected = [t for t in tasks if t["family"] == family]
            self.assertEqual(len(selected), 3)
            self.assertEqual({t["instruction"] for t in selected}, {INSTRUCTIONS[family]})
            self.assertEqual(len({t["source_session_id"] for t in selected}), 3)
        self.assertEqual(len({t["instruction"] for t in tasks}), 4)

    def test_selection_is_reproducible_when_input_order_changes(self):
        candidates = self.candidates()
        first = A.select_tasks(candidates, 3, "seed", 2, INSTRUCTIONS)
        self.assertEqual(first, A.select_tasks(list(reversed(candidates)), 3, "seed", 2, INSTRUCTIONS))
        self.assertNotEqual(first, A.select_tasks(candidates, 3, "other-seed", 2, INSTRUCTIONS))

    def test_duplicate_contexts_and_repository_cap_do_not_pad_a_shortage(self):
        candidates = self.candidates(8)
        for c in candidates:
            c["context_sha256"] = "same-context"
        with self.assertRaisesRegex(ValueError, "no duplicates will be added"):
            A.select_tasks(candidates, 2, "seed", 8, INSTRUCTIONS)
        candidates = self.candidates(8)
        for c in candidates:
            c["source_repo_id"] = "one-repository"
        with self.assertRaisesRegex(ValueError, "repository-cap"):
            A.select_tasks(candidates, 2, "seed", 1, INSTRUCTIONS)

    def test_rebuild_preserves_instances_and_rejects_catalog_changes(self):
        tasks = A.select_tasks(self.candidates(), 1, "seed", 2, INSTRUCTIONS)
        config = {"tasks_per_family": 1, "tasks": tasks}
        stats = {"selected_source_files": 4, "selected_repositories": 4}
        with tempfile.TemporaryDirectory() as tmp, patch.object(T, "build_pack", return_value={"manifest.json": b"{}\n"}):
            out = Path(tmp) / "generated"
            A.write_expansion(out, config, [], stats, Path(tmp))
            runtime = out / "instances/run/output.txt"
            runtime.parent.mkdir(parents=True)
            runtime.write_text("agent output")
            A.write_expansion(out, config, [], stats, Path(tmp))
            self.assertEqual(runtime.read_text(), "agent output")
            with self.assertRaisesRegex(ValueError, "different content"):
                A.write_expansion(out, {**config, "changed": True}, [], stats, Path(tmp))


if __name__ == "__main__":
    unittest.main()
