"""Scene labels stay complete, and counts are per scene rather than per task."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_axes as axes
import m2_tasks as mt


class LabelFileTests(unittest.TestCase):
    def test_every_scene_has_a_valid_label_and_every_label_a_scene(self):
        self.assertEqual(axes.problems(mt.load_tasks(["all"]), axes.load_labels()), [])


class Task:
    suite = "gen"

    def __init__(self, task_id, family=None):
        self.id, self.meta = task_id, {"project": "backend", **({"family": family} if family else {})}


class CensusTests(unittest.TestCase):
    def test_a_family_counts_as_one_scene_however_many_tasks_it_has(self):
        tasks = [Task("s01-a", "ingress"), Task("s02-b", "ingress"), Task("t01-c")]
        labels = {"ingress": {"work": "incident", "credential": "incidental"},
                  "t01": {"work": "incident", "credential": "central"}}
        result = axes.census(tasks, labels)
        self.assertEqual(result["work"]["incident"], {"tasks": 3, "scenes": 2})
        self.assertEqual(result["work"]["test"], {"tasks": 0, "scenes": 0})
        self.assertEqual(result["credential"]["incidental"], {"tasks": 2, "scenes": 1})

    def test_reports_a_stale_label_and_an_unknown_value(self):
        found = axes.problems([Task("t01-c")], {"t01": {"work": "nope", "credential": "central"},
                                                "gone": {"work": "docs", "credential": "central"}})
        self.assertTrue(any("gone has no task" in p for p in found))
        self.assertTrue(any("unknown work" in p for p in found))


if __name__ == "__main__":
    unittest.main()
