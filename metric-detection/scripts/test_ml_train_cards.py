"""Regression tests for the coverage parts of the ML training cards (stdlib unittest)."""
import json
import unittest

from label_rules import exclusion_kind
import ml_train_build as B
import ml_train_cards as C
import ml_train_write as W
import value_gen


class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = C.load(C.CONFIG)
        cls.cards = C.draw(cls.cfg, C.load_catalog(cls.cfg))

    def test_drawing_twice_gives_the_same_cards(self):
        self.assertEqual(self.cards, C.draw(self.cfg, C.load_catalog(self.cfg)))

    def test_dense_cards_hold_many_secrets_that_start_in_tool_output(self):
        dense = [c for c in self.cards if c["dense"]]
        self.assertTrue(dense)
        for c in dense:
            self.assertIn(c["context"], self.cfg["extra_secrets"]["dense"]["contexts"])
            self.assertGreaterEqual(len(c["secrets"]), 4)
            self.assertEqual({s["channel"] for s in c["secrets"]}, {"tool_output"})

    def test_blobs_stay_out_of_credential_positions(self):
        for c in self.cards:
            for n in c["negatives"]:
                if n["kind"] in self.cfg["negatives"]["anywhere_only"]:
                    self.assertEqual(n["position"], "anywhere")

    def test_only_part_of_the_reference_contrasts_stay(self):
        rows = [c for c in self.cards if c["scene"] and any(n.get("contrast") for n in c["negatives"])]
        kept = sum(n.get("contrast", False) and n["kind"] == "reference" for c in rows for n in c["negatives"])
        self.assertLess(kept, 800)  # 1,100 or more when every reference contrast stays
        self.assertGreater(kept, 300)

    def test_command_option_cards_name_a_password_outside_tool_input(self):
        cards = [c for c in self.cards if c["boundary"] and c["boundary"]["rule"] == "command_option"]
        self.assertGreaterEqual(sum(c["variants"] for c in cards if c["split"] != "test_ood"), 200)  # plan 3.4
        for c in cards:
            target = c["secrets"][c["boundary"]["secret"] - 1]
            self.assertEqual(target["type"], "PASSWORD")
            self.assertIn(target["placeholder"], c["boundary"]["instruction"])
            self.assertNotEqual(target["channel"], "tool_input")

    def test_every_drawn_kind_is_a_generator(self):
        for c in self.cards:
            for n in c["negatives"]:
                self.assertIn(n["kind"], value_gen.NEGATIVE_KINDS)


class FollowsCard(unittest.TestCase):
    CARD = {"items": 2, "turns": 1, "language": "en", "negatives": [], "dense": True,
            "secrets": [{"placeholder": f"{{{{password:s{i}}}}}", "kind": "password", "type": "PASSWORD",
                         "channel": "tool_output", "repeat": "once", "mask": None} for i in range(1, 6)]}

    def items(self, split_at):
        names = [s["placeholder"] for s in self.CARD["secrets"]]
        lines = lambda part: "\n".join(f"password{i}={ph}" for i, ph in enumerate(part))
        return [{"turn_id": "t0", "channel": "prompt", "text": "check the config"},
                {"turn_id": "t0", "channel": "tool_output", "text": lines(names[:split_at])},
                {"turn_id": "t0", "channel": "tool_output", "text": lines(names[split_at:])}]

    def test_accepts_secrets_together(self):
        self.assertEqual(W.follows_card(self.CARD, self.items(4)), [])

    def test_rejects_secrets_spread_over_items(self):
        problems = W.follows_card(self.CARD, self.items(2))
        self.assertTrue(any("not together" in p for p in problems), problems)


class CommandOption(unittest.TestCase):
    FORMS = ("mysql -uroot -p{}", "mysqldump -uroot -p{} app", "sshpass -p {} ssh deploy@host",
             "docker login -u ci -p {}", "psql --password={}", "MYSQL_PWD={} mysql")

    def test_every_form_builds_the_whole_value_as_gold(self):
        for form in self.FORMS:
            for kind in ("password", "password_weak"):
                with self.subTest(form=form, kind=kind):
                    template = {"session_id": "cmd", "meta": {"split": "train", "group_id": "cmd", "variants": 5,
                                                              "value_profile": "mltrain"},
                                "items": [{"turn_id": "t0", "channel": "prompt", "text":
                                           "run this: " + form.format("{{" + kind + ":s1}}")}]}
                    sessions, gold, labels = B.build_lines([json.dumps(template)], "cmd", "cmd",
                                                           "metric-detection/templates/ml_train/cmd.jsonl")
                    self.assertEqual(len(gold), 5)
                    errors = []
                    B.check_rows(sessions, gold, labels, "cmd", errors)
                    self.assertEqual(errors, [])


class Blobs(unittest.TestCase):
    def build(self, placeholder, line):
        template = {"session_id": "blob", "meta": {"split": "train", "group_id": "blob", "variants": 3,
                                                  "value_profile": "mltrain"},
                    "items": [{"turn_id": "t0", "channel": "prompt", "text": "why does the install fail"},
                              {"turn_id": "t0", "channel": "tool_output", "text": line.format(placeholder)}]}
        return B.build_lines([json.dumps(template)], "blob", "blob", "metric-detection/templates/ml_train/blob.jsonl")

    def test_new_negatives_build_as_non_gold_and_pass_the_checks(self):
        for kind, line in (("integrity_hash", '"integrity": "{}",'), ("base64_blob", 'logo = "{}"')):
            with self.subTest(kind=kind):
                sessions, gold, labels = self.build("{{neg:" + kind + "}}", line)
                self.assertEqual(gold, [])
                self.assertEqual({r["kind"] for r in labels}, {kind})
                errors = []
                B.check_rows(sessions, gold, labels, "blob", errors)
                self.assertEqual(errors, [])

    def test_values_vary_and_read_as_no_excluded_kind_problem(self):
        d = value_gen.Draw("test-blobs")
        hashes = {value_gen.neg_integrity_hash(d) for _ in range(20)}
        blobs = {value_gen.neg_base64_blob(d) for _ in range(20)}
        self.assertEqual((len(hashes), len(blobs)), (20, 20))
        self.assertTrue(all(h.split("-")[0] in ("sha512", "sha384", "sha256", "sha1") for h in hashes))
        text = '"integrity": "' + next(iter(hashes)) + '"'
        exclusion_kind(text, 14, len(text) - 1)  # must not raise


if __name__ == "__main__":
    unittest.main()
