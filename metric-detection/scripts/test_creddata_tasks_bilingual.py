"""Natural-language variants preserve source identity and use filename placeholders."""
import json
from pathlib import Path
import tempfile
import unittest

import creddata_tasks as T
import creddata_tasks_bilingual as B
import creddata_rollout as R


class BilingualTasksTest(unittest.TestCase):
    def templates(self):
        return json.loads(B.INSTRUCTIONS.read_text())["instructions"]

    def test_pairs_share_sources_and_use_eight_shared_templates(self):
        tasks = [{"task_id": f + "-01", "family": f, "source_session_id": "same-source", "source_item_id": 0,
                  "instruction": "old wording"} for f in T.FAMILIES]
        paired = B.pair_tasks(tasks, self.templates())
        self.assertEqual(len(paired), 8)
        self.assertEqual(len({p["instruction_template"] for p in paired}), 8)
        for base in tasks:
            variants = [p for p in paired if p["task_pair_id"] == base["task_id"]]
            self.assertEqual({p["instruction_language"] for p in variants}, {"ko", "en"})
            self.assertEqual({p["source_session_id"] for p in variants}, {base["source_session_id"]})
            self.assertTrue(all("{source_file}" in p["instruction_template"] for p in variants))
            self.assertTrue(all("subject.py" not in p["instruction_template"] for p in variants))

    def test_existing_tasks_are_reissued_without_destroying_original_definition(self):
        original = {"version": "old", "tasks_per_family": 1, "tasks": [
            {"task_id": "test-01", "family": "test_writing", "instruction": "old", "target_function": "target"}]}
        converted = B.convert_config(original, {"version": "v2", "instructions": self.templates()})
        self.assertEqual(original["tasks"][0]["target_function"], "target")
        self.assertEqual(converted["tasks_per_family"], 2)
        self.assertTrue(all(p["legacy_target_function"] == "target" and "target_function" not in p for p in converted["tasks"]))
        with self.assertRaisesRegex(ValueError, "already language variants"):
            B.pair_tasks(converted["tasks"], self.templates())

    def test_one_per_family_selects_both_languages_or_the_requested_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for family in T.FAMILIES:
                for locale in ("ko", "en"):
                    path = root / (family + "__" + locale)
                    path.mkdir()
                    (path / "task.json").write_text(json.dumps({"family": family, "instruction_language": locale}))
            self.assertEqual(len(R.select_instances(root, "one-per-family")), 8)
            self.assertEqual(len(R.select_instances(root, "one-per-family", "en")), 4)
            with self.assertRaisesRegex(ValueError, "does not match"):
                R.select_instances(root, "analysis__en", "ko")


if __name__ == "__main__":
    unittest.main()
