"""planted.json points at the values as built, for every task."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_planted as planted
import m2_tasks as mt


class PlantedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = mt.load_tasks()

    def test_workspace_offsets_and_lines_point_at_the_value_as_built(self):
        checked = 0
        for task in self.tasks:
            for entry in planted.planted(task)["entries"]:
                for place in entry["placements"]:
                    if place["source"] not in ("file", "claude_md", "session_hook"):
                        continue
                    built = task.fill((task.dir / "workspace" / place["path"]).read_bytes().decode("utf-8"))
                    self.assertEqual(built[place["start"]:place["end"]], entry["value"], (task.id, entry["name"]))
                    self.assertEqual(built[:place["start"]].count("\n") + 1, place["line"])
                    checked += 1
        self.assertGreater(checked, 300)

    def test_the_other_task_fields_are_found(self):
        task = next(t for t in self.tasks if "{{secret:" in t.spec["prompt"])
        sources = {p["source"] for e in planted.planted(task)["entries"] for p in e["placements"]}
        self.assertIn("prompt", sources)

    def test_entries_cover_secrets_and_decoys_and_every_secret_has_its_value_as_a_form(self):
        for task in self.tasks:
            entries = planted.planted(task)["entries"]
            self.assertEqual({e["name"] for e in entries if e["role"] == "secret"}, set(task.secrets), task.id)
            self.assertEqual({e["name"] for e in entries if e["role"] == "decoy"}, set(task.decoys), task.id)
            for entry in entries:
                self.assertIn({"how": "exact", "text": entry["value"]}, entry["forms"], (task.id, entry["name"]))

    def test_a_scene_is_the_family_or_the_task(self):
        for task in self.tasks:
            want = task.meta.get("family") or task.id.split("-")[0]
            self.assertEqual(planted.planted(task)["scene"], want)


if __name__ == "__main__":
    unittest.main()
