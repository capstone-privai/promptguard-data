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
        self.assertGreaterEqual(sum(c["variants"] for c in cards if c["split"] != "test_ood"), 300)  # plan 3.4
        for c in cards:
            rule = c["boundary"]
            target = c["secrets"][rule["secret"] - 1]
            self.assertIn(target["placeholder"], rule["command"])
            self.assertIn(rule["command"], rule["instruction"])
            self.assertIn(c["lookalike"], C.COMMAND_LOOKALIKES)
            self.assertIn(c["lookalike"], W.card_message(c).split("\n\nCard JSON:")[0])
            self.assertNotEqual(target["channel"], "tool_input")
        prompt = sum(c["secrets"][c["boundary"]["secret"] - 1]["channel"] == "prompt" for c in cards)
        self.assertGreater(prompt / len(cards), 0.3)

    def test_some_sessions_without_secrets_show_a_look_alike(self):
        none = [c for c in self.cards if not c["secrets"] and c["split"] != "test_ood"]
        share = sum(bool(c["lookalike"]) for c in none) / len(none)
        self.assertGreater(share, 0.05)
        self.assertLess(share, 0.15)
        for c in none:
            if c["lookalike"]:
                self.assertIn(c["lookalike"], W.card_message(c).split("\n\nCard JSON:")[0])

    def test_only_command_cards_and_cards_without_secrets_show_a_look_alike(self):
        for c in self.cards:
            if c["boundary"] and c["boundary"]["rule"] == "command_option":
                self.assertTrue(c["lookalike"])
            elif c["secrets"]:
                self.assertIsNone(c["lookalike"])

    def test_command_forms_cover_most_families_and_forms(self):
        rules = [c["boundary"] for c in self.cards if c["boundary"] and c["boundary"]["rule"] == "command_option"]
        programs = {r["command"].split("{{")[0].split()[0] for r in rules}
        self.assertGreaterEqual(len(programs), 20)

    def test_every_drawn_kind_is_a_generator(self):
        for c in self.cards:
            for n in c["negatives"]:
                self.assertIn(n["kind"], value_gen.NEGATIVE_KINDS)


class FollowsCard(unittest.TestCase):
    CARD = {"items": 2, "turns": 1, "language": "en", "negatives": [], "dense": True, "boundary": None,
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
    def build(self, text):
        template = {"session_id": "cmd", "meta": {"split": "train", "group_id": "cmd", "variants": 5,
                                                  "value_profile": "mltrain"},
                    "items": [{"turn_id": "t0", "channel": "prompt", "text": text}]}
        return B.build_lines([json.dumps(template)], "cmd", "cmd", "metric-detection/templates/ml_train/cmd.jsonl")

    def test_every_form_builds_the_whole_value_as_gold(self):
        for family, forms in C.COMMAND_FORMS.items():
            for kind, form in forms:
                for use in (kind, "password_weak") if kind == "password" else (kind,):
                    with self.subTest(family=family, form=form, kind=use):
                        command = form.replace("{{", "{").replace("}}", "}").replace("{p}", "{{" + use + ":s1}}")
                        sessions, gold, labels = self.build("run this: " + command)
                        self.assertEqual(len(gold), 5)
                        errors = []
                        B.check_rows(sessions, gold, labels, "cmd", errors)
                        self.assertEqual(errors, [])

    def test_look_alikes_pass_the_literal_check_and_add_no_gold(self):
        for text in C.COMMAND_LOOKALIKES:
            with self.subTest(text=text):
                self.assertEqual(W.literal_secrets([text]), [])
                self.assertEqual(self.build("run this: " + text)[1], [])

    def card(self, command="mysql -uroot -p{{password:s1}}"):
        return {"items": 2, "turns": 1, "language": "en", "negatives": [], "dense": False,
                "lookalike": 'mysql -uroot -p"$DB_PASS"',
                "secrets": [{"placeholder": "{{password:s1}}", "kind": "password", "type": "PASSWORD",
                             "channel": "prompt", "repeat": "once", "mask": None}],
                "boundary": {"rule": "command_option", "secret": 1, "command": command, "instruction": ""}}

    def test_a_card_needs_its_command_and_look_alike(self):
        good = [{"turn_id": "t0", "channel": "prompt", "text": "run mysql -uroot -p{{password:s1}} please"},
                {"turn_id": "t0", "channel": "tool_output", "text": '{"stdout": "mysql -uroot -p\\"$DB_PASS\\""}'}]
        self.assertEqual(W.follows_card(self.card(), good), [])
        no_command = [{**good[0], "text": "the password is {{password:s1}}"}, good[1]]
        self.assertTrue(any("command mysql" in p for p in W.follows_card(self.card(), no_command)))
        no_lookalike = [good[0], {**good[1], "text": "done"}]
        self.assertTrue(any("look-alike" in p for p in W.follows_card(self.card(), no_lookalike)))


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
