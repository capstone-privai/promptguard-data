"""Source partition invariants: repository isolation, duplicate isolation, reproducibility and input pinning."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

import split_creddata as S


def fixture(repo, number=0, context=None, secret=None):
    value = secret or f"fixture-value-{repo}-{number}"
    context = context or (f"def read_config_{repo}_{number}(settings):\n"
                          f"    return settings.get('endpoint_{repo}_{number}', 'localhost')\n") * 4
    text = context + f'\nPASSWORD="{value}"\n'
    start = text.index(value)
    sid = f"creddata-{repo}-file{number}"
    session = {"session_id": sid, "meta": {
        "creddata_file": f"data/{repo}/src/file{number}.py", "group_id": "creddata-" + repo,
        "origin": "external", "allowed_use": ["rule_eval", "ml_eval"],
        "creddata_commit": "fixture-commit", "dataset_version": "fixture-v1"},
        "items": [{"item_id": 0, "channel": "tool_output", "text": text}]}
    gold = {"session_id": sid, "item_id": 0, "span_id": 0,
            "span": {"start": start, "end": start + len(value), "type": "PASSWORD"}}
    return session, gold


class SplitCredDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sessions = self.root / "sessions.jsonl"
        self.gold = self.root / "gold.jsonl"
        self.rows = [fixture(f"repo{i:02}") for i in range(12)]

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        self.sessions.write_text("".join(json.dumps(s) + "\n" for s, _ in self.rows))
        self.gold.write_text("".join(json.dumps(g) + "\n" for _, g in self.rows))
        return S.load_corpus(self.sessions, self.gold)

    def outputs(self):
        self.load()
        return S.build_outputs(self.sessions, self.gold, [0.8, 0.1, 0.1], S.SEED)

    def test_duplicate_contexts_with_other_values_and_whitespace_stay_together(self):
        context = "def connect(config):\n    use_config(config, retries=3, timeout=10)\n" * 7
        self.rows[:2] = [fixture("repo00", context=context, secret="different-fixture-one"),
                         fixture("repo01", context=context.replace("    ", "\t"), secret="different-fixture-two")]
        corpus = self.load()
        groups = S.components(corpus)
        self.assertIn(["repo00", "repo01"], groups)
        assignments = S.partition(corpus, groups, [0.8, 0.1, 0.1], S.SEED)
        self.assertEqual(assignments["repo00"], assignments["repo01"])

    def test_every_session_assigned_once_and_whole_repositories_stay_together(self):
        self.rows.append(fixture("repo00", number=1))
        output = self.outputs()
        memberships = {s: set(output[s + ".txt"].decode().splitlines()) for s in S.SPLITS}
        all_ids = [sid for ids in memberships.values() for sid in ids]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(set(all_ids), {s["session_id"] for s, _ in self.rows})
        for ids in memberships.values():
            self.assertEqual("creddata-repo00-file0" in ids, "creddata-repo00-file1" in ids)
        manifest = json.loads(output["manifest.json"])
        self.assertEqual(sum(c["sessions"] for c in manifest["counts"].values()), len(self.rows))
        self.assertEqual(sum(c["gold_spans"] for c in manifest["counts"].values()), len(self.rows))
        self.assertFalse(manifest["ready_for_training"])

    def test_assignment_does_not_depend_on_input_row_order(self):
        before = self.outputs()
        self.rows.reverse()
        after = self.outputs()
        for name in ("train.txt", "val.txt", "test.txt", "repositories.jsonl", "duplicate_components.json"):
            self.assertEqual(before[name], after[name])

    def test_repeated_build_is_identical_without_copying_text_or_values(self):
        first = self.outputs()
        source_bytes = (self.sessions.read_bytes(), self.gold.read_bytes())
        self.assertEqual(first, S.build_outputs(self.sessions, self.gold, [0.8, 0.1, 0.1], S.SEED))
        self.assertEqual(source_bytes, (self.sessions.read_bytes(), self.gold.read_bytes()))
        for content in first.values():
            self.assertNotIn(b"fixture-value-", content)
            self.assertNotIn(b"def read_config_", content)

    def test_masked_secret_without_context_does_not_merge_all_key_files(self):
        for session, gold in self.rows:
            text = session["items"][0]["text"]
            span = gold["span"]
            value = text[span["start"]:span["end"]]
            session["items"][0]["text"] = value
            span.update(start=0, end=len(value))
        corpus = self.load()
        self.assertEqual(corpus.contexts, {})
        self.assertEqual(len(S.components(corpus)), 12)

    def test_invalid_or_orphan_gold_is_rejected(self):
        self.rows[0][1]["span"]["end"] = 999999
        with self.assertRaisesRegex(ValueError, "offsets"):
            self.load()
        self.rows[0] = fixture("repo00")
        self.rows[0][1]["session_id"] = "not-present"
        with self.assertRaisesRegex(ValueError, "orphan"):
            self.load()

    def test_duplicate_ids_and_inconsistent_provenance_are_rejected(self):
        self.rows.append(self.rows[0])
        with self.assertRaisesRegex(ValueError, "duplicate gold"):
            self.load()
        self.rows.pop()
        self.rows[0][0]["meta"]["group_id"] = "creddata-other-repo"
        with self.assertRaisesRegex(ValueError, "disagree"):
            self.load()

    def test_changed_inputs_cannot_overwrite_frozen_membership(self):
        before = self.outputs()
        out = self.root / "frozen"
        out.mkdir()
        for name, data in before.items():
            (out / name).write_bytes(data)
        S.check_outputs(out, before)
        self.rows[0][0]["items"][0]["text"] += "\n# changed source\n"
        after = self.outputs()
        with self.assertRaisesRegex(ValueError, "mismatch"):
            S.check_outputs(out, after)
        self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_impossible_group_count_and_invalid_ratios_are_rejected(self):
        corpus = self.load()
        with self.assertRaisesRegex(ValueError, "fewer independent"):
            S.partition(corpus, [list(corpus.repos)], [0.8, 0.1, 0.1], S.SEED)
        with self.assertRaisesRegex(ValueError, "sum to one"):
            S.partition(corpus, S.components(corpus), [0.9, 0.1, 0.1], S.SEED)


if __name__ == "__main__":
    unittest.main()
