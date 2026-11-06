"""Regression tests for the coverage parts of the ML training cards (stdlib unittest)."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from label_rules import exclusion_kind
import ml_train_build as B
import ml_train_cards as C
import ml_train_write as W
import value_gen


class SplitLeak(unittest.TestCase):
    @staticmethod
    def problems(value):
        sessions = [{"session_id": sid, "meta": {"split": sid, "group_id": sid}} for sid in ("train", "val")]
        spans = [(sid, 0, 0, len(value), "PASSWORD") for sid in ("train", "val")]
        errors = []
        B.check_splits(sessions, spans, {(sid, 0): value for sid in ("train", "val")}, errors)
        return errors

    def test_a_weak_value_may_repeat_across_splits(self):
        weak = next(w for w in value_gen.WEAK if not B.is_common(w))
        self.assertEqual(self.problems(weak), [])

    def test_a_distinct_value_may_not(self):
        self.assertEqual(len(self.problems("tq7-Vx2m-Lp9z-Rk4h")), 1)


class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = C.load(C.CONFIG)
        cls.cards = C.draw(cls.cfg, C.load_catalog(cls.cfg))

    def test_drawing_twice_gives_the_same_cards(self):
        self.assertEqual(self.cards, C.draw(self.cfg, C.load_catalog(self.cfg)))

    def test_addon_leaves_the_other_cards_alone(self):
        without = {k: v for k, v in self.cfg.items() if k != "addon"}
        self.assertEqual(self.cards, C.draw(without, C.load_catalog(self.cfg)))
        self.assertEqual(C.draw_addon(without), [])

    def test_addon_cards_match_their_cells(self):
        addon = C.draw_addon(self.cfg, C.load_catalog(self.cfg))
        self.assertEqual(addon, C.draw_addon(self.cfg, C.load_catalog(self.cfg)))
        self.assertEqual(len({c["card_id"] for c in addon}), len(addon))
        self.assertFalse({c["card_id"] for c in addon} & {c["card_id"] for c in self.cards})
        first = self.cfg["addon"][0]
        for cell in first["cells"]:
            cards = [c for c in addon if c["card_id"].startswith(first["prefix"])
                     and (c["context"], c["primary_type"]) == (cell["context"], cell["type"])]
            self.assertEqual(len(cards), cell["count"])
            self.assertEqual({c["split"] for c in cards}, {"train", "val", "test"})
            if "formats" in cell:
                self.assertLessEqual({c["format"] for c in cards}, set(cell["formats"]))

    def test_a_new_addon_keeps_the_earlier_ones(self):
        catalog = C.load_catalog(self.cfg)
        before = C.draw_addon(self.cfg, catalog)
        more = {"version": "another", "prefix": "b", "cells": [{"context": "config", "type": "none", "count": 3}]}
        after = C.draw_addon({**self.cfg, "addon": [*self.cfg["addon"], more]}, catalog)
        self.assertEqual(after[:len(before)], before)
        self.assertEqual([c["card_id"] for c in after[len(before):]], ["b0001", "b0002", "b0003"])
        with self.assertRaises(ValueError):
            C.draw_addon({**self.cfg, "addon": [*self.cfg["addon"], {**more, "prefix": self.cfg["addon"][0]["prefix"]}]}, catalog)

    def test_addon_formats_stay_out_of_the_other_cards(self):
        extra = {f for bundle in self.cfg["addon"] for cell in bundle["cells"] for f in cell.get("formats", [])}
        self.assertFalse(extra & {c["format"] for c in self.cards})

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


class LiteralCheck(unittest.TestCase):
    def test_keeps_real_literals(self):
        for text in ('curl -H "Authorization: Bearer abc123def456"', "Authorization: Basic dXNlcjpwYXNz",
                     "PASSWORD: changeme", "access-key: AKIA4TQ2ORDERSVC7Z", "DB_PWD=/home/a/b".replace("/", "x")):
            with self.subTest(text=text):
                self.assertTrue(W.literal_secrets([text]))

    def test_passes_what_holds_no_value(self):
        for text in ("Authorization: Bearer {{token:s1}}", 'authorization="Bearer {{token:s1}}"',
                     "Authorization:Bearer {{token:s1}}", "Authorization: `Bearer ${token}`",
                     'PASSWORD=\\nAPI_KEY=\\nLOG_LEVEL=info\\n', "token: string", "apiKey: String?",
                     "api_key = _read_secret_file(path)", "PWD=/home/analyst/notebooks"):
            with self.subTest(text=text):
                self.assertEqual(W.literal_secrets([text]), [])


class KeepLocal(unittest.TestCase):
    def test_a_twilio_sid_stays_out_of_the_committed_file_and_is_not_written_again(self):
        sid = "AC" + "0123456789abcdef" * 2  # joined here so this file does not hold one
        self.assertEqual(W.literal_secrets(["account: " + sid]), [])
        self.assertIsNone(W.TWILIO_SID.search("account: " + sid + "0"))
        cfg = C.load(C.CONFIG)
        card = next(c for c in C.draw(cfg, C.load_catalog(cfg)) if not c["secrets"] and not c["negatives"]
                    and not c["lookalike"] and c["language"] == "en" and c["split"] == "train")
        items = [{"turn_id": "t0", "channel": "tool_output" if n else "prompt", "text": f"line {n}"}
                 for n in range(card["items"])]
        items[-1]["text"] = "account: " + sid
        row = {"custom_id": card["card_id"] + "-1", "type": "succeeded", "stop_reason": "end_turn", "model": "claude-opus-5-5",
               "prompt": "v1 test", "batch_id": "b", "message_id": "m", "usage": {"input_tokens": 0, "output_tokens": 0},
               "text": json.dumps({"items": items})}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(W, "DIR", Path(directory)):
            (Path(directory) / "raw").mkdir()
            cards = Path(directory) / "cards.jsonl"
            cards.write_text(json.dumps(card))
            W.write_jsonl(W.paths("t")["raw"], [row])
            with contextlib.redirect_stdout(io.StringIO()):
                W.cmd_process(argparse.Namespace(name="t", cards=cards))
            p = W.paths("t")
            self.assertEqual(W.read_jsonl(p["templates"]), [])
            self.assertEqual([t["session_id"] for t in W.read_jsonl(p["local"])], [card["card_id"]])
            self.assertEqual(W.pending([card], "t"), [])


class ForeignBraces(unittest.TestCase):
    def test_file_templates_are_escaped_and_build_as_text(self):
        for text in ("{{.Names}}", "{{end}}", "{{closure}}", "{{$k}}"):
            with self.subTest(text=text):
                self.assertEqual(W.escape_foreign_braces(text), "\\" + text)
        template = {"session_id": "b", "meta": {"split": "train", "group_id": "b", "variants": 1, "value_profile": "mltrain"},
                    "items": [{"turn_id": "t0", "channel": "prompt", "text": W.escape_foreign_braces("docker ps --format '{{.Names}} {{end}}'")}]}
        sessions = B.build_lines([json.dumps(template)], "b", "b", "metric-detection/templates/ml_train/b.jsonl")[0]
        self.assertIn("{{.Names}} {{end}}", sessions[0]["items"][0]["text"])

    def test_placeholders_stay_for_the_card_checks(self):
        for text in ("{{password:s1}}", "{{token:s1|base64}}", "{{password}}", "{{neg:hash}}", "{{mask:s1}}",
                     "{{PASSWORD=x}}", "{{ github.sha }}", "\\{{.y}}"):
            with self.subTest(text=text):
                self.assertEqual(W.escape_foreign_braces(text), text)


class Descriptors(unittest.TestCase):
    def test_every_value_reads_as_a_descriptor_in_a_credential_position(self):
        d = value_gen.Draw("test-descriptors")
        for value in {value_gen.neg_descriptor(d) for _ in range(200)}:
            with self.subTest(value=value):
                text = "KEY=" + value + "\n"
                self.assertEqual(exclusion_kind(text, 4, 4 + len(value)), "descriptor")


if __name__ == "__main__":
    unittest.main()
