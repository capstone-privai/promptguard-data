"""The dashboard's counts must equal the scorer's, whatever the adapter does and however the data is sharded."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import catalog, collect, taxonomy  # noqa: E402  (importing pipeline puts metric-detection/ on sys.path)
from pipeline.taxonomy import MAX_GROUPS, OTHER_GROUP, OTHER_TYPE, placeholder_type  # noqa: E402
from pipeline.paths import METRIC_DETECTION  # noqa: E402
from pipeline.runner import prf  # noqa: E402

from evaluation.adapters.base import ItemOutput  # noqa: E402
from evaluation.adapters.reference import IdentityAdapter, OracleAdapter  # noqa: E402
from evaluation.dataset.io import load_sessions  # noqa: E402
from evaluation.run import evaluate_sessions  # noqa: E402
from evaluation.scorer.edits import Edit, apply_edits  # noqa: E402

FIXTURES = METRIC_DETECTION / "evaluation" / "tests" / "fixtures"


class ScriptedAdapter:
    """Every outcome on purpose: gold spans in turn exact, over, partial and missed; items without gold get a false
    positive whose placeholder names an API key (counted as SECRET) or nothing (OTHER)."""

    name = "scripted"

    def describe(self):
        return {"system": self.name}

    def run_session(self, session):
        outputs = {}
        for item in session.items:
            edits = []
            gold = session.gold_for(item.item_id)
            for span in gold:
                turn = (span.span_id + item.item_id) % 4
                if turn == 0:
                    edits.append(Edit(span.start, span.end, "[PASSWORD_1]"))
                elif turn == 1:
                    edits.append(Edit(max(0, span.start - 2), span.end, "[PASSWORD_2]"))
                elif turn == 2:
                    edits.append(Edit(span.start, span.end - 2, "[TOKEN_1]"))
            if not gold and len(item.text) > 30:
                edits.append(Edit(0, 5, "[API_KEY_1]" if item.item_id % 2 == 0 else "[CREDENTIAL_1]"))
            outputs[item.item_id] = ItemOutput(item.item_id, apply_edits(item.text, edits), edits)
        return outputs


def group_of(meta):
    return str(meta.get("source", "-"))


def payload_for(sessions, adapter, dataset="fixture", per_bucket=collect.PER_BUCKET):
    result = evaluate_sessions(sessions, adapter)
    collector = collect.Collector(dataset, group_of, per_bucket)
    lookup = {(session.session_id, item.item_id): (session, item) for session in sessions for item in session.items}
    for score in result.scores:
        session, item = lookup[(score.session_id, score.item_id)]
        collector.add(session, item, score, result.outputs[(score.session_id, score.item_id)])
    payload = collector.payload()
    payload.update(counts=result.metrics["counts"], lines_total=result.metrics["lines_total"])
    return payload, result.metrics


class PlaceholderTypeTest(unittest.TestCase):
    def test_kinds_map_onto_gold_types(self):
        self.assertEqual(placeholder_type("[PASSWORD_3]"), "PASSWORD")
        self.assertEqual(placeholder_type("[API_KEY_12]"), "SECRET")
        self.assertEqual(placeholder_type("[GITHUB_TOKEN_1]"), "TOKEN")
        self.assertEqual(placeholder_type("[AWS_KEY_2]"), "ACCESS_KEY")
        self.assertEqual(placeholder_type("[JWT_1][PASSWORD_2]"), "TOKEN")

    def test_unnamed_kinds_are_other(self):
        self.assertEqual(placeholder_type("[CREDENTIAL_4]"), OTHER_TYPE)
        self.assertEqual(placeholder_type("[SECRET]"), OTHER_TYPE)  # CredSweeper/gitleaks style, no number
        self.assertEqual(placeholder_type(""), OTHER_TYPE)


class CatalogTest(unittest.TestCase):
    def test_every_grouped_dataset_has_names(self):
        self.assertEqual(set(taxonomy.GROUPS), set(catalog.DATASETS))
        names = catalog.as_json()
        self.assertEqual(set(names["types"]), set(taxonomy.TYPES))
        self.assertEqual(set(names["channels"]), set(taxonomy.CHANNELS))

    def test_sub_groups(self):
        self.assertEqual(taxonomy.group_of("sessions_from_CredData")({"creddata_file": "data/x/y.py"}), "코드")
        self.assertEqual(taxonomy.group_of("sessions_from_CredData")({"creddata_file": "data/x/key.pem"}), "키·인증서")
        self.assertEqual(taxonomy.group_of("sessions_from_SWE-Gym")({"group_id": "swe-gym-getmoto"}), "getmoto")
        self.assertEqual(taxonomy.group_of("sessions_new")({"scenario": "s1"}), "s1")
        self.assertEqual(catalog.dataset_info("sessions_from_newsource").label, "newsource")


class CountsTest(unittest.TestCase):
    def setUp(self):
        self.sessions = load_sessions(FIXTURES / "sessions.jsonl", FIXTURES / "gold.jsonl")

    def check(self, adapter):
        payload, metrics = payload_for(self.sessions, adapter)
        merged = collect.merge([payload])  # raises MergeError when the cells disagree with the scorer
        self.assertEqual(merged["counts"], {key: metrics["counts"][key] for key in collect.COUNT_KEYS})
        result = prf(merged["counts"])
        self.assertEqual(result["recall"], metrics["recall"])
        self.assertEqual(result["precision"], metrics["precision"])
        return merged

    def test_oracle_identity_and_every_outcome(self):
        oracle = self.check(OracleAdapter())
        self.assertEqual(prf(oracle["counts"])["f1"], 1.0)
        identity = self.check(IdentityAdapter())
        self.assertIsNone(prf(identity["counts"])["precision"])
        scripted = self.check(ScriptedAdapter())
        counts = scripted["counts"]
        for key in ("exact", "over", "partial", "missed", "edits_tp", "edits_over", "edits_fp"):
            self.assertGreater(counts[key], 0, key)

    def test_false_positives_take_their_placeholder_type(self):
        merged = self.check(ScriptedAdapter())
        fp_by_type = {}
        for _group, _channel, type_, *values in merged["cells"]:
            fp_by_type[type_] = fp_by_type.get(type_, 0) + values[-1]
        self.assertGreater(fp_by_type.get("SECRET", 0), 0)
        self.assertGreater(fp_by_type.get(OTHER_TYPE, 0), 0)

    def test_sharding_does_not_change_counts_or_picks(self):
        whole, _ = payload_for(self.sessions, ScriptedAdapter(), per_bucket=1)
        halves = [payload_for(part, ScriptedAdapter(), per_bucket=1)[0]
                  for part in (self.sessions[:3], self.sessions[3:])]
        one, two = collect.merge([whole], per_bucket=1), collect.merge(halves, per_bucket=1)
        self.assertEqual(one["cells"], two["cells"])
        self.assertEqual(one["items"], two["items"])
        self.assertEqual({(e["session"], e["item"]) for e in one["examples"]},
                         {(e["session"], e["item"]) for e in two["examples"]})

    def test_tool_input_is_left_out(self):
        sessions = load_sessions(FIXTURES / "sessions.jsonl", FIXTURES / "gold.jsonl")
        moved = sessions[3].items[1]
        sessions[3].items[1] = type(moved)(moved.item_id, moved.turn_id, "tool_input", moved.text)
        payload, metrics = payload_for(sessions, OracleAdapter())
        merged = collect.merge([payload])
        self.assertEqual(metrics["counts"]["gold_excluded"], 1)
        self.assertEqual(sum(row[3] for row in merged["cells"]), metrics["counts"]["exact"])

    def test_mismatch_is_refused(self):
        payload, _ = payload_for(self.sessions, OracleAdapter())
        payload["counts"] = {**payload["counts"], "exact": payload["counts"]["exact"] + 1}
        with self.assertRaises(collect.MergeError):
            collect.merge([payload])


class ExamplesTest(unittest.TestCase):
    def test_examples_show_the_spans_they_were_picked_for(self):
        sessions = load_sessions(FIXTURES / "sessions.jsonl", FIXTURES / "gold.jsonl")
        payload, _ = payload_for(sessions, ScriptedAdapter())
        merged = collect.merge([payload])
        tags = {tag for example in merged["examples"] for tag in example["tags"]}
        self.assertTrue({"PASSWORD:exact", "PASSWORD:over", "PASSWORD:missed", "SECRET:fp", "clean"} <= tags, tags)
        for example in merged["examples"]:
            for start, end, *_ in example["gold"] + example["edits"]:
                self.assertTrue(0 <= start < end <= len(example["text"]))
            self.assertEqual(example["id"], f"{example['session']}#{example['item']}@{example['offset']}")
        self.assertTrue(set(merged["overview"]) <= {example["id"] for example in merged["examples"]})

    def test_windows_cluster_close_spans_and_split_far_ones(self):
        text = ("x" * 99 + "\n") * 40
        spans, owner = collect.windows(text, [(1000, 1010), (1100, 1110), (3500, 3510)])
        self.assertEqual(len(spans), 2)
        self.assertEqual(owner, [0, 0, 1])
        for start, end in spans:
            self.assertTrue(start == 0 or text[start - 1] == "\n")  # snapped to a line start
        self.assertLessEqual(spans[0][0], 1000 - collect.PAD + collect.SNAP)

    def test_many_groups_fold_into_other(self):
        items = {(f"g{index:02d}", "tool_output"): [index + 1, 0, 1] for index in range(MAX_GROUPS + 5)}
        groups = collect._fold_groups(items)
        self.assertEqual(len(set(groups.values())), MAX_GROUPS)
        self.assertEqual(groups["g00"], OTHER_GROUP)  # the smallest
        self.assertEqual(groups[f"g{MAX_GROUPS + 4:02d}"], f"g{MAX_GROUPS + 4:02d}")


if __name__ == "__main__":
    unittest.main()
